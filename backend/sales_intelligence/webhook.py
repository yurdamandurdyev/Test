"""Synchronous webhook delivery with shared Redis update locks; no background tasks."""
from __future__ import annotations
import asyncio
import hashlib
import hmac
import io
import logging
import os
import secrets
from urllib.parse import urlsplit
import httpx
from fastapi import APIRouter, HTTPException, Request
from telegram import Bot, Update
from .analytics import MAX_BYTES, InputError, analyze, export_csv, summary_text
from .bot import GUIDE, MENU, allowed_ids, is_allowed

router = APIRouter()
for logger in ('httpx', 'httpcore', 'telegram'):
    logging.getLogger(logger).setLevel(logging.CRITICAL)


class Store:
    """REST Redis: only opaque update IDs / hashes; all records expire."""
    async def command(self, *args):
        url = os.environ['UPSTASH_REDIS_REST_URL']
        if urlsplit(url).scheme != 'https' or not urlsplit(url).hostname:
            raise RuntimeError('Invalid store configuration')
        async with httpx.AsyncClient(timeout=4, follow_redirects=False) as client:
            response = await client.post(url, headers={'Authorization': 'Bearer ' + os.environ['UPSTASH_REDIS_REST_TOKEN']}, json=list(args))
            response.raise_for_status()
            body = response.json()
            if 'error' in body:
                raise RuntimeError('Store request failed')
            return body['result']

    async def claim(self, key, owner, ttl=90):
        return await self.command('SET', key, owner, 'NX', 'EX', ttl) == 'OK'

    async def release(self, key, owner):
        await self.command('EVAL', "if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('DEL',KEYS[1]) else return 0 end", 1, key, owner)


async def process(update: Update, bot: Bot, store: Store, prefix: str):
    message = update.effective_message
    if not is_allowed(update, allowed_ids()):
        # Never send data to groups or download documents before authorization.
        if message and update.effective_chat.type == 'private':
            await bot.send_message(message.chat_id, 'Доступ закрыт. Передайте администратору ваш числовой Telegram User ID.')
        return
    chat = message.chat_id
    doc = message.document
    if not doc:
        await bot.send_message(chat, GUIDE, reply_markup=MENU)
        return
    if not doc.file_name or not doc.file_name.lower().endswith('.csv') or doc.mime_type not in (None, 'text/csv', 'text/plain', 'application/csv', 'application/vnd.ms-excel', 'application/octet-stream'):
        await bot.send_message(chat, 'Пришлите CSV как документ, а не фото или архив.')
        return
    if doc.file_size is None or doc.file_size > MAX_BYTES:
        await bot.send_message(chat, 'Не удалось проверить размер или файл больше 2 МБ.')
        return
    file = await bot.get_file(doc.file_id)
    if file.file_size is None or file.file_size > MAX_BYTES:
        raise InputError('Файл больше 2 МБ или размер неизвестен.')
    payload = bytes(await file.download_as_bytearray())
    if len(payload) > MAX_BYTES:
        raise InputError('Файл больше 2 МБ.')
    digest = hashlib.sha256(payload).hexdigest()
    key = f'{prefix}:file:{update.effective_user.id}:{digest}'
    if await store.command('GET', key):
        await bot.send_message(chat, 'Этот файл уже обработан за последние 10 минут. Отчёт выше в чате.')
        return
    report = await asyncio.to_thread(analyze, payload)
    # Persist stage receipts: retries after a successful send skip that stage.
    stage = f'{prefix}:update:{update.update_id}'
    if not await store.command('GET', stage + ':summary'):
        await bot.send_message(chat, summary_text(report))
        await store.command('SET', stage + ':summary', '1', 'EX', 604800)
    if not await store.command('GET', stage + ':export'):
        await bot.send_document(chat, io.BytesIO(export_csv(report)), filename='leads-normalized.csv', caption='Все записи сохранены. Контроль качества — в CSV.')
        await store.command('SET', stage + ':export', '1', 'EX', 604800)
    await store.command('SET', key, '1', 'EX', 600)


@router.post('/api/telegram/webhook')
async def webhook(request: Request):
    required = ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_ALLOWED_USER_IDS', 'TELEGRAM_WEBHOOK_SECRET', 'UPSTASH_REDIS_REST_URL', 'UPSTASH_REDIS_REST_TOKEN')
    if not all(os.getenv(k) for k in required) or len(os.environ['TELEGRAM_WEBHOOK_SECRET']) < 32:
        raise HTTPException(503, 'Webhook not configured')
    supplied = request.headers.get('x-telegram-bot-api-secret-token', '')
    if not hmac.compare_digest(supplied, os.environ['TELEGRAM_WEBHOOK_SECRET']):
        raise HTTPException(403, 'Forbidden')
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 65536:
            raise HTTPException(413, 'Update too large')
    try:
        import json
        data = json.loads(body)
        if not isinstance(data, dict) or type(data.get('update_id')) is not int or data['update_id'] < 0:
            raise ValueError()
        ids = allowed_ids()
        if not ids:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(400, 'Invalid update or access configuration')
    token = os.environ['TELEGRAM_BOT_TOKEN']
    prefix = 'si:' + hashlib.sha256(token.encode()).hexdigest()[:16]
    key = f'{prefix}:update:{data["update_id"]}'
    owner = secrets.token_hex(16)
    store = Store()
    claimed = False
    user_key = None
    try:
        async with asyncio.timeout(25):
            if await store.command('GET', key + ':done'):
                return {'ok': True}
            claimed = await store.claim(key + ':lock', owner)
            if not claimed:
                raise HTTPException(503, 'Update in progress')
            async with Bot(token) as bot:
                update = Update.de_json(data, bot)
                if update.message:
                    if is_allowed(update, ids):
                        user_key = f'{prefix}:user:{update.effective_user.id}:lock'
                        if not await store.claim(user_key, owner):
                            user_key = None
                            raise HTTPException(503, 'User request in progress')
                    try:
                        await process(update, bot, store, prefix)
                    except InputError as exc:
                        await bot.send_message(update.effective_chat.id, str(exc))
                await store.command('SET', key + ':done', '1', 'EX', 604800)
                return {'ok': True}
    except HTTPException:
        raise
    except Exception:
        # Never expose transport URLs or exception repr: they may contain bot tokens.
        raise HTTPException(503, 'Temporary processing failure') from None
    finally:
        for lock in ([key + ':lock'] if claimed else []) + ([user_key] if user_key else []):
            try:
                await store.release(lock, owner)
            except Exception:
                pass  # TTL releases lock after interrupted execution.

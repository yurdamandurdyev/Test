"""Synchronous webhook delivery with shared Redis update locks; no background tasks."""
from __future__ import annotations
import asyncio
import hashlib
import hmac
import io
import json
import re
import logging
import os
import secrets
from urllib.parse import urlsplit
import httpx
from fastapi import APIRouter, HTTPException, Request
from telegram import Bot, Update
from telegram.error import BadRequest
from .analytics import MAX_BYTES, InputError, analyze
from .bot import allowed_ids, is_allowed
from .presentation import WELCOME, view, keyboard, human_csv
from .report_pdf import build_pdf

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


STATE_TTL = 3600
MIME_TYPES = (None, 'text/csv', 'text/plain', 'application/csv', 'application/vnd.ms-excel', 'application/octet-stream')
CALLBACK = re.compile(r'r:([a-f0-9]{24}):(overview|sources|budgets|quality|pdf|csv)\Z', re.ASCII)


async def get_payload(bot, file_id):
    remote = await bot.get_file(file_id)
    if remote.file_size is None or remote.file_size > MAX_BYTES:
        raise InputError('Файл больше 2 МБ или размер неизвестен. Пришлите меньшую выгрузку.')
    payload = bytes(await remote.download_as_bytearray())
    if len(payload) > MAX_BYTES:
        raise InputError('Файл больше 2 МБ. Разделите выгрузку на несколько файлов.')
    return payload


async def edit(bot, chat, message_id, text, markup=None):
    try:
        await bot.edit_message_text(chat_id=chat, message_id=message_id, text=text,
                                    parse_mode='HTML', reply_markup=markup)
    except BadRequest as exc:
        if 'message is not modified' not in str(exc).lower():
            raise


async def answer(bot, callback, text=None, alert=False):
    try:
        await bot.answer_callback_query(callback.id, text=text, show_alert=alert)
    except BadRequest:
        pass  # An old callback acknowledgement may expire before a retry arrives.


async def process(update: Update, bot: Bot, store: Store, prefix: str):
    message = update.effective_message
    query = update.callback_query
    if not is_allowed(update, allowed_ids()):
        if query:
            await answer(bot, query, 'Этот отчёт доступен только его владельцу.', True)
        elif message and update.effective_chat.type == 'private':
            await bot.send_message(message.chat_id, 'Доступ закрыт. Попросите администратора добавить ваш Telegram User ID.')
        return
    chat = update.effective_chat.id
    user = update.effective_user.id
    stage = f'{prefix}:update:{update.update_id}'
    if query:
        match = CALLBACK.fullmatch(query.data or '')
        if not match:
            await answer(bot, query, 'Кнопка устарела. Пришлите CSV ещё раз.', True)
            return
        report_id, action = match.groups()
        raw = await store.command('GET', f'{prefix}:report:{report_id}')
        if not raw:
            await answer(bot, query, 'Час хранения истёк. Отправьте CSV заново — я обновлю отчёт.', True)
            return
        state = json.loads(raw)
        if state['owner'] != user or state['chat'] != chat:
            await answer(bot, query, 'Этот отчёт доступен только его владельцу.', True)
            return
        download_key = f'{prefix}:report:{report_id}:download:{action}'
        if action in ('pdf','csv'):
            if await store.command('GET', stage + ':sent'):
                await answer(bot, query, 'Файл уже отправлен в этот чат.')
                return
            if not await store.claim(download_key, 'sending', ttl=30):
                await answer(bot, query, 'Файл уже отправляется или недавно отправлен. Повторите через 30 секунд.')
                return  # Rapid repeat taps and uncertain sends cannot flood the chat.
        await answer(bot, query, 'Готовлю файл…' if action in ('pdf','csv') else None)
        payload = await get_payload(bot, state['file_id'])
        if hashlib.sha256(payload).hexdigest() != state['digest']:
            raise InputError('Файл изменился или недоступен. Отправьте исходную выгрузку повторно.')
        report = await asyncio.to_thread(analyze, payload)
        if action in ('pdf','csv'):
            data = await asyncio.to_thread(build_pdf if action == 'pdf' else human_csv, report)
            await bot.send_document(chat, io.BytesIO(data), filename='sales-report.pdf' if action=='pdf' else 'leads-table.csv',
                                    caption='Отчёт для руководителя · из вашей выгрузки' if action=='pdf' else 'Все записи сохранены. Замечания — на русском языке.')
            await store.command('SET', stage + ':sent', '1', 'EX', 604800)
        else:
            await edit(bot, chat, message.message_id, view(report, action), keyboard(report_id))
        return
    doc = message.document
    if not doc:
        await bot.send_message(chat, WELCOME, parse_mode='HTML')
        return
    if not doc.file_name or not doc.file_name.lower().endswith('.csv') or doc.mime_type not in MIME_TYPES:
        await bot.send_message(chat, 'Нужна выгрузка CSV. В CRM или Excel выберите «CSV UTF-8» и прикрепите её как файл, не как фото или архив.')
        return
    if doc.file_size is None or doc.file_size > MAX_BYTES:
        await bot.send_message(chat, 'Файл больше 2 МБ или размер неизвестен. Разделите выгрузку и отправьте меньший CSV.')
        return
    progress_id = await store.command('GET', stage + ':progress')
    if not progress_id:
        progress = await bot.send_message(chat, 'Проверяю выгрузку и готовлю сводку…')
        progress_id = progress.message_id
        await store.command('SET', stage + ':progress', str(progress_id), 'EX', 604800)
    try:
        payload = await get_payload(bot, doc.file_id)
        digest = hashlib.sha256(payload).hexdigest()
        duplicate_key = f'{prefix}:file:{user}:{digest}'
        previous = await store.command('GET', duplicate_key)
        if previous and await store.command('GET', f'{prefix}:report:{previous}'):
            await edit(bot, chat, int(progress_id), 'Эта выгрузка уже обработана за последние 10 минут. Откройте нужный раздел кнопками ниже.', keyboard(previous))
            return
        report = await asyncio.to_thread(analyze, payload)
        report_id = hmac.new(os.environ['TELEGRAM_BOT_TOKEN'].encode(), f'{user}:{update.update_id}'.encode(), hashlib.sha256).hexdigest()[:24]
        state = json.dumps({'owner':user, 'chat':chat, 'file_id':doc.file_id, 'digest':digest})
        # NX preserves the original one-hour expiry during webhook retries.
        await store.command('SET', f'{prefix}:report:{report_id}', state, 'NX', 'EX', STATE_TTL)
        await edit(bot, chat, int(progress_id), view(report), keyboard(report_id))
        await store.command('SET', duplicate_key, report_id, 'EX', 600)
    except InputError as exc:
        from html import escape
        await edit(bot, chat, int(progress_id), '<b>Не получилось прочитать выгрузку</b>\n\n' + escape(str(exc)[:1500]) + '\n\nИсправьте файл и отправьте его ещё раз.')


async def deliver(data, bot, store, prefix):
    """Shared polling/webhook lifecycle, distributed locks and bounded delivery retries."""
    key = f'{prefix}:update:{data["update_id"]}'
    owner = secrets.token_hex(16)
    claimed = False
    user_key = None
    update = Update.de_json(data, bot)
    try:
        async with asyncio.timeout(25):
            if await store.command('GET', key + ':done'):
                if update.callback_query: await answer(bot, update.callback_query)
                return
            claimed = await store.claim(key + ':lock', owner)
            if not claimed:
                raise HTTPException(503, 'Update in progress')
            if is_allowed(update, allowed_ids()):
                user_key = f'{prefix}:user:{update.effective_user.id}:lock'
                if not await store.claim(user_key, owner):
                    user_key = None
                    if update.callback_query:
                        await answer(bot, update.callback_query, 'Предыдущее действие ещё выполняется. Нажмите снова через несколько секунд.')
                        await store.command('SET', key + ':done', '1', 'EX', 604800)
                        return
                    raise HTTPException(503, 'User request in progress')
            attempt = int(await store.command('INCR', key + ':attempts'))
            await store.command('EXPIRE', key + ':attempts', 604800)
            if attempt > 3:
                # Acknowledge poison updates; no endless Telegram resend loop.
                await store.command('SET', key + ':done', '1', 'EX', 604800)
                if is_allowed(update, allowed_ids()) and await store.claim(key + ':notice', '1', ttl=604800):
                    if update.callback_query:
                        await answer(bot, update.callback_query, 'Не удалось завершить действие. Нажмите кнопку повторно немного позже.', True)
                    else:
                        progress = await store.command('GET', key + ':progress')
                        if progress: await edit(bot, update.effective_chat.id, int(progress), 'Сервис временно недоступен. Попробуйте отправить файл через минуту.')
                return
            if update.message or update.callback_query:
                try:
                    await process(update, bot, store, prefix)
                except InputError:
                    if update.callback_query:
                        await edit(bot, update.effective_chat.id, update.effective_message.message_id, 'Не удалось открыть исходный файл. Отправьте CSV заново.')
                    else:
                        raise
            await store.command('SET', key + ':done', '1', 'EX', 604800)
    finally:
        for lock in ([key + ':lock'] if claimed else []) + ([user_key] if user_key else []):
            try:
                await store.release(lock, owner)
            except Exception:
                pass


@router.post('/api/telegram/webhook')
async def webhook(request: Request):
    required = ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_ALLOWED_USER_IDS', 'TELEGRAM_WEBHOOK_SECRET', 'UPSTASH_REDIS_REST_URL', 'UPSTASH_REDIS_REST_TOKEN')
    if not all(os.getenv(k) for k in required) or len(os.environ['TELEGRAM_WEBHOOK_SECRET']) < 32:
        raise HTTPException(503, 'Webhook not configured')
    supplied = request.headers.get('x-telegram-bot-api-secret-token', '')
    if not hmac.compare_digest(supplied.encode(), os.environ['TELEGRAM_WEBHOOK_SECRET'].encode()):
        raise HTTPException(403, 'Forbidden')
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 65536:
            raise HTTPException(413, 'Update too large')
    try:
        data = json.loads(body)
        if not isinstance(data, dict) or type(data.get('update_id')) is not int or data['update_id'] < 0 or not allowed_ids():
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(400, 'Invalid update or access configuration')
    token = os.environ['TELEGRAM_BOT_TOKEN']
    prefix = 'si:' + hashlib.sha256(token.encode()).hexdigest()[:16]
    store = Store()
    try:
        # Avoid Telegram transport for already completed updates.
        if not data.get('callback_query') and await store.command('GET', f'{prefix}:update:{data["update_id"]}:done'):
            return {'ok':True}
        async with Bot(token) as bot:
            await deliver(data, bot, store, prefix)
        return {'ok':True}
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).warning('telegram_delivery_failed')
        raise HTTPException(503, 'Temporary processing failure') from None

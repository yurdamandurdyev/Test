#!/usr/bin/env python3
"""Use secrets from environment only. Never print transport exceptions or token URLs."""
import argparse
import asyncio
import logging
import os
import sys
from urllib.parse import urlsplit
from telegram import Bot

logging.disable(logging.CRITICAL)
async def run(mode):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        raise ValueError('Set token in environment')
    async with Bot(token) as bot:
        info = await bot.get_me()
        print(f'Bot API connection verified: @{info.username}')
        status = await bot.get_webhook_info()
        if mode == 'identity':
            if status.url:
                print('Webhook already active. Use your own Telegram account export to find your numeric ID; webhook was not changed.')
                return
            updates = await bot.get_updates(timeout=0, allowed_updates=['message'])
            ids = sorted({u.effective_user.id for u in updates if u.message and u.effective_chat.type == 'private' and u.message.text == '/start'})
            print('Private /start sender IDs:', ', '.join(map(str, ids)) or 'none; send /start and repeat')
            print('Authorize only your own ID. Do not automatically authorize every returned ID.')
        elif mode == 'register':
            base = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
            secret = os.getenv('TELEGRAM_WEBHOOK_SECRET', '')
            parsed = urlsplit(base)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment or parsed.path or len(secret) < 32:
                raise ValueError('Invalid configuration')
            await bot.set_webhook(base + '/api/telegram/webhook', secret_token=secret, allowed_updates=['message', 'callback_query'], max_connections=1, drop_pending_updates=False)
            print('Webhook registered; pending updates preserved. Stop every polling instance.')
        else:
            print('Webhook configured:', bool(status.url))
            print('Pending updates:', status.pending_update_count)
            print('Callback delivery enabled:', 'callback_query' in (status.allowed_updates or ()))
            print('Telegram reports delivery error:', bool(status.last_error_date))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['identity','register','status'])
    args = parser.parse_args()
    try:
        asyncio.run(run(args.mode))
    except Exception:
        print('Setup failed. Check secret environment settings and network access. Diagnostic details redacted.', file=sys.stderr)
        raise SystemExit(1)

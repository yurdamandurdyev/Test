"""Polling adapter for the same Redis-backed assistant used by the webhook."""
from __future__ import annotations
import hashlib
import logging
import os
from telegram import Update
from telegram.ext import Application, TypeHandler, ContextTypes


def allowed_ids() -> set[int]:
    return {int(v.strip()) for v in os.getenv('TELEGRAM_ALLOWED_USER_IDS','').split(',') if v.strip()}


def is_allowed(update: Update, ids: set[int]) -> bool:
    return bool(update.effective_user and update.effective_chat and update.effective_user.id in ids and update.effective_chat.type == 'private')


async def dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from .webhook import deliver, Store
    prefix='si:'+hashlib.sha256(os.environ['TELEGRAM_BOT_TOKEN'].encode()).hexdigest()[:16]
    await deliver(update.to_dict(), context.bot, Store(), prefix)


async def on_error(update, context):
    logging.getLogger(__name__).warning('telegram_polling_delivery_failed')


def main():
    required=('TELEGRAM_BOT_TOKEN','TELEGRAM_ALLOWED_USER_IDS','UPSTASH_REDIS_REST_URL','UPSTASH_REDIS_REST_TOKEN')
    if not all(os.getenv(k) for k in required) or not allowed_ids():
        raise SystemExit('Настройте Telegram token, разрешённые ID и Redis в окружении.')
    for name in ('httpx','httpcore','telegram'):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    app=Application.builder().token(os.environ['TELEGRAM_BOT_TOKEN']).concurrent_updates(8).build()
    app.add_handler(TypeHandler(Update, dispatch));app.add_error_handler(on_error)
    app.run_polling(allowed_updates=['message','callback_query'],drop_pending_updates=False)

if __name__=='__main__': main()

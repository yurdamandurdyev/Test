"""Long polling worker, deployed independently of the Vercel frontend."""
from __future__ import annotations
import asyncio
import hashlib
import io
import logging
import os
import time
from dataclasses import dataclass, field
from telegram import Update, ReplyKeyboardMarkup, LinkPreviewOptions
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, Defaults
from .analytics import MAX_BYTES, InputError, analyze, export_csv, summary_text

MENU = ReplyKeyboardMarkup([["Загрузить CSV", "Как устроен отчёт"]], resize_keyboard=True)
GUIDE = ("Отправьте CSV как документ. Я посчитаю лиды, источники и бюджет за последний день и семь дней.\n\n"
         "Нужны столбцы: дата,имя,телефон,источник,бюджет. UTF-8, разделитель — запятая, до 2 МБ и 10 000 записей.\n\n"
         "Нули включаются в средний бюджет; пропуски — нет. Возможные дубли отмечаются, не удаляются. "
         "Файл обрабатывается в памяти. Отчёт и файл ответа останутся в вашем чате Telegram — удалите их, когда они больше не нужны.")


def allowed_ids() -> set[int]:
    return {int(v.strip()) for v in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if v.strip()}


def is_allowed(update: Update, ids: set[int]) -> bool:
    return bool(update.effective_user and update.effective_chat and
                update.effective_user.id in ids and update.effective_chat.type == "private")


@dataclass
class Guard:
    busy: set[int] = field(default_factory=set)
    seen: dict[tuple[int, str], float] = field(default_factory=dict)

    def duplicate(self, user: int, digest: str) -> bool:
        now = time.monotonic()
        self.seen = {k: t for k, t in self.seen.items() if now - t < 600}
        return (user, digest) in self.seen

    def remember(self, user: int, digest: str):
        if len(self.seen) >= 1000:
            self.seen.pop(next(iter(self.seen)))
        self.seen[(user, digest)] = time.monotonic()


guard = Guard()


async def access(update: Update) -> bool:
    if is_allowed(update, allowed_ids()):
        return True
    if update.effective_message:
        await update.effective_message.reply_text("Доступ закрыт. Попросите администратора добавить ваш Telegram User ID. Аналитика доступна только в личном чате.")
    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await access(update):
        await update.effective_message.reply_text("Sales Intelligence\n\n" + GUIDE, reply_markup=MENU)


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await access(update):
        await update.effective_message.reply_text("Отправьте CSV, чтобы получить новый отчёт. Прошлые выгрузки на сервере не хранятся.", reply_markup=MENU)


async def document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await access(update): return
    message, doc, user = update.effective_message, update.effective_message.document, update.effective_user.id
    if not doc.file_name or not doc.file_name.lower().endswith(".csv") or doc.mime_type not in (None, "text/csv", "text/plain", "application/csv", "application/vnd.ms-excel", "application/octet-stream"):
        await message.reply_text("Пришлите CSV как документ, а не фото или архив.")
        return
    if doc.file_size is None or doc.file_size > MAX_BYTES:
        await message.reply_text("Не удалось проверить размер или файл больше 2 МБ. Отправьте меньшую выгрузку.")
        return
    if user in guard.busy:
        await message.reply_text("Предыдущий файл ещё обрабатывается. Дождитесь отчёта.")
        return
    guard.busy.add(user)
    try:
        await message.reply_text("Файл получен. Проверяю данные и считаю сводку…")
        remote = await context.bot.get_file(doc.file_id)
        if remote.file_size and remote.file_size > MAX_BYTES:
            raise InputError("Файл больше 2 МБ.")
        payload = bytes(await remote.download_as_bytearray())
        if len(payload) > MAX_BYTES: raise InputError("Файл больше 2 МБ.")
        digest = hashlib.sha256(payload).hexdigest()
        if guard.duplicate(user, digest):
            await message.reply_text("Этот файл уже обработан за последние 10 минут. Отчёт выше в чате; повторите позже или пришлите обновлённый CSV.")
            return
        result = await asyncio.to_thread(analyze, payload)
        await message.reply_text(summary_text(result))
        attachment = io.BytesIO(export_csv(result))
        attachment.name = "leads-normalized.csv"
        await message.reply_document(attachment, caption="Нормализованные записи и замечания. Все строки сохранены; формулы экранированы.")
        guard.remember(user, digest)
    except InputError as exc:
        await message.reply_text(str(exc))
    except Exception:
        # Do not log exceptions from Telegram transport: they can include token-bearing URLs.
        await message.reply_text("Не удалось завершить обработку. Попробуйте ещё раз немного позже. Данные на сервере не сохранены.")
    finally:
        guard.busy.discard(user)


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await access(update): return
    await update.effective_message.reply_text(GUID if update.effective_message.text == "Как устроен отчёт" else "Прикрепите CSV через скрепку → Файл. Я верну сводку и обработанные записи.", reply_markup=MENU)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.getLogger(__name__).error("Telegram operation failed; details redacted")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or not allowed_ids():
        raise SystemExit("Задайте TELEGRAM_BOT_TOKEN и TELEGRAM_ALLOWED_USER_IDS в окружении.")
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    logging.getLogger("telegram").setLevel(logging.CRITICAL)
    app = Application.builder().token(token).defaults(Defaults(link_preview_options=LinkPreviewOptions(is_disabled=True))).concurrent_updates(8).build()
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(MessageHandler(filters.Document.ALL, document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    app.add_error_handler(on_error)
    app.run_polling(allowed_updates=["message"], drop_pending_updates=True)


if __name__ == "__main__":
    main()

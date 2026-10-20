import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from sales_intelligence import bot
from sales_intelligence.analytics import analyze, summary_text, export_csv

def update(user=1, chat="private", filename="leads.csv", size=100):
    doc = SimpleNamespace(file_name=filename, mime_type="text/csv", file_size=size, file_id="test")
    message = SimpleNamespace(document=doc, reply_text=AsyncMock(), reply_document=AsyncMock())
    return SimpleNamespace(effective_user=SimpleNamespace(id=user), effective_chat=SimpleNamespace(type=chat), effective_message=message)

@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "1,2")
    bot.guard = bot.Guard()

def test_access_control():
    assert bot.is_allowed(update(), {1})
    assert not bot.is_allowed(update(3), {1})
    assert not bot.is_allowed(update(chat="group"), {1})

def test_unauthorized_does_not_download():
    u = update(5)
    context = SimpleNamespace(bot=SimpleNamespace(get_file=AsyncMock()))
    asyncio.run(bot.document(u, context))
    context.bot.get_file.assert_not_called()

def test_bot_uses_same_core_and_deduplicates(csv_data):
    u = update(size=len(csv_data))
    remote = SimpleNamespace(file_size=len(csv_data), download_as_bytearray=AsyncMock(return_value=bytearray(csv_data)))
    context = SimpleNamespace(bot=SimpleNamespace(get_file=AsyncMock(return_value=remote)))
    asyncio.run(bot.document(u, context))
    assert any(c.args[0] == summary_text(analyze(csv_data)) for c in u.effective_message.reply_text.call_args_list)
    attachment = u.effective_message.reply_document.call_args.args[0]
    assert attachment.getvalue() == export_csv(analyze(csv_data))
    asyncio.run(bot.document(u, context))
    assert u.effective_message.reply_document.call_count == 1
    assert not bot.guard.busy

@pytest.mark.parametrize("filename,size", [("bad.exe", 100), ("a.csv", bot.MAX_BYTES+1), ("a.csv", None)])
def test_bad_files_no_download(filename, size):
    u = update(filename=filename, size=size)
    context = SimpleNamespace(bot=SimpleNamespace(get_file=AsyncMock()))
    asyncio.run(bot.document(u, context))
    context.bot.get_file.assert_not_called()

def test_bad_csv_and_retry():
    u = update()
    remote = SimpleNamespace(file_size=7, download_as_bytearray=AsyncMock(return_value=bytearray(b"broken")))
    context = SimpleNamespace(bot=SimpleNamespace(get_file=AsyncMock(return_value=remote)))
    asyncio.run(bot.document(u, context))
    assert not bot.guard.busy and not bot.guard.seen
    u.effective_message.reply_document.assert_not_called()

def test_busy():
    bot.guard.busy.add(1)
    u = update()
    context = SimpleNamespace(bot=SimpleNamespace(get_file=AsyncMock()))
    asyncio.run(bot.document(u, context))
    context.bot.get_file.assert_not_called()

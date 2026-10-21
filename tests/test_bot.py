import json
import pytest
from sales_intelligence import bot, webhook
from sales_intelligence.analytics import analyze, MAX_BYTES
from sales_intelligence.presentation import view
pytestmark=pytest.mark.anyio

async def test_access_control(make_update,telegram_bot):
    assert bot.is_allowed(make_update(telegram_bot),{42})
    assert not bot.is_allowed(make_update(telegram_bot,user=99),{42})
    assert not bot.is_allowed(make_update(telegram_bot,chat_type='group'),{42})

async def test_unauthorized_does_not_download(make_update,telegram_bot,store):
    await webhook.process(make_update(telegram_bot,user=99),telegram_bot,store,'test')
    telegram_bot.get_file.assert_not_called()

async def test_bot_uses_same_core_and_deduplicates(csv_data,make_update,telegram_bot,store):
    await webhook.deliver(make_update(telegram_bot).to_dict(),telegram_bot,store,'test')
    assert telegram_bot.edit_message_text.call_args.kwargs['text']==view(analyze(csv_data))
    telegram_bot.send_document.assert_not_called()
    await webhook.deliver(make_update(telegram_bot).to_dict(),telegram_bot,store,'test')
    assert telegram_bot.get_file.call_count==1
    await webhook.deliver(make_update(telegram_bot,update_id=2).to_dict(),telegram_bot,store,'test')
    assert 'уже обработана' in telegram_bot.edit_message_text.call_args.kwargs['text']
    assert not any(k.endswith(':lock') for k in store.data)

@pytest.mark.parametrize('name,size',[('a.exe',100),('a.csv',MAX_BYTES+1),('a.csv',None)])
async def test_bad_files_no_download(name,size,make_update,telegram_bot,store):
    await webhook.process(make_update(telegram_bot,name=name,size=size),telegram_bot,store,'test')
    telegram_bot.get_file.assert_not_called()

async def test_bad_csv_and_retry(make_update,telegram_bot,store):
    telegram_bot.get_file.return_value.download_as_bytearray.return_value=bytearray(b'broken')
    await webhook.deliver(make_update(telegram_bot).to_dict(),telegram_bot,store,'test')
    assert 'Не получилось' in telegram_bot.edit_message_text.call_args.kwargs['text']
    assert not any(':report:' in k for k in store.data)
    assert not any(k.endswith(':lock') for k in store.data)
    telegram_bot.send_document.assert_not_called()

async def test_busy(make_update,telegram_bot,store):
    await store.claim('test:user:42:lock','other')
    with pytest.raises(webhook.HTTPException):
        await webhook.deliver(make_update(telegram_bot).to_dict(),telegram_bot,store,'test')
    telegram_bot.get_file.assert_not_called()

async def test_polling_uses_shared_engine(monkeypatch,telegram_bot,make_update):
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    shared=AsyncMock();monkeypatch.setattr(webhook,'deliver',shared)
    await bot.dispatch(make_update(telegram_bot),SimpleNamespace(bot=telegram_bot))
    assert shared.call_args.args[0]['update_id']==1

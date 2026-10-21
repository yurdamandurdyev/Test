import json
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from sales_intelligence.api import app
from sales_intelligence import webhook as module

SECRET = 'test-only-webhook-secret-32-characters'
@pytest.fixture
def hook(monkeypatch):
    for key, value in {'TELEGRAM_BOT_TOKEN':'fixture-token','TELEGRAM_ALLOWED_USER_IDS':'42','TELEGRAM_WEBHOOK_SECRET':SECRET,'UPSTASH_REDIS_REST_URL':'https://store.invalid','UPSTASH_REDIS_REST_TOKEN':'fixture-store'}.items():
        monkeypatch.setenv(key,value)
    return TestClient(app)


def test_secret_size_and_schema(hook, monkeypatch):
    assert hook.post('/api/telegram/webhook',json={}).status_code == 403
    headers={'x-telegram-bot-api-secret-token':SECRET}
    assert hook.post('/api/telegram/webhook',headers=headers,content=b' '*65537).status_code == 413
    assert hook.post('/api/telegram/webhook',headers=headers,json={'update_id':True}).status_code == 400
    monkeypatch.delenv('UPSTASH_REDIS_REST_TOKEN')
    assert hook.post('/api/telegram/webhook',headers=headers,json={'update_id':1}).status_code == 503


def test_already_processed_does_not_contact_telegram(hook,monkeypatch):
    command=AsyncMock(return_value='1')
    monkeypatch.setattr(module.Store,'command',command)
    assert hook.post('/api/telegram/webhook',headers={'x-telegram-bot-api-secret-token':SECRET},json={'update_id':1}).status_code == 200
    assert command.await_count == 1


def test_store_failure_does_not_echo_secret(hook,monkeypatch):
    monkeypatch.setattr(module.Store,'command',AsyncMock(side_effect=RuntimeError('fixture-token')))
    response=hook.post('/api/telegram/webhook',headers={'x-telegram-bot-api-secret-token':SECRET},json={'update_id':1})
    assert response.status_code == 503
    assert 'fixture-token' not in response.text

@pytest.mark.anyio
async def test_authorization_before_download(monkeypatch):
    from telegram import Update
    monkeypatch.setenv('TELEGRAM_ALLOWED_USER_IDS','42')
    bot=AsyncMock()
    update=Update.de_json({'update_id':1,'message':{'message_id':1,'date':0,'chat':{'id':99,'type':'private'},'from':{'id':99,'is_bot':False,'first_name':'Test'},'document':{'file_id':'f','file_unique_id':'u','file_name':'a.csv','file_size':10}}},bot)
    await module.process(update,bot,AsyncMock(),'test')
    bot.get_file.assert_not_awaited()
    bot.send_document.assert_not_awaited()

@pytest.fixture
def anyio_backend():
    return 'asyncio'

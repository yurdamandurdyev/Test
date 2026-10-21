import copy
import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from telegram import Update
from sales_intelligence import webhook
from sales_intelligence import telegram_calls as calls
from sales_intelligence.transcripts import documents_to_calls
from sales_intelligence.api import app
from fastapi.testclient import TestClient

TEXT='М: Добрый день, ЖК «Северная Гавань», меня зовут Иван.\nК: Здравствуйте.\nМ: Какой бюджет?\nК: До 12 миллионов.\nМ: Когда планируете покупку?\nК: Весной.\nМ: Предлагаю ипотеку.\nК: Хорошо.\nМ: Приезжайте в субботу в 12:00 на показ.\nК: Скорее да, но я уточню.\nМ: Итак: бюджет 12 млн, пришлю адрес.'


def message(bot,text,uid=1,user=42,reply=None):
    m={'message_id':uid,'date':0,'chat':{'id':user,'type':'private'},'from':{'id':user,'is_bot':False,'first_name':'Test'},'text':text}
    if reply is not None:m['reply_to_message']={'message_id':reply,'date':0,'chat':m['chat'],'text':'prompt'}
    return Update.de_json({'update_id':uid,'message':m},bot)


def payload(bot,text):
    data=text.encode() if isinstance(text,str) else text
    bot.get_file.return_value=SimpleNamespace(file_size=len(data),download_as_bytearray=AsyncMock(return_value=bytearray(data)))


async def upload(bot,store,text=TEXT,uid=1):
    await webhook.deliver(message(bot,text,uid).to_dict(),bot,store,'test')
    rid=next(k.split(':')[-1] for k in store.data if re.fullmatch(r'test:calls:[a-f0-9]{24}',k))
    return rid


@pytest.mark.anyio
async def test_plain_dialog_matches_web_exactly(telegram_bot,store):
    rid=await upload(telegram_bot,store)
    state=json.loads(await store.command('GET',calls.key('test',rid)))
    report=await calls.load_report(state,telegram_bot)
    response=TestClient(app).post('/api/transcripts/analyze',headers={'X-Sales-Client':'web'},json={'documents':[{'name':'Telegram.txt','text':TEXT}],'expected_project':'Северная Гавань'})
    assert response.status_code==200 and report==response.json()
    assert report['average'] is None and report['pending']==1
    assert 'Требует проверки' in telegram_bot.edit_message_text.call_args.kwargs['text']
    assert 0<store.expiry[calls.key('test',rid)]<=3600
    assert 'text' in state and 'reviews' in state


@pytest.mark.anyio
async def test_txt_uses_file_reference_not_saved_transcript(telegram_bot,store,make_update):
    payload(telegram_bot,TEXT)
    update=make_update(telegram_bot,name='calls.txt').to_dict();update['message']['document']['mime_type']='text/plain'
    await webhook.deliver(update,telegram_bot,store,'test')
    state=json.loads(next(v for k,v in store.data.items() if re.fullmatch(r'test:calls:[a-f0-9]{24}',k)))
    assert 'text' not in state and state['file_id']=='fixture-file'
    assert await calls.load_report(state,telegram_bot)==documents_to_calls([{'name':'Telegram.txt','text':TEXT}],'Северная Гавань')


@pytest.mark.anyio
@pytest.mark.parametrize('action',['overview','call:0','criterion:0:4:0','rec:0','csv','pdf'])
async def test_buttons_and_exports(telegram_bot,store,make_update,action):
    rid=await upload(telegram_bot,store)
    await webhook.deliver(make_update(telegram_bot,update_id=2,callback=f'c:{rid}:{action}').to_dict(),telegram_bot,store,'test')
    if action in ('csv','pdf'):
        data=telegram_bot.send_document.call_args.args[1].getvalue()
        assert data.startswith(b'%PDF') if action=='pdf' else 'Требует проверки' in data.decode('utf-8-sig')
        assert telegram_bot.send_document.call_args.kwargs['filename']=='calls-report.'+action
    else:
        text=telegram_bot.edit_message_text.call_args.kwargs['text']
        assert len(text.encode('utf-16-le'))//2<4096
        assert 'Иван' in text or action=='overview'
    telegram_bot.answer_callback_query.assert_awaited()


@pytest.mark.anyio
async def test_review_fail_then_pass_with_exact_quote_and_expiry(telegram_bot,store,make_update):
    rid=await upload(telegram_bot,store);k=calls.key('test',rid)
    original=json.loads(await store.command('GET',k))['expires']
    await webhook.deliver(make_update(telegram_bot,update_id=2,callback=f'c:{rid}:set:0:4:fail').to_dict(),telegram_bot,store,'test')
    state=json.loads(await store.command('GET',k));report=await calls.load_report(state,telegram_bot)
    assert state['expires']==original and report['average']==77.27
    assert report['calls'][0]['criteria'][4]['automatic']['status']=='review'
    telegram_bot.send_message.return_value=SimpleNamespace(message_id=555)
    await webhook.deliver(make_update(telegram_bot,update_id=3,callback=f'c:{rid}:pass:0:4').to_dict(),telegram_bot,store,'test')
    await webhook.deliver(message(telegram_bot,'Поддельная цитата',4,reply=555).to_dict(),telegram_bot,store,'test')
    assert 'Цитата' in telegram_bot.send_message.call_args.args[1]
    # Unrelated messages must not be interpreted as a review response.
    await webhook.deliver(message(telegram_bot,'К: Скорее да, но я уточню.',5).to_dict(),telegram_bot,store,'test')
    assert (await calls.load_report(json.loads(await store.command('GET',k)),telegram_bot))['average']==77.27
    await webhook.deliver(message(telegram_bot,'К: Скорее да, но я уточню.\nПричина: Подтверждаю вручную после проверки.',6,reply=555).to_dict(),telegram_bot,store,'test')
    state=json.loads(await store.command('GET',k));report=await calls.load_report(state,telegram_bot)
    assert report['average']==100 and state['expires']==original
    assert '100.0%' in telegram_bot.edit_message_text.call_args.kwargs['text']
    assert report==documents_to_calls([{'name':'Telegram.txt','text':TEXT}],'Северная Гавань',state['reviews'])
    assert not await store.command('GET','test:call-review:42')


@pytest.mark.anyio
async def test_expired_other_user_and_malformed_buttons(telegram_bot,store,make_update,monkeypatch):
    rid=await upload(telegram_bot,store);before=telegram_bot.edit_message_text.await_count
    monkeypatch.setenv('TELEGRAM_ALLOWED_USER_IDS','42,99')
    for uid,cb,user in [(2,f'c:{rid}:pdf',99),(3,f'c:{rid}:set:0:4:pass',42),(4,'c:not-an-id:pdf',42)]:
        await webhook.deliver(make_update(telegram_bot,update_id=uid,user=user,callback=cb).to_dict(),telegram_bot,store,'test')
    assert telegram_bot.edit_message_text.await_count==before
    telegram_bot.send_document.assert_not_awaited()
    store.now+=3601
    await webhook.deliver(make_update(telegram_bot,update_id=5,callback=f'c:{rid}:pdf').to_dict(),telegram_bot,store,'test')
    assert 'истёк' in telegram_bot.answer_callback_query.call_args.kwargs['text']


@pytest.mark.anyio
async def test_dedup_and_download_cooldown(telegram_bot,store,make_update):
    rid=await upload(telegram_bot,store)
    await webhook.deliver(message(telegram_bot,TEXT,1).to_dict(),telegram_bot,store,'test')
    await webhook.deliver(message(telegram_bot,TEXT,2).to_dict(),telegram_bot,store,'test')
    assert len([k for k in store.data if re.fullmatch(r'test:calls:[a-f0-9]{24}',k)])==1
    for uid in (3,3,4):
        await webhook.deliver(make_update(telegram_bot,update_id=uid,callback=f'c:{rid}:csv').to_dict(),telegram_bot,store,'test')
    assert telegram_bot.send_document.await_count==1


@pytest.mark.anyio
@pytest.mark.parametrize('data,size',[ (b'\xff\xfe',10),(b'M: ok',2097153),(b'\x00',10),(b'x'*40001,40001)])
async def test_invalid_txt(telegram_bot,store,make_update,data,size):
    payload(telegram_bot,data)
    await webhook.deliver(make_update(telegram_bot,name='a.txt',size=size).to_dict(),telegram_bot,store,'test')
    assert 'Не удалось' in telegram_bot.edit_message_text.call_args.kwargs['text']
    assert not [k for k in store.data if re.fullmatch(r'test:calls:[a-f0-9]{24}',k)]


@pytest.mark.anyio
async def test_menu_project_cancel_and_csv_unchanged(telegram_bot,store,make_update):
    for uid,text in enumerate(('/start','📊 Анализ CRM','📞 Анализ звонков','ℹ️ Помощь','/project Тестовый ЖК','/cancel'),1):
        await webhook.deliver(message(telegram_bot,text,uid).to_dict(),telegram_bot,store,'test')
    assert await store.command('GET','test:call-project:42')=='Тестовый ЖК'
    await webhook.deliver(make_update(telegram_bot,update_id=20).to_dict(),telegram_bot,store,'test')
    assert any(re.fullmatch(r'test:report:[a-f0-9]{24}',k) for k in store.data)


def test_long_html_and_pagination():
    report=documents_to_calls([{'text':TEXT}]*20,'Северная Гавань')
    for c in report['calls']:
        c['manager']='<&🦊'*25
        c['criteria'][0]['quote']='<&🦊'*1000
    for action in ['overview:0','overview:3','call:19','criterion:0:0:0','criterion:0:0:5','rec:0']:
        text,kb=calls.page(report,'a'*24,action)
        assert len(text.encode('utf-16-le'))//2<4096 and '<&' not in text
        assert all(len(b.callback_data.encode())<=64 for row in kb.inline_keyboard for b in row)
    assert 'Звонок 20' in str(calls.page(report,'a'*24,'overview:3')[1])


def test_pdf_cyrillic_and_a4():
    from io import BytesIO
    from pypdf import PdfReader
    report=documents_to_calls([{'text':TEXT}],'Северная Гавань')
    doc=PdfReader(BytesIO(calls.build_calls_pdf(report)));text=''.join(p.extract_text() for p in doc.pages)
    assert 'Иван' in text and 'Требует проверки' in text and 'К: Скорее да' in text
    for p in doc.pages:
        assert abs(float(p.mediabox.width)-595.28)<1 and abs(float(p.mediabox.height)-841.89)<1

@pytest.mark.anyio
async def test_review_never_extends_original_ttl(telegram_bot,store,make_update,monkeypatch):
    import time
    now=time.time();monkeypatch.setattr(calls.time,'time',lambda:now)
    rid=await upload(telegram_bot,store)
    now+=3000;store.now+=3000
    await webhook.deliver(make_update(telegram_bot,update_id=2,callback=f'c:{rid}:set:0:4:review').to_dict(),telegram_bot,store,'test')
    assert store.expiry[calls.key('test',rid)]==3600
    store.now=3601
    assert not await store.command('GET',calls.key('test',rid))


@pytest.mark.anyio
async def test_denied_txt_and_changed_file_not_downloaded(telegram_bot,store,make_update):
    payload(telegram_bot,TEXT)
    await webhook.deliver(make_update(telegram_bot,user=99,name='calls.txt').to_dict(),telegram_bot,store,'test')
    telegram_bot.get_file.assert_not_awaited()
    await webhook.deliver(make_update(telegram_bot,update_id=2,name='calls.txt').to_dict(),telegram_bot,store,'test')
    rid=next(k.split(':')[-1] for k in store.data if re.fullmatch(r'test:calls:[a-f0-9]{24}',k))
    payload(telegram_bot,TEXT+'\nК: Изменение.')
    await webhook.deliver(make_update(telegram_bot,update_id=3,callback=f'c:{rid}:pdf').to_dict(),telegram_bot,store,'test')
    telegram_bot.send_document.assert_not_awaited()
    assert 'TXT' in telegram_bot.edit_message_text.call_args.kwargs['text']


@pytest.mark.anyio
async def test_multiple_txt_calls_and_user_lock(telegram_bot,store,make_update):
    payload(telegram_bot,'Звонок 1\n'+TEXT+'\nЗвонок 2\nМ: Алло.\nК: Да.')
    await webhook.deliver(make_update(telegram_bot,name='multi.txt').to_dict(),telegram_bot,store,'test')
    state=json.loads(next(v for k,v in store.data.items() if re.fullmatch(r'test:calls:[a-f0-9]{24}',k)))
    report=await calls.load_report(state,telegram_bot)
    assert report['attempts']==2 and report['pending']==7 and report['average'] is None
    rid=next(k.split(':')[-1] for k in store.data if re.fullmatch(r'test:calls:[a-f0-9]{24}',k))
    await store.claim('test:user:42:lock','other')
    before=telegram_bot.get_file.await_count
    await webhook.deliver(make_update(telegram_bot,update_id=2,callback=f'c:{rid}:pdf').to_dict(),telegram_bot,store,'test')
    assert telegram_bot.get_file.await_count==before
    assert 'Предыдущее действие' in telegram_bot.answer_callback_query.call_args.kwargs['text']

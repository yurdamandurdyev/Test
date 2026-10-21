import copy
import csv
import io
import json
import re
import pytest
from pypdf import PdfReader
from sales_intelligence import webhook
from sales_intelligence.analytics import analyze
from sales_intelligence.presentation import view, keyboard, human_csv, LABELS
from sales_intelligence.report_pdf import build_pdf


def test_views_preserve_core_and_escape(csv_data):
    report=analyze(csv_data);before=copy.deepcopy(report)
    for action in ('overview','sources','budgets','quality'):
        text=view(report,action)
        assert len(text.encode('utf-16-le'))//2<4000
        assert 'potential_duplicate' not in text
    assert '6\u202f916\u202f666,67' in view(report)
    report['week']['sources']={'<b>evil</b> & "x"':8}
    assert '<b>evil</b>' not in view(report,'sources')
    assert '&lt;b&gt;' in view(report,'sources')
    assert before['rows']==report['rows']
    assert all(len(b.callback_data.encode())<=64 for row in keyboard('a'*24).inline_keyboard for b in row)


def test_human_csv_all_rows_and_safe_formulas(csv_data):
    r=analyze(csv_data);r['rows'][0]['name']='=danger()'
    data=human_csv(r)
    rows=list(csv.reader(io.StringIO(data.decode('utf-8-sig'))))
    assert len(rows)==9
    assert rows[1][2]=="'=danger()"
    assert 'Возможное повторение записи' in rows[1][-1]
    assert 'potential_duplicate' not in data.decode('utf-8-sig')
    assert [row[5] for row in rows[1:]]==['12000000','12000000','0','','8500000','','9000000','0']


def test_pdf_real_pages_cyrillic_and_metrics(csv_data):
    r=analyze(csv_data);before=copy.deepcopy(r)
    reader=PdfReader(io.BytesIO(build_pdf(r)))
    assert len(reader.pages)==3
    text='\n'.join(p.extract_text() for p in reader.pages)
    assert 'Заявки' in text and 'Авито' in text and 'Что проверить в CRM' in text
    assert '6 916 666,67' in text.replace('\u202f',' ')
    assert 'potential_duplicate' not in text
    assert r==before
    for page in reader.pages:
        assert abs(float(page.mediabox.width)-595.276)<1
        assert abs(float(page.mediabox.height)-841.89)<1


def test_long_sources_large_amounts_and_empty_budgets():
    data=('дата,имя,телефон,источник,бюджет\n'+''.join(f'2026-10-19,A,DEMO,{"Ж"*1000}{i},999999999999.99\n' for i in range(50))).encode()
    r=analyze(data)
    assert len(view(r,'sources'))<4000
    pdf=PdfReader(io.BytesIO(build_pdf(r)))
    assert 3 <= len(pdf.pages)<=5
    r=analyze('дата,имя,телефон,источник,бюджет\n2026-10-19,A,DEMO,Сайт,\n'.encode())
    assert 'нет данных' in view(r,'budgets')
    assert build_pdf(r).startswith(b'%PDF')

async def uploaded(telegram_bot,make_update,store):
    await webhook.deliver(make_update(telegram_bot).to_dict(),telegram_bot,store,'test')
    key=next(k for k in store.data if ':report:' in k)
    return key.rsplit(':',1)[1]

@pytest.mark.anyio
async def test_callbacks_across_invocations_and_exports(csv_data,telegram_bot,make_update,store):
    rid=await uploaded(telegram_bot,make_update,store)
    state=json.loads(store.data['test:report:'+rid])
    assert set(state)=={'owner','chat','file_id','digest'}
    assert not any(r['name'] in json.dumps(store.data,ensure_ascii=False) for r in analyze(csv_data)['rows'])
    for index,action in enumerate(('overview','sources','budgets','quality','pdf','csv'),start=2):
        await webhook.deliver(make_update(telegram_bot,update_id=index,callback=f'r:{rid}:{action}').to_dict(),telegram_bot,store,'test')
        if action not in ('pdf','csv'):
            assert telegram_bot.edit_message_text.call_args.kwargs['text']==view(analyze(csv_data),action)
    docs=telegram_bot.send_document.call_args_list
    assert len(docs)==2
    assert docs[0].args[1].getvalue().startswith(b'%PDF')
    assert docs[1].args[1].getvalue()==human_csv(analyze(csv_data))
    assert store.expiry['test:report:'+rid]==3600

@pytest.mark.anyio
async def test_owner_and_expiry_before_download(telegram_bot,make_update,store,monkeypatch):
    rid=await uploaded(telegram_bot,make_update,store)
    monkeypatch.setenv('TELEGRAM_ALLOWED_USER_IDS','42,99')
    telegram_bot.reset_mock()
    await webhook.process(make_update(telegram_bot,user=99,callback=f'r:{rid}:pdf'),telegram_bot,store,'test')
    telegram_bot.get_file.assert_not_called()
    assert telegram_bot.answer_callback_query.call_args.kwargs['show_alert']
    store.now=3601
    await webhook.process(make_update(telegram_bot,callback=f'r:{rid}:pdf'),telegram_bot,store,'test')
    telegram_bot.get_file.assert_not_called()
    assert 'истёк' in telegram_bot.answer_callback_query.call_args.kwargs['text']

@pytest.mark.anyio
@pytest.mark.parametrize('data',['r:../../secret:pdf','r:'+('a'*24)+':delete','r:'+('a'*100)+':pdf','garbage'])
async def test_malformed_callbacks(telegram_bot,make_update,store,data):
    await webhook.process(make_update(telegram_bot,callback=data),telegram_bot,store,'test')
    telegram_bot.get_file.assert_not_called()

@pytest.mark.anyio
async def test_double_download_and_replayed_update(telegram_bot,make_update,store):
    rid=await uploaded(telegram_bot,make_update,store)
    for update_id in (2,2,3):
        await webhook.deliver(make_update(telegram_bot,update_id=update_id,callback=f'r:{rid}:pdf').to_dict(),telegram_bot,store,'test')
    assert telegram_bot.send_document.call_count==1
    store.now=31
    await webhook.deliver(make_update(telegram_bot,update_id=4,callback=f'r:{rid}:pdf').to_dict(),telegram_bot,store,'test')
    assert telegram_bot.send_document.call_count==2

@pytest.mark.anyio
async def test_bounded_failure_and_lock_release(telegram_bot,make_update,store):
    telegram_bot.get_file.side_effect=RuntimeError('sensitive transport detail')
    data=make_update(telegram_bot).to_dict()
    for _ in range(3):
        with pytest.raises(RuntimeError):await webhook.deliver(data,telegram_bot,store,'test')
    await webhook.deliver(data,telegram_bot,store,'test')
    await webhook.deliver(data,telegram_bot,store,'test')
    assert telegram_bot.get_file.call_count==3
    assert store.data['test:update:1:done']=='1'
    assert not any(k.endswith(':lock') for k in store.data)
    assert 'временно недоступен' in telegram_bot.edit_message_text.call_args.kwargs['text']

@pytest.mark.anyio
async def test_busy_callback_finishes_without_downloading(telegram_bot,make_update,store):
    rid=await uploaded(telegram_bot,make_update,store)
    await store.claim('test:user:42:lock','another-request')
    telegram_bot.reset_mock()
    await webhook.deliver(make_update(telegram_bot,update_id=2,callback=f'r:{rid}:sources').to_dict(),telegram_bot,store,'test')
    telegram_bot.get_file.assert_not_called()
    assert 'Предыдущее действие' in telegram_bot.answer_callback_query.call_args.kwargs['text']
    assert store.data['test:update:2:done']=='1'
    assert store.data['test:user:42:lock']=='another-request'

@pytest.mark.anyio
async def test_repeated_view_is_not_a_failure(telegram_bot,make_update,store):
    from telegram.error import BadRequest
    rid=await uploaded(telegram_bot,make_update,store)
    telegram_bot.edit_message_text.side_effect=BadRequest('Message is not modified')
    await webhook.deliver(make_update(telegram_bot,update_id=2,callback=f'r:{rid}:overview').to_dict(),telegram_bot,store,'test')
    assert store.data['test:update:2:done']=='1'

@pytest.mark.anyio
async def test_changed_file_is_not_exported(telegram_bot,make_update,store):
    rid=await uploaded(telegram_bot,make_update,store)
    telegram_bot.get_file.return_value.download_as_bytearray.return_value=b'different'
    await webhook.deliver(make_update(telegram_bot,update_id=2,callback=f'r:{rid}:csv').to_dict(),telegram_bot,store,'test')
    telegram_bot.send_document.assert_not_called()
    assert 'Отправьте CSV заново' in telegram_bot.edit_message_text.call_args.kwargs['text']

@pytest.mark.anyio
async def test_uncertain_document_send_is_not_immediately_repeated(telegram_bot,make_update,store):
    rid=await uploaded(telegram_bot,make_update,store)
    telegram_bot.send_document.side_effect=TimeoutError('response lost')
    data=make_update(telegram_bot,update_id=2,callback=f'r:{rid}:csv').to_dict()
    with pytest.raises(TimeoutError):await webhook.deliver(data,telegram_bot,store,'test')
    await webhook.deliver(data,telegram_bot,store,'test')
    assert telegram_bot.send_document.call_count==1


def test_hypothetical_dedup_is_distinct_from_contacts(csv_data):
    r=analyze(csv_data)
    assert r['week']['count']==8 and r['week']['unique_phones']==6
    assert r['alternative']['week']['count']==7
    assert 'разных' not in view(r,'quality').split('Альтернативный сценарий')[1].split('\n')[0]
    assert '7 заявок' in view(r,'quality')
    assert 'Ничего не удалено' in view(r)


def test_telegram_limit_counts_decoded_html(csv_data):
    import html
    r=analyze(csv_data)
    for period in ('day','week'):
        r[period]['sources']={('"<&'*30)+str(i):1 for i in range(40)}
        r[period]['count']=40
    text=view(r,'sources')
    visible=html.unescape(re.sub(r'<[^>]*>','',text))
    assert len(visible.encode('utf-16-le'))//2<4000
    assert '<&' not in text

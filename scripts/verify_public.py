#!/usr/bin/env python3
"""Read public demo and exercise uploads with synthetic data; print no input contents."""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from sales_intelligence.analytics import analyze, export_csv
from sales_intelligence.transcripts import documents_to_calls, export_report

base=sys.argv[1].rstrip('/') if len(sys.argv)>1 else 'https://test-mocha-ten-90.vercel.app'
def request(path,data=None,mime='application/json'):
    headers={'X-Sales-Client':'web','Origin':base,'Content-Type':mime,'X-File-Name':'acceptance.csv'}
    if isinstance(data,dict):data=json.dumps(data,ensure_ascii=False).encode()
    with urllib.request.urlopen(urllib.request.Request(base+path,data=data,headers=headers),timeout=60) as response:
        return response.read(),response.headers

health=json.loads(request('/api/health')[0]);assert health.get('web_ui_version')=='3.0'
demo=json.loads(request('/api/demo/calls')[0]);assert demo['average']==57.95 and len(demo['calls'])==5
text='М: Добрый день, ЖК «Северная Гавань», меня зовут Иван.\nК: Здравствуйте.\nМ: Какой бюджет?\nК: До 12 миллионов.\nМ: Когда планируете покупку?\nК: Весной.\nМ: Предлагаю ипотеку.\nК: Хорошо.\nМ: Приезжайте в субботу в 12:00 на показ.\nК: Скорее да, но я уточню.\nМ: Итак: бюджет 12 млн, пришлю адрес.'
payload={'documents':[{'name':'acceptance.txt','text':text}],'expected_project':'Северная Гавань','reviews':{}}
raw,headers=request('/api/transcripts/analyze',payload);report=json.loads(raw)
assert headers['Cache-Control']=='no-store' and report==documents_to_calls(payload['documents'],payload['expected_project'])
assert report['average'] is None and report['pending']==1
payload['reviews']={'1':{'criteria':{'meeting':{'status':'fail','reason':'Клиент ещё не подтвердил встречу.','quote':'К: Скорее да, но я уточню.'}}}}
report=json.loads(request('/api/transcripts/analyze',payload)[0]);assert report['average']==77.27
assert report==documents_to_calls(payload['documents'],payload['expected_project'],payload['reviews'])
for format in ('csv','html'):
    raw,headers=request('/api/transcripts/export?format='+format,payload)
    assert raw==export_report(report,format) and 'attachment' in headers['Content-Disposition']
csv='дата,имя,телефон,источник,бюджет\n20.10.2026,Тест A,,сайт,1000000\n21.10.2026,Тест B,,Авито,3000000\n21.10.2026,Тест C,,Авито,\n'.encode()
expected=analyze(csv)
assert json.loads(request('/api/analyze',csv,'text/csv')[0])==expected
assert request('/api/export',csv,'text/csv')[0]==export_csv(expected)
assert request('/knowledge.pdf')[0].startswith(b'%PDF')
assert b'<html' in request('/knowledge.html')[0].lower()
print('PASS: Production v3.0; 5 demo calls; anonymous TXT, review, CSV/HTML exports; CRM matches Python; standalone handout preserved. No personal input used.')

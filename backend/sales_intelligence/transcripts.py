"""Conservative, role-aware rules. No LLM, network calls or inferred missing facts."""
import csv
import html
import io
import re
from .analytics import InputError, safe_cell
from .calls import CRITERIA, score_calls

VERSION='rules-1.0'
ROLE=re.compile(r'^\s*(М|К|Менеджер(?:\s+([А-ЯЁ][а-яё-]+))?|Клиент|Manager|Client)\s*[:：]\s*(.+)$',re.I)
DAY=r'(?:понедельник|вторник|сред[ау]|четверг|пятниц[ау]|суббот[ау]|воскресенье|\d{1,2}[./]\d{1,2}(?:[./]\d{4})?)'
TIME=r'(?:\b(?:[01]?\d|2[0-3]):[0-5]\d\b|\bв\s+(?:[01]?\d|2[0-3])\s+час(?:а|ов)?\b)'
UNCERTAIN=r'\b(?:не|нет|если|возможно|наверное|уточню|допустим|пример|цитата)\b|может быть|скорее да|отмен\w*|перенос\w*|перенес\w*'
AMOUNT=r'(?:до\s+)?\d+(?:[.,]\d+)?(?:\s*(?:миллион(?:а|ов)?|млн|тысяч(?:и)?|тыс\.?|руб(?:лей)?|₽))?'
PERIOD=r'(?:весной|летом|осенью|зимой|до нового года|в течение (?:пары|\d+) месяцев|через \d+ (?:дн\w*|недел\w*|месяц\w*)|в этом (?:месяце|году))'
ADVICE={'intro':'Представиться и назвать правильный ЖК.', 'budget':'Уточнить бюджет и единицы суммы.', 'timing':'Уточнить срок покупки.', 'payment':'Предложить доступный способ оплаты.', 'meeting':'Подтвердить с клиентом день и время показа.', 'summary':'Подвести содержательный итог и обозначить следующий шаг.'}


def found(pattern,text):return re.search(pattern,text,re.I)
def clear(text):return not found(UNCERTAIN,text)
def item(status='review',reason='Правило не нашло однозначного подтверждения. Отсутствие совпадения не доказывает нарушение.',quote=''):
    return {'status':status,'reason':reason,'quote':quote,'reviewed':False}


def parse(text):
    turns=[];unparsed=[]
    for index,line in enumerate(text.splitlines(),1):
        if not line.strip():continue
        m=ROLE.match(line)
        if m:
            role='manager' if m[1].lower().startswith(('м','manager')) else 'client'
            turns.append({'role':role,'text':m[3],'quote':line,'line':index,'label_name':m[2]})
        else:unparsed.append(index)
    return turns,unparsed


def automatic(text,expected):
    turns,unparsed=parse(text)
    managers=[t for t in turns if t['role']=='manager'];clients=[t for t in turns if t['role']=='client']
    names=[]
    for t in managers:
        name=found(r'\bменя зовут\s+([А-ЯЁ][а-яё-]+)',t['text'])
        value=name[1] if name else t['label_name']
        if value and value.casefold() not in [n.casefold() for n in names]:names.append(value)
    manager=names[0] if len(names)==1 else None
    connected=True if managers and clients else None
    if re.fullmatch(r'\s*\[?(?:гудки,?\s*сброс|сброс|нет ответа)\]?\s*',text,re.I):connected=False
    criteria={key:item() for key,_,_ in CRITERIA}
    if connected is False:
        criteria={key:item('fail','В записи явно указан несостоявшийся звонок.',text.strip()) for key,_,_ in CRITERIA}
        return manager,connected,criteria,turns,unparsed
    # Positive rules require explicit role labels. Unlabelled commentary is never evidence.
    if connected is not True:
        return manager,connected,criteria,turns,unparsed
    for t in managers:
        greeting=found(r'^(?:добрый день|доброе утро|добрый вечер|здравствуйте)\b',t['text'])
        name=found(r'\bменя зовут\s+[а-яё-]+',t['text'])
        project=found(r'\bЖК\s+[«"]([^»"\n]+)[»"]',t['text'])
        if expected and greeting and name and expected.casefold() in t['text'].casefold() and (not project or project[1].strip().casefold()==expected.casefold()) and clear(t['text']):
            criteria['intro']=item('pass','В реплике менеджера есть приветствие, представление и указанный вами ЖК.',t['quote'])
        elif expected and project and project[1].strip().casefold()!=expected.casefold():
            criteria['intro']=item('fail','Назван другой ЖК. Сравнение выполнено с указанным вами названием.',t['quote'])
    if not expected:criteria['intro']=item(reason='Укажите ожидаемый ЖК: без него нельзя проверить правильность представления.')
    projects={m[1].strip().casefold() for t in managers if (m:=found(r'\bЖК\s+[«"]([^»"\n]+)[»"]',t['text']))}
    if len(projects)>1:criteria['intro']=item(reason='В репликах менеджера названы разные ЖК. Проверьте представление вручную.')
    candidates={'budget':[],'timing':[]}
    for i,t in enumerate(turns):
        if t['role']!='client' or not clear(t['text']):continue
        previous=turns[i-1] if i and turns[i-1]['role']=='manager' else None
        budget_question=previous and re.fullmatch(r'(?:Какой (?:у вас )?бюджет|Бюджет какой|На какой бюджет ориентируетесь|На какую сумму рассчитываете)\?',previous['text'],re.I)
        timing_question=previous and re.fullmatch(r'(?:Когда (?:планируете покупку|покупаете|планируете купить)|Какой срок покупки)\?',previous['text'],re.I)
        if re.fullmatch(r'(?:мой )?бюджет\s*(?:—|:)?\s*'+AMOUNT+r'[.!]?',t['text'],re.I) or (budget_question and re.fullmatch(AMOUNT+r'[.!]?',t['text'],re.I)):
            candidates['budget'].append(t)
        if found(r'(?:купить хочу|планирую купить|покупаю)\s+'+PERIOD,t['text']) or (timing_question and re.fullmatch(PERIOD+r'[.!]?',t['text'],re.I)):
            candidates['timing'].append(t)
    for key,values in candidates.items():
        if len(values)==1:criteria[key]=item('pass','Явный ответ клиента в подходящем контексте. Единицы суммы и календарный год не додумываются.',values[0]['quote'])
        elif len(values)>1:criteria[key]=item(reason='Найдено несколько ответов: проверьте, какое значение согласовано.',quote=values[-1]['quote'])
    payment=[t for t in managers if found(r'^(?:(?:предлагаю|можем предложить|у нас есть)\s+(?:вам\s+)?(?:ипотек\w*|рассрочк\w*)|есть\s+ипотека\s+от застройщика)',t['text']) and clear(t['text']) and '?' not in t['text']]
    if len(payment)==1:criteria['payment']=item('pass','Менеджер явно предлагает ипотеку или рассрочку; упоминание клиента не засчитывается.',payment[0]['quote'])
    proposals=0
    for i,t in enumerate(turns[:-1]):
        if t['role']!='manager' or not found(r'^(?:приезжайте|подъедете|давайте встретимся|приглашаю|назначим встречу|предлагаю встретиться)\b',t['text']) or not found(r'показ|встреч|приезжайте',t['text']):continue
        proposals+=1
        c=turns[i+1]
        if c['role']!='client':continue
        if found(DAY,t['text']) and found(TIME,t['text']) and clear(t['text']):
            if re.fullmatch(r'(?:да|давайте|согласен|согласна|подтверждаю)(?:,?\s*(?:приеду|буду|договорились))?[.!]?',c['text'],re.I):
                criteria['meeting']=item('pass','Менеджер предлагает день и время; следующая реплика клиента явно подтверждает встречу.',''.join(text.splitlines(keepends=True)[t['line']-1:c['line']]).rstrip('\r\n'))
            elif found(r'^(?:нет,?\s*)?не (?:приеду|смогу приехать|буду встречаться)',c['text']):
                criteria['meeting']=item('fail','Клиент явно отказался от предложенной встречи.',c['quote'])
            else:criteria['meeting']=item(reason='День и время предложены, но однозначного согласия клиента нет.',quote=c['quote'])
    if proposals>1:criteria['meeting']=item(reason='Несколько предложений встречи. Проверьте окончательную договорённость.')
    summaries=[t for t in managers if found(r'^(?:итак|подвед[её]м итог|подытожим)\b',t['text']) and clear(t['text'])]
    for t in summaries:
        facts=sum(bool(found(p,t['text'])) for p in (r'\bбюджет\s+'+AMOUNT,r'(?:показ|встреча).*'+DAY+r'.*'+TIME,r'(?:пришлю|отправлю)\s+(?:адрес|подборку|предложение)'))
        if facts>=2:criteria['summary']=item('pass','После явного маркера итога названы минимум два конкретных элемента: сумма бюджета, день/время встречи или обещанный материал.',t['quote'])
    # Conflicting/conditional wording around the same topic invalidates an automatic pass.
    topics={'budget':r'бюджет|миллион|млн','timing':r'купить|покуп|срок','payment':r'ипотек|рассроч','meeting':r'показ|встреч|приед|уточню','summary':r'итог|итак','intro':r'\bЖК\b'}
    for key,pattern in topics.items():
        if criteria[key]['status']=='pass':
            conflict=[t for t in turns if found(pattern,t['text']) and not clear(t['text'])]
            if conflict:criteria[key]=item(reason='В разговоре есть отрицание или условие по этому критерию. Проверьте противоречие.',quote=conflict[-1]['quote'])
    if len(names)>1:
        criteria={key:item(reason='В расшифровке представились несколько менеджеров. Разделите звонки или проверьте критерии вручную.') for key in criteria}
    return manager,connected,criteria,turns,unparsed


def documents_to_calls(documents,expected='',reviews=None):
    if not isinstance(documents,list) or not 1<=len(documents)<=20:raise InputError('Загрузите от 1 до 20 TXT-файлов или вставьте текст.')
    if not isinstance(expected,str) or len(expected)>100:raise InputError('Название ЖК: не более 100 символов.')
    expected=expected.strip();parts=[]
    for doc in documents:
        if not isinstance(doc,dict) or not isinstance(doc.get('text'),str):raise InputError('Нужен текст расшифровки.')
        text=doc['text'].lstrip('\ufeff');name=doc.get('name','Вставленный текст')
        if not isinstance(name,str) or len(name)>200:raise InputError('Слишком длинное имя файла.')
        if not text.strip() or '\x00' in text:raise InputError('TXT пуст или содержит двоичные данные.')
        if len(text)>400000:raise InputError('Общий объём расшифровок — не более 400 000 символов.')
        chunks=re.split(r'^\s*(?:Звонок|Call)\s+\d+\s*$',text,flags=re.M|re.I)
        for chunk in chunks:
            if chunk.strip():parts.append((name,chunk.strip()))
    if not 1<=len(parts)<=20 or sum(len(t) for _,t in parts)>400000:raise InputError('Не более 20 звонков и 400 000 символов за один анализ.')
    if reviews is None:reviews={}
    if not isinstance(reviews,dict) or set(reviews)-{str(i) for i in range(1,len(parts)+1)}:raise InputError('Неизвестный звонок в ручной проверке.')
    calls=[]
    for index,(name,text) in enumerate(parts,1):
        if len(text)>40000 or len(text.splitlines())>2000:raise InputError('Один звонок: не более 40 000 символов и 2000 строк.')
        manager,connected,criteria,turns,unparsed=automatic(text,expected)
        edit=reviews.get(str(index),{})
        if not isinstance(edit,dict) or set(edit)-{'manager','connected','criteria'}:raise InputError('Некорректная ручная проверка.')
        if 'manager' in edit:
            if not isinstance(edit['manager'],str) or not 1<=len(edit['manager'].strip())<=80:raise InputError('Имя менеджера: от 1 до 80 символов.')
            manager=edit['manager'].strip()
        if 'connected' in edit:
            if edit['connected'] is not None and type(edit['connected']) is not bool:raise InputError('Некорректный статус разговора.')
            connected=edit['connected']
        changes=edit.get('criteria',{})
        if not isinstance(changes,dict) or set(changes)-set(criteria):raise InputError('Неизвестный критерий.')
        for key,change in changes.items():
            if not isinstance(change,dict) or set(change)-{'status','reason','quote'} or change.get('status') not in ('pass','fail','review'):raise InputError('Некорректный статус критерия.')
            reason=change.get('reason','');quote=change.get('quote','')
            if not isinstance(reason,str) or not 3<=len(reason.strip())<=1500:raise InputError('Объясните ручную оценку (3–1500 символов).')
            if not isinstance(quote,str) or len(quote)>4000 or (quote and quote not in text):raise InputError('Цитата должна точно присутствовать в расшифровке.')
            if change['status']=='pass' and not quote:raise InputError('Для подтверждения критерия нужна цитата из расшифровки.')
            criteria[key]={**change,'reason':reason.strip(),'quote':quote,'reviewed':True,'automatic':criteria[key]}
        if connected is False:
            criteria={key:{**value,'status':'fail','reason':'Звонок отмечен как несостоявшийся; вне качества менеджеров.','automatic':value.get('automatic',value)} for key,value in criteria.items()}
        calls.append({'id':index,'name':name,'transcript':text,'manager':manager or 'Не определён','connected':connected,'criteria':criteria,'turns':turns,'unparsed_lines':unparsed,'metadata_reviewed':bool(set(edit)&{'manager','connected'})})
    return summarize(calls,expected)


def summarize(calls,expected):
    for call in calls:
        criteria=[]
        for key,label,weight in CRITERIA:
            c=call['criteria'][key];criteria.append({'key':key,'label':label,'weight':weight,'points':weight if c['status']=='pass' else 0 if c['status']=='fail' else None,**c})
        call['criteria']=criteria
        low=sum(c['points'] or 0 for c in criteria);unknown=sum(c['weight'] for c in criteria if c['status']=='review')
        call.update(confirmed_points=low,possible_points=low+unknown,pending=sum(c['status']=='review' for c in criteria),percent=None,raw_score=None)
        if not unknown and call['connected'] is True:
            # Reuse the established scoring contract for every resolved conversation.
            legacy={**call,'criteria':{c['key']:{'passed':c['status']=='pass','reason':c['reason'],'quote':c['quote']} for c in criteria},'recommendation':''}
            scored=score_calls([legacy])['calls'][0];call.update(percent=scored['percent'],raw_score=scored['raw_score'])
        call['recommendations']=[ADVICE[c['key']] for c in criteria if c['status']=='fail'] if call['connected'] is not False else ['Разговор не состоялся. Повторный контакт оцените отдельно.']
        if call['pending']:call['recommendations'].append('Проверьте вручную: '+', '.join(c['label'] for c in criteria if c['status']=='review')+'.')
    connected=[c for c in calls if c['connected'] is True]
    unclassified=sum(c['connected'] is None for c in calls)
    def aggregate(group):
        if not group:return {'average':None,'low':None,'high':None,'count':0,'pending':0}
        low=round(sum(c['confirmed_points'] for c in group)/len(group)/110*100,2)
        high=round(sum(c['possible_points'] for c in group)/len(group)/110*100,2)
        pending=sum(c['pending'] for c in group)
        return {'average':low if not pending else None,'low':low,'high':high,'count':len(group),'pending':pending}
    total=aggregate(connected)
    if unclassified:total['average']=None
    return {'version':VERSION,'expected_project':expected,'calls':calls,'attempts':len(calls),'connected':len(connected),'unclassified':unclassified,'pending':sum(c['pending'] for c in calls),'average':total['average'],'low':total['low'],'high':total['high'],
            'managers':[{'name':name,**aggregate([c for c in connected if c['manager']==name])} for name in sorted({c['manager'] for c in connected})],
            'criteria':[{'key':key,'label':label,'weight':weight,'passed':sum(c['criteria'][i]['status']=='pass' for c in connected),'failed':sum(c['criteria'][i]['status']=='fail' for c in connected),'review':sum(c['criteria'][i]['status']=='review' for c in connected),'total':len(connected)} for i,(key,label,weight) in enumerate(CRITERIA)],
            'limitations':['Правила распознают только ограниченные конструкции, а не смысл произвольной речи. Положительные совпадения также стоит проверять.', 'Неподтверждённые критерии не являются нулями. Диапазон относится только к звонкам с подтверждёнными ролями; нераспознанные разговоры показаны отдельно.', 'Итоговый процент отсутствует до разрешения неоднозначностей. Все ручные изменения помечены; исходный результат правил сохранён.']}


def export_report(report,format):
    if format=='csv':
        stream=io.StringIO(newline='');writer=csv.writer(stream);writer.writerow(['Звонок','Менеджер','Критерий','Статус','Баллы','Вес','Причина','Цитата','Ручная проверка','Итог, %'])
        for call in report['calls']:
            for c in call['criteria']:writer.writerow([safe_cell(v) for v in [call['id'],call['manager'],c['label'],{'pass':'Подтверждено','fail':'Не выполнено','review':'Требует проверки'}[c['status']],c['points'],c['weight'],c['reason'],c['quote'],c['reviewed'],call['percent']]])
        return ('\ufeff'+stream.getvalue()).encode()
    esc=lambda x:html.escape(str(x))
    sections=[]
    for call in report['calls']:
        rows=''.join(f'<tr><td>{esc(c["label"])}</td><td>{esc({"pass":"Подтверждено","fail":"Не выполнено","review":"Требует проверки"}[c["status"]])}</td><td>{c["points"] if c["points"] is not None else "?"}/{c["weight"]}</td><td>{esc(c["reason"])} ({"решение пользователя" if c["reviewed"] else "правило"})<blockquote>{esc(c["quote"])}</blockquote></td></tr>' for c in call['criteria'])
        sections.append(f'<section><h2>Звонок {call["id"]} · {esc(call["manager"])}</h2><p>Итог: {call["percent"] if call["percent"] is not None else "не определён"}; подтверждено {call["confirmed_points"]}/110, возможно до {call["possible_points"]}/110.</p><table>{rows}</table><ul>{''.join('<li>'+esc(r)+'</li>' for r in call['recommendations'])}</ul><pre>{esc(call["transcript"])}</pre></section>')
    return ('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Разбор звонков</title><style>body{font:16px/1.5 system-ui;max-width:1100px;margin:40px auto;padding:20px}table{width:100%;border-collapse:collapse}td{border-bottom:1px solid #bbb;padding:10px;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere}section{margin:30px 0}blockquote{margin:10px;color:#555}</style><h1>Разбор звонков · правила без ИИ</h1><p>Неопределённые критерии требуют проверки; они не превращены в нули. Экспорт содержит расшифровки — не публикуйте его без согласия участников.</p>'+''.join(sections)+'</html>').encode()

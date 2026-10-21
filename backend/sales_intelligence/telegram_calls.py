"""Telegram presentation and expiring review state; calculations live in transcripts.py."""
import asyncio
import hashlib
import hmac
import io
import json
import os
import time
from html import escape
from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup, ReplyKeyboardMarkup, ForceReply
from .analytics import InputError
from .transcripts import documents_to_calls, export_report, parse

MENU = ReplyKeyboardMarkup([['📊 Анализ CRM', '📞 Анализ звонков'], ['ℹ️ Помощь']], resize_keyboard=True)
HELP = ('<b>Signal · CRM и звонки</b>\n\n'
        '📊 CSV → заявки, бюджеты и качество CRM.\n'
        '📞 TXT или текст диалога → критерии, цитаты и рекомендации без ИИ. '
        'Роли: <code>М:</code> и <code>К:</code>. Несколько звонков разделяйте строками «Звонок 1», «Звонок 2».\n\n'
        'Файлы UTF-8, до 2 МБ; до 20 звонков, 40 000 символов на звонок. '
        'Ожидаемый ЖК: Северная Гавань. Изменить для следующих отчётов: <code>/project Название ЖК</code>.\n'
        'Спорные оценки требуют проверки, а не получают ноль. Кнопки и ручные правки доступны один час только вам. '
        'Текст сообщений временно хранится в Redis; для TXT — ссылка на файл и ручные правки. '
        'Сообщения и скачанные файлы остаются в Telegram. /cancel отменяет ввод цитаты.')
STATUS = {'pass':'Подтверждено', 'fail':'Не выполнено', 'review':'Требует проверки'}


def key(prefix, rid): return f'{prefix}:calls:{rid}'
def remaining(state): return max(0, int(state['expires'] - time.time()))
def button(label, rid, action): return Button(label, callback_data=f'c:{rid}:{action}')
def markup(rows): return InlineKeyboardMarkup(rows)
def score(call):
    return f'{call["percent"]}%' if call['percent'] is not None else ('Не состоялся' if call['connected'] is False else f'Требует проверки · {call["confirmed_points"]}–{call["possible_points"]}/110')


def page(report, rid, action='overview'):
    parts=action.split(':'); kind=parts[0]
    back=[button('← Все звонки',rid,'overview')]
    if kind=='overview':
        average='Требует проверки' if report['average'] is None else f'{report["average"]}%'
        text=f'<b>📞 Разбор звонков</b>\n\nЗаписей: <b>{report["attempts"]}</b> · Состоялись: <b>{report["connected"]}</b>\nСтатус не определён: {report["unclassified"]}\nСредняя оценка: <b>{average}</b>\nКритериев на проверке: {report["pending"]}\n\n'
        offset=int(parts[1]) if len(parts)>1 else 0
        if not 0<=offset<(len(report['calls'])+4)//5:raise ValueError('page')
        selected=list(enumerate(report['calls']))[offset*5:(offset+1)*5]
        text+='\n'.join(f'{c["id"]}. {escape(c["manager"][:80])} — {score(c)}' for _,c in selected)
        text+='\n\nПравила распознают ограниченные формулировки, а не смысл речи. Неподтверждённое не равно нулю. Выберите звонок для цитат и проверки.'
        rows=[[button(f'Звонок {c["id"]}',rid,f'call:{i}')] for i,c in selected]
        nav=[]
        if offset:nav.append(button('←',rid,f'overview:{offset-1}'))
        if (offset+1)*5<len(report['calls']):nav.append(button('→',rid,f'overview:{offset+1}'))
        if nav:rows.append(nav)
        rows.append([button('↓ PDF',rid,'pdf'),button('↓ CSV',rid,'csv')])
        return text,markup(rows)
    i=int(parts[1]);call=report['calls'][i]
    title=f'<b>Звонок {call["id"]} · {escape(call["manager"][:80])}</b>\n{score(call)}\n\n'
    if kind=='call':
        rows=[];text=title
        for j,c in enumerate(call['criteria']):
            text+=f'{escape(c["label"])}: <b>{STATUS[c["status"]]}</b> ({"?" if c["points"] is None else c["points"]}/{c["weight"]})\n'
            rows.append([button(c['label'],rid,f'criterion:{i}:{j}:0')])
        if call['connected'] is None:text+='\nРоли не распознаны. Исправьте подписи М:/К: и отправьте заново.'
        rows.extend([[button('Рекомендации',rid,f'rec:{i}')],back])
        return text,markup(rows)
    if kind=='rec':
        return title+'<b>Следующие действия</b>\n'+escape('\n'.join('• '+s for s in call['recommendations']) or 'Все критерии подтверждены. Проверьте цитаты перед использованием оценки.'),markup([[button('← Критерии',rid,f'call:{i}')],back])
    if kind=='criterion':
        j=int(parts[2]);number=int(parts[3]);c=call['criteria'][j]
        detail=f'{STATUS[c["status"]]} · {"решение пользователя" if c["reviewed"] else "правило"}\n\n{c["reason"]}\n\nЦитата:\n{c["quote"] or "Нет однозначного подтверждения."}'
        if c.get('automatic'):detail+='\n\nПервоначально: '+STATUS[c['automatic']['status']]+'\n'+c['automatic']['reason']
        # Slice plain text BEFORE HTML escaping; even all ampersands fit Telegram's UTF-16 limit.
        pages=[detail[n:n+500] for n in range(0,len(detail),500)]
        if not 0<=number<len(pages):raise ValueError('page')
        rows=[]
        if len(pages)>1:rows.append([button('←',rid,f'criterion:{i}:{j}:{number-1}') ] if number else [])
        if number+1<len(pages):
            if not rows:rows.append([])
            rows[-1].append(button('→',rid,f'criterion:{i}:{j}:{number+1}'))
        if call['connected'] is True:
            rows += [[button('✓ Подтвердить',rid,f'pass:{i}:{j}'),button('Не выполнено',rid,f'set:{i}:{j}:fail')],
                     [button('Требует проверки',rid,f'set:{i}:{j}:review')]]
        rows += [[button('← Критерии',rid,f'call:{i}')]]
        return title+f'<b>{escape(c["label"])}</b> · {number+1}/{len(pages)}\n\n'+escape(pages[number]),markup([r for r in rows if r])
    raise ValueError('action')


def build_calls_pdf(report):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from .report_pdf import fonts, INK, MUTED
    fonts();stream=io.BytesIO()
    body=ParagraphStyle('calls-body',fontName='Signal',fontSize=10,leading=15,textColor=INK,spaceAfter=8,splitLongWords=True)
    heading=ParagraphStyle('calls-heading',parent=body,fontName='SignalBold',fontSize=19,leading=25,spaceAfter=15)
    def p(value,style=body):return Paragraph(escape(str(value)).replace('\n','<br/>'),style)
    avg='Требует проверки' if report['average'] is None else f'{report["average"]}%'
    story=[p('signal. / Аналитика звонков',heading),p(f'Записей: {report["attempts"]} · Состоялись: {report["connected"]}\nСредняя оценка: {avg}\nНе определён статус: {report["unclassified"]} · Спорных критериев: {report["pending"]}'),p('Без нейросетей. Неизвестные критерии не превращены в нули. Веса и расчёты — общие с веб-версией. Длинные цитаты здесь сокращены до 700 символов; полный текст подтверждений — в CSV.')]
    for call in report['calls']:
        story += [PageBreak(),p(f'Звонок {call["id"]} · {call["manager"]}',heading),p(score(call))]
        for c in call['criteria']:
            story += [p(f'{c["label"]} — {STATUS[c["status"]]} ({"?" if c["points"] is None else c["points"]}/{c["weight"]})'),p(('Решение пользователя. ' if c['reviewed'] else 'Правило. ')+c['reason']),p('Цитата: '+(c['quote'][:700]+('…' if len(c['quote'])>700 else '') or 'нет однозначной цитаты')),Spacer(1,8)]
        story += [p('Рекомендации',heading),p('\n'.join(call['recommendations']) or 'Все критерии подтверждены. Проверьте цитаты.')]
    def footer(canvas,doc):
        canvas.setFont('Signal',8);canvas.setFillColor(MUTED);canvas.drawString(42,25,'Signal · Личный отчёт · '+report['version']);canvas.drawRightString(550,25,str(doc.page))
    SimpleDocTemplate(stream,pagesize=A4,leftMargin=42,rightMargin=42,topMargin=42,bottomMargin=45,title='Signal · Звонки').build(story,onFirstPage=footer,onLaterPages=footer)
    return stream.getvalue()


async def load_report(state, bot):
    from .webhook import get_payload
    if 'file_id' in state:
        payload=await get_payload(bot,state['file_id'])
        if hashlib.sha256(payload).hexdigest()!=state['digest']:raise InputError('Файл изменился. Пришлите TXT заново.')
        try:text=payload.decode('utf-8-sig')
        except UnicodeDecodeError:raise InputError('Сохраните TXT в кодировке UTF-8.') from None
    else:text=state['text']
    return await asyncio.to_thread(documents_to_calls,[{'name':'Telegram.txt','text':text}],state['project'],state.get('reviews',{}))


async def save_state(store,prefix,rid,state):
    ttl=remaining(state)
    if not ttl:raise InputError('Час хранения истёк. Пришлите текст заново.')
    await store.command('SET',key(prefix,rid),json.dumps(state,ensure_ascii=False),'EX',ttl)


async def handle(update,bot,store,prefix):
    """Called only after the common allowlist and private-chat checks. True consumes update."""
    from .webhook import answer, edit, get_payload, STATE_TTL, MAX_BYTES, MIME_TYPES
    user=update.effective_user.id;chat=update.effective_chat.id;message=update.effective_message
    query=update.callback_query;stage=f'{prefix}:update:{update.update_id}'
    prefs=f'{prefix}:call-project:{user}';pending_key=f'{prefix}:call-review:{user}'
    if query:
        if not (query.data or '').startswith('c:'):return False
        pieces=query.data.split(':');rid=pieces[1] if len(pieces)>2 else ''
        if len(rid)!=24 or any(x not in '0123456789abcdef' for x in rid):
            await answer(bot,query,'Некорректная кнопка.',True);return True
        raw=await store.command('GET',key(prefix,rid));state=json.loads(raw) if raw else None
        if not state or not remaining(state):
            await answer(bot,query,'Час хранения истёк. Пришлите TXT или текст заново.',True);return True
        if state['owner']!=user or state['chat']!=chat:
            await answer(bot,query,'Этот отчёт доступен только его владельцу.',True);return True
        action=':'.join(pieces[2:]);kind=pieces[2]
        import re
        if not re.fullmatch(r'(overview(?::[0-3])?|pdf|csv|call:\d{1,2}|rec:\d{1,2}|criterion:\d{1,2}:[0-5]:\d{1,3}|pass:\d{1,2}:[0-5]|set:\d{1,2}:[0-5]:(fail|review))',action):
            await answer(bot,query,'Некорректная кнопка.',True);return True
        await answer(bot,query)
        report=await load_report(state,bot)
        try:
            if kind in ('set','pass'):
                i,j=int(pieces[3]),int(pieces[4]);call=report['calls'][i];c=call['criteria'][j]
                if call['connected'] is not True:raise ValueError('connection')
                if kind=='pass':
                    prompt_id=await store.command('GET',stage+':prompt')
                    if not prompt_id:
                        prompt=await bot.send_message(chat,'Ответьте на это сообщение точной цитатой из разговора, подтверждающей критерий «'+c['label']+'». Можно добавить отдельной строкой «Причина: …». /cancel — отмена.',reply_markup=ForceReply(selective=True))
                        prompt_id=prompt.message_id
                        await store.command('SET',stage+':prompt',str(prompt_id),'EX',STATE_TTL)
                    await store.command('SET',pending_key,json.dumps({'rid':rid,'call':i,'criterion':j,'prompt':int(prompt_id)}),'EX',remaining(state));return True
                state.setdefault('reviews',{}).setdefault(str(call['id']),{}).setdefault('criteria',{})[c['key']]={'status':pieces[5],'reason':'Ручная проверка пользователя: '+STATUS[pieces[5]]+'.','quote':''}
                report=await load_report(state,bot)
                await save_state(store,prefix,rid,state);action=f'criterion:{i}:{j}:0'
            if kind in ('pdf','csv'):
                if await store.command('GET',stage+':sent'):return True
                if not await store.claim(key(prefix,rid)+':download:'+kind,'sending',ttl=30):
                    await bot.send_message(chat,'Файл уже отправляется или недавно отправлен. Повторите через 30 секунд.');return True
                data=await asyncio.to_thread(build_calls_pdf,report) if kind=='pdf' else export_report(report,'csv')
                await bot.send_document(chat,io.BytesIO(data),filename='calls-report.'+kind,caption='Разбор звонков · ваши данные и ручные оценки')
                await store.command('SET',stage+':sent','1','EX',604800)
            else:
                text,kb=page(report,rid,action);await edit(bot,chat,message.message_id,text,kb)
        except (IndexError,ValueError):await bot.send_message(chat,'Эта страница недоступна. Откройте сводку отчёта или отправьте текст заново.')
        return True
    text=message.text or ''
    if text=='/cancel':
        await store.command('SET',pending_key,'','EX',1);await bot.send_message(chat,'Ввод цитаты отменён.',reply_markup=MENU);return True
    if text.startswith('/project '):
        project=text[9:].strip()
        if not 1<=len(project)<=100:await bot.send_message(chat,'Название ЖК: от 1 до 100 символов.');return True
        await store.command('SET',prefs,project,'EX',STATE_TTL)
        await bot.send_message(chat,'Ожидаемый ЖК для следующих отчётов: '+project+'. Настройка действует час.');return True
    if text in ('/start','/help','ℹ️ Помощь','📊 Анализ CRM','📞 Анализ звонков'):
        if text=='📊 Анализ CRM':body='📊 Пришлите CSV UTF-8 до 2 МБ. Столбцы: дата, имя, телефон, источник, бюджет.'
        elif text=='📞 Анализ звонков':body='📞 Пришлите TXT UTF-8 или вставьте диалог с ролями М:/К:. Несколько звонков разделите строками «Звонок 1», «Звонок 2».\nОжидаемый ЖК: '+escape(await store.command('GET',prefs) or 'Северная Гавань')+'. Изменить: /project Название'
        else:body=HELP
        await bot.send_message(chat,body,parse_mode='HTML',reply_markup=MENU);return True
    pending_raw=await store.command('GET',pending_key) if text else None
    pending=json.loads(pending_raw) if pending_raw else None
    if pending and message.reply_to_message and message.reply_to_message.message_id==pending['prompt']:
        raw=await store.command('GET',key(prefix,pending['rid']));state=json.loads(raw) if raw else None
        if not state or state['owner']!=user or state['chat']!=chat or not remaining(state):
            await bot.send_message(chat,'Отчёт недоступен или срок хранения истёк.');return True
        try:
            report=await load_report(state,bot);call=report['calls'][pending['call']];c=call['criteria'][pending['criterion']]
            quote,_,reason=text.partition('\nПричина:')
            state.setdefault('reviews',{}).setdefault(str(call['id']),{}).setdefault('criteria',{})[c['key']]={'status':'pass','quote':quote.strip(),'reason':reason.strip() or 'Подтверждено пользователем по точной цитате.'}
            report=await load_report(state,bot)
            await save_state(store,prefix,pending['rid'],state)
            body,kb=page(report,pending['rid']);await edit(bot,chat,pending['prompt'],body,kb)
            await store.command('SET',pending_key,'','EX',1)
        except InputError as exc:await bot.send_message(chat,str(exc)+' Ответьте на запрос цитаты ещё раз.')
        return True
    doc=message.document
    is_txt=bool(doc and doc.file_name and doc.file_name.lower().endswith('.txt'))
    if doc and not is_txt:return False
    if not is_txt:
        turns,_=parse(text)
        if {turn['role'] for turn in turns}!={'manager','client'}:
            await bot.send_message(chat,'Пришлите CSV, TXT или диалог с подписями М:/К:. Выберите раздел ниже.',reply_markup=MENU);return True
    progress=await store.command('GET',stage+':progress')
    if not progress:
        progress=(await bot.send_message(chat,'Разбираю звонки и проверяю подтверждения…')).message_id
        await store.command('SET',stage+':progress',str(progress),'EX',604800)
    try:
        if is_txt:
            if doc.mime_type not in MIME_TYPES or doc.file_size is None or doc.file_size>MAX_BYTES:raise InputError('Нужен TXT UTF-8 до 2 МБ с известным размером.')
            payload=await get_payload(bot,doc.file_id)
            try:payload.decode('utf-8-sig')
            except UnicodeDecodeError:raise InputError('Сохраните TXT в кодировке UTF-8.') from None
        else:payload=text.encode()
        project=await store.command('GET',prefs) or 'Северная Гавань'
        digest=hashlib.sha256(payload).hexdigest();dupe=f'{prefix}:call-file:{user}:'+hashlib.sha256((digest+project).encode()).hexdigest()
        previous=await store.command('GET',dupe)
        if previous:
            raw=await store.command('GET',key(prefix,previous))
            if raw:
                old=json.loads(raw)
                if remaining(old):
                    report=await load_report(old,bot);body,kb=page(report,previous);await edit(bot,chat,int(progress),body,kb);return True
        rid=hmac.new(os.environ['TELEGRAM_BOT_TOKEN'].encode(),f'calls:{user}:{update.update_id}'.encode(),hashlib.sha256).hexdigest()[:24]
        existing=await store.command('GET',key(prefix,rid))
        state=json.loads(existing) if existing else {'owner':user,'chat':chat,'expires':time.time()+STATE_TTL,'project':project,'digest':digest,'reviews':{},**({'file_id':doc.file_id} if is_txt else {'text':text})}
        report=await asyncio.to_thread(documents_to_calls,[{'name':'Telegram.txt','text':payload.decode('utf-8-sig')}],state['project'],state['reviews'])
        await save_state(store,prefix,rid,state)
        body,kb=page(report,rid);await edit(bot,chat,int(progress),body,kb)
        await store.command('SET',dupe,rid,'EX',600)
    except InputError as exc:await edit(bot,chat,int(progress),'Не удалось разобрать звонки. '+escape(str(exc)))
    return True

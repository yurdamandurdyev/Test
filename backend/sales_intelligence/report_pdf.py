"""Small, in-memory vector PDF. No browser, network resources or temporary CRM files."""
from io import BytesIO
from pathlib import Path
from threading import Lock
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
from .presentation import dates, money, insights, source_items, plain, LABELS

INK=colors.HexColor('#1d2925'); MUTED=colors.HexColor('#596b61'); SAGE=colors.HexColor('#dce9cb'); GREEN=colors.HexColor('#54755b'); LINE=colors.HexColor('#dce2dc')
_lock=Lock()

def fonts():
    with _lock:
        if 'Signal' not in pdfmetrics.getRegisteredFontNames():
            root=Path(__file__).parent/'fonts'
            pdfmetrics.registerFont(TTFont('Signal', str(root/'DejaVuSans.ttf')))
            pdfmetrics.registerFont(TTFont('SignalBold', str(root/'DejaVuSans-Bold.ttf')))
            pdfmetrics.registerFontFamily('Signal',normal='Signal',bold='SignalBold',italic='Signal',boldItalic='SignalBold')


class Bars(Flowable):
    def __init__(self,items,width=475):
        Flowable.__init__(self);self.items=items;self.width=width;self.height=len(items)*33+8
    def draw(self):
        c=self.canv;maximum=max((v for _,v in self.items),default=1) or 1
        for index,(label,value) in enumerate(self.items):
            y=self.height-22-index*33
            c.setFont('Signal',9);c.setFillColor(INK);c.drawString(0,y,plain(label,49));c.drawRightString(self.width,y,str(value))
            c.setFillColor(LINE);c.roundRect(0,y-12,self.width,5,2,fill=1,stroke=0)
            if value:
                c.setFillColor(GREEN);c.roundRect(0,y-12,self.width*value/maximum,5,2,fill=1,stroke=0)


def build_pdf(report):
    fonts();stream=BytesIO()
    doc=SimpleDocTemplate(stream,pagesize=A4,rightMargin=48,leftMargin=48,topMargin=60,bottomMargin=50,title='Signal · Аналитика заявок',author='Sales Intelligence',pageCompression=1)
    styles={
        'title':ParagraphStyle('title',fontName='SignalBold',fontSize=25,leading=32,textColor=INK,spaceAfter=12),
        'h':ParagraphStyle('h',fontName='SignalBold',fontSize=13,leading=19,textColor=INK,spaceBefore=14,spaceAfter=9),
        'body':ParagraphStyle('body',fontName='Signal',fontSize=9.5,leading=15,textColor=INK,spaceAfter=8,splitLongWords=True),
        'muted':ParagraphStyle('muted',fontName='Signal',fontSize=8.5,leading=13,textColor=MUTED,spaceAfter=7),
        'metric':ParagraphStyle('metric',fontName='SignalBold',fontSize=16,leading=23,textColor=INK,spaceAfter=3),
    }
    def p(text,kind='body'):return Paragraph(escape(str(text)),styles[kind])
    def heading(text):return p(text,'h')
    def footer(c,d):
        c.setFillColor(MUTED);c.setFont('SignalBold',9);c.drawString(48,810,'signal. / ОТДЕЛ ПРОДАЖ')
        c.setStrokeColor(LINE);c.line(48,797,547,797);c.line(48,37,547,37)
        c.setFont('Signal',8);c.drawString(48,24,'Данные загруженного файла · Контакты не публикуются');c.drawRightString(547,24,f'{d.page:02d}')
    w,d=report['week'],report['day']
    story=[p('Заявки. Бюджеты.\nТочки внимания.','title'),p(dates(w),'muted')]
    cells=[]
    for label,value,note in [('Заявки за 7 дней',str(w['count']),f'Последний день: {d["count"]}'),('Распознанные телефоны',str(w['unique_phones']),f'Без распознанного телефона: {w["unidentified"]}'),('Средний бюджет',money(w['budget_mean']),f'Учтено значений: {w["budget_known"]}, нулей: {w["budget_zero"]}')]:
        cells.append([p(label,'muted'),p(value,'metric'),p(note,'muted')])
    # Two columns keep even very large budgets inside their cell.
    table=Table([[cells[0],cells[1]],[cells[2], [p('Что означают числа','muted'),p('Строка — заявка. Разные телефоны — оценка числа контактов, не подтверждение личности.')]]],colWidths=[249,249])
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),SAGE),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),14),('RIGHTPADDING',(0,0),(-1,-1),14),('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),9),('BOX',(0,0),(-1,-1),.5,LINE),('INNERGRID',(0,0),(-1,-1),2,colors.white)]))
    story += [table,heading('Откуда приходят заявки · 7 дней'),Bars(source_items(w,6)),p('Количество обращений по источникам. Это не конверсия и не оценка эффективности рекламы. Длинные названия сокращены; полный реестр — в CSV.','muted'),heading('Последний день'),p(f'{dates(d)} · Заявки: {d["count"]} · Распознанные телефоны: {d["unique_phones"]}.'),p(f'Средний бюджет: {money(d["budget_mean"])}.'),PageBreak()]
    story += [p('Бюджеты без догадок','title'),p(dates(w),'muted'),heading('Два разных показателя'),p(f'Основной средний бюджет: {money(w["budget_mean"])}. Включает нули; пропуски и ошибки исключены.'),p(f'Среднее только по положительным бюджетам: {money(w["budget_positive_mean"])}. Это отдельный показатель, не замена основному.'),heading('Полнота данных · 7 дней')]
    story += [Bars([('Положительный бюджет',w['budget_positive']),('Явно указан ноль',w['budget_zero']),('Бюджет не указан',w['budget_missing']),('Некорректное значение',w['budget_invalid'])]),heading('Распределение бюджетов · весь файл'),Bars(list(report['budget_distribution'].items())),p('Границы: «До 10 млн» — больше нуля и меньше 10 млн; «10–15 млн» — от 10 млн включительно до 15 млн; «От 15 млн» — от 15 млн включительно.','muted'),p('Бюджет в заявке — намерение клиента. Данных о сделках, выручке, рекламных расходах и конверсии в этой выгрузке нет.'),PageBreak()]
    story += [p('Что проверить в CRM','title'),p(f'Весь файл: {report["row_count"]} строк. Одна строка может иметь несколько замечаний.','muted')]
    for item in insights(report): story.append(p('• '+item))
    story.append(heading('Проверяемые записи'))
    for key,count in report['quality'].items():
        ids=[str(r['id']) for r in report['rows'] if key in r['issues']]
        story.append(p(f'{LABELS.get(key,"Другое замечание")}: {count}. № записи: '+', '.join(ids[:12])+(' … Полный перечень в таблице.' if len(ids)>12 else '.')))
    story += [heading('Гипотеза дублей — отдельный сценарий'),p(f'Если оставить первую строку каждого полного совпадения: за 7 дней {report["alternative"]["week"]["count"]} заявок, средний бюджет {money(report["alternative"]["week"]["budget_mean"])}. Основной результат: {w["count"]} заявок. Автоматическое удаление не выполнялось.')]
    for group in report['duplicate_groups'][:5]:story.append(p('Возможное совпадение · № записи: '+', '.join(map(str,group[:12]))+(' …' if len(group)>12 else '')))
    if len(report['duplicate_groups'])>5:story.append(p('Остальные группы отмечены в таблице данных.','muted'))
    story += [heading('Как читать отчёт'),p('День — последняя корректная дата файла. Неделя — эта дата и шесть предыдущих дней. Некорректные даты исключаются только из временных показателей. Замечания и распределение бюджетов относятся ко всему файлу. Имена сами по себе не используются для удаления дублей.','muted'),p(f'Методика расчётов: {report["methodology_version"]}. Исходные строки сохранены. Содержательные выводы — детерминированные правила, без генерации фактов нейросетью.','muted')]
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return stream.getvalue()

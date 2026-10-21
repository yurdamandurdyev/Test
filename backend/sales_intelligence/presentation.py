"""Human-facing views only. Never normalize, filter or deduplicate input here."""
from __future__ import annotations
import csv
import html
import io
import re
from datetime import date
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from .analytics import safe_cell

LABELS = {'invalid_date': 'Некорректная дата', 'invalid_phone': 'Телефон не распознан',
          'missing_name': 'Не указано имя', 'budget_missing': 'Бюджет не указан',
          'budget_zero': 'Указан нулевой бюджет', 'budget_invalid': 'Бюджет записан некорректно',
          'missing_source': 'Источник не указан', 'unknown_source': 'Источник вне справочника',
          'potential_duplicate': 'Возможное повторение записи'}
ACTIONS = ('overview', 'sources', 'budgets', 'quality', 'pdf', 'csv')
WELCOME = ('<b>Signal · Аналитика отдела продаж</b>\n\n'
           'Отправьте выгрузку лидов — покажу объём обращений, бюджеты и записи, которые стоит проверить. '
           'Подробности и PDF откроются кнопками под отчётом.\n\n'
           '📎 Прикрепите CSV как <b>файл</b>, до 2 МБ.\n'
           'Столбцы: дата, имя, телефон, источник, бюджет. При экспорте выберите CSV UTF-8 с разделителем «запятая».\n\n'
           'Кнопки работают <b>1 час</b> и только для вас. Ссылка на файл хранится временно; '
           'сам файл и ответы остаются в вашем чате Telegram.')


def plain(value, limit=80):
    return ' '.join(str(value).split())[:limit]


def escape(value, limit=80):
    return html.escape(plain(value, limit))


def money(value):
    if value is None:
        return 'нет данных'
    return f'{value:,.2f}'.replace(',', '\u202f').replace('.', ',').removesuffix(',00') + ' ₽'


def dates(period):
    def fmt(s): return date.fromisoformat(s).strftime('%d.%m.%Y')
    return f'{fmt(period["start"])} — {fmt(period["end"])}'


def source_items(period, limit=8):
    items = sorted(period['sources'].items(), key=lambda x: (-x[1], x[0]))
    top = [(plain(k, 60), v) for k,v in items[:limit]]
    if len(items) > limit:
        top.append(('Остальные источники (суммарно)', sum(v for _,v in items[limit:])))
    return top


def insights(report):
    q = report['quality']; result = []
    if report['duplicate_groups']:
        groups = report['duplicate_groups']
        result.append(f'Группы возможных дублей: {len(groups)}; отмеченных строк: {sum(map(len, groups))}. Совпали дата, имя, нормализованный телефон, источник и бюджет. Записи не удалены.')
    if q.get('budget_missing') or q.get('budget_invalid'):
        result.append(f'Уточните бюджет. Строк без бюджета: {q.get("budget_missing", 0)}; с некорректным значением: {q.get("budget_invalid", 0)}. Они исключены из среднего, но сохранены в реестре.')
    if q.get('budget_zero'):
        result.append(f'Записи с нулевым бюджетом: {q["budget_zero"]}. Проверьте их: это записанные нули, а не пропуски. Они входят в средний бюджет.')
    if q.get('invalid_phone'):
        result.append(f'Уточните телефоны в {q["invalid_phone"]} строках: эти записи не участвуют в подсчёте уникальных распознанных телефонов.')
    if q.get('invalid_date'):
        result.append(f'Исправьте даты в {q["invalid_date"]} строках: они сохранены в файле, но исключены из временных показателей.')
    if report['repeat_contacts']:
        result.append(f'Повторные обращения в разные даты: {len(report["repeat_contacts"])} групп по телефону. Это не основание удалять заявки.')
    if not result:
        result.append('По проверяемым правилам критичных замечаний не найдено. Это не подтверждение достоверности исходных сведений.')
    return result


def view(report, section='overview'):
    w,d = report['week'],report['day']
    title = {'overview':'Общая аналитика','sources':'Источники заявок','budgets':'Бюджеты','quality':'Что проверить в данных'}[section]
    lines = [f'<b>{title}</b>', dates(w), '']
    if section == 'overview':
        lines += [f'📥 Заявки за 7 дней: <b>{w["count"]}</b> · за последний день: <b>{d["count"]}</b>',
                  f'👥 Разных распознанных телефонов: <b>{w["unique_phones"]}</b>',
                  f'💰 Средний бюджет: <b>{money(w["budget_mean"])}</b>',
                  f'Расчёт по {w["budget_known"]} значениям, включая {w["budget_zero"]} нулевых.', '', '<b>Основные источники · 7 дней</b>']
        lines += [f'{escape(k)} — <b>{v}</b>' for k,v in source_items(w,3)]
        affected = sum(bool(r['issues']) for r in report['rows'])
        lines += ['',f'🔎 Есть замечания: <b>{affected} из {report["row_count"]} строк файла</b>.',
                  'Телефоны — приближение к числу контактов, не подтверждённые люди.',
                  'Ничего не удалено. Подробности и файлы — ниже.']
    elif section == 'sources':
        lines += ['<b>Последние 7 дней</b>']
        lines += [f'{escape(k)} — <b>{v}</b> · {v/w["count"]*100:.1f}%' for k,v in source_items(w)] if w['count'] else ['Нет заявок.']
        lines += ['', '<b>Последний день</b>']
        lines += [f'{escape(k)} — {v}' for k,v in source_items(d,5)]
        lines += ['', 'Это объём обращений. Без расходов, сделок и статусов нельзя оценить эффективность рекламы или конверсию.']
    elif section == 'budgets':
        lines += [f'<b>Средний · 7 дней:</b> {money(w["budget_mean"])}',
                  f'<b>Только положительные · 7 дней:</b> {money(w["budget_positive_mean"])}',
                  f'<b>Средний · последний день:</b> {money(d["budget_mean"])}','',
                  f'За 7 дней: положительных {w["budget_positive"]}, нулевых {w["budget_zero"]}, без бюджета {w["budget_missing"]}, некорректных {w["budget_invalid"]}.',
                  '', '<b>Распределение · весь файл</b>']
        lines += [f'{escape(k)} — {v}' for k,v in report['budget_distribution'].items()]
        lines += ['', 'Нули входят в основное среднее. Пропуски и ошибки исключены. Бюджет заявки не равен выручке.']
    else:
        lines += ['<b>Замечания · весь файл</b>']
        lines += [f'{LABELS.get(k,"Другое замечание")} — <b>{v}</b>' for k,v in report['quality'].items()]
        lines += ['',f'Групп возможных дублей: <b>{len(report["duplicate_groups"])}</b>.']
        for group in report['duplicate_groups'][:3]:
            lines.append('Строки реестра: ' + ', '.join(map(str,group[:12])) + ('…' if len(group)>12 else ''))
        lines += ['Совпали дата, имя, телефон после нормализации, источник и бюджет. Это гипотеза, не доказанный дубль.',
                  '',f'<b>Альтернативный сценарий · 7 дней:</b> {report["alternative"]["week"]["count"]} заявок, средний {money(report["alternative"]["week"]["budget_mean"])}.',
                  'Только если оставить первую запись каждого полного совпадения. Основная сводка не меняется.',
                  f'Повторные обращения по телефону в разные даты: {len(report["repeat_contacts"])} групп по всему файлу. Они сохранены.',
                  '', 'Проверьте отмеченные строки в таблице перед исправлением CRM. У одной строки может быть несколько замечаний.']
    result = '\n'.join(lines)
    visible = html.unescape(re.sub(r'<[^>]*>', '', result))
    assert len(visible.encode('utf-16-le')) // 2 < 4000
    return result


def keyboard(report_id):
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f'r:{report_id}:{action}') for label,action in row] for row in [
        [('Обзор','overview'),('Источники','sources')], [('Бюджеты','budgets'),('Качество и дубли','quality')],
        [('↓ Отчёт PDF','pdf'),('↓ Таблица CSV','csv')]]])


def human_csv(report):
    out = io.StringIO(newline=''); writer=csv.writer(out)
    writer.writerow(['№ записи','Дата','Имя','Телефон','Источник','Бюджет, ₽','Что проверить'])
    for r in report['rows']:
        writer.writerow([safe_cell(v) for v in [r['id'],r['date'] or r['raw'].get('дата',''),r['name'],r['phone'] or r['raw'].get('телефон',''),r['source'],r['budget_exact'] if r['budget_exact'] is not None else r['raw'].get('бюджет',''),'; '.join(LABELS.get(i,'Другое замечание') for i in r['issues'])]])
    return ('\ufeff'+out.getvalue()).encode('utf-8')

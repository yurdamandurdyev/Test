#!/usr/bin/env python3
"""Compute before redaction; never normalize masked contact labels as input phones."""
import argparse
import copy
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from sales_intelligence.analytics import analyze
from sales_intelligence.calls import score_calls

def redact(report):
    result = copy.deepcopy(report)
    contacts = {}
    for row in result['rows']:
        phone = row['phone']
        key = phone or row['raw'].get('телефон', '')
        contacts.setdefault(key, f'Контакт {len(contacts) + 1:02d}')
        row['phone'] = contacts[key] if phone else None
        row['raw']['телефон'] = contacts[key] if key else ''
    for group in result['repeat_contacts']:
        group['phone'] = contacts[group['phone']]
    result['notes'].append('Контакты маскированы после расчёта. Метрики и связи записей сохранены; экспорт не является исходным CSV для повторного анализа.')
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('csv', type=Path)
    parser.add_argument('annotations', type=Path)
    args = parser.parse_args()
    out = Path(__file__).resolve().parents[1] / 'backend/sales_intelligence/demo'
    out.mkdir(exist_ok=True)
    reports = {'leads': redact(analyze(args.csv.read_bytes())), 'calls': score_calls(json.loads(args.annotations.read_text()))}
    for name, report in reports.items():
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if re.search(r'(?<!\d)(?:\+7|8)\d{10}(?!\d)', text):
            raise SystemExit('Unmasked contact detected; publication blocked')
        (out / f'{name}.json').write_text(text, encoding='utf-8')

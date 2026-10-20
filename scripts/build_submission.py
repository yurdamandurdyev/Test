#!/usr/bin/env python3
"""Package private handoff separately from the public source tree."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('--inputs', type=Path, required=True)
p.add_argument('--results', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
if root == a.out.resolve() or root in a.out.resolve().parents:
    raise SystemExit('Private submission must be OUTSIDE the public repository.')
a.out.mkdir(parents=True, exist_ok=True)
for name in ['01-calls', '02-crm/results', '03-knowledge', '04-report', 'inputs', 'source']:
    (a.out / name).mkdir(parents=True, exist_ok=True)
for name in ['calls-report.html', 'calls-scores.csv', 'calls-report.json', 'calls-annotations.json']:
    shutil.copy2(a.results / name, a.out / '01-calls' / name)
for name in ['leads-report.json', 'leads-summary.txt', 'leads-normalized.csv']:
    shutil.copy2(a.results / name, a.out / '02-crm/results' / name)
shutil.copy2(root / 'deliverables/02-analyze-leads.py', a.out / '02-crm/analyze_leads.py')
(a.out / '02-crm/START-HERE.md').write_text('''# Запуск без опыта программирования

Установите Python 3.12+ с python.org (Windows: отметьте Add Python to PATH).
Откройте терминал в этой папке и выполните:

```bash
python analyze_leads.py "../inputs/лиды.csv" --out results
```

На Windows можно использовать `py`, на macOS — `python3` вместо `python`.
Это один самостоятельный скрипт: pip, сервер и npm не нужны.

В results уже лежит фактический результат запуска на оригинальном файле.
leads-summary.txt — читаемый отчёт; leads-report.json — полный расчёт;
leads-normalized.csv — записи и замечания, с защитой от формул в таблицах.
Повторный запуск обновляет эти выходные файлы, исходный CSV не меняет.
При ошибке вы увидите причину; код завершения 2. При успехе код 0.

День — последняя дата файла, неделя — она и шесть предыдущих дней.
Нули включены в среднее, пропуски нет. Возможные дубли сохранены,
альтернативные результаты показаны отдельно. Подробности: ../source/docs/AUDIT.md.

Не публикуйте входной CSV и results: они содержат персональные данные.
''', encoding='utf-8')
for src, dest in [('03-knowledge.html', 'knowledge.html'), ('03-knowledge.pdf', 'knowledge.pdf')]:
    shutil.copy2(root / 'deliverables' / src, a.out / '03-knowledge' / dest)
shutil.copy2(root / 'deliverables/04-report.html', a.out / '04-report/report.html')
for file in a.inputs.iterdir():
    if file.is_file(): shutil.copy2(file, a.out / 'inputs' / file.name)
shutil.copy2(a.results / 'source-manifest.json', a.out / 'inputs/source-manifest.json')
files = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=root).decode().split('\0')
for name in set(files):
    if not name: continue
    source = root / name
    if not source.is_file(): continue
    target = a.out / 'source' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
(a.out / 'START-HERE.md').write_text('''# Sales Intelligence — приватный комплект

Этот комплект содержит оригинальные CRM-данные. Передавайте его только уполномоченному получателю. Не размещайте архив в публичном репозитории или открытой папке.

1. Звонки: `01-calls/calls-report.html` открывается без сети. Таблица всех критериев — `calls-scores.csv`.
2. CRM: инструкция `02-crm/START-HERE.md`, скрипт `analyze_leads.py`, фактические результаты в `results`.
3. Памятка: `03-knowledge/knowledge.pdf` — одна A4; HTML рядом.
4. Отчёт: `04-report/report.html`. Время и ссылку на чат заполните своими фактическими данными.
5. Веб-продукт и бот: `source/README.md`. Аудит и методика — `source/docs/AUDIT.md`, результаты проверок — `source/docs/QA.md`, история — `source/docs/WORK_LOG.md`.

Публично безопасен только source, прошедший целевую проверку: в нём нет исходных контактов и расшифровок. Public demo использует отдельно обозначенные синтетические данные.

Токен Telegram и доступ Vercel не были предоставлены. Где их безопасно настроить и как выполнить live-проверки, описано в README. Секреты в чат не отправляйте.
''', encoding='utf-8')
shutil.make_archive(str(a.out.parent / 'sales-intelligence-private'), 'zip', a.out)
shutil.make_archive(str(a.out.parent / 'sales-intelligence-source'), 'zip', a.out / 'source')
print('Created private submission and separate public-safe source archives.')

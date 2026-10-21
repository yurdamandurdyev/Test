# Signal — Sales Intelligence Platform

Рабочий React-продукт для аналитики лидов, разбора звонков и обучения. Python-ядро общее для CLI, API и Telegram. Никаких LLM-ключей для расчётов.

## Что находится в проекте

| Часть | Реализация |
|---|---|
| Overview | Периоды, источники, динамика и замечания по данным |
| CRM Analytics | Загрузка CSV, пересчёт, фильтры, пагинация, качество, возможные дубли, повторы, JSON/CSV-экспорт |
| Call Intelligence | Общедоступные расшифровки задания, критерии, цитаты, оценки и рекомендации из проверенных аннотаций |
| Knowledge Base | Одностраничная памятка, открытая методология |
| Telegram | Личный чат, интерактивная сводка, PDF, русская таблица, Redis-состояние с TTL |
| Публичное демо | Все 8 лидов и 5 звонков задания; телефоны маскированы после расчёта |

Фактические результаты проверок и ограничения: [docs/QA.md](docs/QA.md).
Методика: [AUDIT.md](docs/AUDIT.md), решения: [ARCHITECTURE.md](docs/ARCHITECTURE.md), источники проверки лекции: [FACT_CHECK.md](docs/FACT_CHECK.md), журнал работы: [WORK_LOG.md](docs/WORK_LOG.md).

## Четыре обязательных результата

Приватный комплект сдачи создаётся отдельно от публичного репозитория:

| Задание | Файлы в комплекте |
|---|---|
| 1 · Звонки | `01-calls/calls-report.html`, `calls-scores.csv`, `calls-report.json`, `calls-annotations.json` |
| 2 · Лиды | `02-crm/analyze_leads.py`, `START-HERE.md`, `results/leads-summary.txt`, `leads-report.json`, `leads-normalized.csv` |
| 3 · Памятка | `03-knowledge/knowledge.html` и `knowledge.pdf` — одна A4 |
| 4 · Отчёт | `04-report/report.html` — время и ссылка на чат оставлены для заполнения |

Публичные независимые файлы: `deliverables/02-analyze-leads.py`, `03-knowledge.html`, `03-knowledge.pdf`, `04-report.html`. Публичный JSON содержит результаты задания с маскированными контактами; исходный CSV с телефонами в Git не включён. В этой рабочей среде они лежат в `/workspace/private-results`, оригиналы — `/workspace/private-inputs`, общий комплект — `/workspace/submission`.

Для задачи 2 достаточно Python 3.12+, без npm, сервера и pip:

```bash
python deliverables/02-analyze-leads.py "/путь/к/лиды.csv" --out artifacts
```

Это сгенерированная автономная сборка того же ядра, не независимая реализация формул. После изменения ядра обновляйте её командой `python scripts/build_standalone.py`; тест проверяет совпадение результата. Полная инструкция новичку: [docs/BEGINNER.md](docs/BEGINNER.md).

## Локальная разработка

Нужны Node.js 24, Python 3.12+, npm и uv 0.12.23. Работайте в существующем checkout; отдельный git worktree не требуется.

```bash
python -m pip install uv==0.12.23
uv sync --frozen --extra test
npm ci
python scripts/init_local.py
```

`init_local.py` создаёт игнорируемый `.env` со случайными локальными паролем и ключом сессии, не выводя их. Существующий файл не перезаписывает. Откройте `.env` в редакторе: `APP_PASSWORD` — пароль входа в веб-интерфейс. Не пересылайте `.env` и не добавляйте его в Git.

В первом терминале:

```bash
.venv/bin/python scripts/run_local.py api
```

Во втором:

```bash
npm run dev
```

Откройте в браузере адрес, указанный Vite (обычно `http://localhost:5173`). В Windows замените `.venv/bin/python` на `.venv\Scripts\python.exe`. API слушает только loopback на порту 8000; Vite проксирует запросы с того же origin. Публичный деморежим работает и без `.env`; загрузка своей CRM требует входа.

### Звонки и демонстрационные данные

Пять исходных звонков доступны без входа через `/api/demo/calls`. CRM `/api/demo` содержит восемь исходных записей; контакты заменены стабильными метками после нормализации и расчётов. `/api/demo.csv` — маскированный экспорт результата, не исходник для повторного расчёта. Связи дублей и повторных обращений сохранены. Приватный `/api/calls` остаётся закрытым API для отдельно подключённых аннотаций; публичный интерфейс показывает набор задания.

Для воспроизводимой пересборки безопасного набора:

```bash
.venv/bin/python scripts/build_public_demo.py /private/лиды.csv /private/calls-annotations.json
```


## Telegram

Интерактивный аналитический ассистент: `/start` → CSV → компактная сводка. Inline-кнопки открывают источники, бюджеты, качество и дубли; скачивают PDF для руководителя и таблицу с русскими замечаниями. Кнопки действуют один час, только для владельца. Выгрузка хранится в Telegram; Redis хранит временную ссылку и служебные отметки.

Рабочая инфраструктура — Vercel webhook + существующий Upstash Redis. Новые сервисы и секреты не нужны. После обновления кода **повторите регистрацию webhook**, чтобы добавить `callback_query`:

```bash
.venv/bin/python scripts/telegram_setup.py register
.venv/bin/python scripts/telegram_setup.py status
```

Секреты должны быть доступны процессу через защищённое окружение; скрипт не читает их из аргументов и не печатает. `status` должен показать `Callback delivery enabled: True`. Polling для локальной разработки использует тот же обработчик и Redis: `.venv/bin/python scripts/run_local.py bot`. Не запускайте его одновременно с webhook.

[Устройство ассистента, TTL, пределы повторной доставки и сценарий приёмки](docs/TELEGRAM_ASSISTANT.md).

## Vercel: веб и API

Готовы `vercel.json`, ASGI entrypoint `api/index.py`, `requirements.txt` с хешами, Vite production build. Хеш-навигация не требует универсального SPA-rewrite; `/api/*` направляется в Python-функцию.

1. Исходники опубликованы в [yurdamandurdyev/Test](https://github.com/yurdamandurdyev/Test), ветка `main`. Импортируйте этот репозиторий. При переносе публикуйте **только содержимое проекта**: без приватного комплекта сдачи, `.env`, оригиналов и результатов.
2. В Vercel выберите **Add New → Project → Import Git Repository**. Root Directory — корень проекта; framework Vite, Node 24, build `npm run build`, output `dist`. Настройки берутся из `vercel.json`.
3. Для публичного демо оставьте `APP_PASSWORD`, `SESSION_SECRET` и `CALLS_ANNOTATIONS_*` незаданными. Демо открывается, приватные API закрыты.
4. Для закрытой работы задайте через Vercel Environment Variables случайные `APP_PASSWORD` (≥16 символов), `SESSION_SECRET` (≥32), `COOKIE_SECURE=true`. Не используйте префикс `VITE_`: он предназначен для клиентских переменных. Включите защиту проекта / rate limit `/api/login` в Vercel Firewall до работы с CRM. In-memory лимитер не даёт глобальных гарантий в serverless.
5. Оригинальные демонстрационные звонки уже включены в безопасный публичный набор; дополнительные переменные для них не нужны.
6. Выполните Deploy. После деплоя проверьте `/api/health` (status ok), демо, отказ `/api/calls` без входа, login, загрузку нового CSV и экспорт. Локальные проверки не заменяют этот шаг.
7. Свой домен подключается через Project → Settings → Domains; примените DNS-записи, которые покажет Vercel.

В текущей сессии нет `VERCEL_TOKEN`, project/org binding или доступной интеграции Vercel. Публичный URL не создан. Git-доступ не предоставляет учётные данные Vercel. Публикация пользователем разрешена, но технический доступ пока не настроен.

## Тесты

```bash
uv sync --frozen --extra test
npm ci
python scripts/build_standalone.py
.venv/bin/pytest -q
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

На машине с готовым Chromium можно не скачивать браузер:

```bash
CHROMIUM_PATH=/usr/bin/chromium npm run test:e2e
```

Для дополнительного браузерного теста оригинальных приватных звонков:

```bash
CHROMIUM_PATH=/usr/bin/chromium CALLS_ANNOTATIONS_PATH=/workspace/private-results/calls-annotations.json npm run test:e2e
```

По умолчанию этот один тест явно пропускается без приватного набора, остальные выполняются на синтетических fixtures. Тестовые пароли в `playwright.config.ts` и тестах — публичные фикстуры, не рабочие секреты. Не используйте их в deployment.

Офлайн-рендер и PDF:

```bash
CHROMIUM_PATH=/usr/bin/chromium node scripts/check_offline.mjs artifacts "/путь/calls-report.html"
```

Сеть у браузера выключена. Скрипт подаёт точные HTML-байты через `setContent`, поскольку управляемый браузер этой среды запрещает file://. Факт двойного щелчка на обычном пользовательском компьютере отдельно не утверждается.

Проверка приватности перед публикацией:

```bash
python scripts/security_check.py --private-csv "/путь/лиды.csv" --private-calls "/путь/звонки.txt"
npm audit
uvx pip-audit -r requirements.txt --no-deps --disable-pip
```

Сканер ищет известные персональные данные из оригиналов и форматы токенов, не печатая совпадения. Это целевая проверка, не универсальная гарантия отсутствия всех секретов.

## Структура

```text
backend/sales_intelligence/  analytics, calls, API, Telegram
web/src/                    React, типы, представление, график, стили
api/index.py                Vercel ASGI entrypoint
scripts/                    CLI, сборка артефактов, запуск, проверки
tests/                      Python + Playwright; Vitest рядом с lib.ts
deliverables/               публично безопасные автономные материалы
docs/                       аудит, архитектура, факты, QA и история
public/                     памятка и методология, без CRM и расшифровок
```

Система не хранит историю CRM, не создаёт ссылки на несохранённые отчёты, не предсказывает конверсию и не оценивает сотрудников по вымышленным данным. Добавление аккаунтов, базы, истории и LLM-рекомендаций — отдельные расширения с собственным основанием и моделью доступа.

## Бесплатная демонстрация: Vercel + webhook

Пошаговый запуск и ручная приёмка: [docs/FREE_DEPLOY.md](docs/FREE_DEPLOY.md). Платный Render worker исключён по новой инструкции. Polling сохранён для локальной разработки; на Vercel используйте `/api/telegram/webhook` и бесплатный Redis для распределённых блокировок. Не запускайте оба режима одновременно.

Обновлённая самостоятельная памятка: [HTML](public/knowledge.html), [PDF A4](public/knowledge.pdf). Приватный архив предыдущей сдачи не пересобирался.

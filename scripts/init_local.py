#!/usr/bin/env python3
"""Create local-only secrets without displaying them or overwriting user configuration."""
import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / ".env"
if path.exists():
    print(".env уже существует; оставлен без изменений.")
else:
    text = (
        f"APP_PASSWORD={secrets.token_urlsafe(24)}\n"
        f"SESSION_SECRET={secrets.token_urlsafe(48)}\n"
        "COOKIE_SECURE=false\n"
        "CALLS_ANNOTATIONS_PATH=\n"
        "TELEGRAM_BOT_TOKEN=\n"
        "TELEGRAM_ALLOWED_USER_IDS=\n"
    )
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as file:
        file.write(text)
    print("Создан локальный .env с правами 0600. Посмотрите APP_PASSWORD в редакторе; не публикуйте файл.")

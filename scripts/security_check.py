#!/usr/bin/env python3
"""Scan publishable files for known private inputs and token formats; never print matches."""
import argparse
import csv
import re
import os
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--private-csv", type=Path)
parser.add_argument("--private-calls", type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
names = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root).decode().split("\0")
paths = {root / n for n in names if n}
paths.update(p for p in (root / "dist").rglob("*") if p.is_file())
needles: set[str] = set()
if args.private_csv:
    with args.private_csv.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            needles.update((row["телефон"], re.sub(r"\D", "", row["телефон"])))
env_file = root / '.env'
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            if key in {'APP_PASSWORD', 'SESSION_SECRET', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_WEBHOOK_SECRET', 'UPSTASH_REDIS_REST_TOKEN'} and value:
                needles.add(value)
for key in ('APP_PASSWORD', 'SESSION_SECRET', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_WEBHOOK_SECRET', 'UPSTASH_REDIS_REST_TOKEN', 'VERCEL_TOKEN'):
    if os.getenv(key): needles.add(os.environ[key])
errors = []
for path in paths:
    if not path.is_file():
        continue
    relative = path.relative_to(root)
    if path.name.startswith(".env") and path.name != ".env.example":
        errors.append((str(relative), "environment file")); continue
    if any(p in relative.parts for p in ("private", "artifacts", "test-results", "playwright-report")):
        errors.append((str(relative), "private directory")); continue
    try: text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError: continue
    if any(n and n in text for n in needles):
        errors.append((str(relative), "known personal data"))
    if re.search(r"\b\d{8,12}:[A-Za-z0-9_-]{30,50}\b", text) or re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", text):
        errors.append((str(relative), "credential pattern"))
if errors:
    for path, kind in errors: print(f"BLOCKED: {path}: {kind}; content redacted")
    raise SystemExit(1)
print(f"PASS: {len(paths)} publishable files scanned; no known input PII or credential patterns. Not a universal secret detector.")

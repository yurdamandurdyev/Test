#!/usr/bin/env python3
"""Load the local .env without shell evaluation; launch API or Telegram worker."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("service", choices=["api", "bot"], default="api", nargs="?")
args = parser.parse_args()
config = root / ".env"
if config.exists():
    for line in config.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
os.environ["PYTHONPATH"] = str(root / "backend")
command = [sys.executable, "-m", "sales_intelligence.bot"] if args.service == "bot" else [sys.executable, "-m", "uvicorn", "sales_intelligence.api:app", "--host", "127.0.0.1", "--port", "8000"]
raise SystemExit(subprocess.call(command, cwd=root))

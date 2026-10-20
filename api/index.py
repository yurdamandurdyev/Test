"""Vercel ASGI entrypoint. No polling or filesystem writes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sales_intelligence.api import app

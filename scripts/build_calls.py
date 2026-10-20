#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sales_intelligence.calls import export_bundle

parser = argparse.ArgumentParser(description="Сборка офлайн-отчёта из проверенных аннотаций")
parser.add_argument("annotations", type=Path)
parser.add_argument("--out", type=Path, default=Path("artifacts"))
args = parser.parse_args()
export_bundle(json.loads(args.annotations.read_text(encoding="utf-8")), args.out)

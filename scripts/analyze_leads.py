#!/usr/bin/env python3
"""Standalone standard-library CLI; installation is not required."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sales_intelligence.analytics import InputError, analyze, export_csv, summary_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Сводка лидов: день и последние 7 дней")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--out", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    try:
        from sales_intelligence.analytics import MAX_BYTES
        with args.csv.open("rb") as f:
            report = analyze(f.read(MAX_BYTES + 1))
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "leads-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.out / "leads-summary.txt").write_text(summary_text(report), encoding="utf-8")
        (args.out / "leads-normalized.csv").write_bytes(export_csv(report))
        print(summary_text(report))
        return 0
    except (InputError, OSError) as exc:
        print(f"Не удалось обработать файл: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

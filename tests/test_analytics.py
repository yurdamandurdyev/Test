import csv
import io
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
import pytest
from sales_intelligence.analytics import InputError, MAX_BYTES, analyze, budget, export_csv, parse_date, phone, safe_cell

HEADER = "дата,имя,телефон,источник,бюджет\n"

def test_reference_totals(csv_data):
    r = analyze(csv_data)
    assert r["day"]["count"] == 3
    assert r["week"]["count"] == 8
    assert r["week"]["start"] == "2026-10-13"
    assert r["day"]["budget_mean"] == 8_000_000
    assert r["week"]["budget_mean"] == 6_916_666.67
    assert r["week"]["budget_positive_mean"] == 10_375_000
    assert r["week"]["sources"] == {"Авито": 3, "Сайт": 1, "Сарафан": 1, "Яндекс": 3}
    assert r["alternative"]["day"]["budget_mean"] == 6_000_000
    assert r["alternative"]["week"]["budget_mean"] == 5_900_000
    assert r["alternative"]["excluded_row_ids"] == [2]
    assert r["duplicate_groups"] == [[1, 2]]
    assert r["repeat_contacts"][0]["row_ids"] == [3, 8]
    assert r["row_count"] == 8
    assert sum(d["count"] for d in r["timeline"]) == 8

@pytest.mark.parametrize("value,valid", [("2024-02-29", True), ("29.02.2025", False), ("2026-13-01", False), ("1.2.2026", False), ("2026-10-19T00:00", False), ("", False)])
def test_date_rules(value, valid):
    assert (parse_date(value) is not None) == valid

@pytest.mark.parametrize("value,result,status", [("", None, "missing"), ("0", Decimal(0), "zero"), ("12 000,50", Decimal("12000.50"), "positive"), ("-1", None, "invalid"), ("NaN", None, "invalid"), ("inf", None, "invalid"), ("1e9", None, "invalid"), ("=1+1", None, "invalid"), ("1.001", None, "invalid")])
def test_budget_rules(value, result, status):
    assert budget(value) == (result, status)

def test_week_boundaries_and_invalid_dates():
    r = analyze((HEADER + "2026-10-19,A,+70000000001,сайт,10\n2026-10-13,A,+70000000002,сайт,20\n2026-10-12,A,+70000000003,сайт,30\n31.02.2026,A,+70000000004,сайт,40\n").encode())
    assert r["week"]["count"] == 2
    assert r["row_count"] == 4
    assert r["quality"]["invalid_date"] == 1
    assert r["rows"][3]["raw"]["дата"] == "31.02.2026"

def test_decimal_rounding_and_numeric_duplicate():
    r = analyze((HEADER + '2026-10-19,A,+70000000001,сайт,12.00\n2026-10-19,A,+70000000001,сайт,12\n').encode())
    assert r["duplicate_groups"] == [[1, 2]]
    r = analyze((HEADER + '2026-10-19,A,+70000000001,сайт,0.01\n2026-10-19,B,+70000000002,сайт,0.02\n').encode())
    assert r["day"]["budget_mean"] == 0.02

def test_same_names_not_deleted():
    r = analyze((HEADER + '2026-10-19,A,+70000000001,сайт,12\n2026-10-19,A,+70000000002,сайт,12\n').encode())
    assert not r["duplicate_groups"]
    assert r["alternative"]["day"]["count"] == 2

@pytest.mark.parametrize("payload", [b"", b"\xff", b"a,b\n1,2", b"\0", (HEADER + "2026-10-19,A").encode(), HEADER.encode(), (HEADER + '2026-10-19,"A,+70000000001,сайт,1').encode(), (HEADER + "never,A,1,сайт,1").encode(), b"x" * (MAX_BYTES + 1)])
def test_rejects_invalid_input(payload):
    with pytest.raises(InputError): analyze(payload)

def test_bom_quoted_fields_unknown_source_and_raw():
    r = analyze(("\ufeff" + HEADER + '2026-10-19," A, B ",not-a-phone,Unknown,"1 200,50"\n').encode())
    assert r["rows"][0]["name"] == "A, B"
    assert r["rows"][0]["raw"]["имя"] == " A, B "
    assert r["day"]["budget_mean"] == 1200.50
    assert r["quality"]["unknown_source"] == 1
    assert r["day"]["unidentified"] == 1

def test_only_missing_budget():
    r = analyze((HEADER + "2026-10-19,A,+70000000001,сайт,\n").encode())
    assert r["day"]["budget_mean"] is None
    assert r["day"]["budget_known"] == 0

@pytest.mark.parametrize("value", ["=HYPERLINK(\"x\")", "+7", "-2", "@SUM(1)", " \t=2", "\ttext", "\rtext"])
def test_formula_escaping(value):
    assert safe_cell(value).startswith("'")

def test_export_and_cli_match(csv_data, tmp_path):
    source = tmp_path / "input.csv"
    source.write_bytes(csv_data)
    p = subprocess.run([sys.executable, "scripts/analyze_leads.py", str(source), "--out", str(tmp_path)], capture_output=True)
    assert p.returncode == 0, p.stderr
    assert json.loads((tmp_path / "leads-report.json").read_text()) == analyze(csv_data)
    lines = list(csv.reader(io.StringIO(export_csv(analyze(csv_data)).decode("utf-8-sig"))))
    assert len(lines) == 9
    assert lines[1][3].startswith("'+7")

def test_cli_failure_exit(tmp_path):
    p = subprocess.run([sys.executable, "scripts/analyze_leads.py", str(tmp_path / "missing")], capture_output=True)
    assert p.returncode == 2

def test_phone():
    assert phone("8 (000) 000-00-01") == "+70000000001"
    assert phone("abc70000000001") is None

def test_limit_rows_and_long_fields():
    with pytest.raises(InputError, match="10 000"):
        analyze((HEADER + "2026-10-19,A,1,сайт,0\n" * 10001).encode())
    with pytest.raises(InputError, match="2 000"):
        analyze((HEADER + f'2026-10-19,{"A"*2001},1,сайт,0\n').encode())

def test_calendar_underflow_is_readable_error():
    with pytest.raises(InputError, match="слишком ранняя"):
        analyze((HEADER + "0001-01-01,A,1,сайт,1\n").encode())

def test_generated_standalone_matches_core(csv_data, tmp_path):
    source = tmp_path / "input.csv"
    source.write_bytes(csv_data)
    completed = subprocess.run([sys.executable, "deliverables/02-analyze-leads.py", str(source), "--out", str(tmp_path)], capture_output=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads((tmp_path / "leads-report.json").read_text()) == analyze(csv_data)

def test_budget_distribution_boundaries():
    values = ["0", "9999999.99", "10000000", "14999999.99", "15000000", "", "-1"]
    data = HEADER + "".join(f"2026-10-19,Test {i},DEMO-{i},сайт,{v}\n" for i, v in enumerate(values))
    r = analyze(data.encode())
    assert r["budget_distribution"] == {"Ноль": 1, "До 10 млн": 1, "10–15 млн": 2, "От 15 млн": 1, "Нет / ошибка": 2}
    assert r["week"]["budget_invalid"] == 1

"""One implementation for CLI, HTTP and Telegram. No LLM or network required."""
from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

VERSION = "1.0"
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 10_000
HEADERS = ("дата", "имя", "телефон", "источник", "бюджет")
SOURCES = {
    "яндекс": "Яндекс", "yandex": "Яндекс", "я.директ": "Яндекс",
    "авито": "Авито", "avito": "Авито", "сайт": "Сайт", "сарафан": "Сарафан",
}


class InputError(ValueError):
    pass


def parse_date(value: str) -> date | None:
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value)
        if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", value):
            d, m, y = map(int, value.split("."))
            return date(y, m, d)
    except ValueError:
        pass
    return None


def phone(value: str) -> str | None:
    if not re.fullmatch(r"\+?[\d ()-]+", value):
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    return None


def budget(value: str) -> tuple[Decimal | None, str]:
    if not value:
        return None, "missing"
    cleaned = value.replace(" ", "").replace("\u00a0", "").replace(",", ".")
    if not re.fullmatch(r"\d{1,12}(?:\.\d{1,2})?", cleaned):
        return None, "invalid"
    try:
        number = Decimal(cleaned)
        return number, "zero" if number == 0 else "positive"
    except InvalidOperation:
        return None, "invalid"


def rounded(value: Decimal) -> float:
    return float(value.quantize(Decimal(".01"), rounding=ROUND_HALF_UP))


def period(rows: list[dict], start: date, end: date) -> dict[str, Any]:
    selected = [r for r in rows if r["date"] and start.isoformat() <= r["date"] <= end.isoformat()]
    values = [Decimal(r["budget_exact"]) for r in selected if r["budget_exact"] is not None]
    positive = [v for v in values if v > 0]
    phones = {r["phone"] for r in selected if r["phone"]}
    return {
        "start": start.isoformat(), "end": end.isoformat(), "count": len(selected),
        "sources": dict(sorted(Counter(r["source"] for r in selected).items())),
        "budget_mean": rounded(sum(values) / len(values)) if values else None,
        "budget_positive_mean": rounded(sum(positive) / len(positive)) if positive else None,
        "budget_known": len(values), "budget_positive": len(positive),
        "budget_missing": sum(r["budget_status"] == "missing" for r in selected),
        "budget_invalid": sum(r["budget_status"] == "invalid" for r in selected),
        "budget_zero": sum(r["budget_status"] == "zero" for r in selected),
        "unique_phones": len(phones),
        "unidentified": sum(not r["phone"] for r in selected),
    }


def analyze(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_BYTES:
        raise InputError("Файл больше 2 МБ. Разделите выгрузку на несколько файлов.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError("Нужен CSV в UTF-8. При экспорте выберите «CSV UTF-8».") from exc
    if "\0" in text:
        raise InputError("Файл содержит нулевые байты и не похож на текстовый CSV.")
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader)
    except (StopIteration, csv.Error) as exc:
        raise InputError("CSV пуст или повреждён.") from exc
    normalized_header = [s.strip().casefold() for s in header]
    if len(normalized_header) != len(HEADERS) or set(normalized_header) != set(HEADERS):
        raise InputError("Нужны ровно пять столбцов: дата,имя,телефон,источник,бюджет. Разделитель — запятая.")
    rows = []
    try:
        for cells in reader:
            if not cells or all(not c.strip() for c in cells):
                continue
            if len(rows) >= MAX_ROWS:
                raise InputError("Максимум 10 000 записей в одном файле.")
            if len(cells) != len(HEADERS):
                raise InputError(f"Строка {reader.line_num}: число полей отличается от заголовка.")
            if any(len(c) > 2000 for c in cells):
                raise InputError(f"Строка {reader.line_num}: поле длиннее 2 000 символов.")
            raw = dict(zip(normalized_header, cells))
            fields = {k: v.strip() for k, v in raw.items()}
            dt, ph = parse_date(fields["дата"]), phone(fields["телефон"])
            amount, status = budget(fields["бюджет"])
            source = SOURCES.get(fields["источник"].casefold(), fields["источник"] or "Не указан")
            issues = []
            if dt is None: issues.append("invalid_date")
            if ph is None: issues.append("invalid_phone")
            if not fields["имя"]: issues.append("missing_name")
            if status in ("missing", "invalid", "zero"): issues.append("budget_" + status)
            if not fields["источник"]: issues.append("missing_source")
            elif fields["источник"].casefold() not in SOURCES: issues.append("unknown_source")
            rows.append({
                "id": len(rows) + 1, "line": reader.line_num, "raw": raw,
                "date": dt.isoformat() if dt else None, "name": fields["имя"],
                "phone": ph, "source": source, "budget": float(amount) if amount is not None else None,
                "budget_exact": str(amount) if amount is not None else None,
                "budget_status": status, "issues": issues,
            })
    except csv.Error as exc:
        raise InputError(f"CSV повреждён около строки {reader.line_num}. Проверьте кавычки.") from exc
    if not rows:
        raise InputError("В CSV есть заголовок, но нет записей.")
    dates = [date.fromisoformat(r["date"]) for r in rows if r["date"]]
    if not dates:
        raise InputError("Нет ни одной корректной даты. Допустимы ДД.ММ.ГГГГ и ГГГГ-ММ-ДД.")
    anchor = max(dates)
    if anchor < date(1, 1, 7):
        raise InputError("Последняя дата слишком ранняя: невозможно построить предыдущие шесть дней в календаре.")
    week_start = anchor - timedelta(days=6)
    fingerprints: dict[tuple, list[int]] = defaultdict(list)
    contacts: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["phone"]:
            contacts[r["phone"]].append(r)
            if r["date"] and r["budget_status"] != "invalid":
                key = (r["date"], r["name"].casefold(), r["phone"], r["source"], Decimal(r["budget_exact"]) if r["budget_exact"] is not None else None)
                fingerprints[key].append(r["id"])
    duplicate_groups = [ids for ids in fingerprints.values() if len(ids) > 1]
    duplicate_ids = {i for ids in duplicate_groups for i in ids}
    omitted = {i for ids in duplicate_groups for i in ids[1:]}
    repeats = [
        {"phone": ph, "row_ids": [r["id"] for r in rs], "dates": sorted({r["date"] for r in rs if r["date"]})}
        for ph, rs in contacts.items() if len({r["date"] for r in rs if r["date"]}) > 1
    ]
    for r in rows:
        if r["id"] in duplicate_ids: r["issues"].append("potential_duplicate")
    deduped = [r for r in rows if r["id"] not in omitted]
    distribution = {"Ноль": 0, "До 10 млн": 0, "10–15 млн": 0, "От 15 млн": 0, "Нет / ошибка": 0}
    for r in rows:
        b = r["budget"]
        label = "Нет / ошибка" if b is None else "Ноль" if b == 0 else "До 10 млн" if b < 10_000_000 else "10–15 млн" if b < 15_000_000 else "От 15 млн"
        distribution[label] += 1
    return {
        "methodology_version": VERSION, "anchor": anchor.isoformat(), "row_count": len(rows),
        "day": period(rows, anchor, anchor), "week": period(rows, week_start, anchor),
        "alternative": {"excluded_row_ids": sorted(omitted), "day": period(deduped, anchor, anchor), "week": period(deduped, week_start, anchor)},
        "quality": dict(sorted(Counter(i for r in rows for i in r["issues"]).items())),
        "duplicate_groups": duplicate_groups, "repeat_contacts": repeats, "rows": rows,
        "timeline": [{"date": (week_start + timedelta(days=i)).isoformat(), "count": sum(r["date"] == (week_start + timedelta(days=i)).isoformat() for r in rows)} for i in range(7)],
        "budget_distribution": distribution,
        "notes": [
            "Основная сводка сохраняет все строки; некорректные даты исключены только из временных агрегатов.",
            "Средний бюджет включает явно указанные нули, исключает пропуски и ошибки; положительное среднее показано отдельно.",
            "Совпадение имени не означает дубль. Группы по телефону — гипотеза, а не подтверждение личности.",
            "Альтернативный сценарий оставляет первую строку каждого полного нормализованного совпадения.",
        ],
    }


def safe_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("\t", "\r", "\n")) or text.lstrip().startswith(("=", "+", "-", "@")) else text


def export_csv(report: dict) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["id", "дата", "имя", "телефон", "источник", "бюджет", "замечания"])
    for r in report["rows"]:
        writer.writerow([safe_cell(v) for v in [r["id"], r["date"], r["name"], r["phone"], r["source"], r["budget_exact"], ";".join(r["issues"])]])
    return ("\ufeff" + stream.getvalue()).encode()


def summary_text(report: dict) -> str:
    lines = ["Сводка по лидам", f"Последняя дата: {report['anchor']} · строк: {report['row_count']}"]
    for label, key in [("День", "day"), ("Неделя", "week")]:
        p = report[key]
        mean = "нет данных" if p["budget_mean"] is None else f"{p['budget_mean']:,.2f} ₽".replace(",", " ")
        positive = "нет данных" if p["budget_positive_mean"] is None else f"{p['budget_positive_mean']:,.2f} ₽".replace(",", " ")
        lines += [f"\n{label}: {p['start']} — {p['end']}", f"Записей: {p['count']}", f"Средний бюджет (с нулями): {mean}", f"Только положительные: {positive}",
                  f"Бюджет: заполнено {p['budget_known']}, нулей {p['budget_zero']}, пропусков {p['budget_missing']}, ошибок {p['budget_invalid']}"]
        sources = list(p["sources"].items())
        lines.append("Источники: " + ", ".join(f"{s[:80]} — {n}" for s, n in sources[:12]))
        if len(sources) > 12: lines.append(f"Ещё источников: {len(sources) - 12}; подробности в файле.")
    lines += [f"\nВозможных групп дублей: {len(report['duplicate_groups'])}. Автоматически не удалены.",
              f"Контактов с обращениями в разные дни: {len(report['repeat_contacts'])}.",
              f"Альтернатива без предполагаемых повторов экспорта: день {report['alternative']['day']['count']}, неделя {report['alternative']['week']['count']}.",
              "Пропуски и ошибки бюджета не включены в среднее; нули включены."]
    return "\n".join(lines)

"""Explicit human-reviewed annotations, deterministic scoring and HTML export."""
import csv
import html
import io
import json
from pathlib import Path

CRITERIA = [
    ("intro", "Приветствие, имя и верный ЖК", 15),
    ("budget", "Выяснен бюджет", 20),
    ("timing", "Выяснен срок покупки", 20),
    ("payment", "Предложен способ оплаты", 15),
    ("meeting", "Назначен показ / встреча", 25),
    ("summary", "Подведён итог", 15),
]


def score_calls(calls: list[dict]) -> dict:
    if not calls:
        return {"calls": [], "average": None, "operational_average": None, "connected": 0, "attempts": 0, "criteria": [], "managers": [], "alternatives": []}
    output = []
    for call in calls:
        if set(call["criteria"]) != {key for key, _, _ in CRITERIA}:
            raise ValueError("Для каждого звонка нужны все шесть критериев")
        if not isinstance(call["connected"], bool):
            raise ValueError("connected должен быть булевым")
        raw = 0
        scored = []
        for key, label, weight in CRITERIA:
            item = call["criteria"][key]
            if type(item["passed"]) is not bool or not item["reason"]:
                raise ValueError("Нужны булева оценка и объяснение")
            if item["passed"] and not item.get("quote"):
                raise ValueError("Для положительной оценки нужна цитата")
            if item.get("quote") and item["quote"] not in call["transcript"]:
                raise ValueError("Цитата отсутствует в расшифровке")
            if not call["connected"] and item["passed"]:
                raise ValueError("Несостоявшийся звонок не может получить баллы")
            points = weight if item["passed"] else 0
            raw += points
            scored.append({"key": key, "label": label, "weight": weight, "points": points, **item})
        output.append({**call, "criteria": scored, "raw_score": raw, "percent": round(raw / 110 * 100, 2) if call["connected"] else None})
    connected = [c for c in output if c["connected"]]
    managers = []
    for name in sorted({c["manager"] for c in connected}):
        selected = [c for c in connected if c["manager"] == name]
        managers.append({"name": name, "count": len(selected), "average": round(sum(c["raw_score"] for c in selected) / len(selected) / 110 * 100, 2)})
    alternatives = []
    total = sum(c["raw_score"] for c in connected)
    for call in connected:
        for scenario in call.get("alternatives", []):
            overrides = scenario["overrides"]
            if not set(overrides) <= {k for k, _, _ in CRITERIA} or any(type(v) is not bool for v in overrides.values()):
                raise ValueError("Некорректный альтернативный сценарий")
            points = sum(c["weight"] if overrides.get(c["key"], c["passed"]) else 0 for c in call["criteria"])
            alternatives.append({
                "call_id": call["id"], "label": scenario["label"], "reason": scenario["reason"],
                "raw_score": points, "percent": round(points / 110 * 100, 2),
                "department_average": round((total - call["raw_score"] + points) / len(connected) / 110 * 100, 2),
            })
    return {
        "calls": output, "attempts": len(output), "connected": len(connected),
        "average": round(sum(c["raw_score"] for c in connected) / len(connected) / 110 * 100, 2) if connected else None,
        "operational_average": round(sum(c["raw_score"] for c in output) / len(output) / 110 * 100, 2),
        "criteria": [{"key": key, "label": label, "weight": weight, "passed": sum(c["criteria"][i]["passed"] for c in connected), "total": len(connected)} for i, (key, label, weight) in enumerate(CRITERIA)],
        "managers": managers,
        "alternatives": alternatives,
    }


def standalone(report: dict) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    cards = []
    for c in report["calls"]:
        rows = "".join(f"<tr><th>{esc(k['label'])}</th><td>{k['points']}/{k['weight']}</td><td>{esc(k['reason'])}<blockquote>{esc(k['quote'] or 'Подтверждающей реплики нет.')}</blockquote></td></tr>" for k in c["criteria"])
        cards.append(f"""<article><h2>Звонок {c['id']} · {esc(c['manager'] or 'Менеджер неизвестен')}</h2>
<p class="score">{c['raw_score']}/110 · {str(c['percent'])+'%' if c['percent'] is not None else 'Не состоялся; вне оценки менеджеров'}</p>
<table><thead><tr><th>Критерий</th><th>Баллы</th><th>Обоснование и реплика</th></tr></thead><tbody>{rows}</tbody></table>
<p><b>Следующий шаг:</b> {esc(c['recommendation'])}</p>
<details><summary>Полная расшифровка</summary><pre>{esc(c['transcript'])}</pre></details></article>""")
    criteria = "".join(f"<li>{esc(c['label'])}: {c['passed']} из {c['total']}</li>" for c in report["criteria"])
    alternatives = "".join(f"<li>Звонок {s['call_id']}: {esc(s['label'])}. {esc(s['reason'])} Балл {s['raw_score']}/110 ({s['percent']}%), отдел {s['department_average']}%.</li>" for s in report["alternatives"])
    return f"""<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Аналитика звонков · Северная Гавань</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#111315;color:#e9e9e8;font:16px/1.6 system-ui,sans-serif}}
main{{max-width:1100px;margin:auto;padding:48px 24px}}.eyebrow{{color:#c3dd99;letter-spacing:3px;font-size:12px}}
h1{{font-size:clamp(32px,5vw,60px);line-height:1.1}}h2{{font-size:24px}}.lede{{color:#bbc0c4;max-width:780px}}
article,section{{border-top:1px solid #373b40;padding:28px 0}}.score{{font-size:24px;color:#c3dd99}}
table{{border-collapse:collapse;width:100%;text-align:left}}td,th{{padding:12px;border-bottom:1px solid #303439;vertical-align:top}}
blockquote{{margin:8px 0;color:#aab2bc;font-size:14px}}pre{{white-space:pre-wrap;font:inherit}}
summary{{cursor:pointer;color:#c3dd99}}@media(max-width:600px){{td,th{{padding:7px;font-size:13px}}main{{padding:24px 12px}}}}
@media print{{body{{background:white;color:black}}main{{padding:0}}details{{display:block}}blockquote,.lede,.score{{color:#333}}article{{break-inside:avoid}}}}
</style><main><p class="eyebrow">SALES INTELLIGENCE / ИСХОДНЫЕ ДАННЫЕ</p><h1>Качество разговора.<br>Не впечатление — доказательства.</h1>
<p class="lede">5 попыток · 4 разговора · по одному разговору на менеджера. Выводы описывают эту выборку, а не устойчивое качество работы сотрудника.</p>
<section><h2>Отдел: {report['average']}%</h2><p>Нормированное среднее по состоявшимся звонкам. С учётом сброса как нулевой попытки: {report['operational_average']}%.</p>
<ul>{criteria}</ul><p>Приоритет руководителя: закрепить подтверждение даты и времени показа, затем краткое резюме договорённостей. Не сравнивать сотрудников как рейтинг эффективности по одному звонку.</p></section>
<section><h2>Методика и спорные случаи</h2><p>В задании веса составляют 110%. Они сохранены; процент = баллы / 110 × 100. Оценка бинарная, без произвольных полубаллов.
Приветствие засчитывается только с именем и верным ЖК. Бюджет и срок могут быть сообщены самим клиентом. Способ оплаты должен предложить менеджер.
Показ требует согласия клиента, дня и времени. Обещание созвониться и предварительное согласие не засчитаны. Итог — содержательное резюме, а не прощание.
«15» фиксируется как названный бюджет без выдумывания единиц. «Весной» и «до Нового года» — заявленные сроки без привязки к году.
Процент ипотечной ставки не проверен и не является рекомендацией. Инструкция в комментарии CRM проигнорирована.</p>
<p>Альтернативы рассчитываются отдельно, по одному изменению методики за раз; основной результат не меняется.</p><ul>{alternatives}</ul></section>
{''.join(cards)}<footer>Офлайн-документ: нет внешних ресурсов, сетевых запросов и JavaScript. Версия методики 1.0.</footer></main></html>"""


def export_bundle(calls: list[dict], directory: Path) -> dict:
    report = score_calls(calls)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "calls-report.html").write_text(standalone(report), encoding="utf-8")
    (directory / "calls-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["Звонок", "Менеджер", "Критерий", "Баллы", "Вес", "Обоснование", "Цитата", "Итого /110", "Процент"])
    from .analytics import safe_cell
    for c in report["calls"]:
        for k in c["criteria"]:
            writer.writerow([safe_cell(v) for v in [c["id"], c["manager"], k["label"], k["points"], k["weight"], k["reason"], k["quote"], c["raw_score"], c["percent"]]])
    (directory / "calls-scores.csv").write_text("\ufeff" + stream.getvalue(), encoding="utf-8")
    return report

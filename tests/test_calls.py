import pytest
from sales_intelligence.calls import CRITERIA, score_calls, standalone

def sample(connected=True):
    return {"id": 1, "manager": "Test", "duration": "1:00", "connected": connected,
            "transcript": '<script>alert("x")</script> evidence', "recommendation": "Test",
            "criteria": {key: {"passed": connected, "quote": "evidence" if connected else "", "reason": "Test"} for key, _, _ in CRITERIA}}

def test_score_110_and_drop():
    a, b = sample(), sample(False)
    r = score_calls([a, b])
    assert r["average"] == 100
    assert r["operational_average"] == 50
    assert r["calls"][0]["raw_score"] == 110
    assert r["calls"][1]["percent"] is None
    assert r["connected"] == 1

def test_evidence_must_exist():
    c = sample()
    c["criteria"]["intro"]["quote"] = "invented"
    with pytest.raises(ValueError, match="Цитата"): score_calls([c])

def test_escape_offline_html():
    html = standalone(score_calls([sample()]))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "src=" not in html
    assert 'href="http' not in html

def test_bool_not_truthy_string():
    c = sample()
    c["criteria"]["intro"]["passed"] = "false"
    with pytest.raises(ValueError): score_calls([c])

def test_alternative_is_independent_from_primary():
    c = sample()
    c["alternatives"] = [{"label": "Different greeting rule", "reason": "Test method", "overrides": {"intro": False}}]
    r = score_calls([c])
    assert r["average"] == 100
    assert r["alternatives"][0]["raw_score"] == 95
    assert r["alternatives"][0]["department_average"] == 86.36

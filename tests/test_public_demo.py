import copy
import importlib.util
import json
import re
from pathlib import Path
from sales_intelligence.api import demo, demo_calls


def test_published_original_metrics_and_no_contacts():
    r = demo()['report']
    assert r['row_count'] == 8
    assert r['day']['count'] == 3
    assert r['day']['budget_mean'] == 8000000
    assert r['week']['budget_mean'] == 6916666.67
    assert r['duplicate_groups'] == [[1, 2]]
    assert r['alternative']['week']['budget_mean'] == 5900000
    assert len(r['repeat_contacts']) == 1
    assert not re.search(r'(?<!\d)(?:\+7|8)\d{10}(?!\d)', json.dumps(r))
    assert len(demo_calls()['calls']) == 5
    assert demo_calls()['operational_average'] == 46.36


def test_redaction_preserves_calculations_and_input(csv_data):
    from sales_intelligence.analytics import analyze
    spec = importlib.util.spec_from_file_location('builder', Path(__file__).parents[1] / 'scripts/build_public_demo.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = analyze(csv_data)
    before = copy.deepcopy(original)
    result = module.redact(original)
    assert original == before
    for key in ('day','week','alternative','quality','duplicate_groups','timeline','budget_distribution','row_count'):
        assert result[key] == original[key]
    for a,b in zip(original['rows'],result['rows']):
        for key in a.keys() - {'phone','raw'}:
            assert a[key] == b[key]
        assert {k:v for k,v in a['raw'].items() if k != 'телефон'} == {k:v for k,v in b['raw'].items() if k != 'телефон'}

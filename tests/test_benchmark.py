import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_benchmark", ROOT / "scripts/benchmark.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)
TASKS = {task["id"]: task for task in json.loads((ROOT / "examples/benchmark_tasks.json").read_text())}


def test_inventory_grader_rejects_the_observed_false_empty_and_missing_nested_root():
    expected = TASKS["inventory-regression"]["expected"]
    assert benchmark.isolated_grade(TASKS["inventory-regression"], json.dumps(expected))["passed"]
    wrong = json.loads(json.dumps(expected))
    wrong[1]["empty"] = True
    wrong[2]["git_roots"] = []
    assert not benchmark.isolated_grade(TASKS["inventory-regression"], json.dumps(wrong))["passed"]


def test_code_grader_accepts_contract_and_rejects_boolean_validation_bug():
    source = '''def paginate(rows, page, size):
    if type(page) is not int or type(size) is not int or page < 1 or size < 1:
        raise ValueError()
    start = (page - 1) * size
    return list(rows[start:start + size])
'''
    result = benchmark.isolated_grade(TASKS["pagination"], source)
    assert result == {"passed": True, "checks": 12}
    wrong = source.replace("type(page) is not int", "not isinstance(page, int)")
    assert not benchmark.isolated_grade(TASKS["pagination"], wrong)["passed"]


def test_grading_does_not_allow_imports_or_extra_top_level_code():
    assert not benchmark.isolated_grade(TASKS["pagination"], "import os\ndef paginate(*args): return []")["passed"]


def test_summary_keeps_missing_agent_cost_unknown_and_counts_failed_attempts():
    row = {"task_id": "one", "policy": "auto", "passed": False, "elapsed_ms": 10,
           "selection": {"decision": {"effort": "medium", "source": "fallback", "latency_ms": 2, "cost_usd": 0.001}},
           "usage": {"input_tokens": 20, "cached_input_tokens": 10, "output_tokens": 3}}
    result = benchmark.summarize([row])["groups"][0]
    assert result["failed_attempts"] == 1 and result["accepted_tasks"] == 0
    assert result["input_tokens"] == 20 and result["agent_cost_usd"] is None

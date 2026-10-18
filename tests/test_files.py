"""Unknown file scope must not become a cheap task because its prompt is short."""
import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from auto_effort import AgentController, Config, EffortRouter, Policy, SubagentRouter, Target
from auto_effort.cli import main
from auto_effort.files import references_files
from auto_effort.protocol import handle


LIVE_CASES = json.loads((Path(__file__).resolve().parents[1] / "examples/file_effort_smoke.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", LIVE_CASES, ids=lambda case: case["id"])
def test_recorded_live_answers_produce_the_expected_file_policy(case):
    result = EffortRouter(Mock(return_value=case["judgment"])).pick(
        case["request"], context=case.get("context", ""), has_files=case.get("has_files", False),
    )
    assert result.effort == case["expected"]


def judgment(level="low", scope=None, confidence=0.99):
    answers = {"effort": {"choice": level, "confidence": confidence}}
    if scope is not None:
        answers["file_scope"] = {"choice": scope, "confidence": 0.99}
    return {"answers": answers}


def controller(judge, mode="auto"):
    return AgentController(Config({"name": "typesafe"}, {"default": Target("test-model", "responses")}, mode=mode), judge)


@pytest.mark.parametrize("prompt", [
    "report.pdf", "Review src/router.py", "Read ./spec and implement it",
    r"Review C:\project\report.pdf", "Look at the attached document",
    "Read this huge file and think for yourself", "Improve the uploaded code",
    "Audit the supplied spreadsheet", "Check README", '<file name="notes">',
    "Do the work described in /tmp/task", "Make this file better",
    "index.html", "theme.css", "trace.bin", "app.config.jsonc",
    "Look through src/styles/theme.scss and improve it",
    "payload.customformat", "`layout.unfamiliar`", "assets/scene.blend",
    ".env", ".gitignore", "config/.private-settings", "Review .env.production",
])
def test_unseen_file_work_cannot_apply_an_unguarded_low_choice(prompt):
    judge = Mock(return_value=judgment())
    result = EffortRouter(judge).pick(prompt, current_effort="low")
    assert (result.effort, result.source, result.reason) == ("high", "fallback", "file_scope_unknown")
    assert result.proposed_effort == "low"
    assert judge.call_count == 1
    state, questions = judge.call_args.args
    assert state["has_files"] is True
    assert questions["file_scope"]["type"] == "choice"
    assert "bounded" in questions["file_scope"]["criteria"]


@pytest.mark.parametrize("prompt", [
    "What is a Python list?", "Explain a file system", "What is the file format?",
    "Implement pagination", "Add pagination to /users", "Explain https://example.com",
    "Version v1.2.3", "1.2.3",
])
def test_general_requests_do_not_implicitly_reference_an_unseen_file(prompt):
    assert references_files(prompt) is False


@pytest.mark.parametrize("level", ["low", "medium"])
def test_concrete_scope_can_keep_lower_effort_without_opening_the_file(level):
    judge = Mock(return_value=judgment(level, "bounded"))
    result = EffortRouter(judge).pick(
        "Replace the literal 'teh' with 'the' in huge-report.md",
        context="Only that exact replacement is requested; no review or other edits.",
    )
    assert (result.effort, result.source) == (level, "jev")
    assert judge.call_count == 1


def test_short_summary_can_establish_scope_for_an_opaque_attachment():
    judge = Mock(return_value=judgment("low", "bounded"))
    result = EffortRouter(judge).pick("Make the change", has_files=True, context="The attached three-line note says 'helllo'; replace it with 'hello'.")
    assert result.effort == "low"
    assert judge.call_args.args[0]["context"].startswith("The attached three-line")


@pytest.mark.parametrize("scope_answer", [
    None, [], {}, {"choice": "unknown", "confidence": 1},
    {"choice": "other", "confidence": 1}, {"choice": "bounded", "confidence": 0.79},
    {"choice": "bounded", "confidence": True}, {"choice": "bounded", "confidence": "1"},
    {"choice": "bounded", "confidence": float("nan")},
    {"choice": "bounded", "confidence": float("inf")},
    {"choice": "bounded", "confidence": 1.01},
    {"choice": "bounded", "confidence": 10 ** 400},
    {"type": "score", "choice": "bounded", "confidence": 1},
])
def test_missing_invalid_or_uncertain_scope_keeps_the_guard(scope_answer):
    response = judgment()
    response["answers"]["file_scope"] = scope_answer
    result = EffortRouter(Mock(return_value=response)).pick("Do X in the file", has_files=True)
    assert (result.effort, result.reason) == ("high", "file_scope_unknown")
    json.dumps(result.to_dict(), allow_nan=False)


def test_scope_confidence_uses_the_configured_threshold():
    response = judgment(scope="bounded")
    response["answers"]["file_scope"]["confidence"] = 0.8
    assert EffortRouter(Mock(return_value=response)).pick("Make the edit", has_files=True).effort == "low"
    assert EffortRouter(Mock(return_value=response), Policy(confidence_threshold=0.9)).pick("Make the edit", has_files=True).effort == "high"


@pytest.mark.parametrize("kwargs, reason", [
    ({"private": True}, "private_request"),
    ({"context": "password=private-example-password"}, "credential_detected"),
    ({"context": "x" * 12_001}, "input_too_large"),
])
def test_file_preflight_fallback_is_high_without_sending_private_or_huge_input(kwargs, reason):
    judge = Mock(side_effect=AssertionError("no egress"))
    result = EffortRouter(judge).pick("Read this file", current_effort="low", **kwargs)
    assert (result.effort, result.reason) == ("high", reason)
    judge.assert_not_called()


@pytest.mark.parametrize("response, reason", [(None, "invalid_judgment"), (judgment(confidence=0.5), "low_confidence"), (judgment("other"), "unclassified_request")])
def test_file_judge_failures_keep_the_guard(response, reason):
    result = EffortRouter(Mock(return_value=response)).pick("Inspect the attachment", has_files=True)
    assert (result.effort, result.reason) == ("high", reason)


def test_unavailable_judge_keeps_the_guard():
    result = EffortRouter(Mock(side_effect=TimeoutError())).pick("Inspect the attachment", has_files=True)
    assert (result.effort, result.reason) == ("high", "judge_unavailable")


@pytest.mark.parametrize("levels, fallback, expected", [
    (("low", "medium"), "low", "medium"),
    (("low", "xhigh"), "low", "xhigh"),
    (("low",), "low", "low"),
    (("low", "high", "ultra"), "ultra", "ultra"),
])
def test_file_guard_respects_supported_levels_and_retains_a_higher_fallback(levels, fallback, expected):
    router = EffortRouter(Mock(return_value=judgment()), Policy(allowed_efforts=levels, fallback_effort=fallback))
    assert router.pick("Inspect it", has_files=True, private=True).effort == expected


def test_manual_low_still_wins_for_file_work():
    judge = Mock()
    result = EffortRouter(judge).pick("Analyze the attached document", effort="low", private=True)
    assert (result.effort, result.source) == ("low", "manual")
    judge.assert_not_called()


def test_file_only_input_gets_high_without_a_paid_judgment():
    judge = Mock()
    result = EffortRouter(judge).pick("", has_files=True)
    assert (result.effort, result.reason) == ("high", "file_scope_unknown")
    judge.assert_not_called()


def test_followup_inherits_file_presence_from_the_accepted_plan():
    result = EffortRouter(Mock(return_value=judgment())).pick("Continue", previous_reply="We will inspect report.pdf and choose a design")
    assert result.effort == "high"


def test_previous_files_do_not_leak_into_a_new_unrelated_request():
    judge = Mock(return_value=judgment())
    router = EffortRouter(judge)
    assert router.pick("Review this file").effort == "high"
    assert router.pick("Explain a Python list", previous_reply="We inspected report.pdf").effort == "low"
    assert "has_files" not in judge.call_args.args[0]


@pytest.mark.parametrize("mode", ["auto", "shadow", "off"])
def test_controller_modes_preserve_their_apply_contract_for_files(mode):
    judge = Mock(return_value=judgment())
    selected = controller(judge, mode).select("Inspect it", has_files=True, current_effort="low")
    assert selected.apply_effort is (mode == "auto")
    if mode == "off":
        judge.assert_not_called()
    else:
        assert selected.decision.effort == "high"
    if mode == "auto":
        assert selected.settings == {"reasoning": {"effort": "high"}}


@pytest.mark.parametrize("has_files", ["true", 1, None, []])
def test_invalid_file_flags_fail_before_a_judge_call(has_files):
    judge = Mock()
    with pytest.raises(ValueError):
        EffortRouter(judge).pick("Inspect it", has_files=has_files)
    assert "error" in handle(controller(judge), {"request": "Inspect it", "has_files": has_files})
    judge.assert_not_called()


def test_json_controller_accepts_an_opaque_file_hint():
    result = handle(controller(Mock(return_value=judgment())), {"id": "file-turn", "request": "Inspect it", "has_files": True})
    assert result["result"]["decision"]["effort"] == "high"
    assert result["id"] == "file-turn"


def test_model_routing_forwards_the_file_hint_to_effort_selection():
    config = Config({"name": "typesafe"}, {"worker": Target("test-model", "codex")}, "worker")
    router = SubagentRouter(config, {"worker": {"role": "worker", "criteria": "Routine work"}}, Mock(return_value=judgment()))
    assert router.select("Inspect it", has_files=True, target="worker").selection.decision.effort == "high"


def test_cli_file_hint_applies_to_a_launch_and_preserves_the_prompt(monkeypatch, capsys):
    monkeypatch.setattr("auto_effort.cli.TypeSafeBackend", lambda *args: Mock(return_value=judgment()))
    monkeypatch.setattr("sys.stdin", io.StringIO("Inspect it"))
    assert main(["run", "--model", "test-model", "--has-files", "--dry-run", "--no-log"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert 'model_reasoning_effort="high"' in result["argv"]


def test_request_file_is_a_prompt_transport_and_not_implicitly_an_attachment(tmp_path, monkeypatch, capsys):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Explain a Python list", encoding="utf-8")
    monkeypatch.setattr("auto_effort.cli.TypeSafeBackend", lambda *args: Mock(return_value=judgment()))
    assert main(["pick", "--request-file", str(prompt), "--no-log"]) == 0
    assert json.loads(capsys.readouterr().out)["effort"] == "low"

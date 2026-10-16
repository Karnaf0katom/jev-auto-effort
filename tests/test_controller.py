import io
import json
from unittest.mock import Mock

import pytest

from auto_effort import AgentController, Config, Target
from auto_effort.cli import main
from auto_effort.protocol import MAX_LINE_CHARS, handle, serve


def reply(level="low"):
    return {"answers": {"effort": {"choice": level, "confidence": 0.99}}}


def controller(adapter="responses", mode="auto", judge=None):
    config = Config({"name": "typesafe"}, {"default": Target("actual-model", adapter)}, mode=mode)
    return AgentController(config, judge or Mock(return_value=reply()))


@pytest.mark.parametrize("adapter", ["responses", "chat-completions"])
def test_request_hook_changes_only_native_effort_and_preserves_agent_loop(adapter):
    judge = Mock(return_value=reply("high"))
    selected = controller(adapter, judge=judge).select("Investigate a complex race", context="A short task summary")
    original = {
        "model": "actual-model", "input": [{"role": "user", "content": "private full input"}],
        "tools": [{"name": "original-tool"}], "stream": True, "metadata": {"session": "same-session"},
        "reasoning": {"summary": "auto", "effort": "medium"},
    }
    result = selected.apply(original)
    for key in ("model", "input", "tools", "stream", "metadata"):
        assert result[key] == original[key]
    if adapter == "responses":
        assert result["reasoning"] == {"summary": "auto", "effort": "high"}
    else:
        assert result["reasoning_effort"] == "high"
    assert original["reasoning"]["effort"] == "medium"
    assert "private full input" not in json.dumps(judge.call_args.args)


def test_codex_controller_returns_launch_arguments_without_starting_an_agent():
    selected = controller("codex").select("Fix a typo")
    assert selected.cli_args == ["-c", 'model_reasoning_effort="low"']
    assert selected.settings == {}


def test_custom_token_budget_mapping_is_declared_by_host():
    target = Target("budget-model", "custom", path=("generationConfig", "thinkingConfig", "thinkingBudget"), values={"low": 512, "medium": 2048, "high": 8192})
    router = AgentController(Config({"name": "typesafe"}, {"default": target}), Mock(return_value=reply("medium")))
    selected = router.select("Implement the documented feature")
    result = selected.apply({"model": "budget-model", "generationConfig": {"temperature": 0.5}})
    assert result["generationConfig"] == {"temperature": 0.5, "thinkingConfig": {"thinkingBudget": 2048}}


def test_shadow_records_a_proposal_without_changing_the_host_request():
    selected = controller(mode="shadow").select("Fix a typo", current_effort="high")
    assert selected.decision.effort == "low"
    assert (selected.apply_effort, selected.reason, selected.settings, selected.cli_args) == (False, "shadow_mode", {}, [])
    original = {"model": "actual-model", "reasoning": {"effort": "high"}}
    assert selected.apply(original) == original


def test_off_makes_no_judge_call_and_no_host_change():
    judge = Mock(side_effect=AssertionError("no network"))
    selected = controller(mode="off", judge=judge).select("Fix a typo")
    assert selected.reason == "router_off"
    assert selected.apply_effort is False
    judge.assert_not_called()


@pytest.mark.parametrize("mode", ["off", "shadow", "auto"])
def test_explicit_user_override_wins_without_a_judge_call(mode):
    judge = Mock()
    selected = controller(mode=mode, judge=judge).select("Fix a typo", effort="high")
    assert selected.apply_effort and selected.decision.source == "manual"
    assert selected.settings == {"reasoning": {"effort": "high"}}
    judge.assert_not_called()


def test_models_without_effort_control_bypass_the_judge():
    target = Target("fixed-model", "disabled", levels=())
    judge = Mock()
    selected = AgentController(Config({"name": "typesafe"}, {"default": target}), judge).select("Solve the task")
    assert selected.reason == "unsupported_target" and selected.decision is None
    assert selected.apply({"model": "fixed-model"}) == {"model": "fixed-model"}
    judge.assert_not_called()


def test_model_mismatch_cannot_apply_a_profile_to_another_model():
    selected = controller().select("Fix a typo")
    with pytest.raises(ValueError, match="does not match"):
        selected.apply({"model": "another-model"})


def test_subagent_target_has_its_own_permitted_efforts():
    judge = Mock(return_value=reply("max"))
    config = Config({"name": "typesafe"}, {
        "parent": Target("parent-model", levels=("low", "medium", "high", "max")),
        "worker": Target("worker-model", levels=("low", "medium")),
    }, default_target="parent")
    selected = AgentController(config, judge).select("Do a small edit", target="worker")
    assert selected.target.model == "worker-model"
    assert selected.decision.effort == "medium" and selected.decision.source == "fallback"
    assert set(judge.call_args.args[1]["effort"]["criteria"]) == {"low", "medium", "other"}


def test_json_lines_handles_multiple_turns_and_recovers_after_bad_input():
    judge = Mock(side_effect=[reply("high"), reply("low")])
    source = io.StringIO('\n'.join([
        json.dumps({"id": "one", "request": "Investigate a race"}),
        'not-json',
        json.dumps({"id": "bad", "request": "x", "private": "false"}),
        json.dumps({"id": "two", "request": "Fix a typo"}),
    ]) + '\n')
    destination = io.StringIO()
    serve(controller(judge=judge), source, destination)
    rows = [json.loads(line) for line in destination.getvalue().splitlines()]
    assert rows[0]["result"]["decision"]["effort"] == "high"
    assert rows[1]["error"]["code"] == "invalid_json"
    assert rows[2]["error"]["code"] == "invalid_request"
    assert rows[3]["result"]["decision"]["effort"] == "low"
    assert judge.call_count == 2


def test_oversized_json_line_is_drained_without_poisoning_the_next_request():
    judge = Mock()
    source = io.StringIO('x' * (MAX_LINE_CHARS * 2) + '\n' + json.dumps({"request": "Private task", "private": True}) + '\n')
    destination = io.StringIO()
    serve(controller(judge=judge), source, destination)
    rows = [json.loads(line) for line in destination.getvalue().splitlines()]
    assert rows[0]["error"]["code"] == "input_too_large"
    assert rows[1]["result"]["decision"]["reason"] == "private_request"
    judge.assert_not_called()


@pytest.mark.parametrize("message", [[], {}, {"request": "Task", "unknown": 1}, {"request": "Task", "id": [1]}, {"request": "Task", "mode": "bogus"}, {"request": "Task", "current_effort": "max"}])
def test_bad_controller_requests_never_reach_judge(message):
    judge = Mock()
    response = handle(controller(judge=judge), message)
    assert response["error"]["code"] == "invalid_request"
    judge.assert_not_called()


def test_init_select_and_doctor_use_only_the_requested_config(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.json"
    assert main(["init", "--config", str(path), "--model", "actual-model", "--backend", "openrouter"]) == 0
    assert json.loads(path.read_text())["targets"]["default"]["model"] == "actual-model"
    capsys.readouterr()
    assert main(["select", "Fix a typo", "--config", str(path), "--private"]) == 0
    assert json.loads(capsys.readouterr().out)["settings"] == {"reasoning": {"effort": "medium"}}
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-key-for-test")
    assert main(["doctor", "--config", str(path)]) in (0, 1)
    report = capsys.readouterr().out
    assert "not-a-real-key-for-test" not in report
    assert json.loads(report)["network_check"] == "not_performed"
    before = path.read_bytes()
    assert main(["init", "--config", str(path), "--model", "changed-model"]) == 2
    assert path.read_bytes() == before


def test_config_roundtrip_and_invalid_capabilities():
    config = Config({"name": "typesafe"}, {"default": Target("model"), "fixed": Target("fixed", "disabled", levels=())})
    assert Config.from_dict(config.to_dict()).to_dict() == config.to_dict()
    data = config.to_dict()
    data["backend"]["api_key"] = "not-real"
    with pytest.raises(ValueError, match="environment"):
        Config.from_dict(data)
    with pytest.raises(ValueError):
        Target("model", "custom", path=("model",), values={"low": "x", "medium": "y", "high": "z"})
    with pytest.raises(ValueError):
        Target("model", "custom", path=("thinking", "budget"), values={"low": 100})
    with pytest.raises(ValueError):
        Target("model", "custom", path=("headers", "authorization"), values={"low": "x", "medium": "y", "high": "z"})


def test_loaded_capability_declarations_cannot_change_through_caller_aliases():
    backend = {"name": "typesafe"}
    targets = {"default": Target("actual-model")}
    config = Config(backend, targets)
    backend["name"] = "unknown-provider"
    targets["default"] = Target("different-model")
    assert config.backend["name"] == "typesafe"
    assert config.targets["default"].model == "actual-model"
    with pytest.raises(TypeError):
        config.targets["default"] = targets["default"]


def test_nullable_native_effort_settings_can_receive_a_selected_level():
    selected = controller().select("Fix a typo")
    assert selected.apply({"model": "actual-model", "reasoning": None})["reasoning"] == {"effort": "low"}


def test_protocol_error_retains_a_valid_correlation_id():
    response = handle(controller(), {"id": "request-9", "request": "Task", "unknown": True})
    assert response["id"] == "request-9" and "error" in response

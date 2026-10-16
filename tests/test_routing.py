from unittest.mock import Mock

import pytest

from auto_effort import Config, DecisionLedger, SubagentRouter, Target, TraceContext


def make_router(tmp_path, judge, mode="auto"):
    config = Config({"name": "typesafe"}, {
        "worker": Target("routine-model", "codex"),
        "scout": Target("small-model", "codex", ("low", "medium")),
        "deep": Target("reasoning-model", "codex"),
    }, "worker", mode)
    routes = {
        "worker": {"criteria": "Routine bounded implementation", "role": "worker"},
        "scout": {"criteria": "Read-only lookup with exact acceptance", "role": "scout"},
        "deep": {"criteria": "Hard reasoning or a lower-lane failure", "role": "deep"},
    }
    return SubagentRouter(config, routes, judge, ledger=DecisionLedger(tmp_path / "trial.sqlite3"))


def replies(target="scout", confidence=0.99):
    return [{"answers": {"model": {"choice": target, "confidence": confidence}}, "usage": {"cost": 0.001}}, {"answers": {"effort": {"choice": "low", "confidence": 0.99}}, "usage": {"cost": 0.002}}]


def test_model_choice_precedes_effort_and_uses_the_selected_targets_ladder(tmp_path):
    judge = Mock(side_effect=replies())
    router = make_router(tmp_path, judge)
    routed = router.select("Find the controller action mapping", trace=TraceContext(ticket="DEMO-1", parent_session_id="brain-1"))
    assert routed.model_choice.target == "scout"
    assert routed.selection.target.model == "small-model"
    assert routed.selection.cli_args == ["-c", 'model_reasoning_effort="low"']
    assert judge.call_args_list[0].args[1]["model"]["criteria"]["scout"].startswith("Role: scout.")
    assert set(judge.call_args_list[1].args[1]["effort"]["criteria"]) == {"low", "medium", "other"}
    records = list(router.ledger.export())
    assert records[0]["trace"]["role"] == "scout"
    assert records[0]["model_source"] == "jev"
    assert records[-1]["choice"]["confidence"] == 0.99
    assert router.ledger.summary()["groups"][0]["known_model_judge_cost_usd"] == 0.001


@pytest.mark.parametrize("target,confidence,reason", [("scout", 0.4, "low_confidence"), ("other", 0.99, "unclassified_request"), ("invented", 0.99, "invalid_judgment")])
def test_uncertain_or_invented_model_keeps_the_declared_baseline(tmp_path, target, confidence, reason):
    routed = make_router(tmp_path, Mock(side_effect=replies(target, confidence))).select("An unclear task")
    assert routed.model_choice.reason == reason
    assert routed.selection.target.model == "routine-model"


def test_private_task_skips_both_judges(tmp_path):
    judge = Mock(side_effect=AssertionError("no egress"))
    routed = make_router(tmp_path, judge).select("Private task", private=True)
    assert routed.model_choice.reason == "private_request"
    assert routed.selection.decision.reason == "private_request"
    judge.assert_not_called()


def test_confirmation_without_task_context_keeps_both_baselines(tmp_path):
    judge = Mock(side_effect=AssertionError("no task supplied"))
    routed = make_router(tmp_path, judge).select("Continue")
    assert routed.model_choice.reason == "no_task_context"
    assert routed.selection.decision.reason == "no_task_context"
    judge.assert_not_called()


def test_shadow_keeps_the_actual_model_and_effort_and_records_the_model_proposal(tmp_path):
    router = make_router(tmp_path, Mock(side_effect=replies()), "shadow")
    routed = router.select("Find an input mapping", current_effort="high")
    assert routed.model_choice.target == "scout"
    assert routed.selection.target.model == "routine-model"
    assert not routed.selection.apply_effort
    assert list(router.ledger.export())[0]["effective_effort"] == "high"


def test_explicit_model_and_effort_skip_judging_in_every_mode(tmp_path):
    for mode in ("auto", "shadow", "off"):
        judge = Mock()
        routed = make_router(tmp_path, judge, mode).select("Task", target="deep", effort="high")
        assert routed.selection.target.model == "reasoning-model"
        assert routed.selection.apply_effort
        assert routed.model_choice.source == "manual"
        judge.assert_not_called()


def test_invalid_override_rejects_before_any_provider_call(tmp_path):
    judge = Mock()
    router = make_router(tmp_path, judge)
    with pytest.raises(ValueError):
        router.select("Task", target="invented", effort="high")
    with pytest.raises(ValueError):
        router.select("Task", effort="max")
    judge.assert_not_called()


def test_report_can_isolate_the_selected_trial(tmp_path):
    router = make_router(tmp_path, Mock(side_effect=replies() + replies()))
    router.select("Find input mapping", trace=TraceContext(trial_id="one"))
    router.select("Find input mapping", trace=TraceContext(trial_id="two"))
    assert router.ledger.summary(trial_id="one")["decisions"] == 1
    assert router.ledger.summary()["decisions"] == 2

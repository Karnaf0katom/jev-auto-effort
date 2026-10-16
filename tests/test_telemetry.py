import io
import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from auto_effort import AgentController, Config, Decision, DecisionLedger, Target, TraceContext
from auto_effort.cli import main
from auto_effort.protocol import handle


def controller(ledger, mode="auto", judge=None):
    config = Config({"name": "typesafe"}, {"worker": Target("test-model", "codex")}, "worker", mode)
    return AgentController(config, judge or Mock(return_value={"answers": {"effort": {"choice": "low", "confidence": 0.99}}, "usage": {"cost": 0.001}}), ledger=ledger)


def test_selection_preserves_lineage_without_storing_private_content(tmp_path):
    ledger = DecisionLedger(tmp_path / "trial.sqlite3")
    trace = TraceContext(project_id="project-1", task_id="task-1", ticket="DEMO-1", session_id="child-1", parent_session_id="brain-1", role="worker", trial_id="trial-1", attempt=2)
    selected = controller(ledger).select("private request contents", context="private context", previous_reply="private previous reply", private=True, trace=trace)
    rows = list(ledger.export())
    assert rows[0]["decision_id"] == selected.to_dict()["decision_id"]
    assert rows[0]["trace"]["parent_session_id"] == "brain-1"
    assert rows[0]["trace"]["attempt"] == 2
    assert rows[0]["decision"]["reason"] == "private_request"
    assert rows[0]["model_source"] == "caller"
    assert "private request" not in json.dumps(rows)
    assert "private context" not in json.dumps(rows)
    assert "private previous" not in json.dumps(rows)
    if os.name != "nt":
        assert ledger.path.stat().st_mode & 0o777 == 0o600


def test_shadow_proposal_and_manual_override_record_the_actual_setting(tmp_path):
    ledger = DecisionLedger(tmp_path / "trial.sqlite3")
    host = controller(ledger, "shadow")
    shadow = host.select("Small edit", current_effort="high")
    manual = host.select("Small edit", current_effort="medium", effort="high")
    records = {r["decision_id"]: r for r in ledger.export()}
    assert records[shadow.decision_id]["decision"]["effort"] == "low"
    assert records[shadow.decision_id]["effective_effort"] == "high"
    assert records[shadow.decision_id]["apply_effort"] is False
    assert records[manual.decision_id]["effective_effort"] == "high"
    assert records[manual.decision_id]["decision"]["source"] == "manual"


def test_exit_zero_does_not_become_acceptance_and_missing_costs_stay_unknown(tmp_path):
    ledger = DecisionLedger(tmp_path / "trial.sqlite3")
    decision_id = ledger.record_selection(Decision("low", "manual", "explicit_override"), model="test-model")
    ledger.record_execution(decision_id, status="completed", exit_code=0, elapsed_ms=25)
    group = ledger.summary()["groups"][0]
    assert group["acceptance_unknown"] == 1 and group["acceptance_passed"] == 0
    assert group["known_agent_cost_usd"] is None and group["known_judge_cost_usd"] is None
    assert group["known_tokens"] is None
    assert group["mean_elapsed_ms"] == 25
    ledger.record_outcome(decision_id, acceptance="failed", evidence_id="check-1", tokens=40, agent_cost_usd=0.02, retries=1)
    ledger.record_outcome(decision_id, acceptance="passed", evidence_id="check-2", tokens=80, agent_cost_usd=0.04, retries=2)
    report = ledger.summary()
    assert report["decisions"] == 1
    assert report["groups"][0]["acceptance_passed"] == 1
    assert report["groups"][0]["acceptance_failed"] == 0
    assert report["groups"][0]["known_agent_cost_usd"] == 0.04
    assert report["groups"][0]["known_tokens"] == 80
    assert len([r for r in ledger.export() if r["kind"] == "outcome"]) == 2


def test_dry_runs_are_excluded_from_trial_results(tmp_path):
    ledger = DecisionLedger(tmp_path / "trial.sqlite3")
    selected = controller(ledger).select("Small edit", dry_run=True)
    ledger.record_outcome(selected.decision_id, acceptance="passed", evidence_id="check-1")
    assert ledger.summary() == {"schema_version": 1, "decisions": 0, "dry_runs": 1, "groups": []}


def test_no_orphan_outcomes_and_no_unattributed_acceptance(tmp_path):
    ledger = DecisionLedger(tmp_path / "trial.sqlite3")
    with pytest.raises(ValueError, match="unknown decision"):
        ledger.record_outcome("missing", acceptance="unknown")
    decision_id = controller(ledger).select("Small edit").decision_id
    with pytest.raises(ValueError, match="evidence"):
        ledger.record_outcome(decision_id, acceptance="passed")
    for kwargs in ({"tokens": True}, {"tokens": -1}, {"agent_cost_usd": float("nan")}, {"retries": 1.5}):
        with pytest.raises(ValueError):
            ledger.record_outcome(decision_id, acceptance="unknown", **kwargs)


def test_concurrent_writers_preserve_all_decisions_and_close_connections(tmp_path):
    location = tmp_path / "trial.sqlite3"
    def write(index):
        ledger = DecisionLedger(location)
        decision_id = controller(ledger).select("Small edit", trace=TraceContext(task_id=f"task-{index}")).decision_id
        ledger.record_outcome(decision_id, acceptance="passed", evidence_id=f"check-{index}")
        return decision_id
    with ThreadPoolExecutor(max_workers=4) as executor:
        identities = list(executor.map(write, range(20)))
    assert len(set(identities)) == 20
    assert DecisionLedger(location).summary()["groups"][0]["acceptance_passed"] == 20
    with sqlite3.connect(location) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_protocol_traces_each_turn_and_rejects_bad_metadata_before_judging(tmp_path):
    ledger = DecisionLedger(tmp_path / "trial.sqlite3")
    judge = Mock(return_value={"answers": {"effort": {"choice": "low", "confidence": 0.99}}})
    host = controller(ledger, judge=judge)
    result = handle(host, {"id": "turn-1", "request": "Small edit", "trace": {"session_id": "session-1", "ticket": "DEMO-1"}})
    assert result["result"]["decision_id"]
    response = handle(host, {"request": "Small edit", "trace": {"session_id": "/private/path"}})
    assert response["error"]["code"] == "invalid_request"
    assert judge.call_count == 1
    assert ledger.summary()["decisions"] == 1


def test_storage_failure_is_visible_without_leaking_path(tmp_path):
    ledger = DecisionLedger(tmp_path / "private-location")
    ledger.path.mkdir()
    response = handle(controller(ledger), {"request": "Small edit"})
    assert response["error"]["code"] == "logging_unavailable"
    assert "private-location" not in json.dumps(response)


def test_cli_pick_outcome_report_export_and_explicit_disable(tmp_path, capsys):
    location = tmp_path / "trial.sqlite3"
    assert main(["pick", "Private task", "--private", "--ledger", str(location), "--ticket", "DEMO-1"]) == 0
    decision_id = json.loads(capsys.readouterr().out)["decision_id"]
    assert main(["outcome", decision_id, "--ledger", str(location), "--acceptance", "passed", "--evidence-id", "check-1", "--tokens", "100"]) == 0
    capsys.readouterr()
    assert main(["report", "--ledger", str(location)]) == 0
    assert json.loads(capsys.readouterr().out)["groups"][0]["acceptance_passed"] == 1
    assert main(["export", "--ledger", str(location)]) == 0
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r["kind"] for r in records] == ["selection", "outcome"]
    disabled = tmp_path / "disabled.sqlite3"
    assert main(["pick", "Task", "--private", "--ledger", str(disabled), "--no-log"]) == 0
    assert "decision_id" not in json.loads(capsys.readouterr().out)
    assert not disabled.exists()


@pytest.mark.parametrize("failure,status,expected", [
    (None, "completed", 0),
    (OSError("private-error"), "launch_error", 2),
    (subprocess.TimeoutExpired("private-command", 1), "timeout", 124),
])
def test_launch_records_execution_without_claiming_correctness(tmp_path, monkeypatch, capsys, failure, status, expected):
    location = tmp_path / "trial.sqlite3"
    monkeypatch.setattr(sys, "stdin", io.StringIO("Private request"))
    runner = Mock(side_effect=failure) if failure else Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(subprocess, "run", runner)
    assert main(["run", "--model", "test-model", "--private", "--ledger", str(location)]) == expected
    records = list(DecisionLedger(location).export())
    assert records[-1]["status"] == status
    assert "Private request" not in json.dumps(records)
    assert "private-error" not in capsys.readouterr().err
    assert DecisionLedger(location).summary()["groups"][0]["acceptance_unknown"] == 1


def test_reports_do_not_create_an_empty_database(tmp_path):
    ledger = DecisionLedger(tmp_path / "absent.sqlite3")
    assert ledger.summary()["decisions"] == 0
    assert not ledger.path.exists()


def test_continuation_has_its_own_decision_and_preserves_the_original(tmp_path):
    ledger = DecisionLedger(tmp_path / "trial.sqlite3")
    selected = controller(ledger).select("Small edit", trace=TraceContext(task_id="one", trial_id="trial"))
    original = ledger.get(selected.decision_id)
    inherited = ledger.inherit(selected.decision_id, parent_session_id="original-session")
    continued = ledger.get(inherited)
    assert inherited != selected.decision_id
    assert continued["trace"]["parent_decision_id"] == selected.decision_id
    assert continued["trace"]["parent_session_id"] == "original-session"
    assert continued["trace"]["task_id"] == "one"
    assert continued["effective_effort"] == "low"
    assert continued["decision"]["reason"] == "inherited_selection"
    assert continued["decision"]["source"] == "fallback"
    assert ledger.get(selected.decision_id) == original


def test_execution_observations_do_not_claim_acceptance_or_double_count_tokens(tmp_path):
    ledger = DecisionLedger(tmp_path / "trial.sqlite3")
    selected = controller(ledger).select("Small edit")
    for tokens in (100, 100, 150):
        ledger.record_observation(selected.decision_id, session_id="native-1", turn_id="turn-1",
                                  status="completed", model="test-model", effort="medium", tokens=tokens)
    group = ledger.summary()["groups"][0]
    assert group["acceptance_unknown"] == 1
    assert group["acceptance_passed"] == 0
    assert group["known_observed_tokens"] == 150
    assert group["observed_sessions"] == 1
    assert group["effort_mismatches"] == 1


def test_inspect_inherit_observe_and_selection_probe_cli(tmp_path, capsys):
    location = tmp_path / "trial.sqlite3"
    config = tmp_path / "config.json"
    Config({"name": "typesafe"}, {"worker": Target("test-model", "codex")}, "worker").save(config)
    assert main(["select", "Task", "--config", str(config), "--private", "--ledger", str(location)]) == 0
    identity = json.loads(capsys.readouterr().out)["decision_id"]
    assert main(["inspect", identity, "--ledger", str(location)]) == 0
    assert json.loads(capsys.readouterr().out)["effective_effort"] == "medium"
    assert main(["inherit", identity, "--parent-session-id", "native-1", "--ledger", str(location)]) == 0
    continued = json.loads(capsys.readouterr().out)
    assert continued["trace"]["parent_decision_id"] == identity
    assert main(["observe", continued["decision_id"], "--session-id", "native-2", "--turn-id", "turn-1", "--status", "completed", "--tokens", "42", "--ledger", str(location)]) == 0
    capsys.readouterr()
    assert main(["pick", "Task", "--private", "--dry-run", "--ledger", str(location)]) == 0
    capsys.readouterr()
    assert DecisionLedger(location).summary()["dry_runs"] == 1


def test_report_distinguishes_uncertain_proposals_from_applied_fallback(tmp_path):
    ledger = DecisionLedger(tmp_path / "trial.sqlite3")
    judge = Mock(return_value={"answers": {"effort": {"choice": "high", "confidence": 0.4}}})
    selected = controller(ledger, judge=judge).select("Diagnose the supplied issue")
    group = ledger.summary()["groups"][0]
    assert group["effective_effort"] == "medium"
    assert group["proposed_efforts"] == {"high": 1}
    assert group["fallback_reasons"] == {"low_confidence": 1}
    assert group["selection_only"] == 1
    assert ledger.get(selected.decision_id)["decision"]["proposed_effort"] == "high"


def test_repair_cannot_silently_link_to_a_missing_decision(tmp_path):
    with pytest.raises(ValueError, match="parent decision"):
        controller(DecisionLedger(tmp_path / "trial.sqlite3")).select("Repair", trace=TraceContext(parent_decision_id="missing", attempt=2))


def test_historical_probe_correction_preserves_history_and_cannot_hide_work(tmp_path, capsys):
    ledger = DecisionLedger(tmp_path / "trial.sqlite3")
    selected = controller(ledger).select("Transport probe")
    original = ledger.get(selected.decision_id)
    for _ in range(2):
        assert main(["mark-probe", selected.decision_id, "--ledger", str(ledger.path)]) == 0
        capsys.readouterr()
    assert ledger.get(selected.decision_id) == original
    assert sum(row["kind"] == "probe" for row in ledger.export()) == 1
    assert ledger.summary() == {"schema_version": 1, "decisions": 0, "dry_runs": 1, "groups": []}
    with pytest.raises(ValueError):
        ledger.inherit(selected.decision_id, parent_session_id="source")
    with pytest.raises(ValueError, match="probe"):
        ledger.bind_session(selected.decision_id, "native")
    launched = controller(ledger).select("Real task")
    ledger.record_execution(launched.decision_id, status="launch_error")
    with pytest.raises(ValueError, match="no execution"):
        ledger.mark_probe(launched.decision_id)


def test_cumulative_session_usage_is_not_added_again_for_a_second_decision(tmp_path):
    ledger = DecisionLedger(tmp_path / "trial.sqlite3")
    host = controller(ledger)
    identities = []
    for request, tokens in (("First task", 100), ("Continue", 150)):
        selected = host.select(request, effort="low")
        identities.append(selected.decision_id)
        ledger.record_observation(selected.decision_id, session_id="native-1", turn_id="turn-" + str(tokens),
                                  status="completed", model="test-model", effort="low", tokens=tokens)
    result = ledger.summary()
    assert result["groups"][0]["decisions"] == 2
    assert result["groups"][0]["observed_sessions"] == 1
    assert result["groups"][0]["known_observed_tokens"] == 150
    assert result["observations"] == {"sessions": 1, "known_tokens": 150, "token_samples": 1}
    # Event chronology, rather than selection/export order, determines freshness.
    ledger.record_observation(identities[0], session_id="native-1", turn_id="late-turn",
                              status="completed", model="test-model", effort="low", tokens=200)
    assert ledger.summary()["groups"][0]["known_observed_tokens"] == 200


def test_shared_session_totals_are_not_allocated_to_competing_effort_groups(tmp_path):
    ledger = DecisionLedger(tmp_path / "trial.sqlite3")
    host = controller(ledger)
    for effort, tokens in (("low", 100), ("high", 150)):
        selected = host.select("Task", effort=effort)
        ledger.record_observation(selected.decision_id, session_id="native-1", turn_id="turn-" + effort,
                                  status="completed", model="test-model", effort=effort, tokens=tokens)
    result = ledger.summary()
    assert result["observations"] == {"sessions": 1, "known_tokens": 150, "token_samples": 1}
    assert all(group["known_observed_tokens"] is None and group["shared_session_token_samples_excluded"] == 1 for group in result["groups"])

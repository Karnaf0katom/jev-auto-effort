"""Local, prompt-free decision records and host-reported task outcomes."""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import sys
import uuid
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .core import Decision, EFFORTS

POLICY_VERSION = "effort-v1"
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_ROLES = {"controller", "scout", "worker", "reviewer", "deep"}


def ledger_path() -> Path:
    """Store evidence outside source checkouts; no network export is performed."""
    if os.environ.get("AUTO_EFFORT_LEDGER"):
        return Path(os.environ["AUTO_EFFORT_LEDGER"]).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AutoEffort" / "decisions.sqlite3"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AutoEffort" / "decisions.sqlite3"
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "auto-effort" / "decisions.sqlite3"


def _identifier(value: str | None) -> None:
    if value is not None and (not isinstance(value, str) or not _ID.fullmatch(value)):
        raise ValueError("trace identifiers must be short opaque labels")


def _numeric(value: Any, *, integer: bool = False) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int if integer else (int, float)):
        raise ValueError("outcome metrics must be nonnegative finite numbers")
    try:
        valid = value >= 0 and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("outcome metrics must be nonnegative finite numbers")


@dataclass(frozen=True)
class TraceContext:
    """Host-supplied identity only. Use opaque IDs rather than paths or task prose."""

    project_id: str | None = None
    task_id: str | None = None
    ticket: str | None = None
    session_id: str | None = None
    parent_session_id: str | None = None
    trial_id: str | None = None
    parent_decision_id: str | None = None
    role: str = "controller"
    attempt: int = 1

    def __post_init__(self) -> None:
        for key, value in asdict(self).items():
            if key not in ("role", "attempt"):
                _identifier(value)
        if self.role not in _ROLES:
            raise ValueError("unknown trace role")
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 1:
            raise ValueError("trace attempt must be a positive integer")


class DecisionLedger:
    """SQLite handles concurrent processes. Records never contain requests or replies.

    Storage failures are raised, so a host cannot mistake an unlogged call for a
    recorded one. Correctness is supplied by the host's acceptance check, never Jev
    or an agent process's exit code. Repeated outcome reports retain their history;
    the summary uses only the latest report for each decision.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else ledger_path()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, decision_id TEXT NOT NULL REFERENCES decisions(id), kind TEXT NOT NULL, record TEXT NOT NULL)")
            connection.execute("CREATE INDEX IF NOT EXISTS events_decision ON events(decision_id, seq)")
            with connection:
                yield connection
        finally:
            connection.close()

    def record_selection(
        self, decision: Decision | None, *, model: str | None = None,
        target: str | None = None, adapter: str | None = None,
        mode: str = "auto", apply_effort: bool = True,
        current_effort: str | None = None, allowed_efforts: tuple[str, ...] = (),
        fallback_effort: str | None = None, threshold: float = 0.8,
        reason: str | None = None, trace: TraceContext | None = None,
        dry_run: bool = False, model_source: str = "caller",
    ) -> str:
        if mode not in ("off", "shadow", "auto"):
            raise ValueError("unknown trace mode")
        if model_source not in ("caller", "manual", "jev", "fallback"):
            raise ValueError("unknown model selection source")
        if model is not None and (not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_./:-]{1,200}", model)):
            raise ValueError("trace model must be a model identifier")
        _identifier(target)
        _identifier(adapter)
        _identifier(reason)
        if not isinstance(apply_effort, bool) or not isinstance(dry_run, bool):
            raise ValueError("trace application flags must be booleans")
        _numeric(threshold)
        if threshold is None or not 0.8 <= threshold <= 1:
            raise ValueError("trace confidence threshold must be between 0.8 and 1")
        if trace is not None and not isinstance(trace, TraceContext):
            raise ValueError("trace must be a TraceContext")
        if any(level not in EFFORTS for level in (*allowed_efforts, current_effort, fallback_effort) if level is not None):
            raise ValueError("unknown trace effort")
        identity = uuid.uuid4().hex
        record = {
            "schema_version": 1, "decision_id": identity,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "policy_version": POLICY_VERSION, "implementation_version": "0.4.0a1",
            "trace": asdict(trace or TraceContext()),
            "model": model, "model_source": model_source, "target": target,
            "adapter": adapter, "mode": mode, "dry_run": dry_run,
            "apply_effort": apply_effort,
            "effective_effort": decision.effort if decision and apply_effort else current_effort,
            "baseline_effort": current_effort,
            "allowed_efforts": list(allowed_efforts), "fallback_effort": fallback_effort,
            "confidence_threshold": threshold,
            "reason": reason or (decision.reason if decision else "router_off"),
            "decision": decision.to_dict() if decision else None,
        }
        payload = json.dumps(record, allow_nan=False)
        with self._connect() as connection:
            if record["trace"]["parent_decision_id"] and not connection.execute(
                "SELECT 1 FROM decisions WHERE id = ?", (record["trace"]["parent_decision_id"],)
            ).fetchone():
                raise ValueError("parent decision must exist in this ledger")
            connection.execute("INSERT INTO decisions VALUES (?, ?)", (identity, payload))
        return identity

    def _event(self, decision_id: str, kind: str, values: dict[str, Any]) -> None:
        _identifier(decision_id)
        record = {
            "schema_version": 1, "decision_id": decision_id, "kind": kind,
            "created_at": datetime.now(timezone.utc).isoformat(), **values,
        }
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not connection.execute("SELECT 1 FROM decisions WHERE id = ?", (decision_id,)).fetchone():
                raise ValueError("unknown decision id in this ledger")
            if connection.execute("SELECT 1 FROM events WHERE decision_id = ? AND kind = 'probe'", (decision_id,)).fetchone():
                raise ValueError("a marked selection-only probe cannot receive execution or outcome events")
            connection.execute("INSERT INTO events (decision_id, kind, record) VALUES (?, ?, ?)", (decision_id, kind, json.dumps(record, allow_nan=False)))

    def record_execution(
        self, decision_id: str, *, status: str, elapsed_ms: float | None = None,
        exit_code: int | None = None,
    ) -> None:
        if status not in ("started", "completed", "timeout", "launch_error", "interrupted"):
            raise ValueError("unknown execution status")
        _numeric(elapsed_ms)
        if exit_code is not None and (isinstance(exit_code, bool) or not isinstance(exit_code, int)):
            raise ValueError("exit code must be an integer")
        self._event(decision_id, "execution", {"status": status, "elapsed_ms": elapsed_ms, "exit_code": exit_code})

    def record_model_choice(self, decision_id: str, choice: dict[str, Any], *, baseline_target: str) -> None:
        _identifier(baseline_target)
        if set(choice) != {"target", "source", "reason", "confidence", "latency_ms", "cost_usd"}:
            raise ValueError("invalid model choice record")
        for key in ("target", "source", "reason"):
            _identifier(choice[key])
        for key in ("confidence", "latency_ms", "cost_usd"):
            _numeric(choice[key])
        self._event(decision_id, "model_choice", {"choice": choice, "baseline_target": baseline_target})

    def bind_session(self, decision_id: str, session_id: str) -> None:
        _identifier(session_id)
        if session_id is None:
            raise ValueError("session binding needs an identity")
        self._event(decision_id, "session_binding", {"session_id": session_id})

    def get(self, decision_id: str) -> dict[str, Any]:
        """Inspect one selection without exposing a prompt or creating a ledger."""
        _identifier(decision_id)
        if not self.path.exists():
            raise ValueError("unknown decision id in this ledger")
        with self._connect() as connection:
            row = connection.execute("SELECT record FROM decisions WHERE id = ?", (decision_id,)).fetchone()
        if row is None:
            raise ValueError("unknown decision id in this ledger")
        return json.loads(row[0])

    def mark_probe(self, decision_id: str) -> None:
        """Classify an old selection-only probe without rewriting its selection.

        A selection with any execution, binding or outcome cannot be hidden as a
        probe. The correction is retained as a separate, idempotent event.
        """
        self.get(decision_id)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            kinds = {row[0] for row in connection.execute("SELECT kind FROM events WHERE decision_id = ?", (decision_id,))}
            if kinds - {"probe", "model_choice"}:
                raise ValueError("only a selection with no execution or outcome can be marked as a probe")
            if "probe" not in kinds:
                record = {"schema_version": 1, "decision_id": decision_id, "kind": "probe",
                          "created_at": datetime.now(timezone.utc).isoformat()}
                connection.execute("INSERT INTO events (decision_id, kind, record) VALUES (?, 'probe', ?)", (decision_id, json.dumps(record)))

    def inherit(self, decision_id: str, *, parent_session_id: str) -> str:
        """Carry a launch setting to a new session with its own decision identity.

        No new judgment is implied. Manual changes are a separate host action.
        """
        _identifier(parent_session_id)
        if not parent_session_id:
            raise ValueError("a continuation needs its source session identity")
        original = self.get(decision_id)
        with self._connect() as connection:
            marked_probe = connection.execute("SELECT 1 FROM events WHERE decision_id = ? AND kind = 'probe'", (decision_id,)).fetchone()
        if marked_probe or original["dry_run"] or original["mode"] != "auto" or not original["apply_effort"] or not original["effective_effort"]:
            raise ValueError("only an applied automatic selection can be inherited")
        trace = replace(TraceContext(**original["trace"]), session_id=None,
                        parent_session_id=parent_session_id, parent_decision_id=decision_id)
        return self.record_selection(
            Decision(original["effective_effort"], "fallback", "inherited_selection"),
            model=original["model"], target=original["target"], adapter=original["adapter"],
            allowed_efforts=tuple(original["allowed_efforts"]),
            fallback_effort=original["fallback_effort"], threshold=original["confidence_threshold"],
            current_effort=original["effective_effort"], trace=trace, model_source="caller",
        )

    def record_observation(
        self, decision_id: str, *, session_id: str, turn_id: str,
        status: str, model: str | None = None, effort: str | None = None,
        tokens: int | None = None, elapsed_ms: float | None = None,
    ) -> None:
        """Store measured execution separately from host-reported acceptance.

        Token counts are cumulative for a session; reports use the newest value
        for each session rather than adding repeated completion notifications.
        """
        _identifier(session_id)
        _identifier(turn_id)
        if not session_id or not turn_id or status not in ("completed", "failed", "interrupted"):
            raise ValueError("invalid execution observation")
        if model is not None and (not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_./:-]{1,200}", model)):
            raise ValueError("observation model must be a model identifier")
        if effort is not None and effort not in EFFORTS:
            raise ValueError("unknown observed effort")
        _numeric(tokens, integer=True)
        _numeric(elapsed_ms)
        self._event(decision_id, "observation", {
            "session_id": session_id, "turn_id": turn_id, "status": status,
            "model": model, "effort": effort, "tokens": tokens, "elapsed_ms": elapsed_ms,
        })

    def record_outcome(
        self, decision_id: str, *, acceptance: str, evidence_id: str | None = None,
        tokens: int | None = None, agent_cost_usd: float | None = None,
        retries: int | None = None, elapsed_ms: float | None = None,
    ) -> None:
        if acceptance not in ("passed", "failed", "unknown"):
            raise ValueError("acceptance must be passed, failed, or unknown")
        _identifier(evidence_id)
        if acceptance != "unknown" and evidence_id is None:
            raise ValueError("passed or failed acceptance needs an evidence id")
        _numeric(tokens, integer=True)
        _numeric(retries, integer=True)
        _numeric(agent_cost_usd)
        _numeric(elapsed_ms)
        self._event(decision_id, "outcome", {
            "acceptance": acceptance, "evidence_id": evidence_id,
            "verification_source": "host_reported", "tokens": tokens,
            "agent_cost_usd": agent_cost_usd, "retries": retries,
            "elapsed_ms": elapsed_ms,
        })

    def export(self) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return
        with self._connect() as connection:
            connection.execute("BEGIN")
            for (payload,) in connection.execute("SELECT record FROM decisions ORDER BY rowid"):
                record = json.loads(payload)
                yield {"kind": "selection", **record}
                for (event,) in connection.execute("SELECT record FROM events WHERE decision_id = ? ORDER BY seq", (record["decision_id"],)):
                    yield json.loads(event)

    def summary(self, *, project_id: str | None = None, trial_id: str | None = None) -> dict[str, Any]:
        _identifier(project_id)
        _identifier(trial_id)
        selections, outcomes, executions, choices, observations = {}, {}, {}, {}, {}
        probes = set()
        for record in self.export():
            identity = record["decision_id"]
            if record["kind"] == "selection":
                selections[identity] = record
            elif record["kind"] == "outcome":
                outcomes[identity] = record
            elif record["kind"] == "execution":
                executions[identity] = record
            elif record["kind"] == "model_choice":
                choices[identity] = record["choice"]
            elif record["kind"] == "observation":
                observations.setdefault(identity, {})[record["session_id"]] = record
            elif record["kind"] == "probe":
                probes.add(identity)
        groups: dict[tuple, list] = {}
        dry_runs = 0
        for identity, selection in selections.items():
            if project_id is not None and selection["trace"]["project_id"] != project_id or trial_id is not None and selection["trace"]["trial_id"] != trial_id:
                continue
            if selection["dry_run"] or identity in probes:
                dry_runs += 1
                continue
            source = (selection["decision"] or {}).get("source", "none")
            key = (selection["mode"], selection["model"], selection["effective_effort"], source, selection["model_source"], selection["trace"]["role"])
            groups.setdefault(key, []).append((selection, outcomes.get(identity), executions.get(identity)))
        latest_observations, session_groups = {}, {}
        for key, samples in groups.items():
            for selection, _, _ in samples:
                for sid, observation in observations.get(selection["decision_id"], {}).items():
                    session_groups.setdefault(sid, set()).add(key)
                    if sid not in latest_observations or observation["created_at"] > latest_observations[sid]["created_at"]:
                        latest_observations[sid] = observation
        rows = []
        for (mode, model, effort, source, model_source, role), samples in groups.items():
            verdicts = Counter(outcome["acceptance"] if outcome else "unknown" for _, outcome, _ in samples)
            costs = [o["agent_cost_usd"] for _, o, _ in samples if o and o["agent_cost_usd"] is not None]
            judge_costs = [s["decision"]["cost_usd"] for s, _, _ in samples if s["decision"] and s["decision"]["cost_usd"] is not None]
            token_values = [o["tokens"] for _, o, _ in samples if o and o["tokens"] is not None]
            model_costs = [choices[s["decision_id"]]["cost_usd"] for s, _, _ in samples if s["decision_id"] in choices and choices[s["decision_id"]]["cost_usd"] is not None]
            retry_values = [o["retries"] for _, o, _ in samples if o and o["retries"] is not None]
            elapsed_values = [o["elapsed_ms"] if o and o["elapsed_ms"] is not None else e["elapsed_ms"] for _, o, e in samples if (o and o["elapsed_ms"] is not None) or (e and e["elapsed_ms"] is not None)]
            group_observations = {}
            for selection, _, _ in samples:
                for sid, observation in observations.get(selection["decision_id"], {}).items():
                    if sid not in group_observations or observation["created_at"] > group_observations[sid]["created_at"]:
                        group_observations[sid] = observation
            observed = list(group_observations.values())
            # A cumulative session total cannot be allocated to multiple effort
            # or model groups. Keep those group totals unknown; the report-level
            # measurement still counts that native session once.
            observed_tokens = [o["tokens"] for o in observed if o["tokens"] is not None and len(session_groups[o["session_id"]]) == 1]
            rows.append({
                "mode": mode, "model": model, "effective_effort": effort, "source": source, "model_source": model_source, "role": role,
                "decisions": len(samples), "acceptance_passed": verdicts["passed"],
                "acceptance_failed": verdicts["failed"], "acceptance_unknown": verdicts["unknown"],
                "executions_observed": sum(e is not None for _, _, e in samples),
                "known_agent_cost_usd": sum(costs) if costs else None, "agent_cost_samples": len(costs),
                "known_judge_cost_usd": sum(judge_costs) if judge_costs else None, "judge_cost_samples": len(judge_costs),
                "known_tokens": sum(token_values) if token_values else None, "token_samples": len(token_values),
                "known_model_judge_cost_usd": sum(model_costs) if model_costs else None, "model_judge_cost_samples": len(model_costs),
                "known_retries": sum(retry_values) if retry_values else None, "retry_samples": len(retry_values),
                "mean_elapsed_ms": sum(elapsed_values) / len(elapsed_values) if elapsed_values else None,
                "elapsed_samples": len(elapsed_values),
                "selection_only": sum(e is None and not observations.get(s["decision_id"]) for s, _, e in samples),
                "launch_errors": sum(e is not None and e["status"] == "launch_error" for _, _, e in samples),
                "missing_outcomes": sum(o is None for _, o, _ in samples),
                "fallback_reasons": dict(Counter(s["reason"] for s, _, _ in samples if (s["decision"] or {}).get("source") == "fallback")),
                "proposed_efforts": dict(Counter(s["decision"]["proposed_effort"] for s, _, _ in samples if s["decision"] and s["decision"].get("proposed_effort"))),
                "observed_sessions": len(observed),
                "known_observed_tokens": sum(observed_tokens) if observed_tokens else None,
                "observed_token_samples": len(observed_tokens),
                "shared_session_token_samples_excluded": sum(len(session_groups[o["session_id"]]) > 1 for o in observed),
                "effort_mismatches": sum(o["effort"] is not None and o["effort"] != effort for o in observed),
                "model_mismatches": sum(o["model"] is not None and o["model"] != model for o in observed),
            })
        result = {"schema_version": 1, "decisions": sum(row["decisions"] for row in rows), "dry_runs": dry_runs, "groups": rows}
        if latest_observations:
            measured_tokens = [o["tokens"] for o in latest_observations.values() if o["tokens"] is not None]
            result["observations"] = {"sessions": len(latest_observations),
                                      "known_tokens": sum(measured_tokens) if measured_tokens else None,
                                      "token_samples": len(measured_tokens)}
        return result

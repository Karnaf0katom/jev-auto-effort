"""An effort hook for agent-control tools, with per-request modes and native patches."""
from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import Any

from .core import Decision, EffortRouter, Policy
from .profiles import Config, Target
from .telemetry import DecisionLedger, TraceContext


@dataclass(frozen=True)
class Selection:
    target_name: str
    target: Target
    mode: str
    decision: Decision | None
    apply_effort: bool
    reason: str
    settings: dict[str, Any]
    cli_args: list[str]
    decision_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": 1, "target": self.target_name, "model": self.target.model,
            "mode": self.mode, "apply_effort": self.apply_effort, "reason": self.reason,
            "decision": self.decision.to_dict() if self.decision else None,
            "settings": copy.deepcopy(self.settings), "cli_args": list(self.cli_args),
        }
        if self.decision_id is not None:
            result["decision_id"] = self.decision_id
        return result

    def apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Copy a native request and patch effort only; never alter its model or content."""
        if not isinstance(payload, dict):
            raise ValueError("native payload must be an object")
        result = copy.deepcopy(payload)
        if not self.apply_effort:
            return result
        if payload.get("model") != self.target.model:
            raise ValueError("native request model does not match the configured target")
        _merge(result, self.settings)
        return result


def _merge(destination: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, dict):
            if destination.get(key) is None:
                destination[key] = {}
            if not isinstance(destination[key], dict):
                raise ValueError("native effort settings conflict with the configured adapter")
            _merge(destination[key], value)
        else:
            destination[key] = value


class AgentController:
    """The host calls select() immediately before each model request or agent launch.

    No agent process, transcript reader, provider proxy, or automatic global hook is
    started. Each call is independent, including subagent requests with their own target.
    """

    def __init__(self, config: Config, decider=None, *, ledger: DecisionLedger | None = None) -> None:
        self.config = config
        self.decider = config.make_backend() if decider is None else decider
        self.ledger = ledger

    def select(
        self, request: str, *, target: str | None = None, context: str = "",
        previous_reply: str = "", current_effort: str | None = None,
        effort: str = "auto", private: bool = False, mode: str | None = None,
        trace: TraceContext | None = None, dry_run: bool = False, model_source: str = "caller",
    ) -> Selection:
        if trace is not None and not isinstance(trace, TraceContext):
            raise ValueError("trace must be a TraceContext")
        if not isinstance(dry_run, bool):
            raise ValueError("dry_run must be a boolean")
        if model_source not in ("caller", "manual", "jev", "fallback"):
            raise ValueError("unknown model selection source")
        selection = self._select(
            request, target=target, context=context, previous_reply=previous_reply,
            current_effort=current_effort, effort=effort, private=private, mode=mode,
        )
        if self.ledger is None:
            return selection
        identity = self.ledger.record_selection(
            selection.decision, model=selection.target.model, target=selection.target_name,
            adapter=selection.target.adapter, mode=selection.mode,
            apply_effort=selection.apply_effort, current_effort=current_effort,
            allowed_efforts=selection.target.levels, fallback_effort=selection.target.fallback,
            threshold=self.config.confidence_threshold, reason=selection.reason,
            trace=trace, dry_run=dry_run, model_source=model_source,
        )
        return replace(selection, decision_id=identity)

    def _select(
        self, request: str, *, target: str | None = None, context: str = "",
        previous_reply: str = "", current_effort: str | None = None,
        effort: str = "auto", private: bool = False, mode: str | None = None,
    ) -> Selection:
        name = target or self.config.default_target
        if name not in self.config.targets:
            raise ValueError("unknown configured target")
        selected = self.config.targets[name]
        mode = self.config.mode if mode is None else mode
        if mode not in ("off", "shadow", "auto"):
            raise ValueError("mode must be off, shadow, or auto")
        if not isinstance(private, bool):
            raise ValueError("private must be a boolean")
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a nonempty string")
        if selected.adapter == "disabled":
            if effort != "auto":
                raise ValueError("this target has no declared effort control")
            return Selection(name, selected, mode, None, False, "unsupported_target", {}, [])
        policy = Policy(selected.levels, selected.fallback, self.config.confidence_threshold)
        router = EffortRouter(self.decider, policy)
        if effort == "auto" and mode == "off":
            # Validate the baseline without a judge call, then leave the host untouched.
            router.pick(request, context=context, previous_reply=previous_reply, current_effort=current_effort, effort=current_effort or selected.fallback)
            return Selection(name, selected, mode, None, False, "router_off", {}, [])
        decision = router.pick(
            request, context=context, previous_reply=previous_reply,
            current_effort=current_effort, effort=effort, private=private,
        )
        applied = effort != "auto" or mode == "auto"
        settings, args = selected.patch(decision.effort) if applied else ({}, [])
        return Selection(name, selected, mode, decision, applied, decision.reason if applied else "shadow_mode", settings, args)

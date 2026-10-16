import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from auto_effort import EffortRouter, JevCLIBackend, TypeSafeBackend


def test_cli_keeps_state_off_process_arguments(monkeypatch):
    state = {"request": "Literal $(no shell)", "context": "Caller summary"}
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, '{"answers":{}}', ""))
    monkeypatch.setattr(subprocess, "run", runner)
    assert JevCLIBackend("/path with spaces/jev")(state, {"effort": {"type": "choice"}}) == {"answers": {}}
    assert state["request"] not in runner.call_args.args[0]
    assert runner.call_args.args[0][0] == "/path with spaces/jev"
    assert json.loads(runner.call_args.kwargs["input"]) == state
    assert runner.call_args.kwargs["timeout"] == 5.0
    assert runner.call_args.kwargs["shell"] is False


def test_nonzero_cli_error_is_not_leaked(monkeypatch):
    runner = Mock(return_value=subprocess.CompletedProcess([], 1, "private", "token"))
    monkeypatch.setattr(subprocess, "run", runner)
    result = EffortRouter(JevCLIBackend()).pick("Fix a typo")
    assert result.reason == "judge_unavailable"
    assert "token" not in json.dumps(result.to_dict())


def test_timeout_uses_fallback(monkeypatch):
    runner = Mock(side_effect=subprocess.TimeoutExpired("jev", 0.01, "private body"))
    monkeypatch.setattr(subprocess, "run", runner)
    assert EffortRouter(JevCLIBackend(timeout=0.01)).pick("Fix a typo").reason == "judge_unavailable"


def test_sdk_uses_official_client_context_and_no_retries(monkeypatch):
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.system_one.return_value.model_dump.return_value = {"answers": {}}
    factory, retry = Mock(return_value=client), Mock()
    monkeypatch.setitem(sys.modules, "typesafe_sdk", SimpleNamespace(TypeSafeClient=factory, RetryPolicy=retry))
    state, questions = {"request": "Fix a typo"}, {"effort": {"type": "choice"}}
    assert TypeSafeBackend(timeout=2)(state, questions) == {"answers": {}}
    retry.assert_called_once_with(max_retries=0)
    factory.assert_called_once_with(model="jev-1.13.0", timeout=2, retry=retry.return_value)
    client.system_one.assert_called_once_with(state=state, questions=questions)
    client.__exit__.assert_called_once()


@pytest.mark.parametrize("backend", [JevCLIBackend, TypeSafeBackend])
@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True, 10 ** 400])
def test_invalid_timeout_is_rejected(backend, timeout):
    with pytest.raises(ValueError):
        backend(timeout=timeout)

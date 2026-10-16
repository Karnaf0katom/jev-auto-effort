import io
import json
import os
import subprocess
import sys
from unittest.mock import Mock

import pytest

from auto_effort.cli import main


def judgment(choice="low", confidence=0.99):
    return {"answers": {"effort": {"choice": choice, "confidence": confidence}}}


@pytest.mark.parametrize("fmt, expected", [
    ("json", "low"), ("effort", "low"), ("codex", ["-c", 'model_reasoning_effort="low"']),
    ("responses", {"reasoning": {"effort": "low"}}),
])
def test_portable_output_formats(monkeypatch, capsys, fmt, expected):
    backend = Mock(return_value=judgment())
    monkeypatch.setattr("auto_effort.cli.TypeSafeBackend", lambda *args: backend)
    assert main(["pick", "Fix a typo", "--format", fmt]) == 0
    stdout = capsys.readouterr().out
    value = stdout.strip() if fmt == "effort" else json.loads(stdout)
    assert (value["effort"] if fmt == "json" else value) == expected


def test_stdin_json_text_remains_a_request_not_configuration(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"request": "hi", "effort": "max"}'))
    assert main(["pick", "--private"]) == 0
    assert json.loads(capsys.readouterr().out)["effort"] == "medium"


def test_file_request_and_manual_override(tmp_path, capsys):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Diagnose the issue", encoding="utf-8")
    assert main(["pick", "--request-file", str(prompt), "--effort", "high"]) == 0
    assert json.loads(capsys.readouterr().out)["source"] == "manual"


def test_conflicting_inputs_are_rejected(tmp_path, capsys):
    assert main(["pick", "request", "--request-file", str(tmp_path / "file")]) == 2
    assert capsys.readouterr().out == ""


def test_launch_plan_hides_request_and_does_not_start_agent(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("Fix a typo"))
    runner = Mock(side_effect=AssertionError("must not launch"))
    monkeypatch.setattr(subprocess, "run", runner)
    assert main(["run", "--model", "caller-model", "--effort", "low", "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["argv"] == ["codex", "exec", "--model", "caller-model", "-c", 'model_reasoning_effort="low"', "-"]
    assert plan["request_via"] == "stdin"
    assert "Fix a typo" not in str(plan)
    runner.assert_not_called()


def test_run_applies_jev_choice_to_agent_and_preserves_prompt(monkeypatch, capsys):
    prompt = "Fix a typo; $(touch /tmp/should-never-exist)"
    monkeypatch.setattr(sys, "stdin", io.StringIO(prompt))
    monkeypatch.setattr("auto_effort.cli.TypeSafeBackend", lambda *args: Mock(return_value=judgment("high")))
    runner = Mock(return_value=subprocess.CompletedProcess([], 7))
    monkeypatch.setattr(subprocess, "run", runner)
    assert main(["run", "--model", "caller-model"]) == 7
    command = runner.call_args.args[0]
    assert 'model_reasoning_effort="high"' in command
    assert prompt not in command
    assert runner.call_args.kwargs["input"] == prompt
    assert runner.call_args.kwargs["shell"] is False
    assert json.loads(capsys.readouterr().err)["auto_effort"]["source"] == "jev"


def test_provider_failure_does_not_prevent_agent_launch(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("Fix a typo"))
    monkeypatch.setattr("auto_effort.cli.TypeSafeBackend", lambda *args: Mock(side_effect=TimeoutError("private value")))
    runner = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(subprocess, "run", runner)
    assert main(["run", "--model", "caller-model", "--current", "high"]) == 0
    assert 'model_reasoning_effort="high"' in runner.call_args.args[0]
    output = capsys.readouterr().err
    assert "private value" not in output
    assert json.loads(output)["auto_effort"]["reason"] == "judge_unavailable"


@pytest.mark.skipif(os.name == "nt", reason="the fake shebang executables exercise POSIX launch semantics")
def test_actual_jev_cli_protocol_and_agent_launch(tmp_path, monkeypatch, capsys):
    # Real subprocesses exercise stdin, argv quoting, and the eventual consumer.
    judge = tmp_path / "jev"
    judge.write_text(
        '#!' + sys.executable + '\n'
        'import json, sys\n'
        'state = json.load(sys.stdin)\n'
        'questions = json.loads(sys.argv[sys.argv.index("--questions") + 1])\n'
        'assert state["request"] == "Fix a typo"\n'
        'assert "other" in questions["effort"]["criteria"]\n'
        'print(json.dumps({"answers":{"effort":{"choice":"low","confidence":0.99}}}))\n',
        encoding="utf-8",
    )
    judge.chmod(0o755)
    agent = tmp_path / "codex"
    agent.write_text(
        '#!' + sys.executable + '\n'
        'import sys\n'
        'assert sys.argv[1:] == ["exec", "--model", "caller-model", "-c", \'model_reasoning_effort="low"\', "-"]\n'
        'assert sys.stdin.read() == "Fix a typo"\n'
        'print("FAKE-AGENT-PASS")\n',
        encoding="utf-8",
    )
    agent.chmod(0o755)
    monkeypatch.setattr(sys, "stdin", io.StringIO("Fix a typo"))
    assert main([
        "run", "--model", "caller-model", "--backend", "jev-cli",
        "--jev-command", str(judge), "--codex-command", str(agent),
    ]) == 0
    assert json.loads(capsys.readouterr().err)["auto_effort"]["effort"] == "low"

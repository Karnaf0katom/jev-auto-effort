import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from auto_effort.models import ModelOption
from auto_effort.terminal import configuration, launch_argv, main


OPTIONS = tuple(ModelOption(slug, name, levels, "medium", "codex") for name, slug, levels in (
    ("Sol", "gpt-6.1-sol", ("low", "medium", "high", "xhigh", "max", "ultra")),
    ("Luna", "gpt-6-luna", ("low", "medium", "high", "xhigh", "max")),
    ("Astra", "gpt-6-astra", ("low", "medium", "high", "xhigh", "max", "ultra")),
))


@pytest.fixture
def terminal(monkeypatch):
    judge = Mock(side_effect=[
        {"answers": {"model": {"choice": "luna", "confidence": 0.99}}},
        {"answers": {"effort": {"choice": "low", "confidence": 0.99}}},
    ])
    monkeypatch.setattr("auto_effort.terminal.discover_codex_models", lambda command: OPTIONS)
    monkeypatch.setattr("auto_effort.terminal.shutil.which", lambda command: "/test/codex")
    monkeypatch.setattr("auto_effort.profiles.JevCLIBackend", lambda *args: judge)
    execute = Mock()
    monkeypatch.setattr("auto_effort.terminal.os.execv", execute)
    return judge, execute


def test_quoted_prompt_and_herdr_environment_survive_terminal_launch(terminal, monkeypatch, capsys):
    judge, execute = terminal
    monkeypatch.setenv("HERDR_PANE_ID", "pane:test")
    prompt = '--model fake; $(touch nope) "quoted"\nשורה שנייה'
    cwd = os.getcwd()
    assert main(["--", prompt]) == 0
    assert execute.call_args.args == ("/test/codex", [
        "/test/codex", "--model", "gpt-6-luna", "-c", 'model_reasoning_effort="low"',
        "--yolo", "--", prompt,
    ])
    assert os.environ["HERDR_PANE_ID"] == "pane:test"
    assert os.getcwd() == cwd
    assert judge.call_args_list[0].args[0]["request"] == prompt
    assert judge.call_count == 2
    assert prompt not in capsys.readouterr().err


def test_private_dry_run_uses_fallback_without_judge_or_launch(terminal, capsys):
    judge, execute = terminal
    assert main(["--private", "--dry-run", "Sensitive task"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert (plan["model"], plan["effort"], plan["launch"]) == ("gpt-6.1-sol", "medium", False)
    assert "Sensitive task" not in str(plan)
    judge.assert_not_called()
    execute.assert_not_called()


def test_manual_model_and_deeper_effort_skip_both_judges(terminal):
    judge, execute = terminal
    assert main(["--model", "astra", "--effort", "ultra", "Analyze the proof"]) == 0
    command = execute.call_args.args[1]
    assert command[command.index("--model") + 1] == "gpt-6-astra"
    assert 'model_reasoning_effort="ultra"' in command
    judge.assert_not_called()


def test_manual_model_still_selects_effort(terminal):
    judge, execute = terminal
    judge.side_effect = [{"answers": {"effort": {"choice": "high", "confidence": 0.99}}}]
    assert main(["-m", "sol", "Investigate the bug"]) == 0
    assert judge.call_count == 1
    assert 'model_reasoning_effort="high"' in execute.call_args.args[1]


def test_provider_failure_keeps_launch_available_and_does_not_echo_error(terminal, capsys):
    judge, execute = terminal
    judge.side_effect = RuntimeError("private provider detail")
    assert main(["Fix the bug"]) == 0
    command = execute.call_args.args[1]
    assert "gpt-6.1-sol" in command
    assert 'model_reasoning_effort="medium"' in command
    output = capsys.readouterr().err
    assert "fallback" in output
    assert "private provider detail" not in output


def test_low_confidence_model_and_effort_keep_medium_baseline(terminal):
    judge, execute = terminal
    judge.side_effect = [
        {"answers": {"model": {"choice": "astra", "confidence": 0.4}}},
        {"answers": {"effort": {"choice": "high", "confidence": 0.4}}},
    ]
    assert main(["Unclear task"]) == 0
    assert "gpt-6.1-sol" in execute.call_args.args[1]
    assert 'model_reasoning_effort="medium"' in execute.call_args.args[1]


@pytest.mark.parametrize("prompt", ["api_key=sk-proj-" + "A" * 30, "a" * 12_001])
def test_package_privacy_and_size_guards_are_reused(terminal, prompt):
    judge, execute = terminal
    assert main([prompt]) == 0
    judge.assert_not_called()
    assert 'model_reasoning_effort="medium"' in execute.call_args.args[1]


@pytest.mark.parametrize("argv", [[], [" "], ["--model", "invented", "Task"],
    ["--model", "luna", "--effort", "ultra", "Task"], ["Task\0invalid"]])
def test_invalid_input_never_reaches_judge_or_launcher(terminal, argv):
    judge, execute = terminal
    assert main(argv) == 2
    judge.assert_not_called()
    execute.assert_not_called()


def test_file_input_is_preserved_and_conflicting_inputs_are_rejected(terminal, tmp_path):
    judge, execute = terminal
    source = tmp_path / "task.txt"
    source.write_text("First line\nSecond line\n", encoding="utf-8")
    assert main(["--request-file", str(source), "--no-yolo"]) == 0
    assert execute.call_args.args[1][-1] == source.read_text()
    assert "--yolo" not in execute.call_args.args[1]
    judge.reset_mock()
    execute.reset_mock()
    assert main(["Task", "--request-file", str(source)]) == 2
    judge.assert_not_called()
    execute.assert_not_called()


def test_discovery_failure_stops_before_paid_selection(terminal, monkeypatch):
    judge, execute = terminal
    def fail(*args):
        raise ValueError("Codex model discovery failed")
    monkeypatch.setattr("auto_effort.terminal.discover_codex_models", fail)
    assert main(["Task"]) == 2
    judge.assert_not_called()
    execute.assert_not_called()


def test_only_advertised_models_and_auto_efforts_are_eligible():
    config, routes = configuration(OPTIONS[:1], None, "auto", "jev")
    assert set(routes) == {"sol"}
    assert config.targets["sol"].levels == ("low", "medium", "high")
    assert routes["sol"]["role"] == "controller"
    with pytest.raises(ValueError, match="fallback"):
        configuration(OPTIONS[1:], None, "auto", "jev")


def test_failed_exec_is_recorded_as_launch_error(terminal, monkeypatch):
    from auto_effort.telemetry import DecisionLedger
    _, execute = terminal
    execute.side_effect = OSError("exec failed")
    assert main(["--private", "Task"]) == 2
    events = list(DecisionLedger().export())
    assert events[-1]["kind"] == "execution"
    assert events[-1]["status"] == "launch_error"


@pytest.mark.skipif(os.name == "nt", reason="execv and the terminal shortcut are exercised on POSIX")
def test_real_process_replacement_keeps_prompt_terminal_and_environment(tmp_path):
    """Run the complete CLI with fake RPC/judge/agent executables, not a shell."""
    fake = tmp_path / "codex"
    fake.write_text('#!' + sys.executable + '''
import json, os, sys
if sys.argv[1:] == ["app-server"]:
    for line in sys.stdin:
        msg = json.loads(line)
        if msg["method"] == "initialize":
            print(json.dumps({"id": msg["id"], "result": {}}), flush=True)
        elif msg["method"] == "model/list":
            print(json.dumps({"id": msg["id"], "result": {"data": [{
                "model": "gpt-6.1-sol", "defaultReasoningEffort": "medium",
                "supportedReasoningEfforts": [{"reasoningEffort": level} for level in ("low", "medium", "high")]
            }], "nextCursor": None}}), flush=True)
else:
    print(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "pane": os.environ["HERDR_PANE_ID"], "pid": os.getpid()}))
''', encoding="utf-8")
    fake.chmod(0o755)
    prompt = '--model fake; $(touch never-created) "quotes"\nשלום'
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
           "HERDR_PANE_ID": "test-pane", "AUTO_EFFORT_LEDGER": str(tmp_path / "ledger.sqlite3")}
    proc = subprocess.Popen([sys.executable, "-m", "auto_effort.terminal", "--private",
                             "--codex-command", str(fake), "--", prompt],
                            cwd=tmp_path, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, errors = proc.communicate(timeout=20)
    assert proc.returncode == 0, errors
    receipt = json.loads(output)
    assert receipt["pid"] == proc.pid
    assert receipt["argv"][-2:] == ["--", prompt]
    assert "exec" not in receipt["argv"]
    assert receipt["pane"] == "test-pane"
    assert receipt["cwd"] == str(tmp_path)
    assert not (tmp_path / "never-created").exists()

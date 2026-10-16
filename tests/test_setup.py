import io
import json
import os
import subprocess
import sys
from unittest.mock import Mock

import pytest

from auto_effort import AgentController, Config, Target
from auto_effort.cli import main
from auto_effort.models import ModelOption, discover_codex_models, parse_codex_models


def test_preferred_model_picker_has_requested_versions_without_claiming_access(capsys):
    assert main(["models"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert {row["model"] for row in result["models"]} == {"gpt-6-astra", "gpt-6.1-sol", "gpt-6-luna"}
    assert result["availability"] == "not_checked"
    assert all(row["source"] == "documented" for row in result["models"])


def test_codex_capabilities_win_over_documented_presets():
    rows = [
        {"model": "gpt-6.1-sol", "defaultReasoningEffort": "low", "supportedReasoningEfforts": [{"reasoningEffort": level} for level in ("low", "high", "ultra")]},
        {"model": "gpt-6-astra", "hidden": True, "supportedReasoningEfforts": [{"reasoningEffort": "high"}]},
        {"model": "fixed-model", "supportedReasoningEfforts": []},
        {"model": "new-model", "supportedReasoningEfforts": [{"reasoningEffort": "unknown"}, {"reasoningEffort": "medium"}]},
        None,
    ]
    options = parse_codex_models(rows)
    assert [(row.model, row.levels, row.default_effort) for row in options] == [
        ("gpt-6.1-sol", ("low", "high", "ultra"), "low"),
        ("new-model", ("medium",), "medium"),
    ]


@pytest.mark.skipif(os.name == "nt", reason="POSIX fake executable; parser and setup are cross-platform")
def test_real_discovery_handshake_and_pagination_never_start_an_agent(tmp_path):
    fake = tmp_path / "codex"
    fake.write_text(
        '#!' + sys.executable + '\n'
        'import json, sys\n'
        'assert sys.argv[1:] == ["app-server"]\n'
        'init = json.loads(sys.stdin.readline())\n'
        'assert init["method"] == "initialize"\n'
        'print(json.dumps({"id": init["id"], "result": {}}), flush=True)\n'
        'assert json.loads(sys.stdin.readline())["method"] == "initialized"\n'
        'for page in range(2):\n'
        '    msg = json.loads(sys.stdin.readline())\n'
        '    assert msg["method"] == "model/list"\n'
        '    assert msg["params"]["includeHidden"] is False\n'
        '    if page: assert msg["params"]["cursor"] == "page-2"\n'
        '    model = "gpt-6.1-sol" if page == 0 else "gpt-6-luna"\n'
        '    print(json.dumps({"id": msg["id"], "result": {"data": [{"model": model, "supportedReasoningEfforts": [{"reasoningEffort": "high"}]}], "nextCursor": "page-2" if page == 0 else None}}), flush=True)\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    options = discover_codex_models(str(fake), timeout=3)
    assert [option.model for option in options] == ["gpt-6.1-sol", "gpt-6-luna"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX fake executable")
def test_discovery_errors_do_not_echo_provider_messages(tmp_path):
    fake = tmp_path / "codex"
    fake.write_text('#!' + sys.executable + '\nimport json, sys\nmsg=json.loads(sys.stdin.readline())\nprint(json.dumps({"id":msg["id"],"error":{"message":"private provider diagnostic"}}),flush=True)\n', encoding="utf-8")
    fake.chmod(0o755)
    with pytest.raises(ValueError, match="discovery failed") as error:
        discover_codex_models(str(fake), timeout=3)
    assert "private provider diagnostic" not in str(error.value)


@pytest.mark.skipif(os.name == "nt", reason="POSIX fake executable and process liveness check")
def test_discovery_timeout_reaps_its_metadata_process(tmp_path):
    fake = tmp_path / "codex"
    fake.write_text('#!' + sys.executable + '\nimport os, pathlib, sys\npathlib.Path(sys.argv[0] + ".pid").write_text(str(os.getpid()))\nsys.stdin.readline()\nsys.stdin.readline()\n', encoding="utf-8")
    fake.chmod(0o755)
    with pytest.raises(ValueError, match="timed out"):
        discover_codex_models(str(fake), timeout=0.5)
    pid = int((tmp_path / "codex.pid").read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.parametrize("timeout", [0, -1, True, float("inf"), float("nan"), 61])
def test_invalid_discovery_timeout_never_starts_a_process(monkeypatch, timeout):
    start = Mock(side_effect=AssertionError("must not start"))
    monkeypatch.setattr(subprocess, "Popen", start)
    with pytest.raises(ValueError):
        discover_codex_models(timeout=timeout)
    start.assert_not_called()


def test_codex_setup_uses_discovered_support_and_manual_model_alias(tmp_path, monkeypatch, capsys):
    discovery = Mock(return_value=(ModelOption("gpt-6.1-sol", "Sol", ("low", "high", "ultra"), "low", "codex"),))
    monkeypatch.setattr("auto_effort.setup.discover_codex_models", discovery)
    path = tmp_path / "config.json"
    assert main(["setup", "--host", "codex", "--model", "sol", "--backend", "jev-cli", "--config", str(path)]) == 0
    target = Config.load(path).targets["default"]
    assert (target.model, target.levels, target.fallback) == ("gpt-6.1-sol", ("low", "high"), "low")
    assert json.loads(capsys.readouterr().out)["next"][-1] == str(path)
    discovery.assert_called_once()


def test_missing_codex_model_is_rejected_without_writing_config(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("auto_effort.setup.discover_codex_models", lambda *args: (ModelOption("gpt-6-luna", "Luna", ("medium",), "medium"),))
    path = tmp_path / "config.json"
    assert main(["setup", "--host", "codex", "--model", "astra", "--backend", "typesafe", "--config", str(path)]) == 2
    assert not path.exists()


def test_interactive_picker_consumes_choices_without_judging_a_request(tmp_path, monkeypatch, capsys):
    stream = io.StringIO("2\n1\n2\n")  # OpenAI, OpenRouter, Luna.
    monkeypatch.setattr(stream, "isatty", lambda: True)
    monkeypatch.setattr(sys, "stdin", stream)
    path = tmp_path / "picked.json"
    assert main(["setup", "--config", str(path)]) == 0
    target = Config.load(path).targets["default"]
    assert (target.model, target.adapter, target.levels) == ("gpt-6-luna", "responses", ("low", "medium", "high"))
    assert "Choose your model" in capsys.readouterr().err


def test_noninteractive_setup_requires_explicit_choices(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    path = tmp_path / "config.json"
    assert main(["setup", "--config", str(path)]) == 2
    assert not path.exists()


@pytest.mark.parametrize("host, model, expected", [
    ("claude-code", "sonnet", ("claude-code", {}, ["--effort", "high"])),
    ("claude-api", "my-claude-model", ("custom", {"output_config": {"effort": "high"}}, [])),
    ("grok", "grok-4.7", ("responses", {"reasoning": {"effort": "high"}}, [])),
    ("antigravity", "my-selected-gemini", ("disabled", {}, [])),
])
def test_other_host_setup_has_native_settings_and_passthrough(tmp_path, host, model, expected, capsys):
    path = tmp_path / f"{host}.json"
    assert main(["setup", "--config", str(path), "--host", host, "--model", model, "--backend", "typesafe"]) == 0
    config = Config.load(path)
    judge = Mock(side_effect=AssertionError("no network"))
    selected = AgentController(config, judge).select("Task", **({} if host == "antigravity" else {"effort": "high"}))
    assert (selected.target.adapter, selected.settings, selected.cli_args) == expected
    judge.assert_not_called()
    if host == "antigravity":
        assert selected.reason == "unsupported_target"


@pytest.mark.parametrize("alias, model", [("astra", "gpt-6-astra"), ("sol", "gpt-6.1-sol"), ("luna", "gpt-6-luna")])
def test_offline_setup_preserves_existing_config_and_never_launches(tmp_path, monkeypatch, capsys, alias, model):
    path = tmp_path / "config.json"
    discovery = Mock(side_effect=AssertionError("offline"))
    monkeypatch.setattr("auto_effort.setup.discover_codex_models", discovery)
    arguments = ["setup", "--host", "codex", "--model", alias, "--levels", "low,medium,high", "--backend", "typesafe", "--config", str(path)]
    assert main(arguments) == 0
    assert Config.load(path).targets["default"].model == model
    before = path.read_bytes()
    assert main(arguments) == 2
    assert path.read_bytes() == before
    discovery.assert_not_called()


@pytest.mark.parametrize("mode, manual, expected_args", [
    ("auto", False, ["-c", 'model_reasoning_effort="medium"']),
    ("shadow", False, []),
    ("off", False, []),
    ("off", True, ["-c", 'model_reasoning_effort="high"']),
])
def test_saved_codex_launch_preserves_modes_and_forwards_original_request(tmp_path, monkeypatch, capsys, mode, manual, expected_args):
    path = tmp_path / "config.json"
    Config({"name": "typesafe"}, {"default": Target("gpt-6-luna", "codex")}, mode=mode).save(path)
    prompt = "Original request\nwith its second line."
    monkeypatch.setattr(sys, "stdin", io.StringIO(prompt))
    runner = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(subprocess, "run", runner)
    arguments = ["run", "--config", str(path), "--private", "--ephemeral", "--cwd", str(tmp_path)]
    if manual:
        arguments += ["--effort", "high"]
    assert main(arguments) == 0
    assert runner.call_args.args[0] == ["codex", "exec", "--model", "gpt-6-luna", *expected_args, "--ephemeral", "-"]
    assert runner.call_args.kwargs["input"] == prompt
    assert runner.call_args.kwargs["cwd"] == tmp_path
    assert runner.call_args.kwargs["shell"] is False


def test_claude_code_launch_uses_its_native_flag(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.json"
    Config({"name": "typesafe"}, {"default": Target("sonnet", "claude-code")}).save(path)
    monkeypatch.setattr(sys, "stdin", io.StringIO("Original task"))
    runner = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(subprocess, "run", runner)
    assert main(["run", "--config", str(path), "--effort", "low"]) == 0
    assert runner.call_args.args[0] == ["claude", "-p", "--model", "sonnet", "--effort", "low"]
    assert runner.call_args.kwargs["input"] == "Original task"


def test_api_target_cannot_be_launched_as_a_cli(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.json"
    Config({"name": "typesafe"}, {"default": Target("grok-4.7")}).save(path)
    monkeypatch.setattr(sys, "stdin", io.StringIO("Task"))
    runner = Mock(side_effect=AssertionError("must not launch"))
    monkeypatch.setattr(subprocess, "run", runner)
    assert main(["run", "--config", str(path), "--private"]) == 2
    runner.assert_not_called()


def test_claude_code_rejects_non_native_effort_levels():
    with pytest.raises(ValueError, match="native"):
        Target("model", "claude-code", levels=("none", "medium"))


def test_native_codex_schema_and_events_options_are_forwarded(tmp_path, monkeypatch, capsys):
    schema = tmp_path / "schema.json"
    monkeypatch.setattr(sys, "stdin", io.StringIO("Task"))
    assert main(["run", "--model", "luna", "--effort", "low", "--dry-run", "--json", "--skip-git-repo-check", "--output-schema", str(schema)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["argv"] == ["codex", "exec", "--model", "gpt-6-luna", "-c", 'model_reasoning_effort="low"', "--json", "--skip-git-repo-check", "--output-schema", str(schema.resolve()), "-"]


def test_agent_launch_timeout_returns_fixed_error_without_prompt_or_exception(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("private original prompt"))
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired(["private-command"], 1, output="private diagnostic")))
    assert main(["run", "--model", "luna", "--effort", "low", "--launch-timeout", "1"]) == 124
    output = capsys.readouterr()
    assert output.out == ""
    assert "agent launch timed out" in output.err
    assert "private" not in output.err


@pytest.mark.parametrize("value", ["nan", "inf", "0", "3601"])
def test_bad_launch_timeout_rejects_before_judging(monkeypatch, capsys, value):
    monkeypatch.setattr(sys, "stdin", io.StringIO("Task"))
    backend = Mock(side_effect=AssertionError("must not judge"))
    monkeypatch.setattr("auto_effort.cli.TypeSafeBackend", backend)
    assert main(["run", "--model", "luna", "--launch-timeout", value]) == 2
    backend.assert_not_called()


def test_api_launch_rejects_before_judging(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.json"
    Config({"name": "typesafe"}, {"default": Target("grok-4.7")}).save(path)
    monkeypatch.setattr(sys, "stdin", io.StringIO("Task"))
    backend = Mock(side_effect=AssertionError("must not judge"))
    monkeypatch.setattr("auto_effort.profiles.TypeSafeBackend", lambda *args: backend)
    assert main(["run", "--config", str(path)]) == 2
    backend.assert_not_called()


@pytest.mark.parametrize("option, value", [("--backend", "openrouter"), ("--levels", "high"), ("--threshold", "1")])
def test_saved_launch_cannot_silently_ignore_backend_or_policy_options(tmp_path, monkeypatch, capsys, option, value):
    path = tmp_path / "config.json"
    Config({"name": "typesafe"}, {"default": Target("gpt-6-luna", "codex")}).save(path)
    monkeypatch.setattr(sys, "stdin", io.StringIO("Task"))
    assert main(["run", "--config", str(path), option, value]) == 2
    assert "saved config" in capsys.readouterr().err

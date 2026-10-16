"""Verify a wheel in a fresh environment, without provider credentials or a checkout import."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def check_wheel(wheel: Path) -> None:
    wheel = wheel.resolve(strict=True)
    example = Path(__file__).resolve().parents[1] / "examples" / "controller.mjs"
    environment = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME", "TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "AUTO_EFFORT_CONFIG"):
        environment.pop(name, None)

    with tempfile.TemporaryDirectory(prefix="auto-effort-installed-") as directory:
        work = Path(directory)
        environment["AUTO_EFFORT_LEDGER"] = str(work / "decisions.sqlite3")
        venv = work / "venv"
        binaries = venv / ("Scripts" if os.name == "nt" else "bin")
        python = binaries / ("python.exe" if os.name == "nt" else "python")
        cli = binaries / ("auto-effort.exe" if os.name == "nt" else "auto-effort")

        def run(*command: str, input: str | None = None, expected: int = 0) -> str:
            result = subprocess.run(
                command, input=input, capture_output=True, text=True, encoding="utf-8",
                cwd=work, env=environment, timeout=90, shell=False,
            )
            if result.returncode != expected:
                raise RuntimeError(f"Installation check failed: {result.stdout}\n{result.stderr}")
            return result.stdout

        def require(condition: bool, message: str) -> None:
            if not condition:
                raise RuntimeError(message)

        run(sys.executable, "-m", "venv", str(venv))
        run(str(python), "-m", "pip", "install", "--no-deps", "--no-index", str(wheel))
        metadata = json.loads(run(str(python), "-I", "-c", (
            "import auto_effort, json; from importlib.metadata import version; "
            "from auto_effort import AgentController, Config, Target; "
            "print(json.dumps({'version': version('jev-auto-effort'), 'source': auto_effort.__file__}))"
        )))
        require(venv.resolve() in Path(metadata["source"]).resolve().parents, "Import did not come from the installed wheel")
        require(run(str(cli), "--version").strip() == f"auto-effort {metadata['version']}", "CLI version disagrees with installed metadata")
        instructions = json.loads(run(str(cli), "instructions"))
        require(instructions["skill"] == "auto-subagents" and "ccc spawn" in instructions["instructions"], "Bundled helper skill is missing from the wheel")
        manual = json.loads(run(str(cli), "pick", "Fix a typo", "--effort", "low"))
        require((manual["effort"], manual["source"]) == ("low", "manual"), "Manual selection failed")
        run(str(cli), "outcome", manual["decision_id"], "--acceptance", "passed", "--evidence-id", "installed-check", "--tokens", "10")
        report = json.loads(run(str(cli), "report"))
        require(report["decisions"] == 1 and report["groups"][0]["acceptance_passed"] == 1, "Installed decision/outcome logging failed")
        catalog = json.loads(run(str(cli), "models"))
        require({row["model"] for row in catalog["models"]} == {"gpt-6-astra", "gpt-6.1-sol", "gpt-6-luna"} and catalog["availability"] == "not_checked", "Installed model picker has incorrect presets or availability claims")

        config = work / "config.json"
        run(str(cli), "init", "--config", str(config), "--model", "installed-model", "--backend", "openrouter")
        doctor = json.loads(run(str(cli), "doctor", "--config", str(config), expected=1))
        require(doctor["credential_present"] is False and doctor["network_check"] == "not_performed", "Doctor did not report the missing credential locally")
        private = json.loads(run(str(cli), "select", "Private task", "--config", str(config), "--private"))
        require(private["settings"] == {"reasoning": {"effort": "medium"}} and private["decision"]["reason"] == "private_request", "Private selection failed without provider dependencies")
        original = json.loads(run(str(cli), "inspect", private["decision_id"]))
        inherited = json.loads(run(str(cli), "inherit", private["decision_id"], "--parent-session-id", "installed-session"))
        require(inherited["decision_id"] != original["decision_id"] and inherited["trace"]["parent_decision_id"] == original["decision_id"] and inherited["effective_effort"] == "medium", "Installed continuation lost its effort or lineage")
        run(str(cli), "observe", inherited["decision_id"], "--session-id", "installed-next", "--turn-id", "turn-1", "--status", "completed", "--tokens", "42")
        require(json.loads(run(str(cli), "inspect", original["decision_id"])) == original, "Continuation changed its source selection")
        off = json.loads(run(str(cli), "select", "Task", "--config", str(config), "--mode", "off"))
        require(off["settings"] == {} and not off["apply_effort"], "Off mode changed the host settings")

        messages = '\n'.join([
            json.dumps({"id": "one", "request": "Private task", "private": True}),
            "not-json",
            json.dumps({"id": "two", "request": "Continue", "private": True}),
        ]) + '\n'
        rows = [json.loads(line) for line in run(str(cli), "serve", "--config", str(config), input=messages).splitlines()]
        require(len(rows) == 3 and rows[0]["id"] == "one" and rows[2]["id"] == "two", "Installed protocol lost request correlation")
        require(rows[1]["error"]["code"] == "invalid_json" and rows[2]["result"]["decision"]["reason"] == "private_request", "Installed protocol did not recover from invalid input")

        prompt = "Preserve the original request\nincluding its second line.\n"
        plan = json.loads(run(str(cli), "run", "--model", "installed-model", "--private", "--dry-run", input=prompt))
        require(plan["request_via"] == "stdin" and 'model_reasoning_effort="medium"' in plan["argv"], "Installed launch plan did not configure stdin or the selected effort")

        codex_config = work / "codex.json"
        run(str(cli), "setup", "--config", str(codex_config), "--host", "codex", "--model", "sol", "--levels", "low,medium,high", "--backend", "typesafe")
        configured = json.loads(run(str(cli), "run", "--config", str(codex_config), "--private", "--dry-run", "--ephemeral", input=prompt))
        require(configured["selection"]["model"] == "gpt-6.1-sol" and 'model_reasoning_effort="medium"' in configured["argv"] and "--ephemeral" in configured["argv"], "Installed saved-profile launch did not apply model and effort")
        require(prompt not in json.dumps(configured), "Installed launch plan exposed the original prompt")

        claude_config = work / "claude.json"
        run(str(cli), "setup", "--config", str(claude_config), "--host", "claude-code", "--model", "sonnet", "--backend", "typesafe")
        claude_plan = json.loads(run(str(cli), "run", "--config", str(claude_config), "--effort", "low", "--dry-run", input=prompt))
        require(claude_plan["argv"] == ["claude", "-p", "--model", "sonnet", "--effort", "low"], "Installed Claude Code profile has incorrect launch arguments")

        node = shutil.which("node")
        node_checked = node is not None and example.is_file()
        if node_checked:
            environment["AUTO_EFFORT_COMMAND"] = str(cli)
            rows = [json.loads(line) for line in run(node, str(example), str(config), "--private").splitlines()]
            require(len(rows) == 2 and all(row["model"] == "installed-model" and row["decision"]["reason"] == "private_request" for row in rows), "Node controller did not complete two installed-CLI exchanges")
        print(json.dumps({"version": metadata["version"], "wheel": wheel.name, "installation": "passed", "node_controller": "passed" if node_checked else "not_available"}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    args = parser.parse_args()
    check_wheel(args.wheel)


if __name__ == "__main__":
    main()

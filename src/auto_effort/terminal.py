"""Select one terminal task, then replace the launcher with interactive Codex."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import uuid
from pathlib import Path

from .core import EFFORTS
from .models import ModelOption, discover_codex_models, resolve_model
from .profiles import Config, Target
from .routing import SubagentRouter
from .telemetry import DecisionLedger, TraceContext, ledger_path


ROUTES = {
    "sol": (
        "gpt-6.1-sol",
        "Default for a complete interactive coding task: implementation, debugging, "
        "review, several steps, or work whose scope may expand. Use when uncertain.",
    ),
    "luna": (
        "gpt-6-luna",
        "Only a small, fully specified task: an exact read-only lookup, text extraction, "
        "or one trivial mechanical edit with an obvious check. No diagnosis or architecture.",
    ),
    "astra": (
        "gpt-6-astra",
        "Difficult reasoning across interacting systems, a hard proof, a subtle concurrency "
        "failure, or a documented failure of a cheaper model. Urgency alone is insufficient.",
    ),
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="ca", description='Open interactive Codex with Auto model and effort. Example: ca "fix the login bug"',
    )
    result.add_argument("prompt", nargs="?", help="your task, inside quotes")
    result.add_argument("--request-file", type=Path, help="read the task from a UTF-8 file instead")
    result.add_argument("-m", "--model", help="fix the model: sol, luna, astra, or an advertised Codex model ID")
    result.add_argument("-e", "--effort", choices=("auto", *EFFORTS), default="auto", help="fix effort instead of Auto")
    result.add_argument("--private", action="store_true", help="skip Jev and use the selected model's fallback effort")
    result.add_argument("--dry-run", action="store_true", help="select and show settings without opening Codex")
    result.add_argument("--yolo", action=argparse.BooleanOptionalAction, default=True,
                        help="use your normal unrestricted Codex permissions (default: enabled)")
    result.add_argument("--codex-command", default="codex", help=argparse.SUPPRESS)
    result.add_argument("--jev-command", default="jev", help=argparse.SUPPRESS)
    return result


def configuration(options: tuple[ModelOption, ...], model: str | None, effort: str, jev: str):
    """Only offer advertised models and efforts; deeper effort is an explicit opt-in."""
    advertised = {option.model: option for option in options}
    if model:
        model = resolve_model(model)
        if model not in advertised:
            raise ValueError("That model is not advertised by this Codex account. Run auto-effort models --discover.")
        candidates = {"manual": (model, "The user explicitly selected this model.")}
        default = "manual"
    else:
        candidates = {name: row for name, row in ROUTES.items() if row[0] in advertised}
        default = "sol"
        if default not in candidates:
            raise ValueError("Sol 6.1 is unavailable as the fallback. Choose an available model with --model.")
    targets, routes = {}, {}
    for name, (slug, criteria) in candidates.items():
        option = advertised[slug]
        if effort != "auto" and effort not in option.levels:
            if model:
                raise ValueError("That effort is not supported by the selected model.")
            continue
        levels = tuple(level for level in option.levels if level in ("low", "medium", "high") or level == effort)
        if not levels:
            continue
        fallback = "medium" if "medium" in levels else option.default_effort if option.default_effort in levels else levels[0]
        targets[name] = Target(slug, "codex", levels, fallback)
        # These are alternatives for the owning terminal, never child-agent launches.
        routes[name] = {"criteria": criteria, "role": "controller"}
    if default not in targets:
        raise ValueError("The selected effort is unsupported by the fallback model. Choose a compatible --model.")
    return Config({"name": "jev-cli", "command": jev, "timeout": 5}, targets, default), routes


def launch_argv(codex: str, model: str, effort: str, prompt: str, *, yolo: bool) -> list[str]:
    command = [codex, "--model", model, "-c", f'model_reasoning_effort="{effort}"']
    if yolo:
        command.append("--yolo")
    # A leading dash, shell expression, quote, or newline in the prompt stays data.
    return [*command, "--", prompt]


def main(argv: list[str] | None = None, *, default_jev_command: str | None = None) -> int:
    cli = parser()
    if default_jev_command:
        cli.set_defaults(jev_command=default_jev_command)
    args = cli.parse_args(argv)
    try:
        if args.prompt is not None and args.request_file is not None:
            raise ValueError("Use a quoted prompt or --request-file, not both.")
        prompt = args.request_file.read_text(encoding="utf-8") if args.request_file else args.prompt
        if not prompt or not prompt.strip():
            raise ValueError('Add your task: ca "your prompt"')
        if "\0" in prompt:
            raise ValueError("The prompt cannot contain a NUL character.")
        codex = shutil.which(args.codex_command)
        if not codex:
            raise ValueError("Codex is not installed or is missing from PATH.")
        options = discover_codex_models(codex)
        config, routes = configuration(options, args.model, args.effort, args.jev_command)
        # Keep terminal tasks out of CCC's ledger unless the caller explicitly shares it.
        path = Path(os.environ["AUTO_EFFORT_LEDGER"]).expanduser() if os.environ.get("AUTO_EFFORT_LEDGER") else ledger_path().parent.parent / "codex-auto" / "decisions.sqlite3"
        ledger = DecisionLedger(path)
        routed = SubagentRouter(config, routes, ledger=ledger).select(
            prompt, target="manual" if args.model else None, effort=args.effort,
            context="This is the complete task for a new interactive terminal session. Select for the whole task.",
            private=args.private, dry_run=args.dry_run,
            trace=TraceContext(project_id="terminal-codex", task_id=uuid.uuid4().hex, role="controller"),
        )
        selected = routed.selection
        decision = selected.decision
        command = launch_argv(codex, selected.target.model, decision.effort, prompt, yolo=args.yolo)
        model_source, effort_source = routed.model_choice.source, decision.source
        detail = f"model {model_source}, effort {effort_source}"
        if model_source == "fallback":
            detail += f" ({routed.model_choice.reason})"
        if effort_source == "fallback":
            detail += f" ({decision.reason})"
        print(f"Auto → {selected.target.model} / {decision.effort} · {detail}", file=sys.stderr, flush=True)
        if args.dry_run:
            print(json.dumps({"model": selected.target.model, "effort": decision.effort,
                              "model_source": model_source, "effort_source": effort_source,
                              "decision_id": selected.decision_id, "launch": False,
                              "argv": [*command[:-1], "<your prompt>"]}))
            return 0
        ledger.record_execution(selected.decision_id, status="started")
        try:
            # Inherit the real terminal, current directory, auth and all Herdr variables.
            os.execv(codex, command)
        except OSError:
            ledger.record_execution(selected.decision_id, status="launch_error")
            raise
        return 0  # Reached only by a test double; execv replaces this process.
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError, sqlite3.Error):
        # Fixed local errors are useful; raw provider/discovery exceptions may be private.
        error = sys.exc_info()[1]
        message = str(error) if isinstance(error, ValueError) else "Could not read a required file, save the decision, or start Codex."
        print(f"ca: {message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

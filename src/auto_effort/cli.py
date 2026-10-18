"""JSON interface for other tools and an opt-in Codex launch wrapper."""
from __future__ import annotations

import argparse
import io
from importlib import resources
import json
import math
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from .backends import JevCLIBackend, OpenRouterBackend, TypeSafeBackend
from .controller import AgentController
from .core import Decision, EffortRouter, Policy
from .models import PREFERRED_MODELS, discover_codex_models, resolve_model
from .profiles import Config, Target, config_path
from .protocol import serve
from .setup import HOSTS, build_setup
from .routing import SubagentRouter
from .telemetry import DecisionLedger, TraceContext


def _logging_options(parser: argparse.ArgumentParser, *, trace: bool = True) -> None:
    parser.add_argument("--ledger", type=Path, help="local decision database; default: user state directory or AUTO_EFFORT_LEDGER")
    parser.add_argument("--no-log", action="store_true", help="disable local decision logging for this command")
    if trace:
        for name in ("project-id", "task-id", "ticket", "session-id", "parent-session-id", "trial-id", "parent-decision-id"):
            parser.add_argument("--" + name, help="opaque identity label; never a path or prompt")
        parser.add_argument("--role", choices=("controller", "scout", "worker", "reviewer", "deep"), default="controller")
        parser.add_argument("--attempt", type=int, default=1)


def _trace(args: argparse.Namespace) -> TraceContext:
    return TraceContext(**{name: getattr(args, name) for name in TraceContext.__dataclass_fields__})


def _options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--request-file", type=Path, help="read a UTF-8 request from a file; default: stdin")
    parser.add_argument("--context", default="", help="optional task summary sent to Jev")
    parser.add_argument("--previous-reply", default="", help="optional bounded reply or plan being answered")
    parser.add_argument("--has-files", action="store_true", help="task includes files or attachments; no file contents are opened or uploaded")
    parser.add_argument("--backend", choices=("typesafe", "openrouter", "jev-cli"), default="typesafe")
    parser.add_argument("--jev-command", default="jev", help="path to an existing jev CLI")
    parser.add_argument("--judge-model", help="judge model; default is pinned for the selected backend")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--levels", default="low,medium,high", help="comma-separated levels supported by your model")
    parser.add_argument("--fallback", default="medium")
    parser.add_argument("--current", help="retain this permitted level on uncertain or failed judgments")
    parser.add_argument("--effort", default="auto", help="auto, or an explicit permitted effort")
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--private", action="store_true", help="skip the judge and use current/fallback effort")


def _pick(args: argparse.Namespace, request: str) -> Decision:
    levels = args.levels if args.levels is not None else "low,medium,high"
    fallback = args.fallback if args.fallback is not None else "medium"
    threshold = args.threshold if args.threshold is not None else 0.8
    timeout = args.timeout if args.timeout is not None else 5.0
    backend_name = args.backend if args.backend is not None else "typesafe"
    policy = Policy(
        allowed_efforts=tuple(x.strip() for x in levels.split(",")),
        fallback_effort=fallback,
        confidence_threshold=threshold,
    )
    if backend_name == "jev-cli":
        backend = JevCLIBackend(args.jev_command or "jev", timeout)
    elif backend_name == "openrouter":
        backend = OpenRouterBackend(args.judge_model or "typesafe/jev-1.13", timeout)
    else:
        backend = TypeSafeBackend(args.judge_model or "jev-1.13.0", timeout)
    return EffortRouter(backend, policy).pick(
        request, context=args.context, previous_reply=args.previous_reply, current_effort=args.current,
        effort=args.effort, private=args.private,
        has_files=args.has_files,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="auto-effort", description=__doc__)
    parser.add_argument("--version", action="version", version="auto-effort 0.4.0a2")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("instructions", help="emit the bundled CCC auto-subagents skill as JSON")
    pick = sub.add_parser("pick", help="choose effort and return JSON or a setting")
    pick.add_argument("request", nargs="?", help="request text; default: --request-file or stdin")
    _options(pick)
    _logging_options(pick)
    pick.add_argument("--dry-run", action="store_true", help="classify a probe and exclude it from live trial results")
    pick.add_argument("--format", choices=("json", "effort", "codex", "responses"), default="json")

    run = sub.add_parser("run", help="choose effort and launch Codex or a configured Claude Code target")
    _options(run)
    _logging_options(run)
    run.set_defaults(backend=None, jev_command=None, judge_model=None, timeout=None, levels=None, fallback=None, threshold=None)
    run.add_argument("--codex-command", default="codex", help="path to codex")
    run.add_argument("--claude-command", default="claude", help="path to Claude Code")
    run.add_argument("--model", help="Codex model, or astra/sol/luna; alternatively use --config")
    run.add_argument("--config", type=Path, help="launch the saved CLI target instead of specifying --model")
    run.add_argument("--target", help="named target in --config")
    run.add_argument("--mode", choices=("off", "shadow", "auto"))
    run.add_argument("--cwd", type=Path, help="launch directory; leaves the parent process directory unchanged")
    run.add_argument("--ephemeral", action="store_true", help="ask Codex not to persist this test/task session")
    run.add_argument("--json", action="store_true", help="emit native Codex JSONL events")
    run.add_argument("--skip-git-repo-check", action="store_true", help="allow a Codex task in a temporary scenario directory")
    run.add_argument("--output-schema", type=Path, help="Codex JSON schema for the final response")
    run.add_argument("--launch-timeout", type=float, help="stop the CLI task after this many seconds (1..3600)")
    run.add_argument("--dry-run", action="store_true", help="return a launch plan without starting Codex")

    models = sub.add_parser("models", help="show preferred GPT models, or discover your installed Codex capabilities")
    models.add_argument("--discover", action="store_true", help="call Codex model/list; starts no agent task")
    models.add_argument("--codex-command", default="codex")
    models.add_argument("--timeout", type=float, default=15)
    setup = sub.add_parser("setup", help="pick a host, judge backend, and model; create a user configuration")
    setup.add_argument("--config", type=Path)
    setup.add_argument("--host", choices=HOSTS)
    setup.add_argument("--model", help="astra/sol/luna for GPT hosts, or your exact model identifier")
    setup.add_argument("--backend", choices=("typesafe", "openrouter", "jev-cli"))
    setup.add_argument("--jev-command", default="jev")
    setup.add_argument("--judge-model")
    setup.add_argument("--timeout", type=float, default=5)
    setup.add_argument("--codex-command", default="codex")
    setup.add_argument("--target", default="default")
    setup.add_argument("--levels", help="explicit host-supported levels; bypass Codex discovery for offline setup")
    setup.add_argument("--fallback")
    setup.add_argument("--mode", choices=("off", "shadow", "auto"), default="auto")

    init = sub.add_parser("init", help="write a user configuration without storing API keys")
    init.add_argument("--config", type=Path)
    init.add_argument("--backend", choices=("typesafe", "openrouter", "jev-cli"), default="typesafe")
    init.add_argument("--jev-command", default="jev")
    init.add_argument("--judge-model")
    init.add_argument("--timeout", type=float, default=5)
    init.add_argument("--model", required=True, help="your actual agent model identifier")
    init.add_argument("--adapter", choices=("responses", "chat-completions", "codex", "disabled"), default="responses")
    init.add_argument("--target", default="default")
    init.add_argument("--levels", default="low,medium,high")
    init.add_argument("--fallback", default="medium")
    init.add_argument("--mode", choices=("off", "shadow", "auto"), default="auto")

    doctor = sub.add_parser("doctor", help="check configuration, SDK/CLI, and credential presence locally")
    doctor.add_argument("--config", type=Path)
    select = sub.add_parser("select", help="return a configured target's native effort settings")
    select.add_argument("request", nargs="?")
    select.add_argument("--request-file", type=Path)
    select.add_argument("--config", type=Path)
    select.add_argument("--target")
    select.add_argument("--context", default="")
    select.add_argument("--previous-reply", default="")
    select.add_argument("--has-files", action="store_true")
    select.add_argument("--current")
    select.add_argument("--effort", default="auto")
    select.add_argument("--mode", choices=("off", "shadow", "auto"))
    select.add_argument("--private", action="store_true")
    _logging_options(select)
    select.add_argument("--dry-run", action="store_true")
    route = sub.add_parser("route", help="choose a declared sub-agent target and its effort with Jev")
    route.add_argument("request", nargs="?")
    route.add_argument("--request-file", type=Path)
    route.add_argument("--config", type=Path, required=True)
    route.add_argument("--routes", type=Path, required=True, help="JSON target-to-task-rubric and role mapping")
    route.add_argument("--target", help="explicit declared target; bypass automatic model selection")
    route.add_argument("--current-target")
    route.add_argument("--context", default="")
    route.add_argument("--has-files", action="store_true")
    route.add_argument("--current")
    route.add_argument("--effort", default="auto")
    route.add_argument("--mode", choices=("off", "shadow", "auto"))
    route.add_argument("--private", action="store_true")
    _logging_options(route)
    route.add_argument("--dry-run", action="store_true")
    server = sub.add_parser("serve", help="one request/response JSON object per line on stdio")
    server.add_argument("--config", type=Path)
    _logging_options(server, trace=False)
    outcome = sub.add_parser("outcome", help="attach acceptance evidence and measured metrics to a decision")
    outcome.add_argument("decision_id")
    outcome.add_argument("--ledger", type=Path)
    outcome.add_argument("--acceptance", choices=("passed", "failed", "unknown"), required=True)
    outcome.add_argument("--evidence-id", help="opaque reference to the host's acceptance-check evidence")
    outcome.add_argument("--tokens", type=int)
    outcome.add_argument("--agent-cost-usd", type=float)
    outcome.add_argument("--retries", type=int)
    outcome.add_argument("--elapsed-ms", type=float)
    report_parser = sub.add_parser("report", help="summarize choices and host-reported acceptance; missing metrics stay unknown")
    report_parser.add_argument("--ledger", type=Path)
    report_parser.add_argument("--project-id")
    report_parser.add_argument("--trial-id")
    export_parser = sub.add_parser("export", help="write prompt-free decision/event records as JSON Lines to stdout")
    export_parser.add_argument("--ledger", type=Path)
    bind_parser = sub.add_parser("bind", help="record a host's launch receipt and native session identity")
    bind_parser.add_argument("decision_id")
    bind_parser.add_argument("--session-id")
    bind_parser.add_argument("--status", choices=("started", "launch_error"), required=True)
    bind_parser.add_argument("--ledger", type=Path)
    inspect_parser = sub.add_parser("inspect", help="return one prompt-free recorded selection")
    inspect_parser.add_argument("decision_id")
    inspect_parser.add_argument("--ledger", type=Path)
    probe_parser = sub.add_parser("mark-probe", help="exclude an old unexecuted probe without rewriting its selection")
    probe_parser.add_argument("decision_id")
    probe_parser.add_argument("--ledger", type=Path)
    inherit_parser = sub.add_parser("inherit", help="carry an Auto launch setting into a linked continuation, without judging again")
    inherit_parser.add_argument("decision_id")
    inherit_parser.add_argument("--parent-session-id", required=True)
    inherit_parser.add_argument("--ledger", type=Path)
    observe_parser = sub.add_parser("observe", help="record measured execution without claiming acceptance")
    observe_parser.add_argument("decision_id")
    observe_parser.add_argument("--session-id", required=True)
    observe_parser.add_argument("--turn-id", required=True)
    observe_parser.add_argument("--status", required=True, choices=("completed", "failed", "interrupted"))
    observe_parser.add_argument("--model")
    observe_parser.add_argument("--effort")
    observe_parser.add_argument("--tokens", type=int)
    observe_parser.add_argument("--elapsed-ms", type=float)
    observe_parser.add_argument("--ledger", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "instructions":
            skill = resources.files("auto_effort").joinpath("skills/auto-subagents/SKILL.md").read_text(encoding="utf-8")
            print(json.dumps({"instructions": skill, "skill": "auto-subagents"}))
            return 0
        if args.command in ("outcome", "report", "export", "bind", "inspect", "mark-probe", "inherit", "observe"):
            ledger = DecisionLedger(args.ledger)
            if args.command == "mark-probe":
                ledger.mark_probe(args.decision_id)
                print(json.dumps({"decision_id": args.decision_id, "probe_recorded": True}))
            elif args.command == "inspect":
                print(json.dumps(ledger.get(args.decision_id), allow_nan=False))
            elif args.command == "inherit":
                identity = ledger.inherit(args.decision_id, parent_session_id=args.parent_session_id)
                print(json.dumps(ledger.get(identity), allow_nan=False))
            elif args.command == "observe":
                ledger.record_observation(args.decision_id, session_id=args.session_id, turn_id=args.turn_id,
                                          status=args.status, model=args.model, effort=args.effort,
                                          tokens=args.tokens, elapsed_ms=args.elapsed_ms)
                print(json.dumps({"decision_id": args.decision_id, "observation_recorded": True}))
            elif args.command == "bind":
                if args.session_id:
                    ledger.bind_session(args.decision_id, args.session_id)
                ledger.record_execution(args.decision_id, status=args.status)
                print(json.dumps({"decision_id": args.decision_id, "receipt_recorded": True, "session_bound": bool(args.session_id)}))
            elif args.command == "outcome":
                ledger.record_outcome(
                    args.decision_id, acceptance=args.acceptance, evidence_id=args.evidence_id,
                    tokens=args.tokens, agent_cost_usd=args.agent_cost_usd,
                    retries=args.retries, elapsed_ms=args.elapsed_ms,
                )
                print(json.dumps({"decision_id": args.decision_id, "outcome_recorded": True}))
            elif args.command == "report":
                print(json.dumps(ledger.summary(project_id=args.project_id, trial_id=args.trial_id), allow_nan=False))
            else:
                for event in ledger.export():
                    print(json.dumps(event, allow_nan=False))
            return 0
        ledger = DecisionLedger(args.ledger) if hasattr(args, "no_log") and not args.no_log else None
        trace = _trace(args) if args.command in ("pick", "select", "run", "route") else None
        if args.command == "models":
            options = discover_codex_models(args.codex_command, args.timeout) if args.discover else PREFERRED_MODELS
            print(json.dumps({"models": [row.to_dict() for row in options], "availability": "advertised_by_codex" if args.discover else "not_checked"}))
            return 0
        if args.command == "setup":
            if (args.config or config_path()).exists():
                raise FileExistsError
            config, note = build_setup(args)
            path = config.save(args.config)
            print(json.dumps({"config_created": str(path), "model": config.targets[config.default_target].model, "note": note, "next": ["auto-effort", "doctor", "--config", str(path)]}))
            return 0
        if args.command == "init":
            backend = {"name": args.backend, "timeout": args.timeout}
            if args.judge_model:
                backend["model"] = args.judge_model
            if args.backend == "jev-cli":
                backend["command"] = args.jev_command
            target = Target(args.model, args.adapter, tuple(x.strip() for x in args.levels.split(",")) if args.adapter != "disabled" else (), args.fallback)
            config = Config(backend, {args.target: target}, args.target, args.mode)
            path = config.save(args.config)
            print(json.dumps({"config_created": str(path), "next": "auto-effort doctor"}))
            return 0
        if args.command in ("doctor", "serve"):
            config = Config.load(args.config)
            if args.command == "doctor":
                report = config.doctor()
                print(json.dumps(report))
                return 0 if report["ready"] else 1
            for stream in (sys.stdin, sys.stdout):
                if isinstance(stream, io.TextIOWrapper):
                    stream.reconfigure(encoding="utf-8")
            serve(AgentController(config, ledger=ledger), sys.stdin, sys.stdout)
            return 0
        inline = getattr(args, "request", None)
        if inline is not None and args.request_file is not None:
            raise ValueError("use either request text or --request-file")
        request = (
            inline if inline is not None else args.request_file.read_text(encoding="utf-8")
            if args.request_file is not None else sys.stdin.read()
        )
        if args.command == "route":
            result = SubagentRouter(Config.load(args.config), json.loads(args.routes.read_text(encoding="utf-8")), ledger=ledger).select(
                request, context=args.context, private=args.private, target=args.target,
                current_target=args.current_target, current_effort=args.current,
                effort=args.effort, mode=args.mode, trace=trace, dry_run=args.dry_run,
                has_files=args.has_files,
            )
            print(json.dumps(result.to_dict(), allow_nan=False))
            return 0
        if args.command == "select":
            selection = AgentController(Config.load(args.config), ledger=ledger).select(
                request, target=args.target, context=args.context, previous_reply=args.previous_reply,
                current_effort=args.current, effort=args.effort, private=args.private, mode=args.mode, trace=trace, dry_run=args.dry_run,
                has_files=args.has_files,
            )
            print(json.dumps(selection.to_dict(), allow_nan=False))
            return 0
        if args.command == "run":
            if args.launch_timeout is not None and (not math.isfinite(args.launch_timeout) or not 1 <= args.launch_timeout <= 3600):
                raise ValueError("launch timeout must be between 1 and 3600 seconds")
            if args.model is not None and (args.config is not None or args.target is not None):
                raise ValueError("use --model or a configured target, not both")
            if args.model is None:
                if args.config is None and args.target is None:
                    raise ValueError("run needs --model or --config/--target")
                if any(getattr(args, name) is not None for name in ("backend", "jev_command", "judge_model", "timeout", "levels", "fallback", "threshold")):
                    raise ValueError("backend and policy options belong in the saved config; use --model for a direct launch")
                config = Config.load(args.config)
                profile = config.targets.get(args.target or config.default_target)
                if profile is None or profile.adapter not in ("codex", "claude-code"):
                    raise ValueError("run requires a Codex or Claude Code CLI target")
                if profile.adapter == "claude-code" and (args.ephemeral or args.json or args.skip_git_repo_check or args.output_schema):
                    raise ValueError("native Codex launch options cannot be used with Claude Code")
                selected = AgentController(config, ledger=ledger).select(
                    request, target=args.target, context=args.context, previous_reply=args.previous_reply,
                    current_effort=args.current, effort=args.effort, private=args.private, mode=args.mode,
                    trace=trace, dry_run=args.dry_run,
                    has_files=args.has_files,
                )
                model, adapter, native_args = selected.target.model, selected.target.adapter, selected.cli_args
                report = selected.to_dict()
                decision = selected.decision
                decision_id = selected.decision_id
            else:
                if args.mode is not None:
                    raise ValueError("--mode needs a configured target")
                decision = _pick(args, request)
                model, adapter, native_args = resolve_model(args.model), "codex", decision.codex_args()
                report = decision.to_dict()
                decision_id = ledger.record_selection(
                    decision, model=model, adapter=adapter, current_effort=args.current,
                    allowed_efforts=tuple(x.strip() for x in (args.levels or "low,medium,high").split(",")),
                    fallback_effort=args.fallback or "medium", threshold=args.threshold or 0.8,
                    trace=trace, dry_run=args.dry_run,
                ) if ledger else None
            if adapter == "claude-code":
                command = [args.claude_command, "-p", "--model", model, *native_args]
            else:
                command = [args.codex_command, "exec", "--model", model, *native_args]
                if args.ephemeral:
                    command.append("--ephemeral")
                if args.json:
                    command.append("--json")
                if args.skip_git_repo_check:
                    command.append("--skip-git-repo-check")
                if args.output_schema:
                    command.extend(["--output-schema", str(args.output_schema.resolve())])
                command.append("-")
            if args.dry_run:
                print(json.dumps({"decision_id": decision_id, "decision": decision.to_dict() if decision else None, "selection": report, "argv": command, "cwd": str(args.cwd) if args.cwd else None, "request_via": "stdin"}))
                return 0
            print(json.dumps({"auto_effort": report, "decision_id": decision_id}), file=sys.stderr)
            started = time.monotonic()
            if ledger:
                ledger.record_execution(decision_id, status="started")
            try:
                result = subprocess.run(command, input=request, text=True, encoding="utf-8", shell=False, check=False, cwd=args.cwd, timeout=args.launch_timeout)
            except (subprocess.TimeoutExpired, OSError, KeyboardInterrupt) as error:
                if ledger:
                    status = "timeout" if isinstance(error, subprocess.TimeoutExpired) else "interrupted" if isinstance(error, KeyboardInterrupt) else "launch_error"
                    ledger.record_execution(decision_id, status=status, elapsed_ms=(time.monotonic() - started) * 1000)
                raise
            if ledger:
                ledger.record_execution(decision_id, status="completed", elapsed_ms=(time.monotonic() - started) * 1000, exit_code=result.returncode)
            return result.returncode if result.returncode >= 0 else 128 - result.returncode
        decision = _pick(args, request)
        decision_id = ledger.record_selection(
            decision, apply_effort=False, current_effort=args.current,
            allowed_efforts=tuple(x.strip() for x in args.levels.split(",")),
            fallback_effort=args.fallback, threshold=args.threshold, trace=trace, dry_run=args.dry_run,
        ) if ledger else None
        if args.format == "effort":
            print(decision.effort)
        else:
            value = (
                decision.codex_args() if args.format == "codex" else decision.responses_settings()
                if args.format == "responses" else decision.to_dict()
            )
            if args.format == "json" and decision_id:
                value["decision_id"] = decision_id
            print(json.dumps(value, ensure_ascii=False, allow_nan=False))
        if args.format != "json" and decision_id:
            print(json.dumps({"decision_id": decision_id}), file=sys.stderr)
        return 0
    except ValueError as error:
        # Validation messages are fixed strings; provider errors stay inside the router.
        print(f"auto-effort: {error}", file=sys.stderr)
        return 2
    except FileExistsError:
        print("auto-effort: configuration already exists; edit it or choose another --config path", file=sys.stderr)
        return 2
    except OSError:
        print("auto-effort: unavailable local command/file; check its path and permissions", file=sys.stderr)
        return 2
    except sqlite3.Error:
        print("auto-effort: could not persist the decision log; check the ledger or use --no-log", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("auto-effort: agent launch interrupted", file=sys.stderr)
        return 130
    except subprocess.TimeoutExpired:
        print("auto-effort: agent launch timed out", file=sys.stderr)
        return 124

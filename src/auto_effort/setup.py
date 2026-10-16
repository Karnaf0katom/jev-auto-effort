"""Portable setup choices; writes only Auto Effort's own configuration."""
from __future__ import annotations

import sys
from typing import Any

from .models import PREFERRED_MODELS, discover_codex_models, resolve_model
from .profiles import Config, Target

HOSTS = ("codex", "openai", "claude-code", "claude-api", "grok", "antigravity")


def _choose(prompt: str, labels: list[str], default: int = 0) -> int:
    print(prompt, file=sys.stderr)
    for index, label in enumerate(labels, 1):
        print(f"  {index}. {label}", file=sys.stderr)
    for _ in range(3):
        print(f"Choice [{default + 1}]: ", end="", file=sys.stderr, flush=True)
        answer = sys.stdin.readline()
        if not answer:
            raise ValueError("setup input ended before a choice was made")
        answer = answer.strip()
        if not answer:
            return default
        if answer.isdigit() and 1 <= int(answer) <= len(labels):
            return int(answer) - 1
        print("Enter one of the numbered choices.", file=sys.stderr)
    raise ValueError("setup requires a valid numbered choice")


def build_setup(args: Any) -> tuple[Config, str]:
    interactive = sys.stdin.isatty()
    host = args.host
    if host is None:
        if not interactive:
            raise ValueError("noninteractive setup needs --host and --model")
        host = HOSTS[_choose("Where will you use Auto Effort?", list(HOSTS))]
    backend_name = args.backend
    if backend_name is None:
        if not interactive:
            raise ValueError("noninteractive setup needs --backend")
        names = ["openrouter", "typesafe", "jev-cli"]
        backend_name = names[_choose("Which Jev backend do you already use?", names)]
    backend = {"name": backend_name, "timeout": args.timeout}
    if args.judge_model:
        backend["model"] = args.judge_model
    if backend_name == "jev-cli":
        backend["command"] = args.jev_command

    model = args.model
    declared = tuple(part.strip() for part in args.levels.split(",")) if args.levels is not None else None
    options = ()
    if host == "codex" and declared is None:
        options = discover_codex_models(args.codex_command)
    elif host == "openai":
        options = PREFERRED_MODELS
    if model is None:
        if not interactive:
            raise ValueError("choose --model (astra, sol, luna, or an exact model identifier)")
        if options:
            model = options[_choose("Choose your model:", [f"{row.label} ({row.model})" for row in options])].model
        else:
            print("Enter the exact model identifier already available in your host: ", end="", file=sys.stderr, flush=True)
            model = sys.stdin.readline().strip()
            if not model:
                raise ValueError("setup requires a model identifier")
    model = resolve_model(model) if host in ("codex", "openai") else model
    chosen = next((row for row in options if row.model == model), None)
    if host == "codex" and options and chosen is None:
        raise ValueError("selected model is not in Codex's advertised model list")
    if chosen is not None:
        if declared is not None and not set(declared) <= set(chosen.levels):
            raise ValueError("requested efforts are not supported by the selected model")
        # Stay conservative. Higher levels are opt-in, even when advertised.
        levels = declared or tuple(level for level in ("low", "medium", "high") if level in chosen.levels)
        if not levels:
            levels = (chosen.default_effort,)
    else:
        levels = declared or ("low", "medium", "high")
    fallback = args.fallback or ("medium" if "medium" in levels else levels[0])
    if host == "antigravity":
        if declared is not None:
            raise ValueError("Antigravity's documented hook has no effort override; use a custom controller profile for a verified request API")
        target = Target(model, "disabled", levels=())
        note = "Antigravity passthrough: its documented hooks do not expose a native effort override."
    elif host == "claude-api":
        target = Target(model, "custom", levels, fallback, ("output_config", "effort"), {level: level for level in levels})
        note = "Apply selection.settings to your existing Claude API request before each call."
    else:
        adapter = {"codex": "codex", "claude-code": "claude-code", "openai": "responses", "grok": "responses"}[host]
        target = Target(model, adapter, levels, fallback)
        note = (
            "Use auto-effort run --config PATH for new CLI tasks."
            if host in ("codex", "claude-code") else
            "Apply selection.settings through your existing authenticated Responses controller."
        )
    return Config(backend, {args.target: target}, args.target, args.mode), note

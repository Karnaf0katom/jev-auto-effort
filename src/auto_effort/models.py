"""Preferred GPT models and bounded, read-only Codex capability discovery."""
from __future__ import annotations

import json
import math
import queue
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any

from .core import EFFORTS


@dataclass(frozen=True)
class ModelOption:
    model: str
    label: str
    levels: tuple[str, ...]
    default_effort: str
    source: str = "documented"
    recommended: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "levels": list(self.levels)}


# These are setup choices, not account availability claims. Codex discovery wins.
PREFERRED_MODELS = (
    ModelOption("gpt-6.1-sol", "Sol 6.1", ("low", "medium", "high", "xhigh", "max"), "medium", recommended=True),
    ModelOption("gpt-6-luna", "Luna 6", ("none", "low", "medium", "high", "xhigh", "max"), "medium", recommended=True),
    ModelOption("gpt-6-astra", "Astra 6", ("low", "medium", "high", "xhigh", "max"), "medium", recommended=True),
)
MODEL_ALIASES = {"sol": "gpt-6.1-sol", "luna": "gpt-6-luna", "astra": "gpt-6-astra"}


def resolve_model(value: str) -> str:
    return MODEL_ALIASES.get(value.lower(), value)


def parse_codex_models(rows: list[dict[str, Any]]) -> tuple[ModelOption, ...]:
    """Use only advertised, visible models with a usable native effort control."""
    preferred = {option.model: option for option in PREFERRED_MODELS}
    result = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("hidden") is True:
            continue
        model = row.get("model")
        supported = row.get("supportedReasoningEfforts")
        if not isinstance(model, str) or not model.strip() or len(model) > 200 or not isinstance(supported, list):
            continue
        declared = {item.get("reasoningEffort") for item in supported if isinstance(item, dict) and isinstance(item.get("reasoningEffort"), str)}
        levels = tuple(level for level in EFFORTS if level in declared)
        if not levels:
            continue
        default = row.get("defaultReasoningEffort")
        if default not in levels:
            default = "medium" if "medium" in levels else levels[0]
        label = row.get("displayName")
        label = label if isinstance(label, str) and label.strip() and len(label) <= 200 else model
        result[model] = ModelOption(model, label, levels, default, "codex", model in preferred)
    order = {option.model: i for i, option in enumerate(PREFERRED_MODELS)}
    return tuple(sorted(result.values(), key=lambda option: (order.get(option.model, len(order)), option.model)))


def discover_codex_models(command: str = "codex", timeout: float = 15) -> tuple[ModelOption, ...]:
    """Initialize an app-server connection and list models; never start a thread.

    The caller's installed Codex owns authentication. Stderr and raw RPC errors are
    never echoed. A reader thread supports pipes on Windows as well as POSIX.
    """
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 60:
        raise ValueError("model discovery timeout must be between 0 and 60 seconds")
    process = subprocess.Popen(
        [command, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", shell=False,
    )
    messages: queue.Queue = queue.Queue(maxsize=64)

    def read() -> None:
        try:
            while True:
                line = process.stdout.readline(131_073)
                messages.put_nowait(line)
                if not line or len(line) > 131_072:
                    return
        except (OSError, UnicodeError, queue.Full):
            return

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    ident = 0

    def send(method: str, params: dict[str, Any], request_id: int | None = None) -> None:
        message: dict[str, Any] = {"method": method, "params": params}
        if request_id is not None:
            message["id"] = request_id
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    def call(method: str, params: dict[str, Any]) -> dict[str, Any]:
        nonlocal ident
        ident += 1
        send(method, params, ident)
        for _ in range(256):
            try:
                line = messages.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                raise ValueError("Codex model discovery timed out; supply --model and --levels explicitly") from None
            if not line or len(line) > 131_072:
                break
            try:
                message = json.loads(line)
            except (ValueError, RecursionError):
                break
            if not isinstance(message, dict):
                break
            if message.get("id") == ident:
                if "error" in message or not isinstance(message.get("result"), dict):
                    break
                return message["result"]
        raise ValueError("Codex model discovery failed; supply --model and --levels explicitly")

    try:
        call("initialize", {"clientInfo": {"name": "auto_effort", "version": "0.4.0a1"}})
        send("initialized", {})
        rows: list[dict[str, Any]] = []
        cursor = None
        seen = set()
        for _ in range(10):
            params: dict[str, Any] = {"limit": 100, "includeHidden": False}
            if cursor is not None:
                params["cursor"] = cursor
            page = call("model/list", params)
            if not isinstance(page.get("data"), list):
                raise ValueError("Codex returned an invalid model list")
            rows.extend(page["data"])
            cursor = page.get("nextCursor")
            if cursor is None:
                options = parse_codex_models(rows)
                if not options:
                    raise ValueError("Codex advertised no models with an effort control")
                return options
            if not isinstance(cursor, str) or not cursor or cursor in seen:
                break
            seen.add(cursor)
        raise ValueError("Codex model discovery exceeded its page limit")
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        reader.join(timeout=1)
        process.stdin.close()
        process.stdout.close()

"""Thin adapters to existing Jev clients; no separate Decisions API implementation."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any

from .core import _number


def _timeout(value: float) -> None:
    if not _number(value) or value <= 0:
        raise ValueError("timeout must be a positive finite number")


@dataclass(frozen=True)
class JevCLIBackend:
    """Call an existing `jev ask` executable, including the shared fleet client.

    The state goes through stdin, never a command-line argument or temporary file.
    The configured executable is trusted code. Timeout failures kill the subprocess.
    """

    executable: str = "jev"
    timeout: float = 5.0

    def __post_init__(self) -> None:
        _timeout(self.timeout)
        if not isinstance(self.executable, str) or not self.executable.strip():
            raise ValueError("executable must be a nonempty path or command name")

    def __call__(self, state: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
        result = subprocess.run(
            [self.executable, "ask", "--state-file", "-", "--questions", json.dumps(questions), "--json"],
            input=json.dumps(state, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=self.timeout,
            check=False,
            shell=False,
        )
        if result.returncode != 0:
            raise RuntimeError("Jev command failed")
        return json.loads(result.stdout)


@dataclass(frozen=True)
class TypeSafeBackend:
    """Portable backend using TypeSafe's official optional Python SDK.

    The SDK reads TYPESAFE_API_KEY. This package never reads the host's key files.
    No retries: a failed call falls back without a second provider request.
    """

    model: str = "jev-1.13.0"
    timeout: float = 5.0

    def __post_init__(self) -> None:
        _timeout(self.timeout)
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("model must be a nonempty string")

    def __call__(self, state: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
        from typesafe_sdk import RetryPolicy, TypeSafeClient

        with TypeSafeClient(
            model=self.model,
            timeout=self.timeout,
            retry=RetryPolicy(max_retries=0),
        ) as client:
            response = client.system_one(state=state, questions=questions)
            return response.model_dump(mode="json")


@dataclass(frozen=True)
class OpenRouterBackend:
    """Portable adapter to the official OpenRouter SDK's Decisions resource.

    Standalone installations use OPENROUTER_API_KEY; fleet usage keeps JevCLIBackend.
    The official SDK owns the wire format. Retries are explicitly disabled.
    """

    model: str = "typesafe/jev-1.13"
    timeout: float = 5.0

    def __post_init__(self) -> None:
        _timeout(self.timeout)
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("model must be a nonempty string")

    def __call__(self, state: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
        from openrouter import OpenRouter

        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        with OpenRouter(api_key=key, timeout_ms=max(1, int(self.timeout * 1000)), retry_config=None) as client:
            response = client.alpha.decisions.create(
                model=self.model, state=state, questions=questions, retries=None,
            )
            return response.model_dump(mode="json")

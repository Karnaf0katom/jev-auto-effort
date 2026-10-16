"""User-owned model capabilities and installation configuration."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .backends import JevCLIBackend, OpenRouterBackend, TypeSafeBackend
from .core import Policy

ADAPTERS = ("responses", "chat-completions", "codex", "claude-code", "custom", "disabled")
_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_PROTECTED = {"model", "input", "messages", "tools", "instructions", "system", "metadata", "api_key", "apikey", "authorization", "headers", "credentials", "auth", "password", "secret", "token"}


def config_path() -> Path:
    """Follow the platform's user configuration directory; never change host configs."""
    if os.environ.get("AUTO_EFFORT_CONFIG"):
        return Path(os.environ["AUTO_EFFORT_CONFIG"]).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "AutoEffort" / "config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AutoEffort" / "config.json"
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "auto-effort" / "config.json"


@dataclass(frozen=True)
class Target:
    """A controller-declared model and its exact supported native effort values."""

    model: str
    adapter: str = "responses"
    levels: tuple[str, ...] = ("low", "medium", "high")
    fallback: str = "medium"
    path: tuple[str, ...] = ()
    values: dict[str, str | int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip() or len(self.model) > 200:
            raise ValueError("target model must be a nonempty model identifier")
        if self.adapter not in ADAPTERS:
            raise ValueError("unknown target adapter")
        object.__setattr__(self, "path", tuple(self.path))
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))
        if self.adapter == "disabled":
            if self.levels or self.path or self.values:
                raise ValueError("disabled targets must have no levels, path, or values")
            return
        policy = Policy(tuple(self.levels), self.fallback)
        object.__setattr__(self, "levels", policy.allowed_efforts)
        if self.adapter == "claude-code" and any(level not in ("low", "medium", "high", "xhigh", "max") for level in self.levels):
            raise ValueError("Claude Code targets must declare native low/medium/high/xhigh/max effort levels")
        if self.adapter == "custom":
            if (
                not self.path or len(self.path) > 8
                or any(not isinstance(part, str) or not _NAME.fullmatch(part) for part in self.path)
                or any(part.lower() in _PROTECTED for part in self.path)
            ):
                raise ValueError("custom adapter needs a valid effort parameter path")
            if set(self.values) != set(self.levels) or any(
                isinstance(value, bool) or not isinstance(value, (str, int))
                or isinstance(value, str) and (not value or len(value) > 100)
                or isinstance(value, int) and not 0 <= value <= 1_000_000
                for value in self.values.values()
            ):
                raise ValueError("custom values must map every supported level to a string or token budget")
        elif self.path or self.values:
            raise ValueError("path and values are only valid for custom adapters")

    def patch(self, effort: str) -> tuple[dict[str, Any], list[str]]:
        if effort not in self.levels:
            raise ValueError("effort is not supported by this target")
        if self.adapter == "codex":
            return {}, ["-c", f'model_reasoning_effort="{effort}"']
        if self.adapter == "claude-code":
            return {}, ["--effort", effort]
        if self.adapter == "responses":
            return {"reasoning": {"effort": effort}}, []
        if self.adapter == "chat-completions":
            return {"reasoning_effort": effort}, []
        result: dict[str, Any] = {}
        cursor = result
        for part in self.path[:-1]:
            cursor[part] = {}
            cursor = cursor[part]
        cursor[self.path[-1]] = self.values[effort]
        return result, []


@dataclass(frozen=True)
class Config:
    backend: dict[str, Any]
    targets: dict[str, Target]
    default_target: str = "default"
    mode: str = "auto"
    confidence_threshold: float = 0.8

    def __post_init__(self) -> None:
        if (
            not isinstance(self.targets, Mapping) or not self.targets or not isinstance(self.default_target, str)
            or self.default_target not in self.targets
            or any(not isinstance(name, str) or not _NAME.fullmatch(name) or not isinstance(target, Target) for name, target in self.targets.items())
        ):
            raise ValueError("configuration needs named targets and a valid default_target")
        if self.mode not in ("off", "shadow", "auto"):
            raise ValueError("mode must be off, shadow, or auto")
        Policy(confidence_threshold=self.confidence_threshold)
        self.make_backend()  # Validate options without loading an SDK or reading credentials.
        object.__setattr__(self, "backend", MappingProxyType(dict(self.backend)))
        object.__setattr__(self, "targets", MappingProxyType(dict(self.targets)))

    def make_backend(self):
        if not isinstance(self.backend, Mapping) or set(self.backend) - {"name", "model", "timeout", "command"}:
            raise ValueError("backend supports only name, model, timeout, and command; keep keys in the environment")
        name = self.backend.get("name", "typesafe")
        timeout = self.backend.get("timeout", 5.0)
        if name == "typesafe":
            return TypeSafeBackend(self.backend.get("model", "jev-1.13.0"), timeout)
        if name == "openrouter":
            return OpenRouterBackend(self.backend.get("model", "typesafe/jev-1.13"), timeout)
        if name == "jev-cli":
            return JevCLIBackend(self.backend.get("command", "jev"), timeout)
        raise ValueError("backend name must be typesafe, openrouter, or jev-cli")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        if not isinstance(data, dict) or data.get("schema_version") != 1 or set(data) - {
            "schema_version", "backend", "targets", "default_target", "mode", "confidence_threshold",
        }:
            raise ValueError("invalid configuration schema")
        targets = data.get("targets")
        if not isinstance(targets, dict):
            raise ValueError("targets must be a JSON object")
        parsed = {}
        for name, row in targets.items():
            if not isinstance(row, dict) or set(row) - {"model", "adapter", "levels", "fallback", "path", "values"}:
                raise ValueError("invalid target configuration")
            if "model" not in row or not isinstance(row.get("levels", []), list) or not isinstance(row.get("path", []), list) or not isinstance(row.get("values", {}), dict):
                raise ValueError("invalid model capability fields")
            fields = dict(row)
            if "levels" in fields:
                fields["levels"] = tuple(fields["levels"])
            if "path" in fields:
                fields["path"] = tuple(fields["path"])
            parsed[name] = Target(**fields)
        return cls(data.get("backend", {"name": "typesafe"}), parsed, data.get("default_target", "default"), data.get("mode", "auto"), data.get("confidence_threshold", 0.8))

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        path = path or config_path()
        raw = path.read_text(encoding="utf-8")
        if len(raw) > 65_536:
            raise ValueError("configuration is too large")
        return cls.from_dict(json.loads(raw))

    def to_dict(self) -> dict[str, Any]:
        targets = {}
        for name, target in self.targets.items():
            row: dict[str, Any] = {"model": target.model, "adapter": target.adapter, "levels": list(target.levels)}
            if target.adapter != "disabled":
                row["fallback"] = target.fallback
            if target.adapter == "custom":
                row.update(path=list(target.path), values=dict(target.values))
            targets[name] = row
        return {"schema_version": 1, "backend": dict(self.backend), "targets": targets, "default_target": self.default_target, "mode": self.mode, "confidence_threshold": self.confidence_threshold}

    def save(self, path: Path | None = None) -> Path:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation preserves existing user configuration.
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(self.to_dict(), indent=2) + "\n")
        return path

    def doctor(self) -> dict[str, Any]:
        name = self.backend.get("name", "typesafe")
        if name == "jev-cli":
            command = self.backend.get("command", "jev")
            available = shutil.which(command) is not None
            credentials = None  # Existing Jev CLI owns credential discovery.
        else:
            module = "typesafe_sdk" if name == "typesafe" else "openrouter"
            available = importlib.util.find_spec(module) is not None
            credentials = bool(os.environ.get("TYPESAFE_API_KEY" if name == "typesafe" else "OPENROUTER_API_KEY", "").strip())
        return {"ready": available and credentials is not False, "backend": name, "backend_available": available, "credential_present": credentials, "required_extra": name if name != "jev-cli" else None, "credential_env": ("TYPESAFE_API_KEY" if name == "typesafe" else "OPENROUTER_API_KEY") if name != "jev-cli" else None, "mode": self.mode, "targets": list(self.targets), "network_check": "not_performed"}

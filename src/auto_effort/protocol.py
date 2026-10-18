"""A bounded JSON Lines protocol for controllers in any programming language."""
from __future__ import annotations

import json
import sqlite3
from typing import TextIO

from .controller import AgentController
from .telemetry import TraceContext

MAX_LINE_CHARS = 65_536
FIELDS = {"id", "target", "request", "context", "previous_reply", "current_effort", "effort", "private", "mode", "trace", "has_files"}


def handle(controller: AgentController, message: object) -> dict:
    identifier = None
    try:
        if not isinstance(message, dict):
            raise ValueError("invalid request fields")
        identifier = message.get("id")
        if identifier is not None and (not isinstance(identifier, str) or len(identifier) > 128 or any(ord(char) < 32 for char in identifier)):
            identifier = None
            raise ValueError("id must be a short string")
        if set(message) - FIELDS:
            raise ValueError("invalid request fields")
        for field in ("target", "context", "previous_reply", "current_effort", "effort", "mode"):
            if field in message and not isinstance(message[field], str):
                raise ValueError("request option types are invalid")
        options = {key: value for key, value in message.items() if key not in ("id", "request")}
        if "trace" in options:
            if not isinstance(options["trace"], dict):
                raise ValueError("trace must be an object")
            options["trace"] = TraceContext(**options["trace"])
        selection = controller.select(message.get("request"), **options)
        return {"id": identifier, "result": selection.to_dict()}
    except (TypeError, ValueError):
        # Never reflect request fragments, provider errors, or supplied option values.
        return {"id": identifier, "error": {"code": "invalid_request", "message": "Invalid request or unsupported target setting"}}
    except (OSError, sqlite3.Error):
        return {"id": identifier, "error": {"code": "logging_unavailable", "message": "Could not persist the decision record"}}


def serve(controller: AgentController, source: TextIO, destination: TextIO) -> None:
    while True:
        line = source.readline(MAX_LINE_CHARS + 1)
        if not line:
            return
        if len(line) > MAX_LINE_CHARS:
            while not line.endswith("\n"):
                line = source.readline(MAX_LINE_CHARS + 1)
                if not line:
                    break
            response = {"id": None, "error": {"code": "input_too_large", "message": "JSON line exceeds the input limit"}}
        elif not line.strip():
            continue
        else:
            try:
                message = json.loads(line)
            except (ValueError, RecursionError):
                response = {"id": None, "error": {"code": "invalid_json", "message": "Expected one JSON object per line"}}
            else:
                response = handle(controller, message)
        destination.write(json.dumps(response, allow_nan=False) + "\n")
        destination.flush()

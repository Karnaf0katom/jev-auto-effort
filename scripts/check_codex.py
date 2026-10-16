"""Opt-in live Codex scenario checks with objective answers and bounded launches.

These synthetic code-analysis checks measure final answers, not repository edits
or general agent quality. --paired also runs each input at fixed medium effort.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

SCENARIOS = (
    {
        "name": "mechanical-edit", "expected_effort": "low",
        "request": 'Fix only the misspelled word in "The request completed sucessfully." Return the corrected sentence as result.',
        "expected": "The request completed successfully.",
    },
    {
        "name": "pagination-boundaries", "expected_effort": "medium",
        "request": (
            "Review this proposed pagination function: start=(page-1)*size; return rows[start:start+size]. "
            "The contract says page and size must be positive integers (booleans are invalid); invalid values raise ValueError. "
            "For rows=[0,1,2,3,4] and calls (page,size)=(1,2),(3,2),(4,2),(0,2),(True,2),(1,0), "
            "give the correct contract results in order. Use ERROR for ValueError. "
            "Return result as one compact JSON string encoding the list of results, with no spaces."
        ),
        "expected": '[[0,1],[4],[],"ERROR","ERROR","ERROR"]',
    },
    {
        "name": "transaction-race", "expected_effort": "high",
        "request": (
            "Diagnose an interleaving in a READ COMMITTED SQL system. The invariant is at least one doctor on call. "
            "A and B are initially on call. Each transaction independently executes SELECT COUNT(*) WHERE on_call=true; "
            "if count>1 it updates only its own row to false, then commits. Both SELECTs happen before either UPDATE. "
            "Identify the anomaly, the final on-call count, and which proposed fixes guarantee the invariant for this protocol: "
            "(a) SELECT FOR UPDATE on only its own doctor row before reading the count; "
            "(b) lock a single common guard row before reading the count; "
            "(c) SERIALIZABLE isolation with aborted transactions retried from their first statement. "
            "Return result as one compact JSON string with keys anomaly, count, safe. "
            "Use the anomaly's lowercase two-word name, an integer count, and safe as a sorted list of fix letters."
        ),
        "expected": '{"anomaly":"write skew","count":0,"safe":["b","c"]}',
    },
)


def equivalent(actual: str, expected: str) -> bool:
    try:
        return json.loads(actual) == json.loads(expected)
    except (ValueError, TypeError):
        return actual == expected


def check(args: argparse.Namespace) -> int:
    if not 1 <= args.limit <= len(SCENARIOS) or not 1 <= args.timeout <= 180:
        raise ValueError("limit must be 1..3 and timeout 1..180 seconds")
    package = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(package / "src")
    records = []
    failures = 0
    with tempfile.TemporaryDirectory(prefix="auto-effort-codex-scenarios-") as directory:
        work = Path(directory)
        schema = work / "answer.schema.json"
        schema.write_text(json.dumps({"type": "object", "properties": {"result": {"type": "string"}}, "required": ["result"], "additionalProperties": False}), encoding="utf-8")
        for case in SCENARIOS[:args.limit]:
            for policy in (("auto", "medium") if args.paired else ("auto",)):
                prompt = case["request"] + "\nAnswer directly. Do not call tools, read files, browse, spawn agents, or change anything."
                command = [
                    sys.executable, "-m", "auto_effort", "run", "--model", args.model,
                    "--backend", args.backend, "--jev-command", args.jev_command,
                    "--codex-command", args.codex_command, "--effort", policy,
                    "--cwd", str(work), "--ephemeral", "--skip-git-repo-check", "--json",
                    "--output-schema", str(schema),
                    "--launch-timeout", str(args.timeout),
                ]
                started = time.monotonic()
                row = {"scenario": case["name"], "policy": policy, "expected_effort": case["expected_effort"]}
                try:
                    result = subprocess.run(command, input=prompt, capture_output=True, text=True, encoding="utf-8", env=environment, cwd=work, timeout=args.timeout + 20, shell=False)
                    row["elapsed_seconds"] = round(time.monotonic() - started, 3)
                    row["exit_code"] = result.returncode
                    events = []
                    for line in result.stdout.splitlines():
                        try:
                            events.append(json.loads(line))
                        except ValueError:
                            continue
                    for line in result.stderr.splitlines():
                        try:
                            diagnostic = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(diagnostic, dict) and "auto_effort" in diagnostic:
                            row["decision"] = diagnostic["auto_effort"]
                    messages = [event["item"].get("text", "") for event in events if isinstance(event, dict) and event.get("type") == "item.completed" and isinstance(event.get("item"), dict) and event["item"].get("type") == "agent_message"]
                    calls = [event for event in events if isinstance(event, dict) and event.get("type") == "item.completed" and isinstance(event.get("item"), dict) and event["item"].get("type") in ("command_execution", "mcp_tool_call", "web_search", "collab_tool_call")]
                    usages = [event.get("usage") for event in events if isinstance(event, dict) and event.get("type") == "turn.completed"]
                    row["usage"] = usages[-1] if usages else None
                    row["tool_calls"] = len(calls)
                    try:
                        actual = json.loads(messages[-1])["result"] if messages else None
                    except (ValueError, KeyError, TypeError):
                        actual = None
                    row["answer_correct"] = equivalent(actual, case["expected"])
                    row["passed"] = result.returncode == 0 and not calls and row["answer_correct"]
                except subprocess.TimeoutExpired:
                    row.update(passed=False, error="launch_timeout", elapsed_seconds=round(time.monotonic() - started, 3))
                records.append(row)
                print(json.dumps(row), flush=True)
                failures = 0 if row["passed"] else failures + 1
                if failures >= 2:
                    print(json.dumps({"stopped": "two_consecutive_failures"}), flush=True)
                    if args.output:
                        args.output.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
                    return 1
    if args.output:
        args.output.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    return 0 if all(row["passed"] for row in records) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="authorize real judge/model requests using your existing accounts")
    parser.add_argument("--model", default="luna", help="astra, sol, luna, or an exact Codex model ID")
    parser.add_argument("--backend", choices=("typesafe", "openrouter", "jev-cli"), default="typesafe")
    parser.add_argument("--jev-command", default="jev")
    parser.add_argument("--codex-command", default="codex")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--paired", action="store_true", help="compare automatic effort with fixed medium on identical inputs")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"execute": False, "model": args.model, "scenarios": [row["name"] for row in SCENARIOS[:args.limit]], "paired": args.paired, "next": "add --execute to run real Codex requests"}))
        return 0
    try:
        return check(args)
    except (OSError, ValueError):
        print("Codex scenario configuration or local command is unavailable", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

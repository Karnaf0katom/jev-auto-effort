"""Bounded paired public tasks with objective grading and complete attempt records.

Uses ephemeral Codex requests with no agent tools. Code answers are graded in a
separate, time-bounded process against fixture checks. This is not a benchmark
of autonomous repository editing or a statistically powered savings study.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "src"))
from auto_effort import AgentController, Config, DecisionLedger, JevCLIBackend, Target, TraceContext


def grade(task, answer):
    if "function" not in task:
        try:
            return {"passed": json.loads(answer) == task["expected"], "checks": 1}
        except (ValueError, TypeError):
            return {"passed": False, "checks": 1}
    tree = ast.parse(answer)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef) or tree.body[0].name != task["function"]:
        return {"passed": False, "checks": 0, "reason": "expected_one_function"}
    if tree.body[0].decorator_list or any(
        isinstance(node, (ast.Import, ast.ImportFrom, ast.While, ast.Global, ast.Nonlocal))
        or isinstance(node, ast.Attribute) and node.attr.startswith("_")
        or isinstance(node, ast.Name) and node.id.startswith("__")
        for node in ast.walk(tree)
    ):
        return {"passed": False, "checks": 0, "reason": "unsupported_code"}
    builtins = {"ValueError": ValueError, "TypeError": TypeError, "int": int, "bool": bool,
                "list": list, "tuple": tuple, "len": len, "isinstance": isinstance,
                "type": type, "sorted": sorted, "min": min, "max": max, "range": range,
                "enumerate": enumerate, "any": any, "all": all, "zip": zip}
    namespace = {"__builtins__": builtins}
    exec(compile(tree, "<benchmark-answer>", "exec"), namespace)
    function = namespace[task["function"]]
    if task["function"] == "paginate":
        valid = [(([0, 1, 2, 3, 4], 1, 2), [0, 1]), (([0, 1, 2, 3, 4], 3, 2), [4]),
                 (([0, 1], 9, 2), []), (([], 1, 1), []), (([1], 1, 5), [1])]
        invalid = [([1], page, size) for page, size in [(True, 1), (1, False), (0, 1), (-1, 1), (1, 0), (1.5, 1), (1, "2")]]
    else:
        valid = [(([],), []), (([[5, 7], [1, 3], [3, 5]],), [[1, 7]]),
                 (([[1, 1], [3, 4]],), [[1, 1], [3, 4]]), (([[1, 8], [2, 3], [8, 9]],), [[1, 9]]),
                 (([(-3, -1), (-2, 2), (5, 6)],), [[-3, 2], [5, 6]])]
        invalid = [([[True, 2]],), ([[3, 1]],), ([[1]],), ([[1, 2, 3]],), ([[1, "2"]],), ([None],)]
    checks = 0
    for arguments, expected in valid:
        original = copy.deepcopy(arguments)
        if function(*arguments) != expected or arguments != original:
            return {"passed": False, "checks": checks, "reason": "contract_result"}
        checks += 1
    for arguments in invalid:
        try:
            function(*arguments)
        except ValueError:
            checks += 1
        else:
            return {"passed": False, "checks": checks, "reason": "missing_validation"}
    return {"passed": True, "checks": checks}


def isolated_grade(task, answer):
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--grade"],
                            input=json.dumps({"task": task, "answer": answer}), capture_output=True,
                            text=True, timeout=4, cwd=tempfile.gettempdir(),
                            env={key: value for key, value in os.environ.items() if key in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "LANG")})
    return json.loads(result.stdout) if result.returncode == 0 else {"passed": False, "reason": "grader_error"}


def summarize(rows):
    groups = []
    for policy in ("auto", "medium"):
        samples = [row for row in rows if row["policy"] == policy]
        usage = [row["usage"] for row in samples if row.get("usage")]
        groups.append({"policy": policy, "attempts": len(samples),
                       "accepted_tasks": len({row["task_id"] for row in samples if row["passed"]}),
                       "failed_attempts": sum(not row["passed"] for row in samples),
                       "efforts": dict(Counter(row["selection"]["decision"]["effort"] for row in samples)),
                       "effort_sources": dict(Counter(row["selection"]["decision"]["source"] for row in samples)),
                       "elapsed_ms": round(sum(row["elapsed_ms"] for row in samples), 3),
                       "judge_ms": round(sum(row["selection"]["decision"]["latency_ms"] for row in samples), 3),
                       "known_judge_cost_usd": sum(row["selection"]["decision"].get("cost_usd") or 0 for row in samples),
                       "input_tokens": sum(item.get("input_tokens", 0) for item in usage) if usage else None,
                       "cached_input_tokens": sum(item.get("cached_input_tokens", 0) for item in usage) if usage else None,
                       "output_tokens": sum(item.get("output_tokens", 0) for item in usage) if usage else None,
                       "usage_samples": len(usage), "agent_cost_usd": None})
    return {"groups": groups, "note": "Paired public smoke benchmark; cached inputs, fixed execution order and a small sample limit inference. Agent dollars are not reported by Codex and remain unknown."}


def run(args):
    tasks_path = PACKAGE / "examples/benchmark_tasks.json"
    tasks = json.loads(tasks_path.read_text())[:args.limit]
    if (args.output / "results.json").exists() or (args.output / "decisions.sqlite3").exists():
        raise ValueError("benchmark output already contains a trial; choose a fresh directory")
    args.output.mkdir(parents=True, exist_ok=True)
    ledger = DecisionLedger(args.output / "decisions.sqlite3")
    backend = JevCLIBackend(args.jev_command, 5)
    controller = AgentController(Config({"name": "jev-cli", "command": args.jev_command},
                                       {"worker": Target(args.model, "codex")}, "worker"), backend, ledger=ledger)
    rows, consecutive_failures = [], 0
    implementation_manifest = {path.relative_to(PACKAGE).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in sorted((PACKAGE / "src/auto_effort").rglob("*.py"))}
    implementation_sha256 = hashlib.sha256(json.dumps(implementation_manifest, sort_keys=True).encode()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="auto-effort-paired-") as directory:
        work = Path(directory)
        schema = work / "answer.schema.json"
        schema.write_text(json.dumps({"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"], "additionalProperties": False}))
        for index, task in enumerate(tasks):
            # Counterbalance order; both modes receive byte-identical agent prompts.
            policies = ("auto", "medium") if index % 2 == 0 else ("medium", "auto")
            base_prompt = task["request"] + "\nReturn the requested source or JSON serialized as the answer string. Answer directly. Do not use tools, read files, browse, spawn agents, or change anything."
            for policy in policies:
                prompt = base_prompt
                parent_decision = None
                for attempt in range(1, args.attempts + 1):
                    trace = TraceContext(project_id="public-benchmark", task_id=task["id"], trial_id=args.trial_id,
                                         parent_decision_id=parent_decision, attempt=attempt)
                    started = time.monotonic()
                    selection = controller.select(task["summary"], effort="auto" if policy == "auto" else "medium", trace=trace)
                    identity = selection.decision_id
                    ledger.record_execution(identity, status="started")
                    row = {"task_id": task["id"], "category": task["category"], "policy": policy, "attempt": attempt,
                           "selection": selection.to_dict(), "request_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                           "passed": False, "usage": None, "agent_cost_usd": None}
                    command = [args.codex_command, "exec", "--model", args.model, *selection.cli_args, "--ephemeral", "--json",
                               "--skip-git-repo-check", "--output-schema", str(schema), "-"]
                    try:
                        result = subprocess.run(command, input=prompt, text=True, capture_output=True, encoding="utf-8", cwd=work, timeout=args.timeout)
                        events = []
                        for line in result.stdout.splitlines():
                            try:
                                event = json.loads(line)
                                if isinstance(event, dict):
                                    events.append(event)
                            except ValueError:
                                continue
                        items = [event.get("item", {}) for event in events if event.get("type") == "item.completed"]
                        messages = [item.get("text", "") for item in items if item.get("type") == "agent_message"]
                        tools = [item for item in items if item.get("type") in ("command_execution", "mcp_tool_call", "web_search", "collab_tool_call", "file_change")]
                        usage = [event.get("usage") for event in events if event.get("type") == "turn.completed"]
                        row.update(exit_code=result.returncode, tool_calls=len(tools), usage=usage[-1] if usage else None)
                        answer = json.loads(messages[-1])["answer"] if messages else ""
                        verdict = isolated_grade(task, answer)
                        row["grading"] = verdict
                        row["passed"] = result.returncode == 0 and not tools and verdict["passed"]
                        ledger.record_execution(identity, status="completed", exit_code=result.returncode)
                    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
                        row["error"] = "timeout" if isinstance(error, subprocess.TimeoutExpired) else "invalid_execution"
                        ledger.record_execution(identity, status="timeout" if isinstance(error, subprocess.TimeoutExpired) else "launch_error")
                    row["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
                    measured = row["usage"]
                    tokens = measured.get("input_tokens", 0) + measured.get("output_tokens", 0) if measured else None
                    ledger.record_outcome(identity, acceptance="passed" if row["passed"] else "failed", evidence_id=f"{task['id']}-{policy}-{attempt}",
                                          tokens=tokens, retries=attempt - 1, elapsed_ms=row["elapsed_ms"])
                    rows.append(row)
                    (args.output / "results.json").write_text(json.dumps({"schema_version": 1, "model": args.model,
                        "tasks_sha256": hashlib.sha256(tasks_path.read_bytes()).hexdigest(), "implementation_sha256": implementation_sha256,
                        "implementation_manifest": implementation_manifest,
                        "rows": rows, "summary": summarize(rows)}, indent=2) + "\n")
                    print(json.dumps({"task": task["id"], "policy": policy, "effort": selection.decision.effort,
                                      "source": selection.decision.source, "passed": row["passed"], "elapsed_ms": row["elapsed_ms"]}), flush=True)
                    consecutive_failures = 0 if row["passed"] else consecutive_failures + 1
                    if consecutive_failures >= 2:
                        return 1
                    if row["passed"]:
                        break
                    parent_decision = identity
                    prompt += "\nThe previous answer failed the contract checks. Re-read validation and boundary requirements and return a corrected answer."
    return 0 if len({(row["task_id"], row["policy"]) for row in rows if row["passed"]}) == len(tasks) * 2 else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--grade", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--codex-command", default="codex")
    parser.add_argument("--jev-command", default="jev")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--trial-id", default="release-paired-v1")
    parser.add_argument("--output", type=Path, default=Path("benchmark-results"))
    args = parser.parse_args()
    if args.grade:
        try:
            try:
                import resource
                resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
                if sys.platform.startswith("linux"):
                    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
            except ImportError:
                pass
            data = json.load(sys.stdin)
            print(json.dumps(grade(data["task"], data["answer"])))
        except Exception:
            print(json.dumps({"passed": False, "reason": "invalid_answer"}))
        return 0
    if not 1 <= args.limit <= 8 or not 1 <= args.attempts <= 2 or not 1 <= args.timeout <= 180:
        parser.error("limit must be 1..8, attempts 1..2 and timeout 1..180")
    if not args.execute:
        print(json.dumps({"execute": False, "cases": args.limit, "maximum_agent_calls": args.limit * 2 * args.attempts,
                          "model": args.model, "output": str(args.output)}))
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())

"""Run a bounded live smoke check on synthetic public requests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from auto_effort import EffortRouter, JevCLIBackend, TypeSafeBackend


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("typesafe", "jev-cli"), default="typesafe")
    parser.add_argument("--jev-command", default="jev")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    cases = json.loads(Path(__file__).with_name("requests.json").read_text(encoding="utf-8"))[:args.limit]
    backend = JevCLIBackend(args.jev_command) if args.backend == "jev-cli" else TypeSafeBackend()
    router = EffortRouter(backend)
    rows, failures = [], 0
    for case in cases:
        decision = router.pick(case["request"])
        rows.append({"id": case["id"], "expected": case["expected"], **decision.to_dict()})
        failures = failures + 1 if decision.reason == "judge_unavailable" else 0
        if failures >= 2:
            break
    successful = sum(row["source"] == "jev" for row in rows)
    print(json.dumps({
        "cases": rows,
        "jev_decisions": successful,
        "label_matches": sum(row["source"] == "jev" and row["effort"] == row["expected"] for row in rows),
        "note": "Provider smoke check only; not a quality or cost-savings benchmark.",
    }, indent=2, allow_nan=False))
    return 0 if successful == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())

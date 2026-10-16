# Codex scenario evidence — 2026-10-07

Three synthetic code-analysis tasks, each run with automatic effort and fixed
medium on the same model and input. All six answers matched the deterministic
grader and used no tools. These checks did not edit a repository.

Automatic elapsed time totaled 41.416 seconds; fixed medium totaled 34.212 seconds.
The judge added 4.946 seconds across the three automatic calls and reported total
cost $0.000083706. These single runs have different cache usage and uncontrolled
provider latency; the result is not a statistical quality or savings benchmark.
Only the mechanical edit had a confident automatic effort choice. Pagination
and the transaction race retained the configured medium fallback.

This is the exact machine-readable record produced by the bounded harness:

```json
{
  "date": "2026-10-07",
  "model": "gpt-6-luna",
  "codex_version": "0.161.0",
  "scenarios": "scripts/check_codex.py",
  "paired": true,
  "results": [
    {
      "scenario": "mechanical-edit",
      "policy": "auto",
      "expected_effort": "low",
      "elapsed_seconds": 12.067,
      "exit_code": 0,
      "decision": {
        "schema_version": 1,
        "effort": "low",
        "source": "jev",
        "reason": "task_complexity",
        "confidence": 1.0,
        "latency_ms": 1828.711,
        "cost_usd": 2.4318e-05
      },
      "usage": {
        "input_tokens": 19811,
        "cached_input_tokens": 0,
        "cache_write_input_tokens": 0,
        "output_tokens": 19,
        "reasoning_output_tokens": 0
      },
      "tool_calls": 0,
      "answer_correct": true,
      "passed": true
    },
    {
      "scenario": "mechanical-edit",
      "policy": "medium",
      "expected_effort": "low",
      "elapsed_seconds": 11.952,
      "exit_code": 0,
      "decision": {
        "schema_version": 1,
        "effort": "medium",
        "source": "manual",
        "reason": "explicit_override",
        "confidence": null,
        "latency_ms": 0.0,
        "cost_usd": null
      },
      "usage": {
        "input_tokens": 19811,
        "cached_input_tokens": 0,
        "cache_write_input_tokens": 0,
        "output_tokens": 19,
        "reasoning_output_tokens": 0
      },
      "tool_calls": 0,
      "answer_correct": true,
      "passed": true
    },
    {
      "scenario": "pagination-boundaries",
      "policy": "auto",
      "expected_effort": "medium",
      "elapsed_seconds": 16.55,
      "exit_code": 0,
      "decision": {
        "schema_version": 1,
        "effort": "medium",
        "source": "fallback",
        "reason": "low_confidence",
        "confidence": 0.57,
        "latency_ms": 1010.305,
        "cost_usd": 2.8518e-05
      },
      "usage": {
        "input_tokens": 19908,
        "cached_input_tokens": 0,
        "cache_write_input_tokens": 0,
        "output_tokens": 29,
        "reasoning_output_tokens": 0
      },
      "tool_calls": 0,
      "answer_correct": true,
      "passed": true
    },
    {
      "scenario": "pagination-boundaries",
      "policy": "medium",
      "expected_effort": "medium",
      "elapsed_seconds": 12.737,
      "exit_code": 0,
      "decision": {
        "schema_version": 1,
        "effort": "medium",
        "source": "manual",
        "reason": "explicit_override",
        "confidence": null,
        "latency_ms": 0.0,
        "cost_usd": null
      },
      "usage": {
        "input_tokens": 19908,
        "cached_input_tokens": 0,
        "cache_write_input_tokens": 0,
        "output_tokens": 96,
        "reasoning_output_tokens": 65
      },
      "tool_calls": 0,
      "answer_correct": true,
      "passed": true
    },
    {
      "scenario": "transaction-race",
      "policy": "auto",
      "expected_effort": "high",
      "elapsed_seconds": 12.799,
      "exit_code": 0,
      "decision": {
        "schema_version": 1,
        "effort": "medium",
        "source": "fallback",
        "reason": "low_confidence",
        "confidence": 0.56,
        "latency_ms": 2107.271,
        "cost_usd": 3.087e-05
      },
      "usage": {
        "input_tokens": 19964,
        "cached_input_tokens": 19200,
        "cache_write_input_tokens": 0,
        "output_tokens": 34,
        "reasoning_output_tokens": 0
      },
      "tool_calls": 0,
      "answer_correct": true,
      "passed": true
    },
    {
      "scenario": "transaction-race",
      "policy": "medium",
      "expected_effort": "high",
      "elapsed_seconds": 9.523,
      "exit_code": 0,
      "decision": {
        "schema_version": 1,
        "effort": "medium",
        "source": "manual",
        "reason": "explicit_override",
        "confidence": null,
        "latency_ms": 0.0,
        "cost_usd": null
      },
      "usage": {
        "input_tokens": 19964,
        "cached_input_tokens": 0,
        "cache_write_input_tokens": 0,
        "output_tokens": 34,
        "reasoning_output_tokens": 0
      },
      "tool_calls": 0,
      "answer_correct": true,
      "passed": true
    }
  ]
}
```

# Auto Effort

Choose an agent's reasoning effort from the request it is about to handle. Jev makes
one typed classification; a small policy decides whether to apply it. The same
decision works in a Python agent, a command-line launcher, or another tool that
can read JSON.

**Status: experimental alpha candidate, version 0.4.0a1.** MIT licensed. The distribution name is
`jev-auto-effort`, the Python import is `auto_effort`, and the CLI is `auto-effort`.
This package has not been published to a package registry. An optional local CCC
adapter is under validation; it requires this package to be installed separately.

The main session model stays your explicit choice. For helpers, Jev selects a
declared model target, then an effort supported by that target. Manual settings
win; uncertain judgments retain the configured fallback. Local decision records
link launches, continuations, repairs and checked outcomes without storing prompts.

The latest local audit matched 30/30 initial launches to their recorded
settings; 21 were helpers with 18 recorded passes, two failures and one unknown.
Every launch used medium effort. The eight-task paired smoke also used medium
throughout and was slower than fixed medium. These checks show the tested routing
path, without establishing better effort choices or cost savings. See the
[validation record](docs/VALIDATION.md) for methods and limits.

| Guide | Purpose |
|---|---|
| [Install](docs/INSTALL.md) | Source installation, model discovery and setup |
| [Controllers](docs/CONTROLLERS.md) | Python and JSON Lines host integration |
| [Helper routing](docs/ROUTING.md) | Declared roles/models, ledger and continuations |
| [Contributing](CONTRIBUTING.md) | Code map and offline development checks |
| [Release](docs/RELEASING.md) | Reviewed export and reproducible package checks |
| [Attribution](THIRD_PARTY.md) | Reuse and bundled license notices |

Start with [installation](docs/INSTALL.md) and [controller integration](docs/CONTROLLERS.md).
From a standalone source checkout:

```bash
pipx install '.[providers]'
auto-effort setup
auto-effort doctor
auto-effort run --config /path/to/config.json --request-file request.txt --dry-run
```

Supply your own judge key through its environment variable. The controller calls
Auto Effort before each request; installing a package by itself cannot intercept
another application's model calls.

For scripted Codex setup, with your Codex client already authenticated:

```bash
auto-effort models --discover
auto-effort setup --host codex --model sol --backend openrouter
auto-effort run --config /path/to/config.json --request-file request.txt
```

`models` without `--discover` shows the three documented preferred models and
does not claim account access. Discovery calls only Codex's `model/list`; it starts
no agent task. Setup uses the returned capabilities, including differences from
the API catalog. Provide `--levels` for an explicit offline declaration.

```text
incoming request → Jev Choice → confidence + permitted levels → agent effort
                                  uncertain/unavailable → current or fallback
```

Default candidates are `low`, `medium`, and `high`. A confident choice is applied
automatically. Confidence below 0.8, an `other` answer, or a provider failure retains
`--current`, if supplied, otherwise `--fallback` (default `medium`). Explicit
`--effort high` takes precedence and skips Jev. Higher levels become candidates
only when the caller includes them in `--levels`.

## Install from source

Python 3.10 or later:

```bash
python -m pip install '.[typesafe]'
```

The optional extra uses [TypeSafe's official SDK](https://pypi.org/project/typesafe-sdk/).
Set `TYPESAFE_API_KEY` in your environment using your usual secret manager. The
default judge is pinned to `jev-1.13.0`; `--judge-model` can select another model.
The core itself has no runtime dependencies.

OpenRouter users can install `[openrouter]` and choose `--backend openrouter`; its
official SDK reads `OPENROUTER_API_KEY` and calls the pinned `typesafe/jev-1.13` judge.

For a host that already provides a compatible `jev ask` CLI:

```bash
python -m pip install .
auto-effort pick 'Fix a typo in this README' --backend jev-cli
```

Use `--jev-command /path/to/jev` when the compatible CLI is outside PATH.
The package contains no provider credentials or host configuration.

## CLI

```bash
auto-effort pick 'Implement pagination for a list endpoint'
auto-effort pick 'Diagnose an intermittent transaction race' --current medium
auto-effort pick 'Continue' --previous-reply 'We will diagnose the transaction race'
auto-effort pick --request-file request.txt --format effort
auto-effort pick --request-file request.txt --format responses
auto-effort pick 'Solve the supplied proof' --levels low,medium,high,xhigh
auto-effort pick 'Use my manual setting' --effort high
auto-effort pick --request-file private.txt --private --current high
```

`--format json` (default) returns this contract. The values below illustrate a
successful judgment; they are not a benchmark result:

```json
{
  "schema_version": 1,
  "effort": "medium",
  "source": "jev",
  "reason": "task_complexity",
  "confidence": 0.95,
  "latency_ms": 480.0,
  "cost_usd": null
}
```

Other formats return just the effort string, a Codex argument array, or an OpenAI
Responses settings object. `source` is `jev`, `manual`, or `fallback`. Fallback
reasons distinguish low confidence, unclassified requests, unavailable judges,
invalid judgments, private input, recognizable credentials, and oversized input.
A completed selection, including a fallback, exits 0; invalid caller input exits 2.
The [JSON schema](schemas/decision.schema.json) and [Node.js example](examples/node.mjs)
provide a language-independent integration contract.

For sensitive requests, prefer a file or stdin to putting the request in your shell
history and process arguments. The CLI passes state to its Jev subprocess through
stdin. Its output does not include prompts or raw provider exceptions.

## Automatically apply effort to a Codex launch

Prepare a UTF-8 `request.txt`, then inspect or run the launch:

```bash
auto-effort run --model luna --request-file request.txt --dry-run
auto-effort run --model luna --request-file request.txt
```

`run` picks effort, starts `codex exec`, and applies
`-c 'model_reasoning_effort="<level>"'` for this process. The original request goes
to Codex unchanged via stdin; the decision is printed to stderr. The wrapper
preserves Codex's configured permissions and credentials and returns its exit
code. It does not execute through a shell or change global Codex settings.

Use `--config /path/to/config.json` and optional `--target NAME` to launch a saved
CLI profile. Shadow/off modes omit the automatic effort flag; an explicit
`--effort` still takes precedence. Claude Code profiles use its native `--effort`
flag. `--cwd` chooses a task directory, and optional `--launch-timeout SECONDS`
bounds the launch. Codex scenario runs can use `--ephemeral`, `--json`,
`--skip-git-repo-check`, and `--output-schema`; permissions stay under the host's
existing configuration.

Supply `--levels` for direct `--model` launches. Saved Codex setup discovers
capabilities unless levels are supplied explicitly. The policy defaults to the
advertised subset of low/medium/high; deeper efforts remain opt-in. Supported
models, efforts, and defaults depend on the client and account. See the
[Codex model discovery contract](https://learn.chatgpt.com/docs/app-server#models).

This wrapper chooses at launch for one task. An existing running conversation
needs its host to call `pick()` before a new turn and apply that decision through
the host's request API. Installing an MCP tool or skill alone does not automatically
intercept every request.

## Python API

```python
from auto_effort import EffortRouter, Policy, TypeSafeBackend

router = EffortRouter(
    TypeSafeBackend(timeout=5),
    Policy(allowed_efforts=("low", "medium", "high"), fallback_effort="medium"),
)

request = "Implement pagination for a list endpoint"
decision = router.pick(request, context="The endpoint and pagination contract already exist")

# Apply this before issuing the agent's request.
settings = decision.responses_settings()
# response = your_openai_client.responses.create(model=your_model, input=request, **settings)
print(decision.to_dict())
```

OpenAI Responses accepts `reasoning.effort`, with model-dependent support; see
the [official reasoning guide](https://developers.openai.com/api/docs/guides/reasoning).
The commented request above is an integration example; the package itself only
calls Jev and the optional Codex launcher.

Other tools can call `auto-effort pick --format json` as a subprocess and map
`effort` to their own setting. Python hosts can supply an existing Jev decision
function directly:

```python
from auto_effort import EffortRouter

def decide(state, questions):
    return existing_jev_client.decide(state, questions)

router = EffortRouter(decide)
decision = router.pick("Fix the requested bug", current_effort="medium")
```

The backend must return `{"answers": {"effort": {"choice": "low", "confidence": 0.9}}}`,
optionally with `usage.cost`. Custom backends own their timeouts and privacy handling.
The official SDK adapter disables retries and uses its per-operation timeout;
the CLI adapter enforces a subprocess timeout. This alpha has no caching or
background worker and makes one decision call per eligible request.

## Input and privacy

Only the incoming request, an optional caller-supplied context summary, and an optional
previous reply go to the judge. There is no repository scan or automatic transcript upload. `private=True`
or `--private` skips the judge entirely. A small preflight check also skips recognizable
credentials. It is not a comprehensive secret scanner; callers decide what may be
sent to the configured hosted provider. More than 12,000 combined request/context/previous-reply
characters uses fallback rather than silently truncating the task.

The effort decision does not grant permissions, change the user's selected model, or authorize tools.
Jev's confidence is not proof of task quality. [Related work and the evaluation
plan](docs/RESEARCH.md) explain why savings and quality need a paired end-to-end
benchmark before making release claims.

## Develop and evaluate

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python examples/evaluate.py --backend jev-cli --jev-command /path/to/jev --limit 3
```

The evaluator uses synthetic public requests, reports actual choices and confidence,
and stops after two consecutive provider failures. It calls the configured judge;
the tests mock external I/O. The [validation record](docs/VALIDATION.md)
distinguishes current release checks from historical tests and live results.
The current release gate builds and verifies a standalone source export:

```bash
python scripts/check_release.py --output /tmp/auto-effort-release
python scripts/benchmark.py                         # preview; no model requests
python scripts/benchmark.py --execute --jev-command /path/to/jev --output /tmp/auto-effort-benchmark
```

The paired benchmark uses eight public lookup, coding, diagnosis and review
tasks. It grades exact answers and generated functions, counterbalances execution
order, and retains failed attempts and unknown agent costs. It is a small smoke
benchmark, not evidence of autonomous repository-editing quality or general savings.
See [the build spec](BUILD-SPEC.md) for the standalone acceptance check and the
later publish → CCC → PR sequence.

For bounded live Codex scenarios, run from this package directory:

```bash
python scripts/check_codex.py
python scripts/check_codex.py --execute --model luna --paired --output results.json
```

The first command previews the three synthetic scenarios without model calls.
The second compares automatic effort with fixed medium on identical inputs,
checking exact code-analysis answers and recording decisions, latency, and native
token usage. It uses your existing Codex/Jev accounts, ephemeral tasks, and a
temporary directory. These checks do not establish general coding quality or savings.

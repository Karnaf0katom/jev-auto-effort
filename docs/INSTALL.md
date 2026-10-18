# Install and configure Auto Effort

Auto Effort runs where a user installs it. Each installation uses that user's Jev
credentials and model profiles. Agent controllers can start its JSON process or
import its Python library, then call it before each turn or subagent request.

Python 3.10+ is required. Runtime checks have passed on Linux; macOS and Windows
remain unverified. The commands below install the experimental alpha from source.
The package registry release has not been published.

## Install from a checkout

From the standalone checkout, with [pipx](https://pipx.pypa.io/latest/how-to/install-pipx.html) already
available:

```bash
pipx install '.[providers]'
```

The `providers` extra includes both official SDKs. Use `[typesafe]` or `[openrouter]`
for just one. For an existing compatible Jev CLI, install the package without an extra.
Once a package-registry release exists, the equivalent command will be
`pipx install 'jev-auto-effort[providers]'`; that registry command is not available yet.

Alternatively, install into an isolated Python environment:

```bash
python -m venv .venv
```

Use that environment's Python to run `python -m pip install '.[providers]'` from
the standalone checkout. Activate it using your operating system's usual command,
or call `.venv/bin/auto-effort` on Linux/macOS and `.venv\Scripts\auto-effort.exe`
on Windows.

## Set up your judge and agent model

Put `OPENROUTER_API_KEY` or `TYPESAFE_API_KEY` in your environment through your
normal secret manager. Auto Effort's configuration contains no API key. Choose
the backend matching the credentials you have:

```bash
auto-effort setup
auto-effort doctor
auto-effort select 'Implement the documented feature'
```

For TypeSafe, choose `--backend typesafe`. For a local `jev` command, choose
`--backend jev-cli --jev-command /path/to/jev`. `doctor` checks configuration,
SDK/CLI availability, and whether the required credential environment variable is
set. It makes no network requests and does not verify account credit or model access.

`setup` is a numbered terminal wizard for the host, judge backend, and model.
It asks for no API keys. Codex setup calls the installed client's `model/list`
and puts Sol 6.1, Luna 6, and Astra 6 first when available. It records your chosen
model and permits the advertised subset of low/medium/high. `models --discover`
shows the full native support set and defaults; `models` lists the preferred
API models without checking account access.

```bash
auto-effort setup --host codex --model sol --backend openrouter
auto-effort run --config /path/to/config.json --request-file request.txt --dry-run
auto-effort run --config /path/to/config.json --request-file request.txt
```

For offline setup, pass `--levels low,medium,high` to declare support explicitly.
If discovery fails, setup stops and creates no configuration; it does not silently
assume the model is available. `astra`, `sol`, and `luna` resolve respectively to
`gpt-6-astra`, `gpt-6.1-sol`, and `gpt-6-luna` for GPT hosts.

`setup` and the existing lower-level `init` create one profile and never overwrite an existing configuration. Add
other models by editing its `targets` object. A controller can select a target
for its main agent and a different, cheaper profile for a subagent.

The default config is `%APPDATA%\AutoEffort\config.json` on Windows,
`~/Library/Application Support/AutoEffort/config.json` on macOS, and
`${XDG_CONFIG_HOME:-~/.config}/auto-effort/config.json` on Linux. Override it with
`AUTO_EFFORT_CONFIG` or the CLI's `--config` option.

## Claude, Grok, and Antigravity setup

These commands configure Auto Effort on the user's own machine. They do not
install clients, sign in, restore credentials, or change an agent's settings.
Judge authentication is separate from the agent's authentication. The user must
declare efforts supported by their selected model; only Codex has automatic
capability discovery here.

```bash
# Claude Code: uses its native --effort flag when launching a new task.
auto-effort setup --host claude-code --model sonnet --backend openrouter --config claude.json
auto-effort run --config claude.json --request-file request.txt --dry-run
auto-effort run --config claude.json --request-file request.txt

# Claude API: returns an output_config.effort patch to your existing client.
auto-effort setup --host claude-api --model YOUR_CLAUDE_MODEL --backend openrouter --config claude-api.json
auto-effort select 'Implement the feature' --config claude-api.json --effort medium

# Grok Responses API: returns reasoning.effort to your existing client.
auto-effort setup --host grok --model grok-4.7 --backend openrouter --config grok.json
auto-effort select 'Implement the feature' --config grok.json --effort medium

# Antigravity: honest passthrough while a supported effort boundary is absent.
auto-effort setup --host antigravity --model YOUR_SELECTED_MODEL --backend openrouter --config antigravity.json
auto-effort select 'Implement the feature' --config antigravity.json
```

Claude Code's [`--effort`](https://code.claude.com/docs/en/cli-reference) applies
to a newly launched session. Claude's API uses
[`output_config.effort`](https://platform.claude.com/docs/en/build-with-claude/effort).
Grok's [reasoning guide](https://docs.x.ai/developers/model-capabilities/text/reasoning)
defines model-dependent effort support and the Responses request field. Use
`--levels` when the common low/medium/high set differs from your model's support.
API profiles require your host to apply their settings before each model call.

Antigravity's documented [PreInvocation hook](https://www.antigravity.google/docs/hooks#preinvocation)
injects messages but does not expose a native effort override. Its setup profile
therefore has `adapter: disabled`: no Jev call, no applied settings. An MCP tool
alone cannot turn that into automatic routing. A custom controller with a verified
Gemini request boundary can use the existing custom budget/level mapping instead.
No live Claude, Grok, or Antigravity session was used to verify these portable paths.

## Operate and remove

- `auto`: return an effort patch automatically after the confidence gate.
- `shadow`: return a proposal with no operative settings or launch arguments.
- `off`: skip Jev and return no operative patch.

An explicit effort override takes precedence in all modes and makes no Jev call.
For a model with no effort control, declare `"adapter": "disabled", "levels": []`.
It returns an unsupported-target result with no judge call or settings patch.

Use `pipx uninstall jev-auto-effort` to remove a pipx installation. User configuration
is separate and can be retained or deleted by its owner. This package installs no
background service and edits no agent's global settings. A host runs the JSON
process only while it needs the integration.

## Check a built release locally

From a standalone source checkout, build the distribution and run its installation
check:

```bash
python -m pip install '.[dev]'
python -m build
python scripts/check_install.py --wheel dist/jev_auto_effort-0.4.0a2-py3-none-any.whl
```

The check creates and removes a temporary environment, installs the wheel without
extras or network access, and checks imports, CLI commands, configuration, and
protocol recovery outside the checkout. If Node is available, it also runs two
requests through the installed CLI. Its judge checks use private/manual/off modes
with provider credentials removed. This command is included in standalone CI;
the executed checks and remaining limitations are recorded in [VALIDATION.md](VALIDATION.md).

## Run bounded Codex scenarios

Preview first; add `--execute` to make real judge and Codex requests with your own
accounts:

```bash
python scripts/check_codex.py --model luna
python scripts/check_codex.py --execute --model luna --paired --output results.json
```

Use `sol` or `astra` for the other preferred models. `--limit 1..3` bounds cases;
`--timeout 1..180` bounds each launch. The paired run compares automatic effort
with fixed medium on the same input/model and stops after two consecutive failed
checks. It records exact-answer success, unexpected tool calls, token usage,
judgment confidence, and elapsed time. This is an initial synthetic check of code
analysis, with no repository editing; held-out coding tasks remain necessary for
quality and savings recommendations.

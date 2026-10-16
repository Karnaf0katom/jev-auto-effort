# Integrate an agent-control tool

Call Auto Effort immediately before a model request or agent launch. Supply a short
task summary and optional previous plan; retain the host's original conversation,
credentials, tools, permissions, and model request. An effort selector can work
where the host exposes an effort setting or a reasoning token budget.

## Python controller

```python
from auto_effort import AgentController, Config

selector = AgentController(Config.load())

selection = selector.select(
    incoming_request,
    target="default",
    context=approved_task_summary,
    current_effort=current_effort,
)
native_request = selection.apply(original_model_request)
# Pass native_request to your existing authenticated model client.
```

`apply()` copies the request, checks that its model matches the target profile, and
merges only the profile's effort setting. Inputs, tool calls, tools, streaming flags,
metadata, and other settings stay in the original request. For a Codex launch, use
`selection.cli_args` in your normal launch argument array instead of `apply()`.

The host supplies `current_effort` on each call if it wants uncertain judgments
to retain its current setting. Each request is judged independently; a subagent
uses its own target and current effort. Auto Effort does not start another agent.

## Controllers in any language

Start one process for the lifetime of a controller connection:

```bash
auto-effort serve --config /path/to/config.json
```

Send one JSON object per stdin line. A response is flushed to stdout for each line:

```json
{"id":"turn-1","target":"default","request":"Continue","previous_reply":"We will investigate the transaction race and verify the fix","current_effort":"medium"}
```

The response contains `id` and either `result` or `error`. `result` uses the
[controller selection schema](../schemas/selection.schema.json), including:

```json
{
  "target": "default",
  "model": "your-configured-model",
  "mode": "auto",
  "apply_effort": true,
  "settings": {"reasoning": {"effort": "high"}},
  "cli_args": []
}
```

This is an illustrative subset, not a recorded live result. `apply_effort` means
the host should apply the returned patch; it is not a claim that an agent has
already run. Shadow/off/unsupported targets return empty patches. The optional
`decision` explains confidence, fallback, and latency without exposing prompts.

The process is sequential. A host must correlate responses by `id`; it can run a
separate selector process for independent connections. Errors do not poison the
next request. Lines are bounded to 65,536 characters, and the combined request/context/
previous-reply limit is still 12,000 characters. A [working Node client](../examples/controller.mjs)
shows process startup, request correlation, and two calls in one connection.

## Native settings and custom models

| Adapter | What the host applies |
|---|---|
| `responses` | `reasoning.effort` in a model request |
| `chat-completions` | `reasoning_effort` in a compatible model request |
| `codex` | `-c 'model_reasoning_effort="<level>"'` in the launch argument array |
| `claude-code` | `--effort <level>` in a new Claude Code launch argument array |
| `custom` | A caller-declared nested parameter and value mapping |
| `disabled` | No setting; bypass the judge |

Codex `setup` discovers models through `model/list`; the other model support sets
are host declarations. Higher efforts remain opt-in. The terminal picker chooses
the model explicitly, and per-request Jev judgments keep that model fixed.
`run --config PATH --target NAME` launches a saved CLI profile and respects
off/shadow/manual behavior. The [setup guide](INSTALL.md) covers Claude Code,
Claude API, Grok Responses, and Antigravity passthrough.

For a model that uses a token budget, a profile could declare:

```json
{
  "model": "your-budget-model",
  "adapter": "custom",
  "levels": ["low", "medium", "high"],
  "fallback": "medium",
  "path": ["generationConfig", "thinkingConfig", "thinkingBudget"],
  "values": {"low": 512, "medium": 2048, "high": 8192}
}
```

These budgets are an example policy, not recommendations or a claim about a
particular provider/model. Configure and verify the exact path, accepted values,
and budgets against that model's documentation. A custom adapter cannot target
model IDs, prompts, tools, metadata, or credentials.

## Existing conversations

Apply per-call settings only through a host-supported request boundary. Some
providers have specific ways to change effort between turns. For supported GPT-6
standard single-agent Responses calls, OpenAI documents a `configuration_update`
input item that preserves the request-level effort and cached prefix. A controller
using that mechanism should translate the selected effort into that update, keeping
the request-level setting stable. Preserve updates in conversation history, avoid
adjacent updates, and follow the compaction restrictions in the
[official reasoning guide](https://developers.openai.com/api/docs/guides/reasoning#change-reasoning-mid-conversation).

Installing this package or exposing an MCP tool does not itself intercept requests
inside another product. CCC's later integration should invoke this same controller
hook at its supported launch/turn boundary, after the standalone release.

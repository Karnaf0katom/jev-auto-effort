# Related work and evaluation

Researched on 2026-10-07 from primary repositories and provider documentation.
Descriptions below report what each project documents; their claims are not
measurements of Auto Effort.

| Project | Related behavior | What we can learn |
|---|---|---|
| [spending-effort-with-jev](https://github.com/Yaxin9Luo/spending-effort-with-jev) | A Claude Code mod evaluates effort per prompt and switches only with user agreement; it includes per-turn and subagent behavior. | This is close prior art for the central idea. Our first slice is a small portable library and automatic launch boundary. |
| [Jev Auto Router](https://github.com/miniLV/Jev-Auto-Router/blob/master/README.en.md) | An experimental Codex Responses proxy selects both model and effort per model call. Its documentation distinguishes deterministic test coverage from still-incomplete live evidence. | A per-call proxy is another implementation path, but it needs session, streaming, cancellation, and authentication work beyond this library. |
| [Codex Jev Router](https://github.com/suenot/codex-jev-router) | Its current recommended tool selects local evidence; historical model-routing experiments remain. The author reports routed children were cheaper than fixed high-effort children but more expensive than a single continuing agent. | Evaluate complete task cost against a single-agent baseline, including retries and judge cost. A routing decision alone does not prove savings. |
| [RouteLLM](https://github.com/lm-sys/RouteLLM) | Routes requests between stronger and weaker models through a Python API and an OpenAI-compatible server; supports calibration and evaluation. | Benchmark the actual request distribution and compare quality at equal success criteria. This is primarily model routing rather than selecting effort on a fixed model. |
| [jev-route](https://github.com/huzeyfe07/jev-route) | An asynchronous Python intent/tool router with typed outputs and a confidence gate. | Keep the policy separate from the transport. Its purpose is intent/tool dispatch, so adding it is unnecessary for a single effort Choice. |

The idea is not new. The intended contribution is a focused, portable effort
selector: declared supported levels, automatic application, manual overrides,
bounded request input, and explicit fallback results. The first prototype was
original. Version 0.2 selectively ports the advisor's confirmation helper with its
MIT notice and adapts controller patterns from the router. Exact reuse and pinned
sources are recorded in `../THIRD_PARTY.md`.

## Provider contracts

- [TypeSafe introduction](https://docs.typesafe.ai/introduction) documents typed
  Choice results and confidence, and recommends narrow atomic judgments.
- [TypeSafe quickstart](https://docs.typesafe.ai/introduction/quickstart) documents
  `TypeSafeClient.system_one()` and the `TYPESAFE_API_KEY` environment variable.
- [Official Python SDK](https://pypi.org/project/typesafe-sdk/) version 0.7.2 was
  inspected to confirm raw question dictionaries, `model_dump()`, timeout settings,
  and `RetryPolicy(max_retries=0)`. The SDK owns its HTTP contract.
- [Official OpenRouter SDK](https://openrouter.ai/docs/client-sdks/python/overview)
  version 1.3.32 was inspected and exercised through its mock transport. The
  `alpha.decisions.create()` resource supplies portable Jev access, with retries
  disabled. Real fleet calls here continue through the registered Jev CLI.
- [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference)
  documents `model_reasoning_effort`, with support depending on model and client.
- [OpenAI reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)
  documents the Responses `reasoning.effort` field and model-dependent support.

## What must be measured before public performance claims

Run a held-out set of complete tasks on a fixed model, comparing the same agent
at fixed medium effort, fixed high effort, and Auto Effort. Use independent task
success criteria and repeated paired runs. Record:

- Successful task completion and correctness, with the same acceptance checks.
- End-to-end latency, reasoning/output tokens, and total billed cost including Jev.
- Retries and additional turns required after a low-effort choice.
- Fallback rate, effort distribution, and agreement with human routing labels.

The small synthetic smoke set in `examples/requests.json` checks that the provider
and adapter work together. It is not a task-quality benchmark or evidence of
token savings. The labels express our initial rubric; they are not provider truth.

An unresolved risk is that models already adapt reasoning within an effort setting.
If Auto Effort lowers quality or its total cost/latency exceeds a fixed baseline,
keep it experimental or stop promoting the automatic mode. A follow-up needs a
brief caller-supplied summary to classify requests such as “fix it” accurately.

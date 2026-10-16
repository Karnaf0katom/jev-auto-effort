---
name: auto-subagents
description: Choose a model and effort with Jev for an authorized bounded CCC helper task, and record its launch and checked outcome. Use with configured Auto Effort routing; the main model remains the user's choice.
---

# Auto sub-agents

Keep the main session's selected model. Auto effort is selected at launch. The
CCC adapter retains that resolved setting on subsequent turns and links an
inherited handoff to its original decision. Explicit user model/effort changes
take precedence. This skill does not intercept native helper calls.

Use a helper when its separate answer or work is useful to the authorized task.
Give it one deliverable, one acceptance check and a concise final report. Include
the relevant files and constraints rather than the parent conversation. For a
read-only scout, say what exact fact it must find. For an edit, name the allowed
files and the behavior that must pass. For a review, provide the artifact and
require a verdict with specific findings.

From the task's project directory, pass the brief via stdin:

```bash
ccc spawn --engine codex --model auto --effort auto --json \
  --name "bounded-helper" --cwd /path/to/project \
  --task-id bounded-task --routing-summary "Extract the explicitly supplied values and verify each against its declaration."
```

The CLI resolves the parent session through process ancestry. If that is
unavailable, supply `--report-to` with the actual parent session ID. The normal
CCC spawn path enforces admission and model availability. The configured
standalone router asks Jev to select one declared model, then an effort that
model supports; uncertainty keeps the declared fallback. Use an explicit model
or effort only when the user or evidence requires that override. Do not inherit
the parent's expensive model just because it is the parent.

Read the returned `session_id` and `auto_routing_decision_id`. Inspect the helper's
final result through CCC and run its acceptance check. Attach the measured result:

```bash
auto-effort outcome DECISION_ID --acceptance passed --evidence-id CHECK_ID
```

Use `failed` for a failed check, and `unknown` when no acceptance result exists.
Add measured tokens, cost, elapsed time and retries when available; retain unknown
values when they are missing. A successful launch or an agent's own assertion is
not an acceptance check. Preserve decision IDs when an attempt needs repair so
the final evaluation includes the cost of failed attempts.

Use a short task-class summary instead of passing operational instructions and
completion footers to Jev. Keep the actual file/constraint brief on stdin. For a
repair, retain the task ID, set `--attempt 2` (and so on), and link the prior
selection with `--parent-decision-id DECISION_ID`. Use the existing native CPU
waiter while checks are queued; do not repeatedly poll through the model.

Honor project instructions, ticket ownership, concurrency and spending limits.
Helpers do not delegate further. A rejected or uncertain launch is a result to
resolve before another launch; do not bypass its gate or blindly replay it.
Installation does not enable a queue, create tickets or publish changes.

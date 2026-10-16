# Decision records and sub-agent routing

The main agent's model is an explicit user choice. `select` chooses effort for
that model. `route` is the separate boundary for a bounded helper: choose a
declared model target, then choose its supported effort. A controller must call
these boundaries; installation does not intercept native helper tools.

Version 0.4.0a1 also supports inspecting a selection and inheriting it into a
distinct continuation. The resolved launch setting is retained until an explicit
user change or a new host selection. Inherited settings do not make another
judge call and are labeled `inherited_selection`, with `parent_decision_id`
pointing to the original decision. They are not presented as Jev proposals.

The CLI records each `pick`, `select`, `route`, `serve` turn and `run` locally in
SQLite, including manual overrides, fallbacks, off/shadow decisions and dry runs.
The default is the platform's user state directory. Set `AUTO_EFFORT_LEDGER` or
`--ledger` to choose the file; `--no-log` disables recording. Python callers opt
in with `AgentController(config, ledger=DecisionLedger())` or `SubagentRouter`.

Records contain model/effort, support sets, policy version, confidence, judge
latency/cost and opaque project/task/ticket/parent/session IDs. Requests, replies,
source files, provider errors and credentials are not stored. Nothing is uploaded.
Use opaque IDs rather than personal names or paths. Storage failures are visible
and stop selection or launch, rather than silently lose its evidence.

## Record the result of real work

```bash
auto-effort select --config config.json --request-file task.txt \
  --project-id example --task-id task-1 --ticket DEMO-1 --trial-id trial-1
# Save the returned decision_id, then execute and check the task in your host.
auto-effort bind DECISION_ID --session-id SESSION_ID --status started
auto-effort outcome DECISION_ID --acceptance passed --evidence-id check-1 \
  --tokens 1200 --agent-cost-usd 0.03 --retries 0 --elapsed-ms 20000
auto-effort report --trial-id trial-1
auto-effort export > records.jsonl
```

```bash
auto-effort inspect DECISION_ID
auto-effort inherit DECISION_ID --parent-session-id ORIGINAL_SESSION_ID
# Bind the returned new decision ID to the actual continuation session.
auto-effort observe NEW_DECISION_ID --session-id SESSION_ID --turn-id TURN_ID \
  --status completed --tokens 1200
```

Observations retain measured execution without inventing acceptance. Token
observations are cumulative for each session, and reports use its latest value
rather than summing duplicate completion notifications. `completed` is a process
status, not `passed`. Host-requested settings must not be labeled as observed
native settings without execution evidence. Explicit outcome costs, tokens and
quality remain independently host-reported.

Report-level `observations` deduplicates a native session across decisions. A
session shared by multiple routing groups has unknown per-group token allocation;
`shared_session_token_samples_excluded` identifies those exclusions. Cumulative
session measurements are not per-task costs. Use measured task deltas and complete
attempt chains when comparing routing policies.

For transport or classification probes, use `pick`, `select` or `route` with
`--dry-run`; they still classify but are excluded from live trial results. Reports
also expose selection-only counts, failed launches, missing outcomes, fallback
reasons and the available `proposed_effort` labels. Old records without a proposed
label remain unknown; they are not reconstructed by guessing.

For a verified historical probe that was recorded before `--dry-run`, use
`auto-effort mark-probe DECISION_ID`. This appends an audit event and leaves the
original selection unchanged. Only a selection with no execution, binding or
outcome can be corrected this way; a marked probe cannot later receive work
events or be inherited. Keep evidence for the correction in the host's audit.

An evidence ID points to acceptance results retained by the host. Acceptance is
host-reported; Jev never judges final correctness. Zero exit status is execution
evidence only. Missing quality, tokens and cost stay unknown. Repeated outcome
reports retain their history, and reports use only the latest one per decision.
Dry runs are excluded from trial results; off, shadow and automatic runs remain
separate. Both model-judge and effort-judge costs are reported when available.

For retries, retain the task/ticket/trial IDs and increment `--attempt`, optionally
linking `--parent-decision-id`. Reports count decisions, not unique successful
tasks. Compare complete task chains, including failed attempts and both judges,
against fixed effort before claiming savings or changing routing defaults.

Use the same opaque task and trial IDs for a repair, increment `--attempt`, and
pass `--parent-decision-id` for its previous recorded attempt. The referenced
decision must exist in the same ledger. A continuation retains its original
task/trial identity with a distinct selection ID; a newly scoped task should be
selected and identified separately.

## Declare helper targets

Your existing Auto Effort configuration can declare multiple targets. Choose
exact model IDs and native efforts verified in your installed host:

```json
{
  "schema_version": 1,
  "backend": {"name": "typesafe", "timeout": 5},
  "default_target": "worker",
  "mode": "auto",
  "targets": {
    "worker": {"model": "your-routine-model", "adapter": "codex", "levels": ["low", "medium", "high"], "fallback": "medium"},
    "scout": {"model": "your-small-model", "adapter": "codex", "levels": ["low", "medium"], "fallback": "medium"},
    "deep": {"model": "your-reasoning-model", "adapter": "codex", "levels": ["low", "medium", "high"], "fallback": "medium"}
  }
}
```

A separate `routes.json` describes which work each available target can handle:

```json
{
  "worker": {"role": "worker", "criteria": "Routine bounded implementation with an existing contract and one acceptance check."},
  "scout": {"role": "scout", "criteria": "Read-only search, confirmation or small log digest with an exact answer check."},
  "deep": {"role": "deep", "criteria": "Hard reasoning across interacting systems, or a documented lower-lane failure."}
}
```

```bash
auto-effort route --config config.json --routes routes.json --request-file task.txt \
  --parent-session-id parent-1 --ticket DEMO-1 --trial-id trial-1
```

Only declared targets are eligible. The configured default must be in the
routes. The model judge receives each target's declared role and task criteria.
It has no price catalog or measured model-quality ranking; declare the rubric
using models and capabilities verified in your host. A confidence below the
configured threshold (at least 0.8), `other`,
invalid replies or judge failure retain the current/default target. Private
tasks and recognizable credentials skip both judges. Manual `--target` and
`--effort` override their respective automatic choice. Off makes no judge call;
shadow records a model proposal while retaining the host's current model and
effort. Hosts own task readiness, permissions, concurrency and execution.

## Optional CCC launch adapter

This integration requires a CCC build that contains the separate adapter and its
Auto routing endpoints. The Python package does not install that host code, and
this document does not claim the integration is available in upstream CCC.

Install the standalone CLI and declare your available Codex targets first.
Configure the CCC dashboard process with:

```bash
export CCC_AUTO_EFFORT_CONFIG=/path/to/config.json
export CCC_AUTO_MODEL_ROUTES=/path/to/routes.json
# Optional if auto-effort is not on the dashboard process's PATH:
export CCC_AUTO_EFFORT_COMMAND='/path/to/venv/bin/auto-effort'
```

Restart the dashboard and any worker that loads its Codex adapter. In the existing new-session composer,
choose your main model and **Auto (Jev)** in the effort selector. The CLI equivalent
is `ccc spawn --engine codex --model YOUR_MAIN_MODEL --effort auto`, with the task
on stdin. Auto chooses at launch and retains the resolved setting on later CCC
turns. An implicit handoff inherits it with a linked decision. Explicit model
or effort changes take precedence. It does not rejudge every turn or take over
native `spawn_agent` calls.

The main session receives the helper-routing instructions. A helper launch uses
`ccc spawn --engine codex --model auto --effort auto --report-to PARENT_ID` from
the intended project directory. The normal CCC spawn path still validates the
model and enforces admission. A helper cannot create another routed helper.
Selection returns a decision ID; the launch receipt attaches the native session
ID. The host records acceptance evidence after checking the task. No queue is
enabled and no ticket is filed merely by installing or selecting Auto.

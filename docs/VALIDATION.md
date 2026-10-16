# Validation record

## Experimental candidate 0.4.0a1 — 2026-10-15

This candidate adds preserved launch settings in the optional host adapter,
linked continuations and repairs, fallback proposal labels, measured execution,
and explicit selection-only probes. Confidence, privacy and capability guards
remain in place. Completed execution never implies checked acceptance.

The exact standalone source, artifact hashes, runtime, test count, clean-wheel
installation and source-archive reproduction results are recorded in the
accompanying `RELEASE-MANIFEST.json` produced by `scripts/check_release.py`.
A manifest is written only after the complete gate passes. Retained logs identify
failures; the absence of a final manifest is not a passing release check.

The report also checks repeated decisions on one native session: cumulative usage
is counted once, and totals shared by multiple effort/model groups are not assigned
to each group as if they were separate work.

The owning validation environment is Linux. The prepared standalone workflow
covers Python 3.10 and 3.13 on Linux, macOS and Windows; those six CI jobs have
not run. Linux checks and Python syntax compatibility do not establish Windows
or macOS runtime support. Nothing has been published.

The separate optional CCC adapter passed 67 focused tests covering launch
binding, explicit overrides, fast and resumed follow-ups, handoff lineage,
helper depth, repair identities and measurement versus acceptance. Its existing
Auto UI unit checks also passed. Host adapter source is excluded from this MIT
package and needs its own release and runtime application.

## Paired public-task smoke check — 2026-10-15

The run used `gpt-6-luna`, eight task pairs, identical initial agent inputs and
model within each pair, alternating policy order, and at most two attempts.
All tasks passed on the first attempt; no agent tools were used. Code answers
were graded in a separate bounded process against validation and boundary
checks. The inventory case includes the observed false-empty and missing nested
Git-root failure. These fixtures are public synthetic tasks, not held-out
repository-editing projects.

| Measurement | Auto | Fixed medium |
|---|---:|---:|
| Accepted tasks | 8/8 | 8/8 |
| Failed attempts / repairs | 0 / 0 | 0 / 0 |
| Applied effort | 8 medium | 8 medium |
| Effort source | 2 Jev, 6 fallback | 8 explicit |
| Measured elapsed time, including the judge | 114.110 s | 108.927 s |
| Judge time | 12.680 s | 0 s |
| Reported judge cost | $0.000186522 | $0 |
| Input tokens | 160,934 | 160,792 |
| Cached input tokens (included above) | 77,568 | 69,632 |
| Output tokens | 602 | 600 |
| Agent monetary cost | unknown | unknown |

Auto took about 4.8% longer in this small run, with different cache hits and
provider latency. It never applied a lower or higher effort, so this run does
not establish a benefit from adapting effort. It establishes the tested launch,
recording and grading paths. Do not infer general quality, optimal choices or
cost savings. The confidence threshold was not lowered to increase activity.

Full prompt-free attempt records, decision IDs, source hashes, usage and grader
results are in [the public result](../examples/benchmark_results-20261015.json).
The [task fixtures](../examples/benchmark_tasks.json) and
[runner](../scripts/benchmark.py) make the check reproducible. All attempts are
retained; unknown costs remain unknown.
The result hashes identify the benchmark's implementation. Subsequent report
aggregation fixes leave its effort policy unchanged.

## Retrospective installation audit

A separate review reconciled all 22 selections then present in one installation
with native execution and host lineage. Of these, 16 launched sessions matched
the initial recorded model and effort: seven main chats and nine helpers. The
helpers used five small-model, one reviewer-model and three routine-model
launches. Eight helper assignments passed their acceptance checks; one inventory
answer failed and was corrected by its owner. This is evidence that explicit
helper model routing is active, not that every answer or selected effort is best.

All 16 launches used medium; 13 were effort fallbacks. Two later main-chat
executions used a different effort, and one continuation had no routing record.
These gaps motivated the continuation fixes. Missing main-chat acceptance and
agent costs remain unknown. Five setup probes are tracked separately from real
work without rewriting their original selection records. Private transcripts,
project details, host configuration and runtime ledgers are not distributed.

## Historical checks

### Local history refresh — 2026-10-16

A read-only refresh covers all 39 selections and 192 events then present in the
configured installation, including recorded descendants. There are 30 bound
sessions: nine main chats and 21 helpers. All 30 initial native launches match
their recorded model and effort. All used medium: 27 fallbacks and three Jev
effort choices. Helpers used seven small-model, two reviewer-model and 12
routine-model launches. Their recorded outcomes are 18 passed, two failed and
one unknown; main outcomes are one passed and eight unknown or missing.

The additional helper performed a bounded read-only runtime check, with its
owner recording acceptance. The two additional main chats retain medium on their
recorded turns and have no checked outcome. These observations extend the earlier
audit; they do not independently regrade every historical assignment. The two
old later-effort differences and one untracked continuation remain in the history.
No native subagent interception or measured agent-dollar sample is established.
The source repository includes only aggregate results, without private sessions,
project names, host paths or runtime ledgers.

The publication review also adds declared roles to the model-choice rubric and
replaces automatic source discovery with an explicit export manifest. Offline
regressions check routing contracts and prevent unlisted files, path escapes or
symlinks from entering that export. The older live results predate these changes;
they are not a live measurement of the updated rubric.

### Earlier package checks

Version 0.3 previously passed 153 package tests with both provider SDKs installed,
a fresh-wheel installation and Node controller check. Three paired synthetic
scenarios yielded six correct answers, with mostly medium fallbacks. These are
historical results, not a passing receipt for this candidate.

## Release and recommendation limits

The present scope is an experimental standalone selector and explicit host/helper
routing boundary. Installation does not intercept native `spawn_agent` calls or
rejudge every existing conversation turn. The optional adapter retains a resolved
launch selection until an explicit change or a new host selection.

Runtime validation currently covers Linux. Run platform CI before claiming cross-platform support. Before
recommending Auto as an efficiency improvement, evaluate held-out project tasks,
repeat the fixed-effort comparison, retain complete failed-attempt and repair
chains, and measure or explicitly estimate agent costs. The current smoke check
provides no savings claim. See [release checks](RELEASING.md).

# Validation record

## Release candidate 0.4.0a2 — 2026-10-18

The [six-job platform check](https://github.com/Karnaf0katom/jev-auto-effort/actions/runs/39129801523)
passed on Python 3.10 and 3.13 across Linux, macOS and Windows. Each Linux and
macOS job passed 299 tests. Each Windows job passed 294 tests and skipped five
POSIX-only launch/terminal tests. All six jobs verified a clean wheel installation,
the Python/CLI protocols, the Node 22 controller, bundled attribution, and
byte-for-byte wheel reproduction from the source distribution within that job.

The uploaded release manifests were checked against the exact 63-file source
export, and their wheel/source-archive SHA-256 values were verified. This platform
run checks the implementation before this documentation update; the release
workflow checks the final release source again. Artifact hashes and retained logs
are available with that workflow and the prerelease assets.

These installation and regression checks do not establish downstream agent task
quality or cost savings. The routing evaluation below remains a synthetic,
partly development-set result. This release retains experimental alpha status.

## Pre-publication routing evaluation — 2026-10-18

The [recorded evaluation](../examples/file_effort_evaluation-20261018.json)
retains all 76 provider judgments across two phases. Expectations were assigned
before calls using the documented rubric. These are synthetic request descriptions;
no large file was processed and no downstream agent task was executed.

The initial 32 new cases matched 27 expected levels. Four filename/path detection
gaps (HTML, CSS, binary and relative SCSS) caused medium instead of high. One
routine file task conservatively received high. Detection now handles common web
formats, relative paths with arbitrary suffixes, and bare filenames with unknown
suffixes. The confidence threshold remains 0.8.

The second phase rejudged all 32 cases and 12 fresh follow-up cases:

| Expected effort | Matched | Other applied effort |
|---|---:|---|
| Low | 15/15 | None |
| Medium | 5/6 | One high fallback |
| High | 23/23 | None |
| Total | 43/44 | One conservative overestimate |

The 12 follow-up cases matched 12/12. The remaining mismatch proposed medium at
0.79 confidence, below the 0.8 guard, so the file fallback stayed high. The first
32 cases became development data when used to fix detection. The labels reflect
a maintainer rubric, not measured optimal difficulty. Recorded answers were
applied through the real policy; replay time is not live client latency. These
results do not establish downstream quality, cost savings or general accuracy.

## File scope guard development check (0.4.0a1) — 2026-10-18

Unknown file work now defaults to high within the target's supported effort
ladder. An exact edit, named-field lookup or small described section may still
receive lower effort when both the effort and bounded-scope answers meet the
configured confidence threshold. Both questions use one judge call. Hosts can
mark attachments absent from the request text with `has_files`; the selector
does not open referenced files.

The complete package test suite passed: **285 tests** in a Linux portable test snapshot. Tests
cover missing/malformed scope judgments, privacy and input limits, provider
failures, supported effort ladders, manual overrides, controller modes, JSON
input, CLI launch settings and file-only requests. The test recipe now includes
the existing Node `.mjs` examples required by the export manifest.

The [six recorded development cases](../examples/file_effort_smoke.json) use
synthetic public requests and actual Jev answers. Offline replays apply the
expected effort in all six cases: low for an exact replacement, a named-field
lookup and a concrete short reference; high for a filename alone, vague file
work and concurrency diagnosis. An initial live pass was too conservative for
two small tasks. The revised instructions explicitly accept a concrete context
description as evidence of bounded scope; the confidence floor remains 0.8.

These prompts were used while tuning the instructions. The replays check policy
against recorded answers, not future judge reliability. This is not held-out
quality or cost evidence. At this earlier check, a new wheel/source-archive
release gate and the cross-platform CI matrix had not been run.

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
or macOS runtime support. Nothing had been published at the time of that check.

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

Runtime checks cover Python 3.10 and 3.13 on Linux, macOS and Windows, with the
five POSIX-only Windows exclusions recorded above. Before
recommending Auto as an efficiency improvement, evaluate held-out project tasks,
repeat the fixed-effort comparison, retain complete failed-attempt and repair
chains, and measure or explicitly estimate agent costs. The current smoke check
provides no savings claim. See [release checks](RELEASING.md).

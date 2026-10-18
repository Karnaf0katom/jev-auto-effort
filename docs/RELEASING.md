# Experimental alpha release

The candidate is `jev-auto-effort==0.4.0a2`. The GitHub prerelease `v0.4.0a1`
already exists; the updated candidate gets a new version and tag. Publication is a separate owner
action after the exact source and artifacts have been checked. Source and binary
artifacts are MIT licensed with the bundled attribution; optional host adapters
are not included in the distribution.

## Candidate check

From a standalone source checkout, install development/provider test dependencies
and run:

```bash
python -m pip install '.[dev,providers]'
python scripts/check_release.py --output /tmp/auto-effort-release
```

Choose a fresh output directory outside the checkout. The check copies only files
explicitly listed in `export-manifest.json`, tests that
independent export, builds a wheel and source distribution, installs the wheel
in a clean environment, verifies the Python/CLI/Node contracts, and requires the
source distribution to reproduce the wheel. Its output includes a source tree,
artifact SHA-256 values, the source manifest and retained check logs. It makes
no provider calls and does not publish anything.

The export and build use normalized file permissions and a fixed build timestamp
so source-archive reproduction does not depend on the maintainer's local umask.
If reproduction fails, both wheels and their entry-level differences are retained;
the check does not relax its byte-for-byte comparison.

The standalone GitHub workflow runs Python 3.10 and 3.13 on Linux, macOS and
Windows. A prepared workflow is not a passing platform result. Record only the
platforms actually checked in `VALIDATION.md`; keep unexecuted matrix jobs explicit.

## Routing and outcome gates

- A native launch must use its recorded model and supported effort.
- A host adapter must retain resolved launch settings on subsequent turns.
  Handoffs get their own decision identity linked to the original; an inherited
  setting is not presented as another Jev judgment. Explicit user changes win.
- Private, unsupported, uncertain and unavailable-judge paths retain the documented
  fallback. The confidence guard remains at least 0.8.
- Inspect fallback `proposed_effort` independently from applied effort. A short
  task summary is preferable to operational instructions and completion footers.
- Failed launches and repairs keep stable task IDs, incremented attempts and
  parent-decision links. Execution observations never imply acceptance.
- Record checked outcomes, tokens and time when available; unknown agent cost
  stays unknown. Exclude selection-only probes from live-work claims.

## Paired public task check

```bash
python scripts/benchmark.py --execute --model YOUR_AVAILABLE_MODEL \
  --jev-command /path/to/jev --attempts 2 --output /tmp/auto-effort-benchmark
```

The default is eight paired tasks, with at most two attempts per mode when
requested. Each pair starts with identical agent input and model. Task classes
cover exact lookup, the nonempty/nested-Git inventory regression, Python coding,
concurrency/retry diagnosis, and independent evidence review. Output includes
decision IDs, linked repairs, token usage, judge overhead, elapsed time and
objective acceptance. Two consecutive failures stop the run. It does not launch
persistent helper sessions or authorize repository changes.

Retain all attempted work. Compare complete task chains rather than only successful
calls. Counterbalanced order does not remove cache or provider-latency effects.
Expected rubric labels are not proof that a task requires a particular effort.
No dollar-savings claim is permitted without measured or explicitly labeled
estimated agent costs and a suitable baseline.

## Publication contents

Publish the reviewed standalone source export and its checked artifacts. Exclude
host configuration, runtime ledgers, private session evidence and host-adapter
source. Include LICENSE, THIRD_PARTY.md, the upstream MIT notice, public examples,
schemas and the public validation limitations. Document the exact supported host
boundary: CLI launch selection and explicit controller/helper routing. Installation
does not automatically intercept native `spawn_agent` calls or every model request.

For this candidate, review the exported source and artifact hashes, then push the
standalone source to `Karnaf0katom/jev-auto-effort`. Let all six configured CI jobs
pass (Python 3.10/3.13 on Linux, macOS and Windows), including the clean-install
Node controller check, before tagging `v0.4.0a2` as a prerelease. A
`node_controller: not_available` result means that check remains unexecuted.
Retain the experimental alpha status: the routing evaluation does not establish
downstream task quality or agent cost savings.

A package-registry upload is a separate publication action. Nothing in the
check scripts pushes, tags, creates releases or uploads packages.

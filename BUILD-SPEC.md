# Auto Effort architecture and release scope

Version 0.4.0a2 is an experimental standalone Python package and CLI. It selects
reasoning effort at an explicit host request boundary. A separate helper router
selects from caller-declared model targets; the main model remains the user's
choice.

## Existing implementation

- One typed Jev Choice applies only supported efforts. The confidence guard is
  at least 0.8. Uncertain, unavailable, private or unsupported requests retain
  the documented current setting or fallback. Explicit choices bypass Jev.
- Unseen file work raises the automatic fallback to high within the declared
  effort ladder. File hints come from the request or a host-supplied boolean;
  the selector does not open attachments. A second typed choice in the same
  call must confidently establish bounded scope before lower effort is applied.
- Python and JSON Lines controllers return an effort patch. CLI launch adapters
  preserve the original task input and the host's permissions and authentication.
- The local SQLite ledger records selections, model choices, launch receipts,
  continuation and repair links, measured execution, and checked outcomes.
  It stores neither prompts nor replies. Missing measurements remain unknown.
- A continuation receives a distinct decision linked to its source. Inheritance
  retains the resolved launch setting and makes no new judge call. Hosts own
  retaining these settings across later turns and respecting explicit changes.
- Installation does not intercept native subagent tools or every model request.
  The optional CCC adapter is maintained separately from this MIT distribution.

## Validation boundary

The standalone release gate is `scripts/check_release.py`: freeze the source,
test the export, build and install its wheel, check the CLI/Python/Node contracts,
and require the source archive to reproduce the wheel. Its manifest identifies
the exact checked bytes. The CI workflow applies this gate to Python 3.10 and
3.13 on Linux, macOS and Windows. Unexecuted jobs are not passing evidence.

`scripts/benchmark.py` compares bounded public tasks against fixed medium with
identical initial agent input and model. It retains failed attempts and linked
repairs, objective grading, tokens, elapsed time and judge overhead. It is a
smoke benchmark, not a general evaluation of autonomous repository editing.

The cheapest alternative is fixed effort. A performance recommendation requires
held-out project tasks and complete task-chain costs, including retries and the
judge. See [validation](docs/VALIDATION.md), [release checks](docs/RELEASING.md),
[routing](docs/ROUTING.md) and [third-party attribution](THIRD_PARTY.md).

Source publication, package upload and optional host-adapter publication remain
separate owner actions against reviewed source and artifact hashes.

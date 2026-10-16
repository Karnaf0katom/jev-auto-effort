# Contributing

Auto Effort is an experimental Python library and CLI. Keep changes focused on
explicit model/effort selection, host integration contracts, or measured outcomes.
Open an issue before proposing a new host adapter or changing routing defaults.

Install development dependencies and run the offline checks from this checkout:

```bash
python -m pip install -e '.[dev,providers]'
python -m pytest -q
python scripts/check_release.py --output /tmp/auto-effort-release
```

Choose an empty release output directory outside the checkout. The release check
makes no judge or agent calls. Live benchmarks require explicit `--execute` and
use your provider accounts; they are optional for ordinary contributions.

## Code map

| Location | Responsibility |
|---|---|
| `src/auto_effort/core.py` | Effort rubric, capability and confidence guards |
| `src/auto_effort/routing.py` | Declared helper model choice, then effort choice |
| `src/auto_effort/controller.py` | Host settings, off/shadow/auto, continuations |
| `src/auto_effort/backends.py` | Optional judge transports |
| `src/auto_effort/profiles.py`, `models.py`, `setup.py` | Configuration and capability discovery |
| `src/auto_effort/telemetry.py` | Local decisions, lineage and measured outcomes |
| `src/auto_effort/cli.py`, `protocol.py` | CLI and JSON Lines interfaces |
| `tests/`, `schemas/`, `examples/` | Offline regressions, public contracts and fixtures |
| `scripts/check_release.py`, `export-manifest.json` | Reviewed standalone export and packaging checks |

Add intended public files explicitly to `export-manifest.json`. Do not add local
ledgers, credentials, transcripts, private task fixtures or host adapter source.
Preserve required license notices. Publication uses the checked standalone export,
without the parent repository's history.

## Routing changes

Test manual choices, unsupported levels, uncertainty, judge failures, private
input and off/shadow modes. Model routing and effort routing are separate choices;
preserve their separate evidence. Hosts retain permissions and concurrency control.
Installing the package does not intercept native helper calls.

Keep the confidence floor at 0.8. A passing mocked routing test checks policy,
not model judgment quality. A successful process is not accepted work. Performance
claims need held-out tasks, fixed-effort comparisons, failed attempts and complete
agent/judge costs. See [validation](docs/VALIDATION.md) for the current evidence.

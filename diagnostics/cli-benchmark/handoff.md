# CLI-004 handoff

CLI-004 is satisfied by the existing `scripts/run_benchmark.py`; no extra
wrapper or code change was needed. It reads `configs/benchmark.json` and
calls the public `sudoku.runner` API: `RunnerConfig`, `prepare_run`, and
`execute_run`. Prepare-only is the default; only explicit `--execute` calls
solver jobs. `docs/runner-api.md` and `docs/results-schema.md` define the
prepared plan and result contract.

Checks performed:

```powershell
& '.\.venv\Scripts\python.exe' -B '.\scripts\run_benchmark.py' --help
& '.\.venv\Scripts\python.exe' -B '.\scripts\run_benchmark.py' --config '.\configs\benchmark.json' --output '.\diagnostics\cli-benchmark\prepared plan'
```

The prepare-only command accepted paths containing spaces and reported
`Prepared 906 jobs; no solver was run`. The plan contains `run.json` and
`schedule.json`; this was plan preparation, not pilot or benchmark execution.
Captured output is in `prepare-output.txt`. No `--execute`, runner, adapter,
environment, frozen data, README, checklist, status or registry was changed.
No blocker for CLI-004. CLI-005/006 remain pending their analysis API and
README integration.

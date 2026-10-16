# RUN-001..008 — runner handoff

Schema/API ready for SAT08 analysis and SAT06 CLI integration:
`docs/results-schema.md`, `docs/runner-api.md` (v1).

Owned implementation: `src/sudoku/runner.py`, `runner_worker.py`,
`runner_process.py`, `scripts/run_benchmark.py`, `configs/benchmark.json`,
`tests/test_runner.py`. No adapters, checker, data, shared tests, README,
report, venv or coordination checklists changed.

RUN-001..008 evidence: sequential spawn worker; Windows kill-on-close Job
Object assigned before gate release; START/END synchronized shared state;
on-time END separates postprocessing watchdog from solve cutoff; absent/late
END produces TIMEOUT; startup/postprocessing/cleanup failure produces ERROR.
Job termination waits until no active descendants. CSV flushes each result,
preserves unknown timings, rejects duplicate IDs, and links checked solutions.
Config/version/code/data hashes are stored once. Deterministic schedule has
906 unique jobs, C10 subset B16 subset S80; no extra SAT subset runs.

Commands (project root):

```powershell
& '.\.venv\Scripts\python.exe' -B -m pytest tests/test_runner.py -q -p no:cacheprovider --basetemp diagnostics/runner/test-temp-r3 --junitxml diagnostics/runner/tests-r3.xml
& '.\.venv\Scripts\python.exe' -B '.\scripts\run_benchmark.py' --output '.\diagnostics\runner\prepared-plan'
```

Result: 26 tests passed, no skips. Covers final deadline recheck, real diagnostic
worker END near deadline, delayed validation, startup/build/postprocessing hangs,
orphan child cleanup, CSV nulls/artifacts and dependency/cutoff mismatch rejection.
One production SAT worker empty-4x4 fixture checks adapter integration; no claim
of pilot coverage. Initial test run had fixture-parent-directory setup errors;
the final XML supersedes that attempt. Test fixtures stay under diagnostics.

experiment_medium reviewed fairness/races/cleanup; its dependency-version and
cutoff-consistency findings were fixed and rechecked. No remaining review blocker.
Prepared plan only, no research CSV. RUN-009..014 not performed; full backend
pilot and final code/config freeze remain prerequisites to main execution.

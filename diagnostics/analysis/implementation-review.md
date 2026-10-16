# SAT08 implementation handoff — RES-001..007

Implementation and diagnostic verification only. No main CSV or final research
conclusions have been accepted. RES-009/010 remain pending.

## Delivered

- `scripts/analyze_results.py`: analysis API v1 and command line.
- `tests/test_analysis.py`: artificial, explicitly marked fixtures; no solvers.
- `docs/analysis-api.md`: validation rules, null semantics, outputs and integration.
- `diagnostics/analysis/fixtures/sample-run`: six ARTIFICIAL timing observations
  using already frozen input/witness files. Not benchmark evidence.
- `diagnostics/analysis/sample-output-v2`: CSV/LaTeX and PNG/PDF exports from that
  fixture, with DIAGNOSTIC titles and NOT FINAL RESEARCH RESULTS in audit.json.

## Checks

Final test command from the project root:

```powershell
& '.\.venv\Scripts\python.exe' -B -m pytest tests/test_analysis.py -q --basetemp diagnostics/analysis/fixtures/pytest-04 --junitxml diagnostics/analysis/tests-04.xml
```

Result: **35 passed in 20.02 seconds**. XML: `diagnostics/analysis/tests-04.xml`.
Earlier test attempts are retained as diagnostics, not presented as passing.

CLI export command completed successfully: validated six artificial rows.

```powershell
& '.\.venv\Scripts\python.exe' -B scripts/analyze_results.py --run diagnostics/analysis/fixtures/sample-run --output diagnostics/analysis/sample-output-v2 --mode diagnostic
```

Inspected CNF, status-count and matched-time PNGs. The final matched-time v2
figure has legible unclipped captions and integer board-size ticks. Real-data
plots will still need visual review with their actual legend/stratum sizes.

Targeted model-review findings were fixed: diagnostic mode alone cannot waive
UNSAT on real data; TIMEOUT is restricted to measurement/complete phases.
Tests cover these cases. One-repeat/missing samples have no ordinary medians
or speed comparison. Duplicate repeats across runs are rejected.

## Limits and pending evidence

Actual runner CSVs, a code/config-approved run, and final three-repeat results
are still required to accept RES-001..007 on research data. No final statistics
were generated here. The schema has no producer-side solution hash: audit
records analysis-time SHA-256 and a fresh independent checker result; it does
not assert an unavailable historical checksum. Any real-data UNSAT stops
analysis with the job ID and leaves the raw artifacts intact.

No runner, adapter, raw research CSV, frozen data, README, report, checklist,
status or registry file was edited. No benchmark or solver was run.

# Final release regression — core/data/results only

PASS: one complete current-suite execution, **653 passed in 38.84s**, zero
failure/error/skip. No tests or frozen implementation were changed to pass.

From `D:\KHMT\Project solo` (PowerShell):

```powershell
& '.\.venv\Scripts\python.exe' -B -X utf8 diagnostics/final-release-qa/check_core.py before
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\.venv\Scripts\python.exe' -B -X utf8 -m pytest tests -q -p no:cacheprovider -o junit_family=xunit1 --basetemp 'D:\KHMT\Project solo\diagnostics\final-release-qa\pytest-temp-release-01' --junitxml diagnostics/final-release-qa/suite.xml
& '.\.venv\Scripts\python.exe' -B -X utf8 diagnostics/final-release-qa/check_core.py after
```

The basetemp was new for this run. Logs: `suite-output.txt`, `suite.xml`,
`core-before.json`, `core-after.json`, `before-sha256.json`.
Suite XML SHA256:
`9d20dc29bbbf46c0574c1cec85515608107cdf4bfb3212b6b74d127a0d5cc6e0`.

Required current regression groups are explicitly linked to passing JUnit
test IDs in `core-after.json`: SAT/UNSAT agreement with independent oracle,
invalid parser gating, existential auxiliary AMO/EXO checks, mapping at four
sizes, remaining build+solve budgets, validation outside measurement, Windows
hard guard, separate startup/postprocessing watchdogs, deadline/END races and
both process-tree cleanup scenarios (hanging child and orphan on success).
No Windows guard tests were skipped.

Integrity was checked before and after the suite:

- All **32 execution-frozen files**, **169 data-frozen files** and package
  versions match the recorded main run (Python 3.13.5).
- **906** complete scheduled raw rows, **903 SAT / 3 TIMEOUT**; no missing,
  duplicate or unscheduled jobs. Scope counts S80=720, B16=96, C10=90.
- `validate_run` independently rechecked **903 saved solutions**. Their
  hashes equal final analysis acceptance; raw, summary, findings and run
  identities remain consistent with `main-20261016-01`.
- **1,221** tracked core/data/raw/summary/test artifacts stayed byte-identical
  over this QA run. No benchmark rerun or pilot merge.
- Raw SHA256:
  `aac4cde1fed90857ea81a1575e326049be71a528f27a6a744435b94c42dfdda7`.

No blocker or unresolved finding in this core/data/results QA scope. Report,
PDF/provenance, README/publication and automation closure were deliberately
not inspected or modified while SAT09 finalized reports; root must combine
this evidence with the separate final report QA. No overall submission-ready
claim, checklist edit or cross-chat message was made.

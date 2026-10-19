# SAT08 final rep1 — READY_FOR_REPORT_WITH_DECLARED_ERROR

Accepted source snapshot: results/final-snapshots/final-20261020-rep1/.
Output: results/final-analysis/final-20261020-rep1/.
Quality/error flags are preserved, not upgraded to error-free.

## Verified scope and main presentation

- 110,000 primary rep1 jobs, 16,000 distinct attempted puzzles.
- Raw: 109,664 SAT; 335 TIMEOUT; 1 immutable premeasurement guard WinError6.
- Display group only: non-completed=TIMEOUT+ERROR=336; N9/N16/N25=0/2/334.
- Puzzle-level: all 10,000 N9 + 5,000 N16 + 1,000 N25 have at least one primary
  SAT across methods. This does not say each engine solved every puzzle.
- No retry replacement; historical324rep2+343rep3 remain excluded. Acquisition
  witnesses are checked but are not benchmark observations. No solver was run.
- Profile/session/worker remain separate. 24/40-worker noisy trial observations
  stay in coverage/timeline and are excluded from paired performance claims.

## Tables for SAT09

Use coverage-main.tex (SAT/NC), puzzle-completion.tex, encoding-counts-main.tex,
profile-timeline-main.tex and runtime-common-compact.tex. Full raw-status detail
and declared-error.csv are appendix/audit material; no dedicated ERROR section
in the report body is required. Explain the post-hoc NC formula in methods.
runtime-common-report.csv is compact and references sample_row in full
runtime-common.csv. Full exact JSON ID cells can exceed Python CSV's default
field limit: use csv.field_size_limit(16*1024*1024) for the audit file.

## Eight native PGFPlots groups

1. figure-completion.tex — categorical, only marks; sorted method IDs, no lines
   connecting unrelated methods, absent commercial N16/N25 entries remain absent.
2. figure-ecdf.tex — common SAT encoding single-run total ECDF.
3. figure-quantiles.tex — median/p90/p95 on the same common sample.
4. figure-clues.tex — family-separated clue/runtime and HiGHS completion panels;
   includes figure-clue-runtime.tex and figure-clue-completion.tex.
5. figure-cnf.tex — measured total variables and clauses excluding clue units.
6. figure-build-solve.tex — separate component medians, not their sum as total.
7. figure-paired-scatter.tex — exact PW/SC paired observations and equality line.
8. figure-profile-coverage.tex — chronological operational counts, not speedup.

Copy the companion .dat files and nested .tex fragments together to the TeX
build directory, or configure PGFPlots table/input search paths. Keep STIX/CAS
font and final layout under SAT09 ownership. No TeX/PDF render QA is claimed here.
Do not also add old timeout-by-N/paired-ratios plots just to duplicate figures.

figure-scope.json pins the runtime panel sample: 86 common SAT IDs for the three
encodings, N25/permutation/40% clues, largest session selected BY COVERAGE rather
than timing. Its 32-worker observations are resource-contended. PW/SC scatter
states its own paired sample. Full baseline pairs have exact n in CSV; never
compare different pair populations as an isolated leaderboard. One repetition,
no repeated-run median, confidence interval, causal clue-hardness or universal
encoding superiority claim. The source dependence/uniqueness limits are backed
by SAT05's pinned provenance receipt.

## Verification and producer receipt

11 focused tests PASS in tests-sealed.xml. final-QA.json independently checks
all output hashes, 110k denominators, original statuses/None, 1,264 paired strata,
their common IDs/ratios/type7 quantiles, NC grouping and puzzle-level success.
Both frozen input/witness BLOBs and every SAT solution were independently checked
by the final reader. Source contract/receipt/profile/SQLite identities and hashes
were validated before aggregation. Original snapshot is unchanged.

analysis-hashes.json covers all60 output files and pins snapshot/contract and
SAT05 provenance receipts. It is producer integrity evidence, not a signature or
root/report/PDF acceptance. Final HANDOFF.json carries the authoritative pin.

## Reproduction

On a clean project copy with the NEW output path absent:

```powershell
& '.\.venv\Scripts\python.exe' -B scripts/analyze_final_report.py --snapshot results/final-snapshots/final-20261020-rep1 --output results/final-analysis/final-20261020-rep1
& '.\.venv\Scripts\python.exe' -B diagnostics/expansion/final-analysis/finish_figures.py --analysis results/final-analysis/final-20261020-rep1
& '.\.venv\Scripts\python.exe' -B diagnostics/expansion/final-analysis/audit_outputs.py
```

Do not delete accepted outputs to rerun in place. The third command verifies
existing outputs without changing them; it updates only the diagnostic QA JSON.
The second command implements the latest display-group/figure steering and seals
the final receipt. No pinned/core/old analyzer/report/README/raw data was edited.
Pending downstream work: SAT09 integration, >=21-page VI/EN and visual/font QA;
SAT10 package/cross-links. This handoff does not claim full-project completion.

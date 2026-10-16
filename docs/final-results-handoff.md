# SAT08 final results handoff — main-20261016-01

RES-001..007 accepted on the main CSV; RES-009/010 analysis and numerical
traceability completed. RES-008 was delivered separately. No task checklist or
registry was edited. This handoff does not assert final report/PDF acceptance.

## Reproduce

From `D:\KHMT\Project solo`, choose a NEW output directory (the accepted one
already exists and must not be overwritten):

```powershell
& '.\.venv\Scripts\python.exe' -B scripts/analyze_results.py --run results/raw/main-20261016-01 --output results/summary/main-20261016-01-reproduced --mode final
& '.\.venv\Scripts\python.exe' -B diagnostics/analysis/prepare_final_handoff.py --summary results/summary/main-20261016-01-reproduced
```

These commands analyze saved artifacts only. The second command requires the
accepted raw SHA-256 and parent acceptance proof; it independently recomputes
statistics, compares solution hashes, and generates compact paper exports.
API v1 in `docs/analysis-api.md` remains unchanged. No frozen implementation,
adapter, solver, raw CSV or dataset was changed to obtain these results.

## Accepted outputs

All paths below are relative to `results/summary/main-20261016-01/`:

| Purpose | Files |
|---|---|
| Findings and source-row/ID trace | `findings.md`, `paper/raw-row-index.csv` |
| Verification and provenance | `verification.json`, `audit.json` |
| Full stratified results | `summary.csv`, `summary.tex`, `instances.csv` |
| Scope/solved denominators | `coverage.csv`, `paper/coverage.csv`, `paper/coverage.tex` |
| Exact matched sets/statistics | `matched-pairs.csv`, `paper/baseline-matched.csv`, `paper/baseline-matched.tex` |
| CNF counts | `cnf.csv`, `paper/cnf-size.csv`, `paper/cnf-size.tex` |
| Per-observation PAR-2 | `run-par2.csv` |
| Recommended figure group 1 | `paper/figure-cnf-size.png`, `.pdf`, `.svg` |
| Recommended figure group 2 | `paper/figure-runtime.png`, `.pdf`, `.svg`, `paper/runtime-matched.csv` |

Use the two recommended figure groups, coverage and matched baseline tables;
split the baseline table by scope/source if needed in cas-sc. Keep other pair
plots as supporting material. Do not include the original `total-time.pdf`
placeholder or all 28 pair plots. LaTeX exports are tabular fragments; the report
owner supplies captions, labels and appropriate page layout. The long source
tables are machine exports, not automatically typeset publication pages.

Suggested captions for the shared Vietnamese/English numerical source:

- CNF: variables including auxiliaries and clause counts before preprocessing;
  synthetic 50% clues, sizes 4/9/16/25; seed 0 representative because counts
  match across five seeds at fixed size/density. Y axes are logarithmic.
- Runtime: build+setup+solve seconds, 10-second total cutoff, median of
  per-instance three-repeat medians; five identical synthetic IDs per point,
  each density shown separately. All three encodings solved all 60 synthetic
  instances. Public 9×9 and baseline scope counts remain separate tables.

## Validation and limits

Validated 906 observations, 903 independent checker-passed solutions and three
HiGHS timeouts; S80/B16/C10 job counts are 720/96/90. The separate audit
recomputed 301 complete SAT median groups and 252 stratified matched-pair rows.
Solution artifact hashes agree with root acceptance for all 903 SAT results.
The raw checksum before/after is unchanged:
`aac4cde1fed90857ea81a1575e326049be71a528f27a6a744435b94c42dfdda7`.

HiGHS times out in all three repetitions of `synthetic-N25-p30-s0`; penalty
is 20 seconds each, while unknown raw timing components remain missing.
CP-SAT/HiGHS were scheduled on B16 only; commercial backends on C10 only.
There is no evidence here of commercial-engine performance on 16×16/25×25.
No solver is claimed universally fastest.

The recommended real-data PNGs were inspected: no clipping/overlap, readable
legend and caption, explicit units, correct logarithmic axes and density
strata. Vector PDF/SVG companions share the same Matplotlib figure. Review
their final physical placement in the report separately. The original full
CNF figures are readable but have repeated overlapping curves/long legends;
the compact fixed-density variant is recommended for the paper.

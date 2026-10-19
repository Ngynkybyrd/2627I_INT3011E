# Generalized Sudoku SAT — BTL1

Ta Dinh Nguyen (Tạ Đình Nguyên), student ID 24021587, INT3301E_4.
Instructor: TS. Tô Vân Khánh.

## Final documents

| Document | File |
|---|---|
| English report — submitted version, 21 pages | [PDF](reports/24021587_TaDinhNguyen_BTL1_Sudoku_EN.pdf) |
| English LaTeX — Overleaf FAST | [Source ZIP](reports/24021587_TaDinhNguyen_BTL1_Sudoku_LaTeX_EN.zip) |
| Vietnamese report — reference only, 21 pages | [PDF](reports/24021587_TaDinhNguyen_BTL1_Sudoku_VI.pdf) |
| Vietnamese native LaTeX — reference only | [Source ZIP](reports/24021587_TaDinhNguyen_BTL1_Sudoku_LaTeX_VI.zip) |

Naming convention: `24021587_TaDinhNguyen_BTL1_Sudoku_<document/language>`. Internal code/data/contract filenames are retained where required for reproducibility.

Upload the English LaTeX ZIP to Overleaf, select **XeLaTeX**, main document **main.tex**, and keep `\NativeFiguresfalse`. Thirteen diagrams are supplied as vector PDFs with embedded fonts. Original TikZ/PGFPlots sources and numeric data are retained. `OVERLEAF.txt` inside that ZIP explains changing diagrams and refreshing the vector cache. The source is fully editable; this is not a scanned report.

## Experiment and data

The final expanded experiment contains **16,000 puzzles and 110,000 primary observations**, repetition 1, cutoff 10 seconds: **109,664 SAT, 335 TIMEOUT and 1 preserved infrastructure ERROR**. The report may group 336 outcomes as non-completed; the raw ERROR is not relabeled. All 16,000 puzzles have at least one SAT across applicable methods. Timings remain separated by session/profile/worker; one repetition does not establish repeatability. The original 330,000-job/three-repetition plan was superseded and is not claimed complete.

The separate baseline contains 906 observations (903 SAT, 3 TIMEOUT), three repetitions. Baseline documents in `reports/archive/` are historical, not the final submitted reports.

- `src/`, `scripts/`, `tests/`: Python solver, independent checker, runners and tests.
- `data/`: baseline inputs, witnesses and source provenance.
- `results/raw/`, `results/summary/`: baseline raw results and analysis.
- `results/final-snapshots/final-20261020-rep1/`: sealed expanded CSV, all original inputs/witnesses, solutions and provenance. The two SQLite files are transported compressed; the larger one is split into five parts to respect GitHub's per-file limit.
- `results/final-analysis/final-20261020-rep1/`: expanded tables, figures, CSV and sealed analysis hashes.

After cloning, run `python scripts/restore_submission_data.py`. This uses only the standard library and validates all 48 snapshot artifacts against their original SHA-256 hashes. It restores the exact database bytes; it does not run solvers or replace results. Keep approximately 1 GB free for restoration. Databases are not duplicated in the English submission ZIP; use this repository for code and experimental data.

Solver use after installing the pinned Python 3.13 dependencies:

```powershell
python -m sudoku data/synthetic/synthetic-N04-p30-s0.json --method sat --encoding seqcounter --cutoff 10
```

See the API contracts in `docs/` for timing, statuses, datasets and runner behavior. Historical execution approvals record the original machine and experiment; they are not authorization to start a new benchmark on another machine. The regression suite is under `tests/`; no benchmark needs to be rerun merely to read the final results.

Repository: https://github.com/Ngynkybyrd/2627I_INT3011E
The English submission contains only the final English PDF, its portable LaTeX ZIP and this repository link. Code, dependencies, test suite, inputs and raw/processed results are provided here. Vietnamese final/reference documents stay in this repository and are excluded from that submission.

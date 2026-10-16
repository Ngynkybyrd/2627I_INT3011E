# DEL-008 clean-environment reproduction

Date: 2026-10-16 (Asia/Saigon). This is a limited CLI smoke reproduction, not
the 906-job benchmark. No source, dependency, or frozen dataset files changed.

## Environment

- Base interpreter: `C:\Users\admin\AppData\Local\Programs\Python\Python313\python.exe`
- Python: 3.13.5, 64-bit Windows build.
- Fresh venv: `tmp/repro-env/venv`; `sys.prefix` points there,
  `sys.base_prefix` points to the base Python, `system_site_packages=False`.
- Temporary directory: `tmp/repro-env/temp` via `TEMP` and `TMP`.
- Requirements installed: `requirements.txt` exactly, then editable project
  install with README flags. Initial sandboxed pip attempt failed resolving
  PyPI DNS (`getaddrinfo failed`); network access was then approved and the
  same install completed. Pip reported cached pinned wheels; no dependencies
  were omitted.
- `pip check`: `No broken requirements found.` Pip: 25.1.1.
- Exact installed package listing: `diagnostics/repro/installed-packages.txt`.

## Commands

From `D:\KHMT\Project solo` (PowerShell; `PYTHONUTF8=1`, `TEMP`/`TMP` set to
the workspace temp path):

```powershell
& 'C:\Users\admin\AppData\Local\Programs\Python\Python313\python.exe' -m venv 'tmp\repro-env\venv'
& '.\tmp\repro-env\venv\Scripts\python.exe' -m pip install -r requirements.txt
& '.\tmp\repro-env\venv\Scripts\python.exe' -m pip install --no-build-isolation --no-deps -e .
& '.\tmp\repro-env\venv\Scripts\python.exe' -m pip check
& '.\tmp\repro-env\venv\Scripts\python.exe' -B -m sudoku --help
& '.\tmp\repro-env\venv\Scripts\python.exe' -B -m sudoku 'data\synthetic\synthetic-N04-p30-s0.json' --method sat --encoding pairwise --cutoff 10 --json-output 'diagnostics\repro\sat-N04.json'
& '.\tmp\repro-env\venv\Scripts\python.exe' -B -m sudoku 'data\synthetic\synthetic-N09-p30-s0.json' --method sat --encoding pairwise --cutoff 10 --json-output 'diagnostics\repro\sat-N09.json'
& '.\tmp\repro-env\venv\Scripts\python.exe' -B -m sudoku 'data\synthetic\synthetic-N16-p30-s0.json' --method sat --encoding pairwise --cutoff 10 --json-output 'diagnostics\repro\sat-N16.json'
```

## Results

CLI help succeeded and listed all six methods and three SAT encodings. Each
solve exited 0, reported `SAT`, and returned `validation.valid=true`:

| Board | Instance | Build (s) | Solve (s) | Total (s) |
|---|---|---:|---:|---:|
| 4×4 | `synthetic-N04-p30-s0` | 0.001043 | 0.000087 | 0.001130 |
| 9×9 | `synthetic-N09-p30-s0` | 0.007138 | 0.000419 | 0.007557 |
| 16×16 | `synthetic-N16-p30-s0` | 0.058426 | 0.003866 | 0.062292 |

JSON, stdout and stderr for each command are saved as `sat-N*.json`,
`sat-N*.stdout.txt`, and `sat-N*.stderr.txt` in this directory. These are
single-run smoke timings, not benchmark observations. No full schedule was run.

## Package allowlist draft for DEL-005/006/010

This is a preparation checklist, not a staged/final archive. Use a new local
staging directory only after final report/summary review. Do not overwrite an
existing staging path or publish/submit without the user's later instruction.

### Include when final artifacts are accepted

- `README.md`, `.gitignore`, `pyproject.toml`, pinned `requirements.txt`,
  `src/sudoku/`, `scripts/` commands referenced by README, and relevant tests.
- The frozen 80 puzzle inputs, witnesses, manifest, freeze record, public
  validation, and the public-data source/attribution/license or retrieval
  directions. Preserve the exact frozen hashes.
- Raw run provenance and observations from `results/raw/main-20261016-01`:
  `run.json`, `schedule.json`, `execution-freeze.json`,
  `executed-job-ids.json`, `results.csv`, and solution artifacts. Preserve all
  906 rows, including three TIMEOUTs and the 903 SAT solutions; do not filter
  or edit the raw CSV.
- Reviewed analysis tables, audit, and figure files from
  `results/summary/main-20261016-01` once accepted by the analysis/report
  owners. Keep provenance linking these outputs to the raw run and frozen data.
- Report source (`report/main-*.tex`, `report/shared/`, bibliography, required
  figure/table inputs), build instructions, final reviewed PDFs, and applicable
  vendor notices/licenses. For CAS template material, retain the required
  LPPL notice and the source manifest; include only template files needed to
  reproduce the paper.

### Exclude from a submission package

- `.venv/`, `tmp/`, `.tmp/`, `.pytest_cache/`, `.mplconfig/`, pip caches,
  `report/.tools/` compiler/package/font caches, and intermediate `report/build/`.
- CP Optimizer executables/binaries, license keys/files, access tokens, and
  machine-specific environment state.
- Temporary supervisor/launcher locks, console logs, scratch outputs, report
  previews, and intermediate PDFs. Retain only specific audit/provenance files
  needed to reproduce accepted results.

### Still pending before DEL-005/006/010 can close

- Final report/PDF and summary review is still in progress; do not call this
  package final. Check dataset sharing terms and attribution before including
  source snapshots; otherwise ship the permitted derived inputs plus exact
  retrieval instructions and license notice.
- Confirm repository destination/publication authorization and submission
  format/channel later. No remote repository, publication, or LMS action is
  included here.

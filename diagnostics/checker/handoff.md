# SAT03 checker/tests handoff — 16/10/2026

Completed: TEST-001..009 and the temporarily assigned SAT-011.
No production adapter, main benchmark, or solver/license probing is included.
No model.py, sat.py, contracts.py or coordination document was modified.

## APIs

- `sudoku.validation.check_solution(puzzle, solution) -> ValidationResult`:
  independent exact-int domain, shape, row/column/block and clue checks.
  Ordinary list/tuple/Sequence grids are accepted; malformed built-in values
  produce `ValidationResult(False, message)`. Puzzle is assumed to have passed
  the existing validated `Puzzle` constructor. No encoder is imported or called.
- `sudoku.decoding.decode_model(n, model) -> Grid`: reads signed integer
  literals, ignores auxiliary IDs above `(n*n)**3`, returns tuple-of-tuples.
  Raises `DecodeError` (ValueError subclass) for missing/multiple cell values,
  contradictory primary signs, invalid n or malformed literals/model container.
  Repeated identical literals are harmless. A partial assignment is accepted
  when each cell has one positive primary; absent negatives are not required.
  Decoding itself does not establish Sudoku validity or produce SolveResult.
  Adapters must call check_solution and handle decode/checker failure as ERROR.
- `tests.oracle_4x4.solutions_4x4(grid, limit=2)`: independent backtracking
  oracle with no application imports, used only for tiny correctness cases.

## Evidence

Run from `D:\KHMT\Project solo` in PowerShell:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests -q --basetemp diagnostics/checker/tmp --junitxml diagnostics/checker/pytest.xml
```

Result: **292 passed in 0.57s**, exit code 0; no skips.
Runtime: project `.venv\Scripts\python.exe`, Python 3.13.5,
pytest 9.1.1 and python-sat 1.9.dev16.
Raw output: `pytest-output.txt`; machine-readable report: `pytest.xml`.
The evidence directory now exists. On a fresh copy create it before this
command, or omit --basetemp to let pytest use its normal temporary directory.
The first full attempt had 283 passed and one fixture setup error because
the custom basetemp parent did not yet exist. This was an evidence-path setup
issue; no product code change was needed for that error.

Checker-only verification ran first: 26 passed. Then general-size checker
fixtures were added. Final coverage includes:

- malformed solutions, exact ints (reject bool/float), isolated row/column/block
  violations and a changed clue on an otherwise valid completed grid;
- forward/inverse IDs and all four EXO families for n=2,3,4,5, including every
  block boundary and each primary's membership in exactly four groups;
- 168 input truth assignments x AMO/EXO = 336 satisfiability decisions for
  pairwise/seqcounter/bitwise at lengths 3,4,5; auxiliary IDs remain free;
- eight fixed oracle cases: full, single-hole, blank/multiple, sparse/multiple,
  row/column/block conflict and nontrivial UNSAT; 24 full-CNF solver comparisons
  across three encodings, with every returned solution independently checked;
- nontrivial UNSAT fixture `[[1,2,0,0],[0,0,3,0],[0,0,0,0],[0,0,0,0]]`:
  direct clues have no row/column/block duplicates, but the two empty cells in
  the top-left block need 3 and 4 in a row already containing 3;
- malformed puzzle/JSON, missing file, directory-as-file, invalid UTF-8, BOM
  and Vietnamese filename with spaces;
- decoder positive/negative primary IDs, auxiliaries, missing/multiple cells,
  contradictory signs, malformed literals and all four primary-ID ranges.

Existing model diagnostics were read for contract/order/fixture context;
this suite does not call that diagnostic or use it as the validity oracle.
A narrow local sat_model_review (gpt-6.1-sol/high) found no actionable logic
issue in checker, decoder, oracle, nontrivial UNSAT or existential-aux tests.

## Still pending

- TEST-010: differential tests against production SAT/CP-SAT and available
  Gurobi/CPLEX/HiGHS adapters; needs actual adapters/runtime scopes.
- TEST-011: solver smoke runs at 16x16/25x25. General-size checker/mapping/
  decoder fixtures above do not claim those solver smoke runs are complete.
- TEST-012: this command/log covers the current tests only; full integration
  suite and final rerun remain pending the adapters and later model changes.
- SAT-010 and SAT-012: production adapter, statuses/timing and checker gating
  remain owned elsewhere. No benchmark timings or successful SolveResult
  have been produced by this package.

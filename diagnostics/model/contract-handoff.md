# SAT02 contract handoff — 16/10/2026

Contract v1 in `docs/contracts.md` is stable for SAT03/SAT04 implementation.
The model/CNF diagnostic completed successfully with Python 3.13.5 and
python-sat 1.9.dev16; the exact runtime version is recorded in `results.json`.

## APIs ready for use

- `from sudoku.model import Puzzle, parse_puzzle, parse_json, load_puzzle`
- `parse_puzzle(data: object) -> Puzzle`
- `parse_json(text: str) -> Puzzle`
- `load_puzzle(path: str | pathlib.Path) -> Puzzle`
- `Puzzle.n`, `Puzzle.N`, `Puzzle.grid` (immutable tuples), `Puzzle.clue_count`.
- `from sudoku.contracts import InvalidInputError, SolveStatus, ValidationResult,
  Checker, SolveResult, CNFStats`
- Invalid inputs raise `InvalidInputError` with `.status ==
  SolveStatus.INVALID_INPUT`. Exact integers only (bool/float are rejected).
  JSON input is an object with n/grid; extra metadata is ignored.
  File/UTF-8/JSON errors use the same exception.
- Duplicate/conflicting clues that meet shape/domain rules ARE valid input;
  do not reject them as INVALID_INPUT. The CNF makes such puzzles UNSAT.
- SAT03 checker signature:
  `check_solution(puzzle: Puzzle, solution: Sequence[Sequence[int]]) -> ValidationResult`.
  The callable's name is SAT03's choice; the signature/return contract is fixed.
  `ValidationResult(valid: bool, message: str | None = None)` must independently
  check size, exact integer values 1..N, rows, columns, blocks and original clues.
  It must not call the encoder as its validity oracle.
- `SolveResult(status: SolveStatus, method: str, ...)` and nested optional fields
  are fully listed in `docs/contracts.md`. SAT requires a solution AND successful
  independent validation. Parser/CNF construction do not produce SAT results.
- CNF consumers: `from sudoku.sat import build_cnf, encode_amo, ENCODINGS`.
  `build_cnf(puzzle, encoding='pairwise') -> EncodedCNF` exposes `.clauses`
  (list[list[int]]), `.encoding`, `.stats`. Encoding strings: pairwise,
  seqcounter, bitwise. All N^3 primary IDs are reserved before auxiliaries.
- Mapping: `variable_id(n,r,c,v)` and `variable_coordinates(n,variable)`.
  r/c are 0-based, v is 1..N. Negative literals/auxiliary IDs are not mapping inputs.

## Evidence and actual completion

Command from the project directory (PowerShell):

```powershell
& '.\.venv\Scripts\python.exe' '.\diagnostics\model\check_model.py'
```

PASS: 33 invalid-input checks (including bool, float, wrong shape/domain,
malformed JSON, unreadable/missing input), mapping/group checks for 4/9/16/25,
360 AMO/EXO assignment checks with auxiliary variables existentially free,
12 full CNF builds with counts/order checked, and 15 diagnostic 4x4 SAT/UNSAT
logic cases. Counts by pinned library and encoding are in `results.json`.
UTF-8/BOM paths with spaces and Vietnamese characters were also loaded.

Completed in this package: MOD-001..010 and SAT-001..009 (19 tasks).
SAT-010..012 remain pending: no production Glucose3 adapter, model decoding,
or independently checked successful solve was implemented. Glucose3 use in
diagnostics checks CNF satisfiability only; it is not the production adapter
or a substitute for SAT03's checker/tests. No TODO/status file was edited.

No remaining dependency blocks SAT03 from implementing the independent checker
or SAT04 from consuming Puzzle. SAT-010..012 still require the real checker
and agreement on adapter/runner timing integration. Baseline/runtime/license
probing and main benchmarking remain outside this package's ownership.

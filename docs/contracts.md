# Sudoku shared contract v1

Scope: parser/model/CNF are implemented. Solver adapters, independent checker,
runner, CLI and solution decoding are owned/implemented separately. No SAT
success is produced by `build_cnf`.

## Input and model (`sudoku.model`)

- `parse_puzzle(data: object) -> Puzzle`: object/dict with `n` and `grid`;
  extra metadata keys are ignored. `parse_json(text: str) -> Puzzle` parses
  JSON text. `load_puzzle(path: str | Path) -> Puzzle` loads UTF-8 JSON,
  accepting an optional BOM. They raise `InvalidInputError`, whose `status`
  is `SolveStatus.INVALID_INPUT`, for structural/JSON/file/UTF-8 errors.
- `Puzzle(n, grid)` validates and stores immutable tuples; Python callers may
  supply lists or tuples. `n` and every cell must have exact type `int`, so
  bool/float/string are rejected. `n >= 2`, `N = n*n`, `grid` is N by N,
  entries are 0..N; `0` means blank. Properties: `.N`, `.clue_count`.
- Structurally valid conflicting clues are accepted, represented by unit
  clauses, and must yield UNSAT through solving, never INVALID_INPUT.
- `variable_id(n, r, c, v)` = `(r*N+c)*N+v`; r,c are 0-based, v is 1..N.
  `variable_coordinates(n, variable)` inverts positive primary IDs 1..N^3;
  it rejects auxiliary IDs/negative literals. Mapping domain errors raise
  `ValueError`; invalid n raises `InvalidInputError` (a ValueError subclass).
- `iter_exo_groups(n)` yields 4N^2 tuples, each of length N: cell (r,c,v),
  row-value (r,v,c), column-value (c,v,r), block-value (block_r,block_c,v,dr,dc).
  Parentheses specify ascending loop order, not tuple fields. Blocks are n by n.
  `iter_clues(puzzle)` yields `(r,c,v)` in row-major order.

## CNF (`sudoku.sat`)

- Encoding names are exactly `pairwise`, `seqcounter`, `bitwise` (`ENCODINGS`).
- `encode_amo(literals, encoding, *, top_id) -> (clauses, new_top_id)` uses
  distinct positive IDs; top_id must reserve all inputs AND earlier allocations.
  Zero/one inputs need no clauses. Invalid options/IDs raise ValueError.
- `build_cnf(puzzle, encoding='pairwise') -> EncodedCNF`: `.encoding`,
  `.clauses` (list of lists), `.stats` (`CNFStats`). Each group contributes
  its ALO followed by AMO; all clues follow all groups. Duplicate clauses
  stay. No preprocessing, symmetry breaking or clue-specific pruning.
- All N^3 primary IDs are reserved before the first auxiliary; each CardEnc
  call receives the current top_id and updates it. Pairwise has no auxiliaries.
- `CNFStats` fields: `primary_variables`, `auxiliary_variables`,
  `total_variables`, `clauses`, `exo_groups`, `clues`; counts precede solver
  preprocessing. Pairwise: N^3 variables and
  `4*N*N*(1 + N*(N-1)//2) + g` clauses. Other AMO counts refer to the pinned
  PySAT implementation, not a generic theoretical formula.
- CNF clauses are mutable for PySAT interoperability. Treat them as read-only
  after construction; stats describe the original build, not later mutations.

## Checker and results (`sudoku.contracts`)

- `Checker` is a callable protocol:
  `checker(puzzle: Puzzle, solution: Sequence[Sequence[int]]) -> ValidationResult`.
  `ValidationResult(valid: bool, message: str | None = None)`.
  SAT03 supplies the independent implementation: check shape/domain 1..N,
  rows, columns, blocks, and every original clue without using SAT encoding.
- `SolveStatus`: SAT, UNSAT, TIMEOUT, ERROR, INVALID_INPUT, UNAVAILABLE,
  LICENSE_LIMIT. Never map unknown/interrupted solving to UNSAT or count
  missing runtime/license as TIMEOUT. AMO bitwise keeps the one-hot cell model.
- `SolveResult(status: SolveStatus, method: str, ...)` optional fields:
  `encoding`, `raw_status`, `solution`, `build_seconds`, `solve_seconds`,
  `total_seconds`, `stats: CNFStats`, `validation: ValidationResult`, `error`.
  Missing values are None. `solution` is an internal tuple-of-tuples grid;
  it is reserved for SAT with a nonmissing, successful independent validation.
  Construction rejects SAT without these. This guard cannot perform validation
  itself: adapters must actually call the independent checker.
  `to_dict()` exports JSON-compatible nested fields, string status and list grid.
- Method identifiers for downstream adapters: `sat`, `cpsat`, `gurobi`,
  `cplex_mip`, `cpoptimizer`, `highs`. Only SAT uses an encoding; baseline
  encoding/stats are None. Instance ID/repetition are runner metadata.
- Backend raw statuses are retained as strings. Decode/checker failure is
  ERROR with failed validation; only proved infeasibility becomes UNSAT.

## Timing integration (future adapters/runner)

Runner owns the hard wall-clock deadline and worker cleanup on Windows. Its
clock starts after imports and input reading; deadline is start + cutoff
(default 10 seconds). Build includes model/CNF construction AND solver
creation/loading; solve gets only the remaining budget. `build_cnf` does not
start a clock or enforce a timeout. Use a monotonic clock; timestamps shared
with the worker must use the same clock domain. Validation and output are
outside measured build+solve. On normally completed runs,
`total_seconds = build_seconds + solve_seconds`. Unknown components after
forced termination are None, not invented measurements. SAT counts only
when solving finished within deadline and independent checking passed.

Downstream SAT03/04 may implement against this contract. SAT-010..012 remain
pending until the independent checker and adapter/runner integration exist.

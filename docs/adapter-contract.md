# Adapter contract v1 — coordinated before implementation

Existing types/status/validation follow docs/contracts.md; no changes to those definitions.

- sudoku.sat.solve_sat(puzzle: Puzzle, encoding: str = "pairwise", *, cutoff_seconds: float = 10.0, deadline: float | None = None) -> SolveResult.
- sudoku.baselines.solve_baseline(puzzle: Puzzle, method: str, *, cutoff_seconds: float = 10.0, deadline: float | None = None) -> SolveResult.
- Methods: sat, cpsat, gurobi, cplex_mip, cpoptimizer, highs. Encodings only apply to sat.
- Each module exports prepare_backend (SAT: no argument; baseline: method argument) to load optional backend dependencies before measured work. Repeated calls are harmless. Missing dependencies map to UNAVAILABLE in solve results.
- cutoff_seconds is finite and positive; invalid API configuration raises ValueError. deadline, when supplied, is an absolute time.perf_counter() timestamp in the worker clock domain. Effective deadline must not exceed the adapter's own start + cutoff_seconds.
- Imports/input reading precede measured work. Build includes construction and solver creation/loading; solve only receives remaining budget. No model or solver state reused across calls.
- Record actual build/solve/total in seconds; validation/output are excluded. Do not invent component timings after interruption. Preserve raw solver status.
- Independent check_solution from sudoku.validation accepts every returned SAT solution; SAT decoding uses sudoku.decoding.decode_model. Failed decode/checking becomes ERROR.
- UNKNOWN is not UNSAT. Classify TIMEOUT only with evidence of elapsed budget/time-limit interruption; preserve other failure causes as ERROR. Distinguish UNAVAILABLE and LICENSE_LIMIT.
- Native/cooperative limits here are supplemented by the runner's future hard worker/process-tree guard. Do not claim that a native limit alone provides hard Windows termination.
- Internal helper layout is owned by each chat. Runner/CLI consumers use these public entrypoints; no other shared module changes are needed.

## Measurement-end hook — prerequisite for hard guard implementation

Both solve entrypoints additionally accept optional keyword on_measurement_end=None.
When supplied it is callable(end_timestamp, timings), where end_timestamp uses
time.perf_counter() and timings is a mapping with build_seconds, solve_seconds,
total_seconds (unknown components are None). Publish exactly once when measured
build/setup/solve finishes, before decode/checker, timer join and resource cleanup.
Close failed/expired build paths as well; no solving result is implied by this hook.
The default None preserves existing API behavior. Callback failure becomes ERROR
with cleanup, not SAT. Do not hide an exception or publish twice.

Runner will publish END/timings in synchronized shared state with an event, then
send the final checked SolveResult separately. At the deadline the parent rechecks
END: an on-time END switches to a bounded postprocessing watchdog; missing/late END
means solve TIMEOUT and process-tree termination. Postprocessing watchdog failure
is ERROR. Imports/read/startup use a separate guard. No grace extends solve budget.


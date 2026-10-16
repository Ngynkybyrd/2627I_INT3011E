# SAT adapter handoff — 16/10/2026

Completed: SAT-010 and SAT-012. SAT-011 decoder and independent validation are
consumed from SAT03's existing modules; they were not reimplemented here.
No checklist/status/registry file was changed and no main benchmark was run.

## Public API and behavior

Implemented in `src/sudoku/sat.py` according to `docs/adapter-contract.md`:

```python
prepare_backend() -> None
solve_sat(puzzle: Puzzle, encoding: str = "pairwise", *,
          cutoff_seconds: float = 10.0,
          deadline: float | None = None) -> SolveResult
```

`prepare_backend` preloads optional PySAT cardinality/Glucose3 dependencies;
repeated calls are harmless. `solve_sat` also calls it outside measurement,
mapping missing imports/native libraries to UNAVAILABLE. Existing CNF/mapping
APIs and the shared result/status definitions are unchanged.

Every measured call creates a fresh Glucose3 instance. CNF construction,
solver creation/loading and timer setup are build time; the native solve call
is solve time. Effective deadline is the earlier of own start + cutoff and
the supplied absolute `perf_counter()` deadline. Passed deadlines skip work;
build exhaustion skips solve. The timer cooperatively interrupts
`solve_limited(expect_interrupt=True)` using the remaining time.

Late SAT/UNSAT/UNKNOWN results become TIMEOUT. UNKNOWN without deadline or
interruption evidence becomes ERROR. Native True/False/None are retained as
raw status strings; no native result exists when work was skipped.

SAT must be decoded with `decoding.decode_model` and accepted by
`validation.check_solution`; decode/checker failure is ERROR with failed
validation and no published solution. Decode, checking and cleanup occur
outside measured build+solve. Completed component times are actual observed
elapsed values; zero solve time means the native solve was never entered.

Timer cancellation/join precede native deletion in `finally`. If joining
fails, ERROR is returned and native deletion is deferred rather than risking
a callback using freed state; the error explicitly requires worker cleanup.

## Commands and evidence

From `D:\KHMT\Project solo` with PowerShell:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_sat_adapter.py -q --junitxml=diagnostics/sat-adapter/adapter-tests.xml
& '.\.venv\Scripts\python.exe' '.\diagnostics\sat-adapter\smoke.py'
```

- 62 adapter tests passed. Coverage includes SAT/UNSAT, invalid API parameters,
  missing dependency, missing/ambiguous model values, checker rejection/crash,
  build/load/deadline exhaustion, UNKNOWN, native errors, fresh solver cleanup,
  late interrupt callback and timer join failure.
- A real Glucose3 native interrupt was exercised with an injected hard
  pigeonhole fixture. It is an adapter diagnostic, not Sudoku/benchmark data.
- `smoke-results.json`: six SAT cases (16x16 and 25x25, all three encodings)
  passed independent validation and rechecking. An already expired deadline
  returned TIMEOUT without building. Fixtures use valid patterned grids with
  one third of entries removed; no hardness/uniqueness claim is made.
- Full available suite: 409 passed in 2.59 seconds, recorded in
  `regression-tests.xml`. Exact command used:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests -q --basetemp 'D:\KHMT\Project solo\diagnostics\sat-adapter\pytest-temp-regression-20261016-r1' --junitxml=diagnostics/sat-adapter/regression-tests.xml
```

That basetemp was a new, verified path under this diagnostic directory.
The first full-suite attempt had 407 passes and two setup errors creating
pytest's default sandbox temporary directory; using this local temporary
directory resolved the setup issue without changing any existing test.

## Remaining integration boundary

No dependency blocks this adapter API. Runner/CLI can consume it now. Native
interruption and build checkpoints do not guarantee hard Windows termination;
the runner still owns the worker/process guard and process cleanup. It must
also distinguish the measured solve phase from validation/output, which are
outside the cutoff. No worker IPC/hard guard is implemented in this package.
These smoke results cover SAT only and do not claim completion of the
cross-backend TEST-011 acceptance item or a main benchmark.

# SAT04 production baseline adapters

Public API (contract unchanged):

- `sudoku.baselines.prepare_backend(method) -> None`, idempotent pre-import;
  import errors propagate here, while solve maps missing dependencies to UNAVAILABLE.
- `solve_baseline(puzzle, method, *, cutoff_seconds=10.0, deadline=None) -> SolveResult`.
- Methods: `cpsat`, `gurobi`, `cplex_mip`, `cpoptimizer`, `highs`.

Implementation: `src/sudoku/baselines/adapters.py`, exported by `__init__.py`.
Existing CP builders and one shared sparse ILP builder are reused. Each call
creates fresh backend objects. Gurobi/CPLEX/HiGHS use exactly the same matrix,
binary bounds/integrality and constant objective. One thread/worker is set for
every engine; HiGHS option readback is checked. No dataset changes or preprocessing
specific to one backend. Main .venv and dependencies are unchanged.

## Results and timing

All SAT results call production `sudoku.validation.check_solution`. MIP decoding
accepts only finite values within 1e-6 of 0 or 1 and exactly one selected value
per cell; fractional/invalid incumbents cannot produce SAT. HiGHS must report
primal feasibility and acceptable integrality before decoding. Backend raw
statuses are retained. UNKNOWN/ambiguous infeasible-or-unbounded is never UNSAT.
Only actual infeasibility maps to UNSAT; observed deadline/native time limits
map to TIMEOUT. Runtime absence and explicit size errors remain UNAVAILABLE and
LICENSE_LIMIT. Invalid API budget/method raises ValueError before building.

Imports precede measured work. `deadline = min(caller_deadline, start+cutoff)`;
build includes fresh model/solver setup, solve uses remaining time. Decoding,
checker and cleanup are excluded. Results returned after the deadline are
TIMEOUT even if an incumbent exists (conservative; no timestamp is invented).
On-time time-limit incumbents still require validation. Cleanup failure returns
ERROR and preserves raw status/timing instead of escaping the API.

### CP Optimizer limitation and explicit handling

DOcplex 2.32.264 embeds TimeLimit in transmitted CPO; the local protocol cannot
change that parameter after loading. The adapter preloads using
`solver.agent._init_model_in_solver()` so compile/send/load is charged to build.
Native TimeLimit is the remaining budget immediately before that preload.
After loading, a timer uses the actual remaining deadline and calls the public
`solver.abort_search()`; it is cancelled/joined before solver cleanup. Deadline
admission rejects late solutions. The private preload hook needs rechecking on
DOcplex upgrades. This is **cooperative**, not a hard wall-time guarantee.
Exact post-load *native* TimeLimit cannot be promised with this interface.
Runner must kill the worker/process tree on deadline for CP Optimizer and other
engines alike; native settings and the timer do not replace this guard.

## Evidence

Commands (PowerShell):

```powershell
$env:PYTHONPATH='D:\KHMT\Project solo\src'
& 'D:\KHMT\Project solo\.venv\Scripts\python.exe' -B -m pytest -q -p no:cacheprovider 'D:\KHMT\Project solo\tests\test_baseline_adapters.py'
& 'D:\KHMT\Project solo\.venv\Scripts\python.exe' -B 'D:\KHMT\Project solo\diagnostics\baseline-adapters\smoke.py'
```

`pytest.log` contains the adapter test result. Tests cover real 4×4 SAT/UNSAT,
9×9 SAT/repeated fresh calls, CP-SAT/HiGHS 16×16/25×25, free-engine license limits,
bad budgets/deadlines, unavailable imports, fractional/nonfinite MIP values,
checker rejection/errors, late and on-time incumbents, native UNKNOWN evidence,
HiGHS fractional timeout, cleanup failures and CP cooperative abort.

`summary.json`: 22 runtime cases, 14 SAT with production checker pass, 5 UNSAT,
3 LICENSE_LIMIT (16×16 empty model for each free commercial engine). Large
smoke fixtures have almost all clues and demonstrate API/correctness only;
they are not performance evidence, B16/C10 pilot or benchmark. Package versions
and all raw statuses/results are included. No main benchmark has run.

BASE-003/004/006/007/008 implemented with these checks. BASE-005 adapter is
implemented and runtime/checker-tested; exact post-load native limit remains
the documented DOcplex limitation, with cooperative deadline handling in place.
BASE-009 full cross-backend suite and BASE-010 dataset pilot remain pending
SAT adapter/data and runner hard-guard integration. No checklist is ticked here.

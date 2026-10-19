# EXP-04 — solver preflight, 19/10/2026

## Decision for root acceptance

| Size | Included configurations | Evidence |
|---|---|---|
| 9×9 | Glucose3 pairwise/seqcounter/bitwise; CP-SAT; HiGHS; Gurobi; CPLEX MIP; CP Optimizer | Eight fresh sequential guarded jobs on existing synthetic-N09-p70-s0; all SAT/checker PASS |
| 16×16 | Three Glucose3 encodings; CP-SAT; HiGHS | Five reused frozen main-run jobs, input/witness hashes and production checker rechecked |
| 25×25 | Three Glucose3 encodings; CP-SAT; HiGHS | Five reused frozen main-run jobs, input/witness hashes and production checker rechecked |

`matrix.json` supplies 18 included cells and six declared exclusions, for root
to accept before expanded dataset/config freeze. It implies 330,000 main jobs,
3,300 per complete block, and 164 pilot jobs under the proposed dataset counts
and repetitions. These are counts, not completion or wall-time predictions.

## Minimal evidence policy

All old source hashes listed in `results/raw/main-20261016-01/run.json` match
the current files; Python and all seven recorded dependency versions match.
The old dataset freeze hash also matches. Consequently the ten large-board
cells reuse successful original jobs rather than rerunning already established
coverage. `reused-evidence.json` identifies each CSV row and witness SHA256.
Each selected input's SHA256 matches its manifest, and each stored witness
passes the current independent checker. No source, data or original result
was overwritten. `verification.json` records before/after protected hashes.

The fresh diagnostic confirms the current machine can start each distinct
9×9 engine/configuration through existing production adapters and run_job.
It is one selected existing puzzle per configuration, not a sample from the
expanded corpus, new dataset, pilot or benchmark. Hard/easy representativeness
and throughput must await the separate pilot.

## Fairness and cleanup

- All runs are sequential, fresh solver/model per job; no result/model cache.
- Three SAT encodings retain the shared one-hot model. Gurobi/CPLEX/HiGHS use
  the same sparse ILP, N³ binary variables, 4N²+g equalities and objective zero.
  CP-SAT and CP Optimizer use integer/AllDifferent models.
- CP-SAT has one search worker; Gurobi/CPLEX one thread; CP Optimizer Workers=1;
  HiGHS threads=1 with readback; Glucose3 is the sequential engine. Evidence is
  pinned source plus previous runtime checks, not a new CPU thread profiler.
- cutoff=10 seconds for build/setup/solve, pre-import outside measurement.
  START/END uses perf_counter. Native/cooperative limits do not replace the
  runner's hard guard; startup (60s) and postprocessing (30s) are separate.
- `result.json` retains actual build/solve/total and separate whole-job wall time,
  raw status, independent validation and witnesses. Do not interpret these
  one-off diagnostic durations as benchmark medians or compare with old runs.
- `cleanup.json` records assignment, successful terminate_and_wait, and close
  for every fresh JobObject. The production terminate_and_wait method queries
  ActiveProcesses and only returns at zero; run_job also joins/closes the worker.
  All eight jobs returned guard_phase=complete. No new forced-timeout stress test
  was needed; existing runner/cleanup correctness evidence is reused, not rerun.
- CP Optimizer uses pinned DOcplex 2.32.264's private preload hook. Its CPO-native
  TimeLimit cannot be reset after loading, so remaining deadline also has a
  cooperative abort timer and the same hard worker/process-tree guard. END is
  published before timer join/validation/cleanup. Upgrading DOcplex requires review.

## License and declared scope

Existing evidence (no new oversized calls): `diagnostics/solvers/gurobi-16.json`,
`cplex-16.json`, `cpoptimizer-16.json`, `cpoptimizer-25.json` and
`diagnostics/baseline-adapters/summary.json` record LICENSE_LIMIT observations.
The bundled Gurobi limit is 2,000 variables/2,000 linear constraints; CPLEX MIP
Community is 1,000/1,000. Full 9×9 ILP has 729 variables and at most 405
equalities, below both limits. Full 16/25 ILP has 4,096/15,625 variables and
exceeds those known caps without changing the model. No license acquisition,
account signup, purchase, engine substitution or bypass was performed.

CP Optimizer Community's observed limit is search space 2^1000, not the MIP
variable cap. Its prior low-clue large models failed; that does **not** prove
every 16×16/25×25 puzzle is unavailable. Their omission is the explicitly agreed
experimental scope. Excluded matrix cells are not measured TIMEOUT or UNSAT;
do not schedule repeated known-failing license probes or invent durations.

## Reproduction and next input

Executed once:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& 'D:\KHMT\Project solo\.venv\Scripts\python.exe' -B 'D:\KHMT\Project solo\diagnostics\expansion\solvers\preflight.py'
```

`preflight.log` and `verification.json`: PASS, eight new SAT/cleanup records,
ten reused/rechecked cells. Script refuses existing result.json to prevent
silent overwrite or retries. It instruments JobObject only inside its own
parent process; production runner files are unchanged.

Root should cross-check `inventory.json` with EXP-01's new fingerprint and
accept matrix/scope for EXP-07/08/09. No local technical blocker observed.
Dataset correctness, expanded transaction/resume semantics, pilot throughput
and final freeze remain separate gates; this preflight does not authorize them.

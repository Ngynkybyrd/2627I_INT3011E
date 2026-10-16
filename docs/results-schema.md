# Runner results schema v1

Contract for RUN-001..008, analysis and CLI. No research results are produced
by preparing a run or by runner diagnostic tests.

Each new output directory contains `run.json` (config, code hashes, dataset
freeze hash, Python/OS/CPU and package versions), `schedule.json` (ordered
jobs), and, after explicit execution, `executed-job-ids.json`, `results.csv`
and `solutions/<job_id>.json` for checked SAT results. Existing run directories
are never overwritten. Re-runs use separate directories and explicit job IDs.

CSV columns, in order:

```
schema_version,run_id,job_id,instance_id,method,encoding,repetition,scope,
cutoff_seconds,status,raw_status,build_seconds,solve_seconds,total_seconds,
primary_variables,auxiliary_variables,total_variables,clauses,validation,
validation_message,solution_artifact,error,guard_phase
```

- `schema_version=1`; run ID is the output directory name, which must be unique
  across compared runs. Job ID is `instance__method__encoding-or-none__r1`.
  The primary key is `(run_id, job_id)`. Repetition starts at 1.
- Methods: `sat`, `cpsat`, `highs`, `gurobi`, `cplex_mip`, `cpoptimizer`.
  SAT encodings: `pairwise`, `seqcounter`, `bitwise`; baseline encoding empty.
- `scope`: S80 for SAT, B16 for CP-SAT/HiGHS, C10 for the three commercial
  backends. C10 is a subset of B16, which is a subset of S80. SAT is not rerun
  for subset comparisons. Join `instance_id` to the frozen manifest for source,
  density, clues, seed, `n` and `N`; JSON keys n/N are case-sensitive.
- Statuses: SAT, UNSAT, TIMEOUT, ERROR, INVALID_INPUT, UNAVAILABLE,
  LICENSE_LIMIT. Raw status is the adapter's original string; hard termination
  before a final result leaves it empty. No inferred raw solver status.
- Seconds are floating point. Build includes setup/load. Total is build+solve
  when known; unknown values are empty CSV cells / JSON null, never invented
  zeros or a fabricated cutoff observation. A timeout killed before END has
  unknown components. Late END may retain actual observed timings.
- SAT variable/clause counts are before preprocessing; baseline counts empty.
- `validation`: pass/fail/empty (not performed or unavailable). Only SAT with
  pass and a solution is accepted. `solution_artifact` is relative to the run
  directory, written before its row; contains job/instance IDs and checked grid.
- `guard_phase`: complete, startup, measurement, postprocessing, protocol,
  validation, guard, cleanup. Startup/postprocessing/cleanup failure is ERROR;
  absent/late END at the solve deadline is TIMEOUT. Cleanup failure aborts the
  batch. Error text is short diagnostic text, never credentials.

CSV is appended and flushed after each job; duplicate job IDs are rejected.
Keep interrupted files. A separate rerun may use an explicit missing-ID list;
there is no automatic resume or replacement of prior observations.

Analysis must exclude UNAVAILABLE/LICENSE_LIMIT/ERROR from runtime and PAR-2,
report their counts separately, and state the common instance set. Three
successful repetitions are needed for a normal median. Never select the fastest
repeat or compare full-S80 SAT averages to B16/C10 baseline averages.

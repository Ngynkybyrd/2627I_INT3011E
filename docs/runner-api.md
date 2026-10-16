# Runner API v1

`sudoku.runner` is the public interface; worker/process helpers are internal.

- `RunnerConfig(cutoff_seconds=10.0, repetitions=3, schedule_seed=20261016,
  startup_seconds=60.0, postprocessing_seconds=30.0)` validates positive limits.
- `verify_dataset(root=ROOT) -> (scopes, manifest_index)` checks every frozen
  hash and scope identity. It never solves or regenerates data.
- `make_schedule(config=RunnerConfig(), *, root=ROOT) -> list[dict]`: seeded
  shuffle; defaults produce 906 unique jobs: 720 SAT, 96 B16, 90 C10.
- `prepare_run(output_dir, config=RunnerConfig(), *, root=ROOT) -> jobs`:
  creates a NEW directory with run metadata and schedule; no solver calls.
- `run_job(job, config=RunnerConfig(), *, root=ROOT) -> dict`: one isolated
  Windows worker, returns SolveResult-compatible JSON plus `guard_phase`.
- `write_result(output_dir, job, result) -> row`: publish checked solution and
  append/flush CSV. See results-schema.md for columns and null semantics.
- `execute_run(output_dir, *, root=ROOT, job_ids=None) -> completed_count`:
  explicit execution of a prepared plan after rechecking dataset/code/schedule.
  Optional IDs are a JSON-compatible list selecting from the original schedule
  without changing order. Existing CSV is refused; reruns require new output.
  Because the frozen dataset has 80 independently witnessed SAT inputs, an
  UNSAT row is retained but stops the batch with `dataset-disagreement.json`;
  it is not a successful research observation. Investigate before any rerun.

Command (prepare only, no pilot or benchmark):

```powershell
& '.\.venv\Scripts\python.exe' -B '.\scripts\run_benchmark.py' --output '.\diagnostics\runner\prepared-plan'
```

Execution is separate: add `--execute` for an existing plan; optionally provide
`--job-ids <file.json>`. RUN-009..014 remain gated on guard review, pilot and
code/config lock. Preparing a plan does NOT establish RUN-012 completion.

Worker waits at a gate until parent assigns a kill-on-close Windows Job Object.
Then it imports the backend and reads input, outside measurement. START stores
perf_counter time under a shared lock; the adapter receives that absolute
deadline. END stores timestamp/components under the same lock and sets an event
before decode/checker/cleanup. Final checked result travels separately.

Parent rechecks shared END at deadline, independent of pipe notification order.
No/late END means TIMEOUT and whole-tree termination. On-time END gets a separate
bounded postprocessing watchdog; a hung checker/cleanup is ERROR. Startup has its
own watchdog. No grace extends solve time. Job termination waits for zero active
processes before allowing another job; inability to contain/clean up is an error.
Native limits supplement, never replace, the hard guard.

Tests inject small diagnostic workers through private `_worker`; this is not a
configuration option and never creates research rows. Windows is required for
the implemented process containment. No claim of POSIX support is made.

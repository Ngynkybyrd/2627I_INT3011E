# Expanded Sudoku contract v2 — EXP-07A

Status: implementation specification, pending coordinator acceptance. No expanded
dataset, SQLite implementation, pilot or benchmark is claimed by this document.
Authority: SAT-EXPANSION.md, current expansion section of SAT-STATUS.md.
Consumers: SAT05 data, SAT03 QA, SAT06 CLI, SAT08 analysis, SAT09 methods, SAT10
reproduction. SAT07 alone operates benchmark workers. Coordinator owns gates.

## 1. Version, isolation and invariants

- Contract/schema version is integer **2**, SQLite `PRAGMA user_version=2`.
  Reject other versions explicitly. Do not relax or migrate v1 validators.
- New inputs: `data/expanded/<dataset_id>/`; configs: `configs/expanded/`;
  main runs: `results/expanded/<experiment_id>/`; pilot:
  `diagnostics/expansion/pilot/<experiment_id>/`. Never reuse old run directories.
  Diagnostics/fixtures must carry `artificial=true`; real pilot/main reject them.
- Preserve v1 source, freeze files, S80/B16/C10, 906 rows and existing report
  snapshots. New code modules/scripts may import public v1 APIs read-only.
- Main target is 16,000 unique puzzles, not a completion claim. Pilot inputs,
  correctness fixtures, interrupted attempts and repeated runs do not count as
  additional main puzzles. Every research input is witnessed SAT.
- Seconds are SI seconds; elapsed clocks use `time.perf_counter`. Operational
  timestamps are ISO8601 UTC with offset; display Asia/Saigon to the user.
  Null means unknown/not applicable, never zero. Reject NaN/infinity.

## 2. Dataset interchange, seeds and identities

Dataset directory contains `dataset.json`, `manifest.jsonl`, `roots.jsonl`,
`batches.json`, `provenance.json`, `dedup.jsonl`, `freeze.json`, `inputs/`,
`witnesses/`. JSON is UTF-8 without BOM on output; readers accept optional BOM.
Each JSONL line is an independent object. All paths are relative to dataset
directory, POSIX-style, contained after resolution; reject traversal/symlinks
escaping the directory. Do not put witness content in solver input files.

`dataset.json` fields: `schema_version=2`, `dataset_id`, `phase` (`main`/`pilot`),
`artificial=false`, `master_seed=20261019`, `generator_version`,
`canonicalization="sudoku-json-v2"`, `frozen`, `target_counts`, `actual_counts`,
`selection_rule`, `source_commit`, `old_dataset_freeze_sha256`.
IDs: main dataset `expanded-20261019-v2`, pilot dataset
`expanded-pilot-20261019-v2`. A changed frozen dataset gets a new ID, not edits.

Canonical puzzle bytes are UTF-8 of Python-equivalent
`json.dumps({"n": n, "grid": grid}, sort_keys=True, separators=(",", ":"),
ensure_ascii=False) + "\n"`; values are exact integers and grid is nested lists.
`content_sha256` hashes those canonical bytes. `input_sha256` hashes actual file
bytes; these hashes have distinct meanings even when equal. Canonicalize old
S80 inputs identically for exclusion; do not compare only old serialization hashes.
Witness and root-grid content hashes use the same canonical representation.

`instance_id = "e2-<phase>-N<N>-<content_sha256>"`, full 64 lowercase hex digits.
`root_id = "e2-<phase>-N<N>-<family>-r<ordinal:06d>"`; ordinal is assigned within
size/family before masks, retained through resampling. Public root_id is null.
`batch_id = "b001".."b100"`; pilot uses `p001` only.

Deterministic random ordering does not rely on Python's salted hash or library
shuffle implementation: `rank(label, item) = SHA256(UTF8(
"20261019|" + label + "|" + item))`, lexicographic digest order, item string
as tie-breaker. Labels include phase, operation, N, family/root, density and
resample index where applicable; record the exact label and attempt in logs.
When an operation needs an RNG seed, use the first 16 hex digits of rank as an
unsigned 64-bit integer; record as a **decimal string** (lossless across JSON
clients). SAT05 records RNG implementation/version and draws; no outcome-based
selection. Schedule uses the same rank rule with label `schedule|<phase>|<batch>`.

Required manifest record:

| Field | Type / rule |
|---|---|
| schema_version, dataset_id, instance_id, batch_id, phase | v2 and identifiers above |
| n, N | integer block side and board side, N=n*n; main n=3/4/5 |
| input_file, input_sha256, content_sha256 | contained path and full hashes |
| source | `sudoku_exchange` or `synthetic` |
| source_group | easy/medium/hard/diabolical for public, null otherwise |
| source_record_id, source_line, source_url, source_file_sha256 | public provenance; null for synthetic |
| rating_original | exact source token as string, null only if source lacks it |
| rating_value | finite numeric parse if supported, otherwise null; never invented |
| family | `permutation`, `row_cycle`, or null for public |
| root_id, root_content_sha256 | synthetic relationship; null for public |
| clue_percent_requested | integer 20/30/40/50/60 synthetic, null public |
| actual_clues | count of nonzero input cells; actual density derived from N |
| master_seed, derived_seed, seed_label, resample_index | integer master, string seed/label, nonnegative attempt |
| witness_file, witness_sha256, witness_content_sha256 | separate valid completed grid |
| witness_validation | object: valid=true, checker_code_sha256, checked_utc |
| sat_evidence | `checked_generator_witness` or `checked_solver_witness` |
| uniqueness | `unverified` for synthetic; `source_claimed` only with citation for public |
| uniqueness_reference | source statement URL/record or null; no self-proven claim |

`provenance.json` holds source commit
`d8c8ebaee0c08c412cfba96af1923dfa61c83317`, exact URLs, filenames, SHA256s,
license/attribution text references and parser version. Source group is a source
label, not our independently calibrated difficulty classification.

Dedup across all expanded phases, source groups, synthetic families and old S80
uses canonical puzzle content. For public duplicate ownership, scan group order
easy, medium, hard, diabolical, then original source line ascending; first owns
the content, later occurrences are logged with both provenances. After exclusion,
rank eligible entries per group using `public|<group>` and content hash: first
2,500 are main, next 2 are reserved pilot. Insufficient unique supply is a
dataset gate failure, not permission to reduce the target or substitute groups.
Find and independently check witnesses before freeze; failure/unknown witness
blocks acceptance, never silently replace a selected puzzle by an easier one.

## 3. Synthetic roots, batches and pilot

Main synthetic roots: N16 has 500 per family, N25 has 100 per family. Root is the
final fully transformed solution used to produce its five puzzle masks, not the
common base pattern. `roots.jsonl` stores root_id, N, family, grid_file/hash,
seed labels, resample log references and checker evidence. Root grids must be
valid and exactly distinct within expanded roots. No claim of non-isomorphism
or uniform sampling follows from exact deduplication.

Permutation family uses the established legal value/band/row/stack/column
permutations. Row-cycle family starts with a legal permuted board, chooses two
distinct rows in one band, derives the permutation of their values by column,
and exchanges entries in **all columns of one complete nontrivial cycle**.
Use a proper cycle (length 2..N-1), so a whole-row swap alone is not the second
family; if unavailable resample the base/row pair deterministically. Record row
indices, cycle values/columns and base hash. Checker validates the transformed
root and every witness. Families are construction labels, not proven distinct
isomorphism classes. Stop and report inability to meet this family rule.

For each root and percent p, retain `floor(p*N*N/100 + 0.5)` cells ranked by
`mask|<phase>|<root_id>|<p>|<resample_index>` and cell index in row-major order;
other cells become zero. Masks at different densities are independently ranked,
not promised nested. Duplicate puzzle: regenerate that mask with increasing
resample_index, never change its family/root/stratum quota. Duplicate root:
regenerate the same root slot before masks. At 10,000 failed attempts per slot,
stop with evidence; do not fall back to a different family. Root-level dependence
persists even with independent masks and must survive export/statistics.

Batch assignment is frozen before measurements:

- Public: rank the 2,500 main IDs in each group by `batch|public|<group>`;
  each consecutive slice of 25 goes to one batch.
- N16: rank roots per family by `batch|16|<family>`; each batch receives five
  roots per family, with all five masks per root: 50 puzzles, 10 per density,
  five per family/density.
- N25: rank roots per family similarly; each batch receives one root per
  family with five masks: 10 puzzles, two per density, one per family/density.
- Thus each batch has 160 puzzles; root masks never split across batches.
  `batches.json` lists ordered batch IDs and ordered instance IDs plus expected
  stratum counts. Dataset freeze verifies all 100 batches and global counts.

Pilot is separate, disjoint from main/old inputs: eight public (two per group,
reserved above) and ten each N16/N25 (one additional root per family, all five
densities). Extra pilot roots are **not** part of the 1,000/200 main root targets.
Pilot is 28 puzzles, one repetition, expected 8*8+20*5=164 jobs. No correctness
fixtures are included. Fix pilot IDs before its solver results; never merge its
measurements into main. Same matrix policy and 10-second cutoff apply.

`freeze.json`: version, dataset_id, frozen=true, manifest/roots/batches hashes,
`files_sha256` for every input/witness/root/source/provenance/dedup artifact
(excluding freeze itself), expected/actual counts, old-data exclusion hash,
all-witness-check pass. Freeze file itself is hashed in the experiment manifest.
No generation/witness solving occurs during timed main execution.

## 4. Eligibility, schedule and execution boundary

Configuration IDs are `sat:pairwise`, `sat:seqcounter`, `sat:bitwise`, `cpsat`,
`highs`, `gurobi`, `cplex_mip`, `cpoptimizer`. Glucose3 is the only SAT engine.
The last three apply to N9 only; N16/25 exclusions cite observed limits as a
**scope policy**, not a proof that every large instance fails. EXP04 supplies
`matrix.json`: version, N/configuration rows, eligible boolean, scope reason,
runtime/version, threads=1 verification and evidence hashes. Missing preflight
evidence blocks freeze. The expected matrix gives 330,000 main jobs, 3,300 per
batch. Any change to eligibility is an explicit coordinator decision **before**
freeze, with recalculated denominators; never shrink the matrix after failures.
Excluded matrix entries create no timed job or fake TIMEOUT row.

Job identity tuple is `(experiment_id, instance_id, method, encoding, repetition)`;
encoding is `""` for baselines in SQLite/CSV (avoid nullable UNIQUE behavior),
null in adapter requests. Repetition main=1..3, pilot=1 only.
`job_id = "j2-" + SHA256(canonical JSON array of tuple)`; arrays serialize with
compact separators and UTF-8. Configuration IDs and method names are lowercase.
Process batches b001..b100 in order. Within each, rank all jobs by the frozen
schedule seed **20261019**, label in section 2 and job_id; write ordinal unique
over the experiment. Resume follows ordinal, not speed or remaining estimated
cost. Dataset ID remains independent of experiment ID; a new experiment changes
job IDs but cannot retrospectively alter completed observations.

Reuse `sudoku.runner.run_job(job, RunnerConfig(...), root=project_root)` and its
Windows Job Object helpers unchanged. Translate v2 path to project-relative
`file`, provide method/encoding/job_id/instance_id/repetition, `scope="expanded-v2"`
and cutoff_seconds=10 matching RunnerConfig. This API accepts arbitrary job
inputs; **do not call** v1 make_schedule/verify_dataset/execute_run/write_result
for expanded data. Implement a separate v2 orchestrator/storage/export module.

Existing START/END synchronization, absolute perf_counter deadline, startup
60s/postprocessing30s watchdogs and process-tree cleanup are mandatory. Build
includes construction/setup/loading; solve receives only remaining budget.
Solver components come only from adapter/guard observations; no invented times
on forced termination. Controller measures `attempt_wall_seconds` around run_job
including startup/checker/cleanup, separately `checkpoint_seconds` around commit;
session elapsed wall clock covers scheduling/IO/idle too. Do not derive exact
startup/checker breakdown by subtracting times: current API does not expose it.
No CNF persistence and no process/model cache across jobs.

All witnessed-SAT UNSAT, failed validation or cleanup failure stop the experiment
after retaining the observation. Conservatively also halt on ERROR,
INVALID_INPUT, unexpected LICENSE_LIMIT/UNAVAILABLE; preserve the frozen matrix,
investigate rather than completing later blocks around a failing configuration.
TIMEOUT is a valid terminal observation and is never automatically retried.

## 5. SQLite v2 storage and transactions

One local SQLite database `experiment.sqlite3` per experiment, no network drive.
Enable foreign_keys=ON, journal_mode=WAL, synchronous=FULL, busy_timeout=5000ms;
verify settings on open. Single writer; status/export readers use read transactions.
Logical tables below are mandatory (DDL may add indexes, not change semantics):

| Table | Key and required content |
|---|---|
| experiment | singleton experiment_id PK; schema_version, phase, immutable manifest/config/matrix/fingerprint JSON + hashes; state; halt_reason |
| batches | batch_id PK, ordinal UNIQUE, expected_instances/jobs, QA state/reason |
| instances | instance_id PK, content_sha256 UNIQUE, batch FK, **block_side**, **board_side**, manifest_record_json, input/witness hashes, source/group/rating/family/root_id |
| jobs | job_id PK, instance FK, configuration, method, encoding NOT NULL, repetition, ordinal UNIQUE, state PENDING/RUNNING/TERMINAL; UNIQUE(instance_id,method,encoding,repetition) |
| sessions | session_id PK, host, PID, process creation time, started/ended UTC, stop-starting-at, heartbeat UTC, acquisition/recovery reason |
| attempts | attempt_id PK, job FK, attempt_no, session FK, state RUNNING/INTERRUPTED/FINISHED, started/ended UTC, observed wall/checkpoint times, interruption reason; UNIQUE(job_id,attempt_no) |
| results | attempt_id PK/FK, status/raw_status, build/solve/total nullable, CNF counts nullable, validation/message, guard_phase, error; one committed terminal result per job via primary_attempt relation |
| solutions | attempt_id PK/FK results, canonical completed-grid JSON bytes, sha256, independent checker evidence; SAT only |
| primary_attempt | job_id PK/FK jobs, attempt_id UNIQUE/FK results; immutable first terminal result |
| events | increasing event_id PK, UTC, session/job/attempt references, event type and diagnostic JSON |

SQLite column names cannot distinguish n/N: use block_side/board_side, map to
case-sensitive n/N only in dataset JSON. Errors must be short and redacted of
credentials. No authentication or license files belong in DB/exports.

Claim transaction (`BEGIN IMMEDIATE`): verify owner/gates, select next PENDING
ordinal, insert RUNNING attempt and set job RUNNING, commit **before** run_job.
Do not hold a SQL transaction while solving. After run_job and validation,
completion transaction inserts result plus SAT solution/checker evidence, marks
attempt FINISHED and job TERMINAL, inserts primary_attempt, appends event, commits
atomically. HALTED state/reason for fatal results is set in that same transaction.
SQLite solution bytes are authoritative; sidecar solution files are export views,
not a second non-atomic source of truth. No result row can commit without its
required SAT solution; no accepted solution can exist without its result.

Checkpoint duration is known only **after** completion commit: record it in a
separate telemetry event linked to attempt_id, not by rewriting the raw result.
Export joins that event into checkpoint_seconds. A crash between commit and
telemetry leaves checkpoint_seconds null but the job remains terminal; never
rerun a committed job merely because telemetry is missing. Attempt wall ends
before completion commit, so these two durations do not overlap.

No exactly-once solve claim: a crash after solve but before commit may lose that
observation. After exclusive recovery, an orphan RUNNING attempt with no committed
result becomes INTERRUPTED, missing values remain null, job becomes PENDING.
If transaction committed, FINISHED/result/solution/primary are all present and
must never rerun. Any impossible combination fails integrity checks and halts.
Preserve attempts forever; no delete/update of terminal raw result or witness.
Attempt IDs use UUID4; attempt_no increments per job. Primary result is the first
**committed terminal** attempt; INTERRUPTED is operational state, not solver
TIMEOUT/ERROR and not a candidate for fastest-result selection.

## 6. Ownership lock, resume and crash policy

Use an OS-enforced exclusive byte-range lock on a persistent `writer.lock` file
(Windows msvcrt nonblocking one-byte locking), held open for writer lifetime.
Ensure a byte exists; never unlink/recreate the file to break a lock. This works
across sessions; SQLite transactions alone are insufficient to prevent concurrent
solves. A second writer exits busy before importing/starting solvers. Advisory
owner metadata includes host/PID/**process creation time**/session UUID; PID alone
is insufficient. Store heartbeat every <=5s using controller thread, not an AI.

Age/expired heartbeat does not authorize stealing a live OS lock. Recovery requires
successful OS lock acquisition, proving previous owner process identity is gone,
and no surviving prior worker tree. Job Objects normally kill workers on owner
death; if cleanup cannot be established, halt for explicit operator inspection.
Do not kill unrelated processes by name/PID guess. Persist lock-release/recovery
evidence. Never release writer ownership while a worker may still be running.

`resume` is explicit, requires a reason, and may retry only orphan INTERRUPTED or
still PENDING jobs. It cannot retry terminal SAT/TIMEOUT/ERROR/etc. Atomic recovery
and new attempts retain all history; repeated interruptions are visible in audit.
Integrity check, foreign_key_check and full freeze/fingerprint verification precede
resume. Code/data/config/matrix/schedule/checker/dependency or machine/runtime
fingerprint mismatch refuses resume; use a new experiment with reason, never merge
incompatible versions into a single estimate or choose favorable old/new results.
No automatic restart after any supervisor failure.

Fingerprint includes Python executable/version, OS/architecture/CPU/RAM identity,
package versions, native runtime/executable identity/hash (or documented unavailable
version API), thread settings, relevant solver env settings (allowlist, no secrets),
code including imported v1 helpers, CLI, analysis schema, config/matrix/data/schedule
hashes. Available RAM/free disk, process IDs and timestamps are observations, not
resume identity fields. Store environment evidence from EXP01/04 by hash.

Default stop-starting-at is **2026-10-19T22:30:00+07:00**. Check before every claim
and again before worker launch; if elapsed after claim, mark attempt INTERRUPTED
with `not_launched_deadline`, return job PENDING. A running job finishes under its
existing solve/startup/postprocessing guards, commits, then pauses. Signal-based
graceful stop likewise finishes current job; forced termination uses cleanup then
INTERRUPTED, never invented solver status. Persist PAUSED/session end.
Resume after the deadline needs an explicit future `--stop-starting-at` and reason;
this operational session boundary is audited, not a mutation of cutoff/matrix or
experimental hash. It grants no inclusion in the pre-submission report.

## 7. API and CLI boundary (implementation target, not existing commands)

New module `sudoku.expanded_runner`, script `scripts/run_expanded.py`.
SAT07 owns validation/storage/schedule/execution; SAT06 owns argument parsing,
presentation and invokes these APIs without duplicating protocol logic.

| Function | Behavior/result |
|---|---|
| validate_expanded_dataset(dataset_dir) | full schema/hash/witness/balance validation; returns DatasetIndex, no solver |
| prepare_expanded(dataset_dir, experiment_dir, config_path, matrix_path, *, phase) | NEW directory/DB + manifests/schedule; returns experiment_id/counts; no solving |
| pilot_expanded(experiment_dir, *, stop_starting_at) | requires phase=pilot, accepted correctness/preflight; runs fixed164 or approved matrix count |
| run_expanded(experiment_dir, *, stop_starting_at) | main, new experiment, accepted pilot/QA/freeze; refuses prior attempts; returns ExitSummary |
| resume_expanded(experiment_dir, *, reason, stop_starting_at) | explicit verified recovery above; returns ExitSummary |
| expanded_status(experiment_dir) | read-only ProgressSnapshot; no locks stolen/solver calls |
| export_expanded(experiment_dir, output_dir, *, complete_blocks=False) | NEW snapshot/export directory; no solving or DB raw mutations |

CLI arguments: `prepare --dataset --experiment --config --matrix --phase main|pilot`;
`pilot|run --experiment [--stop-starting-at ISO8601]`;
`status --experiment [--json]`;
`resume --experiment --reason TEXT --stop-starting-at ISO8601`;
`export --experiment --output [--complete-blocks]`. No automatic action from status.
Exit codes: 0 successful command/complete, 2 validation/gate/CLI error, 3 writer
busy, 4 paused/deadline, 5 halted runtime/data/cleanup/integrity failure.
ExitSummary: experiment_id, state, completed_jobs/blocks, remaining_jobs, reason.

ProgressSnapshot: primary counts by status, attempts/interrupted separately,
active job/attempt, elapsed session wall, completed/QA-complete blocks,
free_disk_bytes, database/WAL/log bytes, recent wall rate, ETA and its coverage.
ETA sums remaining jobs by N/configuration times median of up to latest50 finished
attempt-wall observations per stratum; missing strata use accepted pilot estimates
and are labeled. Before usable observations ETA is null. It is not a deadline
promise or solver-only runtime. Record fixed disk reserve in config (default1GiB);
below reserve pause before next claim, do not erase raw data. Status never repairs
DB, triggers a solver, expands storage automatically or enables automation.

## 8. Completeness, exports and metric definitions

`execution_complete` block: every job in the frozen eligible matrix has exactly
one primary terminal result for repetitions1/2/3. `qa_complete` additionally:
only SAT/TIMEOUT statuses, all SAT solutions independently rechecked, timings/
counts/schema/hash/identity/order intact, no fatal flags or unresolved interrupted
job, and cluster/balance checks pass. Historical INTERRUPTED attempts may remain
when their jobs later have primary results; report counts and resume reasons.
TIMEOUT does not make a block incomplete. Terminal ERROR/etc makes it ineligible
for report inclusion, not permission to drop that method/row from the denominator.
Pilot QA has one repetition and its declared pilot selection, never main QA.

`export --complete-blocks` uses a SQLite consistent read snapshot and selects only
qa_complete main blocks, never partial observations to fill missing repeats.
Export audit lists all planned/started/execution-complete/qa-complete blocks and
every excluded reason. Retain partial DB data for later explicit resume. Without
the flag export all observations marked `partial`; no report-ready claim.
Main analysis/report cannot consume pilot or artificial data as final evidence.

Export directory: `export.json`, `results.csv`, `attempts.csv`, `jobs.csv`,
`matrix.json`, manifest/batches metadata snapshot, `solutions/`, `hashes.json`.
SQLite backup API creates `snapshot.sqlite3` before export (never copy live WAL
database alone). Export audit records snapshot hash, last event ID, ordered block/
job/attempt sets, selection mode, experiment fingerprint and all file hashes.
`hashes.json` excludes itself; its hash is returned in the export receipt rather
than recursively embedded. SQLite snapshot is authoritative for the exported
selection; no reading newer live rows midway through an export.
Publish into staging then rename to NEW destination only after consistency checks;
on failure retain explicitly incomplete staging, not a partial final export.

`results.csv` schema2, one row per primary terminal attempt, exact columns:
```
schema_version,experiment_id,dataset_id,phase,batch_id,job_id,attempt_id,attempt_no,
instance_id,method,encoding,repetition,block_side,board_side,source,source_group,
rating_original,rating_value,family,root_id,clue_percent_requested,actual_clues,
input_sha256,cutoff_seconds,status,raw_status,build_seconds,solve_seconds,
total_seconds,attempt_wall_seconds,checkpoint_seconds,primary_variables,
auxiliary_variables,total_variables,clauses,validation,validation_message,
solution_ref,solution_sha256,guard_phase,error
```
Empty cells are null except encoding (`""` is the baseline identity sentinel).
Validation is pass/fail/empty. `solution_ref=solutions/<attempt_id>.json` is relative
and content hash covers exported canonical bytes; non-SAT has neither. Export
checks solution identity, original clues and checksum. UTF-8, RFC4180 quoting,
`.` decimal, no locale rounding of raw measurements. Precision presentation is
analysis-only. SAT CNF fields retain v1 definitions; baseline CNF fields empty.
attempt_wall/checkpoint values unknown after crash stay empty.
`attempts.csv` includes every attempt with job identity, number/state/session,
started/ended timestamps, interruption reason, primary boolean, status if present,
observed timing and witness reference if any; it never substitutes for results.csv.
`jobs.csv` includes pending/interrupted jobs and frozen ordinals for coverage.

Analysis definitions (SAT08 must implement explicitly):

- Runtime for an instance/configuration is median of total_seconds across **all
  three** primary repetitions only when all are SAT; build/solve medians follow
  the same eligible set. Mixed SAT/TIMEOUT gets a status vector, no successful-only
  median. Pilot1rep has no three-repeat runtime statistic or paired speed claim.
- Summary median/p90/p95 are computed over those **per-instance medians**, in
  seconds, within declared N/source-group/clue/family strata. Quantiles use sorted
  observations, h=(m-1)*p, linear interpolation between floor(h),ceil(h) (type7).
  m=0 yields null, m=1 its sole value; always publish m and missing/mixed counts.
- PAR-2 per **primary attempt**: SAT=observed total_seconds, TIMEOUT=20seconds.
  ERROR/UNAVAILABLE/LICENSE_LIMIT/INVALID_INPUT/UNSAT and INTERRUPTED have no
  penalty; list their counts, never recode them as timeouts or zero. Per-instance
  PAR-2 is mean of its three primary penalties only if all three are eligible;
  stratum mean over those instances equals per-attempt mean for complete3rep
  blocks. Publish attempt and instance denominators. Historical interrupted or
  alternative-experiment attempts are not additional samples/penalties.
- Coverage denominators: target puzzles/jobs, matrix-planned jobs, selected complete
  blocks/jobs, observed primary jobs, solved primary jobs, any-SAT instances,
  all-three-SAT instances, timeouts and each excluded status separately. Never call
  all16000 achieved from a subset; no cross-experiment dedup to improve scores.
- Paired speed: exact same IDs with three-SAT repeats on both configurations,
  same eligible blocks/strata; report IDs/counts. Median of per-instance A/B
  runtime ratios; zero denominator produces null, not infinity. SAT v1 vs expanded
  remains separate experiments, no pooled timing averages.
- Repetitions are not independent puzzles. Synthetic masks sharing root_id are
  a cluster; if uncertainty intervals are computed, resample roots with all five
  masks jointly within N/family (and retain density strata), not rows/repetitions.
  Public resampling unit is instance. Label method/seed/count; omit intervals
  rather than assume independence. Do not infer size-only complexity across
  different public/synthetic sources or treat sparse clues as proven difficulty.

## 9. Gates and bounded handoff

EXP07A specifies interfaces only. EXP05 produces verified/frozen data; EXP01/04
produce environment/matrix; EXP02/03 certify model/checker and schema/transaction/
crash/lock/resume/UTF8/process-tree tests; SAT06 CLI and SAT08 schema fixtures follow
this accepted contract. Correctness SAT/UNSAT/invalid cases remain separate.
Main requires current integrated suite pass, pilot accepted with real walltime
estimate, immutable fingerprints, workload isolation and coordinator release.
Do not promise all330000 today (10-second cap sum alone is916h40m).
Stop/report inclusion time and unfinished blocks remain explicit.

No real plan conflict is resolved by weakening existing gates. The routine choices
in this document (root-local batches, proper row cycles, fixed ranking, extra pilot
roots, OS lock, terminal-failure halt, schema2 names) are proposed decisions for
coordinator acceptance. If source supply or row-cycle construction cannot meet
them, report the specific failed quota; do not silently change a family or sample.
After acceptance, incompatible contract changes require a new contract revision,
dataset/experiment identity as affected, and downstream review before execution.

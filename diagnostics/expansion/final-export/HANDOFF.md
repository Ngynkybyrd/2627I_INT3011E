# SAT07 final export — PASS with the declared infrastructure ERROR

Snapshot: `results/final-snapshots/final-20261020-rep1/`.
snapshot.json SHA256: `70eaaf0acb6c74ba02f4ca65d8ca3db5d42d83cdbafe6620865d42d5b8af4781`.
Contract: `diagnostics/expansion/final-export/CONTRACT.json`, SHA256
`c15d3072b6b5e8f0e2baaf168ce8f92514dc4b1a6692a8ec71f6b24a8dfbaeef`. Machine handoff: HANDOFF.json.

All100 batches, all16000 instances and110000 immutable primary repetition1 rows
are included:109664 SAT +335 TIMEOUT +1 ERROR. b099 is included. Quality remains
VERIFIED_WITH_DECLARED_INFRASTRUCTURE_ERROR, error_free=false,
selected_scope_observed_complete=true,
original_three_repetition_experiment_complete=false. All instances were tried;
not all attempts solved. Historical rep2=324 and rep3=343 remain in the raw SQLite
backup but are excluded from CSV. Diagnosticretry is pinned supplemental evidence
only, never a primary replacement or an extra observation.

## Reader wire

results.csv uses exact expanded CSV_FIELDS plus session_id,profile,workers,
timing_policy. Baseline encoding and null values are empty. Every SAT reference
is `sqlite:snapshot.sqlite3#solutions/<attempt_id>`: bind UUID4 as a parameter to
`SELECT payload,sha256,checker_json FROM solutions WHERE attempt_id=?`.
Verify BLOB hash against the CSV and stored hash, canonical n/grid bytes, original
clues and independent checker. TIMEOUT/ERROR have no solution reference.

inputs.sqlite3 embeds all16000 input and original acquisition-witness BLOBs in
table inputs, keyed by instance_id; exact column names/hashes are in CONTRACT.json.
instances.jsonl contains frozen manifest records. Original input_file paths are
provenance, not a dependency on live source files. Snapshot is self-contained:
no100k solution sidecar files and no live-database reads are needed by SAT08.

profiles.json is a DIRECT session_id→metadata mapping. Actual worker row counts:
`{"1": 353, "24": 160, "32": 97660, "4": 11187, "40": 160, "8": 480}`. Keep actual session/profile/worker
contexts separate; do not relabel earlier work as32 workers. Source session files,
metrics when present, root-authorized profile/gate refs and acknowledgement/
completion/recovery/diagnostic evidence are copied and pinned by files_sha256.
Parallel trial workload timings are resource-contended;24/40-worker trial
observations must not be interpreted as isolated scientific speedups.

The ERROR stays exactly the acknowledged N16 seqcounter job/attempt and original
result_json: WinError6, guard_phase=guard, before measured build/solve, null
component times. It is neither UNSAT/TIMEOUT nor a cleanup failure. No retry
timing or retry SAT outcome was substituted into its row.

## QA and execution

18 focused fake tests passed,0 fail/skip (focused-final.xml; prior focused.xml had
17 before the explicit TIMEOUT test was added). Tests cover exact ERROR binding/
classification, valid SAT, invalid SAT, TIMEOUT/None, altered checksum/identity,
worker/scope separation, all100-batch selection, missing/duplicate/extra IDs and
artificial rejection. No fullsuite or solver/benchmark was run.

One SQLite backup was closed before verification. Export verified complete
expected IDs, frozen matrix/schedule ordinal identities, all inputs/witnesses,
root cluster linkage, source metadata hashes, full SQLite integrity/FK, no active
attempt/open session, every selected primary/state/configuration, finite or null
timings, guard phases, every SAT canonical solution checksum and independent
checker/CNF counts, checkpoint values, all session profiles/authorization refs,
exact error acknowledgement, diagnostic checker evidence and all status totals.
The original source manifest/index/raw primary data and core were not changed.

Root independently verified all48 artifact hashes: see
diagnostics/expansion/root-wave3/final-snapshot-root-check.json (PASS).
This handoff step did not export again or repeat the full data audit. SAT08 has
been released by root to analyze this frozen scope; report/provenance acceptance
belongs to later gates. No blocker remains within SAT07 export scope.

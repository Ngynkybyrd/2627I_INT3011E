"""Finalize receipts only; no export, solver, benchmark or repeated data audit."""
from collections import Counter
import hashlib,json,pathlib,xml.etree.ElementTree as ET

ROOT=pathlib.Path(__file__).resolve().parents[3]
HERE=pathlib.Path(__file__).parent
SNAP=ROOT/"results/final-snapshots/final-20261020-rep1"

def sha(path):
    with pathlib.Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()
def read(path):return json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))

receipt=read(SNAP/"snapshot.json");profiles=read(SNAP/"profiles.json")
assert sha(SNAP/"snapshot.json")=="70eaaf0acb6c74ba02f4ca65d8ca3db5d42d83cdbafe6620865d42d5b8af4781"
assert receipt["status"]=="PASS" and receipt["quality"]=="VERIFIED_WITH_DECLARED_INFRASTRUCTURE_ERROR" and receipt["error_free"] is False
assert receipt["primary_counts"]==dict(SAT=109664,TIMEOUT=335,ERROR=1)
assert receipt["observed_jobs"]==receipt["expected_jobs"]==110000 and receipt["selected_instances"]==16000
assert receipt["excluded_primary_counts"]=={"2":324,"3":343}
assert receipt["producer_sha256"]==sha(ROOT/"scripts/export_expanded_final.py")
assert receipt["rolling_helper_sha256"]==sha(ROOT/"scripts/export_expanded_rolling.py")
assert receipt["files_sha256"]["CONTRACT.json"]==sha(HERE/"CONTRACT.json")==sha(SNAP/"CONTRACT.json")
suite=ET.parse(HERE/"focused-final.xml")
assert len(list(suite.iter("testcase")))==18 and not list(suite.iter("failure")) and not list(suite.iter("error")) and not list(suite.iter("skipped"))
root_check=ROOT/"diagnostics/expansion/root-wave3/final-snapshot-root-check.json"
assert read(root_check)["status"]=="PASS"
workers=Counter()
for sid,count in receipt["session_counts"].items():workers[str(profiles[sid]["workers"])]+=count
proof=dict(status="PASS",quality=receipt["quality"],error_free=False,selected_scope_observed_complete=True,
    original_three_repetition_experiment_complete=False,snapshot_dir=str(SNAP),snapshot_receipt_path=str(SNAP/"snapshot.json"),snapshot_sha256=sha(SNAP/"snapshot.json"),
    contract_path=str(HERE/"CONTRACT.json"),contract_sha256=sha(HERE/"CONTRACT.json"),
    expected_jobs=110000,observed_jobs=110000,selected_instances=16000,selected_repetitions=[1],primary_counts=receipt["primary_counts"],
    excluded_primary_counts=receipt["excluded_primary_counts"],by_size=receipt["by_size"],worker_row_counts=dict(workers),session_counts=receipt["session_counts"],
    declared_error=receipt["declared_error"],snapshot_artifact_count=len(receipt["files_sha256"]),
    root_check=dict(path=str(root_check),sha256=sha(root_check),status="PASS"),
    tests=dict(passed=18,failed=0,skipped=0,fullsuite=False,path=str(HERE/"focused-final.xml"),sha256=sha(HERE/"focused-final.xml")),
    exporter_sha256=sha(ROOT/"scripts/export_expanded_final.py"),test_source_sha256=sha(ROOT/"tests/expanded/test_final_export.py"),solver_calls=0,
    pending_scientific_acceptance="SAT08 analysis and later report/provenance QA; this receipt approves export data only")
(HERE/"HANDOFF.json").write_text(json.dumps(proof,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
text=f"""# SAT07 final export — PASS with the declared infrastructure ERROR

Snapshot: `results/final-snapshots/final-20261020-rep1/`.
snapshot.json SHA256: `{proof['snapshot_sha256']}`.
Contract: `diagnostics/expansion/final-export/CONTRACT.json`, SHA256
`{proof['contract_sha256']}`. Machine handoff: HANDOFF.json.

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
`{json.dumps(dict(workers),sort_keys=True)}`. Keep actual session/profile/worker
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

Root independently verified all{len(receipt['files_sha256'])} artifact hashes: see
diagnostics/expansion/root-wave3/final-snapshot-root-check.json (PASS).
This handoff step did not export again or repeat the full data audit. SAT08 has
been released by root to analyze this frozen scope; report/provenance acceptance
belongs to later gates. No blocker remains within SAT07 export scope.
"""
(HERE/"HANDOFF.md").write_text(text,encoding="utf-8",newline="\n")
print(json.dumps(dict(status="PASS",snapshot_sha256=proof["snapshot_sha256"],artifact_count=proof["snapshot_artifact_count"],tests=18,worker_row_counts=dict(workers)),ensure_ascii=False))

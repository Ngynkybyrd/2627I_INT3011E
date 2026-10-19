"""Explicit, root-authorized throughput resume. Timings are resource-contended.

This standalone entry point intentionally lives outside the original frozen
source list. It reuses the unchanged schema2 validation, storage and guarded
fresh-process runner. Only the coordinator thread touches SQLite.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import parallel_process_lifecycle as lifecycle
from sudoku import expanded_runner as api
from sudoku import expanded_storage as storage
from sudoku.expanded_common import ExpandedError, deadline, read, require, sha, stamp, write, contained, dumps

PROFILE = "parallel-throughput-capacity-recovery-v2"
TIMING_POLICY = "resource-contended"
REPORTING_POLICY = "separate-by-session"


RECOVERY_RECEIPT = ROOT / "diagnostics/expansion/root-wave3/handle-error-recovery-ack.json"
RECOVERY_SHA256 = "2c26ad94b4f9f164b5a2dc1bd65e6f6c8921a44a8957c82b947e1f238e7a71cf"


def acknowledged_errors(db):
    require(sha(RECOVERY_RECEIPT) == RECOVERY_SHA256, "Recovery receipt changed", 5)
    ack = read(RECOVERY_RECEIPT)
    exp = db.execute("SELECT experiment_id,manifest_json FROM experiment").fetchone()
    require(ack.get("accepted_by") == "root" and ack.get("accepted") is True and
            ack.get("experiment_id") == exp[0] and ack.get("scientific_sha256") == json.loads(exp[1])["scientific_sha256"],
            "Recovery receipt subject mismatch", 5)
    errors = [dict(row) for row in db.execute("SELECT r.attempt_id,a.job_id,r.status,r.result_json FROM results r JOIN attempts a USING(attempt_id) WHERE r.status NOT IN ('SAT','TIMEOUT') ORDER BY r.attempt_id")]
    require(errors == ack["acknowledged_fatal_results"] and len(errors) == 1, "Unacknowledged fatal result prevents recovery", 5)
    result = json.loads(errors[0]["result_json"])
    require(result.get("status") == "ERROR" and result.get("guard_phase") == "guard" and
            result.get("error") == "OSError: [WinError 6] The handle is invalid" and
            all(result.get(k) is None for k in ("build_seconds", "solve_seconds", "total_seconds", "validation")),
            "Only the exact premeasurement handle failure can be acknowledged", 5)
    return ack


def compact_status(directory):
    # Full _load including independent checker runs before admission and at scope completion.
    # This read transaction only presents progress; it makes no additional QA claim.
    db = storage.connect(directory, readonly=True)
    try:
        db.execute("BEGIN")
        row = db.execute("SELECT experiment_id,state,halt_reason FROM experiment").fetchone()
        return dict(experiment_id=row[0], state=row[1], reason=row[2],
                    primary_counts=dict(db.execute("SELECT r.status,COUNT(*) FROM primary_attempt p JOIN results r USING(attempt_id) GROUP BY r.status")),
                    progress_diagnostic_only=True, exit_code=5 if row[1] == "HALTED" else 4)
    finally:
        db.close()


SCOPE_COMPLETE_REASON = "selected repetition scope complete; original repetitions2/3 not requested"


def authorization_subject(manifest, workers, scope=None, *, min_available_ram_mb=6144, authorized_workers_max=100, worker_memory_reserve_mb=512):
    return dict(schema_version=1, accepted_by="root", accepted=True,
                experiment_id=manifest["experiment_id"],
                scientific_sha256=manifest["scientific_sha256"],
                script_sha256=sha(__file__), profile=PROFILE, workers=workers,
                timing_policy=TIMING_POLICY, reporting_policy=REPORTING_POLICY,
                min_available_ram_mb=min_available_ram_mb, authorized_workers_max=authorized_workers_max,
                worker_memory_reserve_mb=worker_memory_reserve_mb,
                idle_low_ram_seconds=30, recovery_receipt_sha256=RECOVERY_SHA256,
                lifecycle_sha256=sha(ROOT / "scripts/parallel_process_lifecycle.py"), **(scope or {}))


def verify_authorization(manifest, workers, path, expected_sha, scope=None, *, min_available_ram_mb=6144, authorized_workers_max=100, worker_memory_reserve_mb=512):
    require(path is not None and expected_sha, "Explicit root authorization path and SHA256 required")
    path = Path(path).resolve()
    require(path.is_relative_to(ROOT.resolve()), "Authorization receipt must be inside project root")
    require(sha(path) == expected_sha, "Authorization receipt SHA256 mismatch", 5)
    receipt = read(path)
    subject = authorization_subject(manifest, workers, scope, min_available_ram_mb=min_available_ram_mb,
                                    authorized_workers_max=authorized_workers_max, worker_memory_reserve_mb=worker_memory_reserve_mb)
    require(all(type(receipt.get(k)) is type(v) and dumps(receipt.get(k)) == dumps(v)
                for k, v in subject.items()), "Root parallel authorization subject mismatch", 5)
    return dict(path=str(path.relative_to(ROOT)), sha256=expected_sha, receipt=receipt)


def selected_scope(db, manifest, repetition):
    if repetition is None:
        return {}
    target = db.execute("SELECT COUNT(*) FROM jobs WHERE repetition=?", (repetition,)).fetchone()[0]
    require(target > 0, "Selected repetition has no scheduled jobs")
    return dict(selected_repetitions=[repetition], target_jobs=target,
                effective_repetitions=1, original_manifest_repetitions=manifest["config"]["repetitions"])


def scope_progress(db, repetition):
    total, completed = db.execute("""SELECT COUNT(*),COUNT(p.attempt_id) FROM jobs j
        LEFT JOIN primary_attempt p USING(job_id) WHERE j.repetition=?""", (repetition,)).fetchone()
    return dict(scope_state="COMPLETED" if total and completed == total else "PAUSED",
                scope_planned_jobs=total, scope_completed_jobs=completed,
                scope_remaining_jobs=total-completed)


def claim_selected(db, session, repetition):
    """Same durable attempt transitions as storage.claim, filtered by scope."""
    with storage.transaction(db):
        job = db.execute("SELECT * FROM jobs WHERE state='PENDING' AND repetition=? ORDER BY ordinal LIMIT 1",
                         (repetition,)).fetchone()
        if job is None:
            return None
        aid = str(uuid.uuid4())
        number = db.execute("SELECT COALESCE(MAX(attempt_no),0)+1 FROM attempts WHERE job_id=?", (job["job_id"],)).fetchone()[0]
        db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,NULL,NULL,NULL)",
                   (aid, job["job_id"], number, session, "RUNNING", stamp()))
        db.execute("UPDATE jobs SET state='RUNNING' WHERE job_id=? AND state='PENDING'", (job["job_id"],))
        storage.event(db, "CLAIM", {"selected_repetition": repetition}, session=session, job=job["job_id"], attempt=aid)
    return dict(job, attempt_id=aid, attempt_no=number)


def finalize_scope(directory, db, sid, manifest, scope, repetition):
    """Publish a derived completion receipt; never complete the original scope."""
    api._load(directory, db)  # Full frozen inputs/fingerprint/integrity and independent result recheck.
    progress = scope_progress(db, repetition)
    require(progress["scope_state"] == "COMPLETED", "Selected scope exhausted without complete primary results", 5)
    require(db.execute("SELECT 1 FROM attempts WHERE state='RUNNING' LIMIT 1").fetchone() is None,
            "Selected completion has unfinished attempts", 5)
    db.execute("UPDATE experiment SET state='PAUSED',halt_reason=?", (SCOPE_COMPLETE_REASON,))
    batches = [dict(batch_id=row[0], expected_jobs=row[1], completed_jobs=row[2]) for row in db.execute("""
        SELECT i.batch_id,COUNT(*),COUNT(p.attempt_id) FROM jobs j JOIN instances i USING(instance_id)
        LEFT JOIN primary_attempt p USING(job_id) WHERE j.repetition=? GROUP BY i.batch_id ORDER BY i.batch_id""", (repetition,))]
    profiles = []
    for row in db.execute("""SELECT DISTINCT a.session_id FROM primary_attempt p
        JOIN jobs j USING(job_id) JOIN attempts a ON a.attempt_id=p.attempt_id WHERE j.repetition=?""", (repetition,)):
        path = directory / "session-manifests" / (row[0] + ".json")
        require(path.is_file(), "Selected primary session manifest missing", 5)
        source = read(path)
        profiles.append(dict(session_id=row[0], path=str(path.relative_to(directory)), sha256=sha(path),
                             profile=source.get("profile", "original-sequential"),
                             timing_policy=source.get("timing_policy", "sequential")))
    receipt = dict(schema_version=1, session_id=sid, experiment_id=manifest["experiment_id"],
                   scientific_sha256=manifest["scientific_sha256"], original_state="HALTED", utc=stamp(),
                   original_config=manifest["config"], effective_config=dict(manifest["config"], repetitions=1),
                   batches=batches, source_sessions=profiles, reporting_policy=REPORTING_POLICY,
                   independent_validation="Full schema2 load/integrity and stored primary result checks passed; original three-repetition batch QA remains separate.",
                   scientific_reporting_note="Only selected repetition contributes to active target and timing summaries; retained repetitions2/3 are excluded. Separate timing summaries by session and profile; concurrent timings are resource-contended.",
                   **scope, **progress)
    (directory / "scope-completions").mkdir(exist_ok=True)
    path = directory / "scope-completions" / (sid + ".json")
    receipt.update(scope_state="COMPLETED_WITH_ERROR", all_selected_jobs_observed=True, quality_state="HAS_PRESERVED_INFRASTRUCTURE_ERROR", error_free=False,
                   preserved_errors=acknowledged_errors(db)["acknowledged_fatal_results"],
                   recovery_receipt_sha256=RECOVERY_SHA256,
                   reporting_note="All selected jobs have observations; historical ERROR remains primary. Do not claim all jobs solved or error-free QA.")
    write(path, receipt)
    db.execute("UPDATE experiment SET state='HALTED',halt_reason=?", ("Selected scope observed completely; preserved acknowledged infrastructure ERROR requires explicit reporting",))
    storage.event(db, "SELECTED_SCOPE_COMPLETED", {"path":str(path.relative_to(directory)), "sha256":sha(path), **scope, **progress}, session=sid)
    return progress


def check_resumable(db):
    require(db.execute("SELECT state FROM experiment").fetchone()[0] in ("PAUSED", "HALTED"),
            "Parallel resume requires PAUSED experiment", 5)
    require(db.execute("SELECT 1 FROM attempts WHERE state='RUNNING' LIMIT 1").fetchone() is None,
            "Running attempts require original cleanup/recovery before parallel resume", 5)
    require(db.execute("SELECT 1 FROM sessions WHERE ended_utc IS NULL LIMIT 1").fetchone() is None,
            "Unfinished session requires original cleanup/recovery before parallel resume", 5)
    acknowledged_errors(db)
    require(db.execute("SELECT 1 FROM events WHERE type='REJECTED_OBSERVATION' LIMIT 1").fetchone() is None,
            "Rejected observation prevents parallel resume", 5)


def available_physical_mb():
    """Windows physical availability, sampled only when admitting work."""
    import ctypes
    require(os.name == "nt", "Capacity memory admission requires Windows")
    class Memory(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
            (key, ctypes.c_uint64) for key in ("total", "available", "page_total", "page_available",
                                              "virtual_total", "virtual_available", "extended")]
    memory = Memory()
    memory.length = ctypes.sizeof(memory)
    require(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)), "Windows available RAM query failed", 5)
    return memory.available / (1024 * 1024)


class ActiveIntervals:
    """Thread-safe in-memory accounting; workers never access SQLite."""
    def __init__(self):
        self.lock = threading.Lock()
        self.active = self.peak = 0
        self.first_started_utc = self.last_ended_utc = None

    def enter(self):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            if self.first_started_utc is None:
                self.first_started_utc = stamp()

    def leave(self):
        with self.lock:
            self.active -= 1
            self.last_ended_utc = stamp()


def _timed_job(run_job, request, config, intervals):
    start = time.perf_counter()
    intervals.enter()
    try:
        result = run_job(request, config, root=ROOT)
        return result, time.perf_counter() - start
    finally:
        intervals.leave()


def coordinate(db, sid, index, config, workers, run_job, start_check, heartbeat, max_jobs=None, repetition=None,
               *, min_available_ram_mb=6144, worker_memory_reserve_mb=512, memory_reader=None, idle_low_ram_seconds=30, clock=None):
    """Bounded futures; stop admission, then persist every in-flight outcome.

    start_check returns a pause reason or None; exceptions halt admission. Both
    callbacks, all claims and all commits execute in the caller thread.
    """
    futures = {}
    pause_reason = None
    failure = None
    fatal = False
    exhausted = False
    claimed = 0
    memory_reader = memory_reader or available_physical_mb
    clock = clock or time.perf_counter
    initial_available = memory_reader()
    require(type(initial_available) in (int, float) and 0 <= initial_available < float("inf"), "Invalid initial available RAM reading", 5)
    memory_cap = min(workers, max(0, int((initial_available-min_available_ram_mb)//worker_memory_reserve_mb)))
    intervals = ActiveIntervals()
    first_claim = last_result = None
    first_claim_utc = last_result_utc = None
    minimum_available = initial_available
    throttles = throttle_events = 0
    idle_low_since = None
    throttled = False
    statuses = Counter()

    def ram_allows_admission():
        nonlocal minimum_available, throttles, throttle_events, idle_low_since, throttled, pause_reason
        available = memory_reader()
        require(type(available) in (int, float) and 0 <= available < float("inf"), "Invalid available RAM reading", 5)
        minimum_available = available if minimum_available is None else min(minimum_available, available)
        if available < min_available_ram_mb or memory_cap == 0:
            throttles += 1
            if not throttled and throttle_events < 100:
                storage.event(db, "RAM_ADMISSION_THROTTLED", {"available_mb":available, "floor_mb":min_available_ram_mb}, session=sid)
                throttle_events += 1
            throttled = True
            if not futures:
                if idle_low_since is None:
                    idle_low_since = clock()
                elif clock()-idle_low_since >= idle_low_ram_seconds:
                    pause_reason = "available physical RAM or session memory capacity below authorized reserve for 30 idle seconds"
            else:
                idle_low_since = None
            return False
        if throttled and throttle_events < 100:
            storage.event(db, "RAM_ADMISSION_RECOVERED", {"available_mb":available}, session=sid)
            throttle_events += 1
        throttled = False
        idle_low_since = None
        return True

    def remember(exc):
        nonlocal failure
        if failure is None:
            failure = exc

    def interrupt_if_running(active, reason):
        row = db.execute("SELECT state FROM attempts WHERE attempt_id=?", (active["attempt_id"],)).fetchone()
        if row and row[0] == "RUNNING":
            storage.interrupt(db, active["attempt_id"], reason)

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="guarded-job") as pool:
        while True:
            # Consume every completed future before admitting replacement work;
            # a fatal result in this set prevents all subsequent admissions.
            for future in list(futures):
                if not future.done():
                    continue
                active = futures.pop(future)
                try:
                    result, wall = future.result()
                    record = index["records"][active["instance_id"]]
                    fatal = storage.finish(db, active["attempt_id"], result, record,
                                           index["dataset_dir"], wall) or fatal
                    status = db.execute("SELECT status FROM results WHERE attempt_id=?", (active["attempt_id"],)).fetchone()[0]
                    statuses[status] += 1
                    last_result = clock()
                    last_result_utc = stamp()
                except BaseException as exc:
                    remember(exc)
                    try:
                        interrupt_if_running(active, "parallel worker/persistence failure: " + str(exc)[:300])
                    except BaseException as cleanup_exc:
                        remember(cleanup_exc)
            try:
                heartbeat()
                if not (failure or fatal or pause_reason or exhausted):
                    pause_reason = start_check()
                while not (failure or fatal or pause_reason or exhausted) and len(futures) < max(1, memory_cap):
                    if max_jobs is not None and claimed >= max_jobs:
                        pause_reason = "session max-jobs reached"
                        break
                    # Recheck completed work before every launch, including the
                    # initial fill if a short worker already failed.
                    if any(f.done() for f in futures):
                        break
                    pause_reason = start_check()
                    if pause_reason:
                        break
                    if not ram_allows_admission():
                        break
                    claim_clock = clock()
                    active = storage.claim(db, sid) if repetition is None else claim_selected(db, sid, repetition)
                    if active is None:
                        exhausted = True
                        break
                    claimed += 1
                    if first_claim is None:
                        first_claim = claim_clock
                        first_claim_utc = stamp()
                    try:
                        pause_reason = start_check()
                        if pause_reason:
                            interrupt_if_running(active, "not_launched: " + pause_reason)
                            break
                        record = index["records"][active["instance_id"]]
                        request = dict(active, encoding=active["encoding"] or None,
                                       scope="expanded-v2", cutoff_seconds=config.cutoff_seconds,
                                       file=os.path.relpath(contained(index["dataset_dir"], record["input_file"]), ROOT))
                        futures[pool.submit(_timed_job, run_job, request, config, intervals)] = active
                    except BaseException:
                        interrupt_if_running(active, "parallel admission failure")
                        raise
            except BaseException as exc:
                remember(exc)
            if not futures and (failure or fatal or pause_reason or exhausted):
                break
            if futures:
                try:
                    wait(futures, timeout=0.25, return_when=FIRST_COMPLETED)
                except BaseException as exc:
                    remember(exc)
            elif not (failure or fatal or pause_reason or exhausted):
                threading.Event().wait(0.25)
    elapsed = max(0, last_result-first_claim) if first_claim is not None and last_result is not None else 0
    metrics = dict(new_jobs=sum(statuses.values()), claimed_jobs=claimed, execution_wall_seconds=elapsed,
                   requested_workers=workers, effective_memory_cap=memory_cap,
                   initial_available_mb=initial_available, worker_memory_reserve_mb=worker_memory_reserve_mb,
                   jobs_per_second=sum(statuses.values())/elapsed if elapsed else 0,
                   peak_inflight=intervals.peak, min_available_mb=minimum_available, ram_throttle_count=throttles,
                   statuses=dict(statuses), first_claim_utc=first_claim_utc, last_result_utc=last_result_utc,
                   first_worker_started_utc=intervals.first_started_utc, last_worker_ended_utc=intervals.last_ended_utc,
                   timing_interval="first claim through last committed result; excludes preflight",
                   inflight_definition="concurrently active guarded run_job calls, including worker startup/cleanup")
    return dict(pause_reason=pause_reason, fatal=fatal, failure=failure, metrics=metrics)


def run(experiment, *, workers=4, execute=False, stop_starting_at=None,
        authorization=None, authorization_sha256=None, stop_file=None, max_jobs=None, repetition=None,
        min_available_ram_mb=6144, authorized_workers_max=100, worker_memory_reserve_mb=512):
    require(type(authorized_workers_max) is int and 1 <= authorized_workers_max <= 100, "Authorized worker maximum must be between 1 and 100")
    require(type(workers) is int and 1 <= workers <= authorized_workers_max, "Workers exceed root-authorized worker maximum")
    require(type(min_available_ram_mb) is int and min_available_ram_mb > 0, "Minimum available RAM MB must be positive")
    require(type(worker_memory_reserve_mb) is int and 128 <= worker_memory_reserve_mb <= 2048, "Worker memory reserve MB must be between 128 and 2048")
    resources = dict(min_available_ram_mb=min_available_ram_mb, authorized_workers_max=authorized_workers_max,
                     worker_memory_reserve_mb=worker_memory_reserve_mb)
    require(max_jobs is None or (type(max_jobs) is int and max_jobs > 0), "Max-jobs must be positive")
    require(repetition is None or (type(repetition) is int and repetition == 1), "Only explicit repetition1 selection is supported")
    directory = Path(experiment).resolve()
    require((directory / "experiment.json").is_file(), "Prepared experiment required")
    if not execute:
        db = storage.connect(directory, readonly=True)
        db.execute("PRAGMA cache_size=-262144")
        try:
            manifest, _ = api._load(directory, db)
            scope = selected_scope(db, manifest, repetition)
            return dict(execute=False, profile=PROFILE, workers=workers,
                        timing_policy=TIMING_POLICY, reporting_policy=REPORTING_POLICY,
                        max_jobs=max_jobs,
                        state=db.execute("SELECT state FROM experiment").fetchone()[0],
                        remaining_jobs=db.execute("SELECT COUNT(*) FROM jobs WHERE state='PENDING'").fetchone()[0],
                        required_root_authorization=authorization_subject(manifest, workers, scope, **resources),
                        **scope, **(scope_progress(db, repetition) if repetition else {}))
        finally:
            db.close()
    require(stop_starting_at is not None, "Explicit future stop-starting-at required")
    stop = deadline(stop_starting_at)
    require(stop > datetime.now(timezone.utc), "Explicit future stop-starting-at required")
    stop_file = Path(stop_file).resolve() if stop_file else None
    with storage.WriterLock(directory):
        db = storage.connect(directory)
        db.execute("PRAGMA cache_size=-262144")
        sid = None
        previous_signal = None
        stopped = threading.Event()
        try:
            print(f"{stamp()} preflight start; SQLite cache_size=-262144 (256 MiB); all validation checks retained", file=sys.stderr, flush=True)
            manifest, index = api._load(directory, db)
            print(f"{stamp()} preflight complete", file=sys.stderr, flush=True)
            refs = api._gates(manifest)
            check_resumable(db)
            scope = selected_scope(db, manifest, repetition)
            receipt = verify_authorization(manifest, workers, authorization, authorization_sha256, scope, **resources)
            if repetition:
                # Preserve every original record while avoiding scans through
                # retained pending repetitions2/3 on each selected claim.
                db.execute("CREATE INDEX IF NOT EXISTS parallel_selected_pending_ordinal ON jobs(repetition,state,ordinal)")
            from sudoku.runner import RunnerConfig, run_job
            lifecycle_info = lifecycle.install()
            config = RunnerConfig(**{k: manifest["config"][k] for k in
                                     ("cutoff_seconds", "repetitions", "schedule_seed", "startup_seconds", "postprocessing_seconds")})
            if repetition:
                config = RunnerConfig(**dict(vars(config), repetitions=1))
            sid = storage.new_session(db, stop.isoformat(), PROFILE + "; resource-contended; separate timings by session")
            metadata = dict(session_id=sid, scientific_manifest=manifest, gate_refs=refs,
                            stop_starting_at=stop.isoformat(), profile=PROFILE, workers=workers,
                            stop_file=str(stop_file) if stop_file else None,
                            max_jobs=max_jobs,
                            script_sha256=sha(__file__), authorization=receipt,
                            timing_policy=TIMING_POLICY, reporting_policy=REPORTING_POLICY,
                            scientific_reporting_note="Mixed sequential/concurrent execution; separate timing summaries by session and profile. Concurrent timings are resource-contended, not isolated benchmarks.")
            metadata.update(scope)
            metadata["lifecycle_fix"] = lifecycle_info
            metadata["recovery_receipt_sha256"] = RECOVERY_SHA256
            metadata.update(resources)
            if repetition:
                metadata["scope_at_start"] = scope_progress(db, repetition)
                metadata["scientific_reporting_note"] += " Only repetition1 is requested; retained repetitions2/3 are excluded from active target and timing summaries."
            (directory / "session-manifests").mkdir(exist_ok=True)
            write(directory / "session-manifests" / (sid + ".json"), metadata)
            storage.event(db, "PARALLEL_PROFILE_AUTHORIZED", metadata, session=sid)
            storage.event(db, "GATES_VERIFIED", refs, session=sid)
            storage.event(db, "EXACT_INFRASTRUCTURE_ERROR_ACKNOWLEDGED", {"receipt_path":str(RECOVERY_RECEIPT.relative_to(ROOT)), "receipt_sha256":RECOVERY_SHA256, "historical_error_preserved":True}, session=sid)
            db.execute("UPDATE experiment SET state='RUNNING',halt_reason=NULL")
            if threading.current_thread() is threading.main_thread():
                previous_signal = signal.signal(signal.SIGINT, lambda *_: stopped.set())
            last_heartbeat = 0.0

            def heartbeat():
                nonlocal last_heartbeat
                if time.monotonic() - last_heartbeat >= 2:
                    db.execute("UPDATE sessions SET heartbeat_utc=? WHERE session_id=?", (stamp(), sid))
                    last_heartbeat = time.monotonic()

            def start_check():
                if stopped.is_set() or datetime.now(timezone.utc) >= stop:
                    return "stop requested/deadline"
                if stop_file is not None and stop_file.exists():
                    return "stop file requested"
                if shutil.disk_usage(directory).free < manifest["config"]["disk_reserve_bytes"]:
                    return "disk reserve"
                require(api._gates(manifest) == refs, "Accepted gate references changed during session", 5)
                require(sha(__file__) == metadata["script_sha256"], "Parallel coordinator changed during session", 5)
                require(sha(authorization) == authorization_sha256, "Parallel authorization changed during session", 5)
                require(sha(ROOT / "scripts/parallel_process_lifecycle.py") == receipt["receipt"]["lifecycle_sha256"], "Lifecycle adapter changed during session", 5)
                return None

            outcome = coordinate(db, sid, index, config, workers, run_job, start_check, heartbeat, max_jobs, repetition,
                                 min_available_ram_mb=min_available_ram_mb, worker_memory_reserve_mb=worker_memory_reserve_mb)
            stage_metrics = {"profile":PROFILE, "session_id":sid, "workers":workers, **resources, **scope, **outcome["metrics"]}
            write(directory / "session-manifests" / (sid + ".metrics.json"), stage_metrics)
            storage.event(db, "CAPACITY_SESSION_METRICS", stage_metrics, session=sid)
            if outcome["failure"]:
                raise outcome["failure"]
            if outcome["fatal"]:
                db.execute("UPDATE experiment SET state='HALTED',halt_reason=COALESCE(halt_reason,'fatal concurrent outcome')")
            elif repetition and scope_progress(db, repetition)["scope_remaining_jobs"] == 0:
                finalize_scope(directory, db, sid, manifest, scope, repetition)
            elif outcome["pause_reason"]:
                db.execute("UPDATE experiment SET state='PAUSED',halt_reason=?", (outcome["pause_reason"],))
            else:
                db.execute("UPDATE experiment SET state='COMPLETED',halt_reason=NULL")
        except BaseException as exc:
            if sid:
                db.execute("UPDATE experiment SET state='HALTED',halt_reason=?", (str(exc)[:500],))
                storage.event(db, "HALTED", {"error": str(exc)[:500], "profile": PROFILE}, session=sid)
            raise
        finally:
            if previous_signal is not None:
                signal.signal(signal.SIGINT, previous_signal)
            try:
                if sid:
                    db.execute("UPDATE sessions SET ended_utc=?,heartbeat_utc=? WHERE session_id=?", (stamp(), stamp(), sid))
                    storage.event(db, "SESSION_ENDED", {"profile": PROFILE, "timing_policy": TIMING_POLICY}, session=sid)
            finally:
                db.close()
    snapshot = compact_status(directory)
    snapshot["capacity_metrics"] = stage_metrics
    if repetition:
        db = storage.connect(directory, readonly=True)
        db.execute("PRAGMA cache_size=-262144")
        try:
            snapshot.update(scope_progress(db, repetition))
            snapshot.update(scope)
            snapshot["quality_state"] = "HAS_PRESERVED_INFRASTRUCTURE_ERROR"
            if snapshot["scope_remaining_jobs"] == 0:
                snapshot["scope_state"] = "COMPLETED_WITH_ERROR"
            if snapshot["state"] != "HALTED":
                snapshot["exit_code"] = 0 if snapshot["scope_state"] == "COMPLETED" else 4
        finally:
            db.close()
    return snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--authorized-workers-max", type=int, default=100)
    parser.add_argument("--min-available-ram-mb", type=int, default=6144)
    parser.add_argument("--worker-memory-reserve-mb", "--per-worker-reserve-mb", dest="worker_memory_reserve_mb", type=int, default=512)
    parser.add_argument("--execute", action="store_true", help="explicitly authorize starting work after receipt validation")
    parser.add_argument("--stop-starting-at")
    parser.add_argument("--stop-file", type=Path, help="existence requests a graceful pause; in-flight workers drain")
    parser.add_argument("--max-jobs", type=int, help="pause after this many new claims in the session")
    parser.add_argument("--repetition", type=int, choices=[1], help="run only repetition1; preserve all other scheduled jobs and results")
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--authorization-sha256")
    args = parser.parse_args(argv)
    try:
        result = run(**vars(args))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result.get("exit_code", 0)
    except (ExpandedError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "exit_code": getattr(exc, "exit_code", 5)}), file=sys.stderr)
        return getattr(exc, "exit_code", 5)


if __name__ == "__main__":
    raise SystemExit(main())



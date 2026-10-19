"""Artificial concurrent adapters only: no Sudoku solver or worker process."""
import importlib.util
import json
from pathlib import Path
import threading
import time

import pytest

from sudoku import expanded_storage as storage
from sudoku.expanded_common import ExpandedError, write, sha
from sudoku.runner import RunnerConfig


PATH = Path(__file__).resolve().parents[2] / "scripts/run_expanded_parallel.py"
SPEC = importlib.util.spec_from_file_location("parallel_runner_tests", PATH)
parallel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parallel)


@pytest.fixture
def store(tmp_path):
    directory = tmp_path / "experiment"
    directory.mkdir()
    record = dict(instance_id="artificial", content_sha256="a" * 64,
                  batch_id="b", n=3, N=9, input_file="not-read.json")
    index = dict(dataset_dir=str(tmp_path), records={"artificial": record},
                 batches=[dict(batch_id="b", ordinal=1, instance_ids=["artificial"])])
    jobs = [dict(job_id=f"j{i}", instance_id="artificial", configuration="cpsat",
                 method="cpsat", encoding="", repetition=i, ordinal=i, batch_id="b")
            for i in range(1, 13)]
    storage.initialize(directory, dict(experiment_id="artificial", artificial=True), index, jobs)
    db = storage.connect(directory)
    sid = storage.new_session(db, "2099-01-01T00:00:00+00:00", "artificial tests")
    yield db, sid, index
    db.close()


def result(status="TIMEOUT"):
    return dict(status=status, method="cpsat", encoding=None, solution=None,
                guard_phase="measurement", raw_status="ARTIFICIAL_NO_SOLVER")


def run_fake(store, fake, check=lambda: None, heartbeat=lambda: None, workers=4):
    db, sid, index = store
    return parallel.coordinate(db, sid, index, RunnerConfig(), workers, fake, check, heartbeat)


def assert_drained(db):
    assert db.execute("SELECT COUNT(*) FROM attempts WHERE state='RUNNING'").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM results").fetchone()[0] == db.execute("SELECT COUNT(*) FROM primary_attempt").fetchone()[0]
    storage.integrity(db)


def test_bounded_concurrency_unique_claims_and_resume_preserves_primary(store):
    db, sid, index = store
    first = storage.claim(db, sid)
    storage.finish(db, first["attempt_id"], result(), index["records"]["artificial"], index["dataset_dir"], .01)
    original = db.execute("SELECT * FROM results").fetchone()
    lock = threading.Lock()
    active = 0
    peak = 0
    seen = []
    barrier = threading.Barrier(3)

    def fake(job, config, *, root):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            seen.append(job["job_id"])
            number = len(seen)
        if number <= 3:
            barrier.wait(timeout=5)
        time.sleep(.02)
        with lock:
            active -= 1
        return result()

    outcome = run_fake(store, fake, workers=3)
    assert outcome == dict(pause_reason=None, fatal=False, failure=None)
    assert 2 <= peak <= 3 and active == 0
    assert len(seen) == len(set(seen)) == 11
    assert first["job_id"] not in seen
    assert tuple(db.execute("SELECT * FROM results WHERE attempt_id=?", (first["attempt_id"],)).fetchone()) == tuple(original)
    assert_drained(db)
    seen.clear()
    run_fake(store, fake, workers=3)
    assert seen == []


def test_stop_drains_all_started_workers_and_no_replacement(store):
    started = threading.Event()
    release = threading.Event()
    count = 0
    lock = threading.Lock()

    def fake(job, config, *, root):
        nonlocal count
        with lock:
            count += 1
            if count == 3:
                started.set()
        assert release.wait(5)
        return result()

    def check():
        if started.is_set():
            release.set()
            return "stop file requested"

    outcome = run_fake(store, fake, check, workers=3)
    assert outcome["pause_reason"] == "stop file requested"
    assert count == 3
    assert store[0].execute("SELECT COUNT(*) FROM results").fetchone()[0] == 3
    assert_drained(store[0])


def test_session_job_cap_pauses_and_preserves_every_started_outcome(store):
    db, sid, index = store
    seen = []
    def fake(job, config, *, root):
        seen.append(job["job_id"])
        time.sleep(.01)
        return result()
    outcome = parallel.coordinate(db, sid, index, RunnerConfig(), 4, fake,
                                  lambda: None, lambda: None, max_jobs=5)
    assert outcome["pause_reason"] == "session max-jobs reached"
    assert len(seen) == len(set(seen)) == 5
    assert db.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 5
    assert_drained(db)


@pytest.mark.parametrize("mode", ["fatal", "exception", "gate", "heartbeat"])
def test_failures_stop_admission_and_drain_other_results(store, mode):
    barrier = threading.Barrier(3)
    ready = threading.Event()
    count = 0
    lock = threading.Lock()

    def fake(job, config, *, root):
        nonlocal count
        with lock:
            count += 1
        barrier.wait(timeout=5)
        ready.set()
        if job["job_id"] == "j1" and mode == "exception":
            raise RuntimeError("fake worker failed")
        # Keep the other two in flight after j1 failure is observed.
        if job["job_id"] != "j1":
            time.sleep(.05)
        return result("ERROR" if job["job_id"] == "j1" and mode == "fatal" else "TIMEOUT")

    def check():
        if ready.is_set() and mode == "gate":
            raise ExpandedError("gate changed", 5)

    def heartbeat():
        if ready.is_set() and mode == "heartbeat":
            raise RuntimeError("heartbeat failed")

    outcome = run_fake(store, fake, check, heartbeat, workers=3)
    assert count == 3
    if mode == "fatal":
        assert outcome["fatal"] and outcome["failure"] is None
    else:
        assert outcome["failure"] is not None
    assert_drained(store[0])
    assert store[0].execute("SELECT COUNT(*) FROM results").fetchone()[0] == (2 if mode == "exception" else 3)


@pytest.mark.parametrize("case", ["state", "running", "session", "fatal", "rejected"])
def test_resume_safety_guards(store, case):
    db, sid, index = store
    db.execute("UPDATE experiment SET state='PAUSED'")
    db.execute("UPDATE sessions SET ended_utc='done'")
    parallel.check_resumable(db)
    if case == "state":
        db.execute("UPDATE experiment SET state='RUNNING'")
    elif case == "running":
        storage.claim(db, sid)
    elif case == "session":
        db.execute("UPDATE sessions SET ended_utc=NULL")
    elif case == "fatal":
        active = storage.claim(db, sid)
        storage.finish(db, active["attempt_id"], result("ERROR"), index["records"]["artificial"], index["dataset_dir"], .01)
        db.execute("UPDATE experiment SET state='PAUSED'")
    else:
        storage.event(db, "REJECTED_OBSERVATION")
    with pytest.raises(ExpandedError):
        parallel.check_resumable(db)


@pytest.mark.parametrize("key", ["script_sha256", "scientific_sha256", "workers", "accepted_by", "accepted", "timing_policy", "reporting_policy", "profile"])
def test_authorization_binds_exact_execution_subject(tmp_path, monkeypatch, key):
    monkeypatch.setattr(parallel, "ROOT", tmp_path)
    manifest = dict(experiment_id="test", scientific_sha256="b" * 64)
    path = tmp_path / "authorization.json"
    receipt = parallel.authorization_subject(manifest, 4)
    write(path, receipt)
    assert parallel.verify_authorization(manifest, 4, path, sha(path))["receipt"] == receipt
    receipt[key] = "tampered"
    write(path, receipt)
    with pytest.raises(ExpandedError, match="subject mismatch"):
        parallel.verify_authorization(manifest, 4, path, sha(path))


def test_bad_receipt_hash_and_missing_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(parallel, "ROOT", tmp_path)
    manifest = dict(experiment_id="test", scientific_sha256="b" * 64)
    path = tmp_path / "authorization.json"
    write(path, parallel.authorization_subject(manifest, 4))
    with pytest.raises(ExpandedError, match="SHA256 mismatch"):
        parallel.verify_authorization(manifest, 4, path, "0" * 64)
    with pytest.raises(ExpandedError, match="required"):
        parallel.verify_authorization(manifest, 4, None, None)


def test_plan_is_readonly_and_never_takes_writer_lock(tmp_path, monkeypatch):
    directory = tmp_path / "plan"
    directory.mkdir()
    (directory / "experiment.json").write_text("{}")
    calls = []

    class DB:
        def execute(self, query):
            return self
        def fetchone(self):
            return ["PAUSED"]
        def close(self):
            calls.append("close")

    def connect(path, *, readonly=False):
        assert readonly is True
        calls.append("readonly")
        return DB()

    def forbidden(*args, **kwargs):
        pytest.fail("plan attempted mutation")

    monkeypatch.setattr(storage, "connect", connect)
    monkeypatch.setattr(storage, "WriterLock", forbidden)
    monkeypatch.setattr(parallel.api, "_load", lambda *args: (dict(experiment_id="test", scientific_sha256="b" * 64), {}))
    output = parallel.run(directory)
    assert output["execute"] is False and output["timing_policy"] == "resource-contended"
    assert calls == ["readonly", "close"]


@pytest.fixture
def scoped(store):
    db, sid, index = store
    record = index["records"]["artificial"]
    for i in range(1, 13):
        iid = f"i{i}"
        copied = dict(record, instance_id=iid, content_sha256=f"{i:064x}")
        db.execute("INSERT INTO instances VALUES(?,?,?,?,?,?)", (iid, copied["content_sha256"], "b", 3, 9, json.dumps(copied)))
        index["records"][iid] = copied
        db.execute("UPDATE jobs SET instance_id=?,repetition=? WHERE job_id=?", (iid, (i-1)%3+1, f"j{i}"))
    return store


def test_selected_claim_only_rep1_and_retains_other_primary(scoped):
    db, sid, index = scoped
    for _ in range(2):
        active = storage.claim(db, sid)
        storage.finish(db, active["attempt_id"], result(), index["records"][active["instance_id"]], index["dataset_dir"], .01)
    before = [tuple(r) for r in db.execute("SELECT * FROM results ORDER BY attempt_id")]
    seen = []
    def fake(job, config, *, root):
        assert job["repetition"] == 1
        seen.append(job["job_id"])
        return result()
    outcome = parallel.coordinate(db, sid, index, RunnerConfig(), 4, fake,
                                  lambda: None, lambda: None, repetition=1)
    assert outcome == dict(pause_reason=None, fatal=False, failure=None)
    assert set(seen) == {"j4", "j7", "j10"}
    assert all(row in [tuple(r) for r in db.execute("SELECT * FROM results")] for row in before)
    assert db.execute("SELECT COUNT(*) FROM jobs WHERE repetition!=1 AND state='PENDING'").fetchone()[0] == 7
    assert parallel.scope_progress(db, 1) == dict(scope_state="COMPLETED", scope_planned_jobs=4, scope_completed_jobs=4, scope_remaining_jobs=0)
    assert_drained(db)


@pytest.mark.parametrize("key", ["selected_repetitions", "target_jobs", "effective_repetitions", "original_manifest_repetitions"])
def test_receipt_binds_selected_scope(tmp_path, monkeypatch, key):
    monkeypatch.setattr(parallel, "ROOT", tmp_path)
    manifest = dict(experiment_id="test", scientific_sha256="b" * 64)
    scope = dict(selected_repetitions=[1], target_jobs=4, effective_repetitions=1, original_manifest_repetitions=3)
    receipt = parallel.authorization_subject(manifest, 4, scope)
    path = tmp_path / "receipt.json"
    write(path, receipt)
    parallel.verify_authorization(manifest, 4, path, sha(path), scope)
    receipt[key] = 0
    write(path, receipt)
    with pytest.raises(ExpandedError, match="subject mismatch"):
        parallel.verify_authorization(manifest, 4, path, sha(path), scope)


@pytest.mark.parametrize("cap", [None, 2])
def test_selected_run_completion_is_paused_original_and_honest_scope(scoped, tmp_path, monkeypatch, cap):
    db, sid, index = scoped
    directory = Path(db.execute("PRAGMA database_list").fetchone()[2]).parent
    config = dict(cutoff_seconds=10.0, repetitions=3, schedule_seed=1,
                  startup_seconds=60.0, postprocessing_seconds=30.0, disk_reserve_bytes=0)
    manifest = dict(experiment_id="test", scientific_sha256="b"*64, config=config)
    write(directory / "experiment.json", manifest)
    db.execute("UPDATE sessions SET ended_utc='done'")
    db.execute("UPDATE experiment SET state='PAUSED'")
    monkeypatch.setattr(parallel, "ROOT", tmp_path)
    monkeypatch.setattr(parallel.api, "_load", lambda *args: (manifest, index))
    monkeypatch.setattr(parallel.api, "_gates", lambda *args: {})
    monkeypatch.setattr(parallel.api, "expanded_status", lambda *args: dict(state=db.execute("SELECT state FROM experiment").fetchone()[0], exit_code=4))
    import sudoku.runner
    def fake(job, runner_config, *, root):
        assert runner_config.repetitions == 1 and job["repetition"] == 1
        return result()
    monkeypatch.setattr(sudoku.runner, "run_job", fake)
    scope = parallel.selected_scope(db, manifest, 1)
    path = tmp_path / "authorization.json"
    write(path, parallel.authorization_subject(manifest, 4, scope))
    output = parallel.run(directory, execute=True, repetition=1, max_jobs=cap,
                          stop_starting_at="2099-01-01T00:00:00+00:00",
                          authorization=path, authorization_sha256=sha(path))
    assert output["state"] == "PAUSED"
    assert output["scope_planned_jobs"] == 4
    assert output["scope_completed_jobs"] == (cap or 4)
    assert output["exit_code"] == (4 if cap else 0)
    assert db.execute("SELECT COUNT(*) FROM jobs WHERE repetition!=1 AND state='PENDING'").fetchone()[0] == 8
    assert db.execute("SELECT COUNT(*) FROM sessions WHERE ended_utc IS NULL").fetchone()[0] == 0
    new_sid = db.execute("SELECT session_id FROM sessions WHERE session_id!=?", (sid,)).fetchone()[0]
    session = json.loads((directory / "session-manifests" / (new_sid+".json")).read_text())
    assert session["original_manifest_repetitions"] == 3 and session["selected_repetitions"] == [1]
    if cap is None:
        receipt = json.loads((directory / "scope-completions" / (new_sid+".json")).read_text())
        assert receipt["batches"] == [dict(batch_id="b", expected_jobs=4, completed_jobs=4)]
        assert receipt["effective_config"]["repetitions"] == 1
        assert receipt["original_config"]["repetitions"] == 3
        assert receipt["source_sessions"][0]["profile"] == parallel.PROFILE
        assert db.execute("SELECT halt_reason FROM experiment").fetchone()[0] == parallel.SCOPE_COMPLETE_REASON
    assert_drained(db)

"""Real 07 SQLite operations on tiny artificial DBs, no run_job or solvers."""
import importlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from tests.expanded.reference import canonical, content_hash, full


@pytest.fixture
def store(tmp_path):
    storage = importlib.import_module("sudoku.expanded_storage")
    directory, dataset = tmp_path / "experiment", tmp_path / "dataset"
    directory.mkdir(); dataset.mkdir()
    (dataset / "input.json").write_bytes(canonical(3, full(3)))
    record = {"instance_id": "artificial-iid", "content_sha256": content_hash(3, full(3)),
              "batch_id": "b001", "n": 3, "N": 9, "input_file": "input.json"}
    index = {"records": {record["instance_id"]: record},
             "batches": [{"batch_id": "b001", "ordinal": 1, "instance_ids": [record["instance_id"]]}]}
    jobs = [{"job_id": f"artificial-job-{i}", "instance_id": record["instance_id"],
             "configuration": "cpsat", "method": "cpsat", "encoding": "", "repetition": i,
             "batch_id": "b001", "ordinal": i} for i in (1, 2)]
    storage.initialize(directory, {"experiment_id": "artificial-storage-only", "artificial": True}, index, jobs)
    db = storage.connect(directory)
    sid = storage.new_session(db, "2099-01-01T00:00:00+00:00", "artificial QA, no solver")
    yield storage, db, sid, directory, dataset, record
    db.close()


def sat_result():
    return {"status": "SAT", "method": "cpsat", "encoding": None,
            "raw_status": "ARTIFICIAL_FIXTURE_NOT_SOLVER", "solution": full(3),
            "validation": {"valid": True}, "guard_phase": "complete",
            "build_seconds": 0.1, "solve_seconds": 0.2, "total_seconds": 0.3}


def test_real_schema_settings_claim_and_attempt_history(store):
    s, db, sid, _, _, _ = store
    assert db.execute("PRAGMA user_version").fetchone()[0] == 2
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert db.execute("PRAGMA synchronous").fetchone()[0] == 2
    assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    first = s.claim(db, sid)
    assert first["job_id"] == "artificial-job-1" and first["attempt_no"] == 1
    s.interrupt(db, first["attempt_id"], "injected interruption; no worker launched")
    second = s.claim(db, sid)
    assert second["job_id"] == first["job_id"] and second["attempt_no"] == 2
    assert second["attempt_id"] != first["attempt_id"]
    assert db.execute("SELECT state FROM attempts WHERE attempt_id=?", (first["attempt_id"],)).fetchone()[0] == "INTERRUPTED"
    s.integrity(db)


def test_completion_is_atomic_immutable_and_not_retried(store):
    s, db, sid, _, dataset, record = store
    claim = s.claim(db, sid)
    assert not s.finish(db, claim["attempt_id"], sat_result(), record, dataset, 0.5)
    for table in ("results", "solutions", "primary_attempt"):
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(f"DELETE FROM {table}")
    with pytest.raises(Exception) as caught:
        s.finish(db, claim["attempt_id"], sat_result(), record, dataset, 0.5)
    assert type(caught.value).__name__ == "ExpandedError"
    assert s.claim(db, sid)["job_id"] == "artificial-job-2"
    s.integrity(db)


def test_exception_before_commit_rolls_back_result_witness_primary(store):
    s, db, sid, _, dataset, record = store
    claim = s.claim(db, sid)
    def fail():
        raise RuntimeError("injected before completion COMMIT")
    with pytest.raises(RuntimeError, match="injected"):
        s.finish(db, claim["attempt_id"], sat_result(), record, dataset, 0.5, _before_commit=fail)
    for table in ("results", "solutions", "primary_attempt"):
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert db.execute("SELECT state FROM attempts").fetchone()[0] == "RUNNING"
    s.interrupt(db, claim["attempt_id"], "exclusive recovery fixture")
    assert s.claim(db, sid)["attempt_no"] == 2
    s.integrity(db)


def test_process_exit_before_commit_rolls_back_real_sqlite(store):
    s, db, sid, directory, dataset, record = store
    claim = s.claim(db, sid)
    code = """
import json, os, sys
sys.path.insert(0, sys.argv[1])
from sudoku import expanded_storage as s
db=s.connect(sys.argv[2])
s.finish(db,sys.argv[3],json.loads(sys.argv[6]),json.loads(sys.argv[5]),sys.argv[4],0.5,_before_commit=lambda:os._exit(77))
"""
    completed = subprocess.run([sys.executable, "-B", "-c", code,
        str(Path(__file__).resolve().parents[2] / "src"), str(directory), claim["attempt_id"],
        str(dataset), json.dumps(record), json.dumps(sat_result())], capture_output=True, timeout=10)
    assert completed.returncode == 77, completed.stderr.decode(errors="replace")
    for table in ("results", "solutions", "primary_attempt"):
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert db.execute("SELECT state FROM attempts").fetchone()[0] == "RUNNING"
    s.integrity(db)


def test_commit_survives_missing_checkpoint_telemetry(store, monkeypatch):
    s, db, sid, _, dataset, record = store
    claim = s.claim(db, sid)
    original = s.event
    def fail_checkpoint(db, kind, *args, **kwargs):
        if kind == "CHECKPOINT":
            raise RuntimeError("injected telemetry loss")
        return original(db, kind, *args, **kwargs)
    monkeypatch.setattr(s, "event", fail_checkpoint)
    with pytest.raises(RuntimeError, match="telemetry"):
        s.finish(db, claim["attempt_id"], sat_result(), record, dataset, 0.5)
    assert db.execute("SELECT COUNT(*) FROM primary_attempt").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM events WHERE type='CHECKPOINT'").fetchone()[0] == 0
    assert s.claim(db, sid)["job_id"] == "artificial-job-2"
    s.integrity(db)


@pytest.mark.parametrize("status", ("UNSAT", "ERROR", "INVALID_INPUT", "UNAVAILABLE", "LICENSE_LIMIT"))
def test_fatal_observation_is_retained_and_halt_atomic(store, status):
    s, db, sid, _, dataset, record = store
    claim = s.claim(db, sid)
    result = {"status": status, "method": "cpsat", "encoding": None,
              "guard_phase": "complete", "error": "ARTIFICIAL DIAGNOSTIC"}
    assert s.finish(db, claim["attempt_id"], result, record, dataset, 0.5)
    assert db.execute("SELECT state FROM experiment").fetchone()[0] == "HALTED"
    assert db.execute("SELECT status FROM results").fetchone()[0] == status
    assert db.execute("SELECT COUNT(*) FROM solutions").fetchone()[0] == 0
    s.integrity(db)


def test_terminal_timeout_not_interrupted_or_reclaimed(store):
    s, db, sid, _, dataset, record = store
    claim = s.claim(db, sid)
    assert not s.finish(db, claim["attempt_id"], {"status": "TIMEOUT", "method": "cpsat", "encoding": None,
                                               "guard_phase": "measurement"}, record, dataset, 1)
    with pytest.raises(Exception) as caught:
        s.interrupt(db, claim["attempt_id"], "must refuse")
    assert type(caught.value).__name__ == "ExpandedError"
    assert s.claim(db, sid)["job_id"] == "artificial-job-2"


def test_bad_sat_fails_real_checker_and_never_stores_solution(store):
    s, db, sid, _, dataset, record = store
    claim = s.claim(db, sid)
    result = sat_result()
    result["solution"] = [[1]*9 for _ in range(9)]
    assert s.finish(db, claim["attempt_id"], result, record, dataset, 0.5)
    assert db.execute("SELECT status FROM results").fetchone()[0] == "ERROR"
    assert db.execute("SELECT COUNT(*) FROM solutions").fetchone()[0] == 0


@pytest.mark.parametrize("method,encoding", (("highs", None), ("cpsat", "pairwise"), (None, None)))
def test_wrong_adapter_identity_refused_before_publication(store, method, encoding):
    s, db, sid, _, dataset, record = store
    claim = s.claim(db, sid)
    result = sat_result()
    result.update(method=method, encoding=encoding)
    with pytest.raises(s.ExpandedError, match="configuration mismatch"):
        s.finish(db, claim["attempt_id"], result, record, dataset, 0.5)
    for table in ("results", "solutions", "primary_attempt"):
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert db.execute("SELECT state FROM attempts").fetchone()[0] == "RUNNING"


def test_os_writer_lock_refuses_second_process_without_unlink(tmp_path):
    assert os.name == "nt", "This real OS-lock test requires Windows; no skip-as-pass"
    s = importlib.import_module("sudoku.expanded_storage")
    code = """
import sys
sys.path.insert(0,sys.argv[1])
from sudoku.expanded_storage import WriterLock
try:
    with WriterLock(sys.argv[2]): pass
except Exception as exc:
    sys.exit(getattr(exc,'exit_code',99))
sys.exit(0)
"""
    args = [sys.executable, "-B", "-c", code, str(Path(__file__).resolve().parents[2] / "src"), str(tmp_path)]
    lock_path = tmp_path / "writer.lock"
    with s.WriterLock(tmp_path):
        before_inode = lock_path.stat().st_ino
        completed = subprocess.run(args, capture_output=True, timeout=10)
        assert completed.returncode == 3, completed.stderr.decode(errors="replace")
        assert lock_path.stat().st_ino == before_inode
    assert lock_path.exists() and lock_path.read_bytes() == b"0"
    completed = subprocess.run(args, capture_output=True, timeout=10)
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")

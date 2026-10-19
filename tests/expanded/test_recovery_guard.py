"""Bounded diagnostic workers/recovery only, never research Sudoku solving."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path

import pytest

from sudoku import expanded_runner as api
from sudoku.runner import run_job
from tests.test_runner import job, config, diagnostic_worker
from tests.expanded.test_storage_transactions import store


@pytest.mark.parametrize("mode", ("child_hang", "orphan_success"))
def test_reused_windows_jobobject_cleans_diagnostic_descendants(tmp_path, mode):
    assert os.name == "nt", "Real Windows guard execution required; no skip-as-pass"
    pid_file = tmp_path / "child.pid"
    result = run_job(job(mode, pid_file=str(pid_file)), config(), _worker=diagnostic_worker)
    assert result["status"] == ("TIMEOUT" if mode == "child_hang" else "UNSAT")
    pid = int(pid_file.read_text())
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if handle:
        try:
            assert kernel.WaitForSingleObject(handle, 0) == 0
        finally:
            kernel.CloseHandle(handle)


@pytest.mark.parametrize("mode", ("build_hang", "slow_validation", "late_end"))
def test_guard_cutoff_and_postprocessing_are_separate(mode):
    result = run_job(job(mode), config(), _worker=diagnostic_worker)
    if mode == "slow_validation":
        assert result["status"] == "UNSAT" and result["total_seconds"] < 0.25
    else:
        assert result["status"] == "TIMEOUT" and result["guard_phase"] == "measurement"


@pytest.mark.parametrize("case", ("stale_owner", "live_owner", "wrong_orphan_evidence"))
def test_real_recover_state_machine_requires_owner_and_exact_evidence(store, tmp_path, monkeypatch, case):
    s, db, sid, _, _, _ = store
    attempt = s.claim(db, sid)
    session = db.execute("SELECT * FROM sessions WHERE session_id=?", (sid,)).fetchone()
    identity = {"attempt_id": attempt["attempt_id"], "session_id": sid,
                "pid": session["pid"], "creation_time": session["creation_time"]}
    evidence = tmp_path / "artificial-recovery-evidence.json"
    evidence.write_text(json.dumps({"artificial": True, "cleanup_verified": True,
        "orphans": [] if case == "wrong_orphan_evidence" else [identity]}), encoding="utf-8")
    # Only the private recovery function is injected; public/artificial run
    # gates remain intact. This is not root-accepted research cleanup evidence.
    relative = str(evidence.relative_to(api.ROOT)).replace("\\", "/")
    monkeypatch.setattr(api, "_gates", lambda manifest, recovery=False:
                        {"gates": {"recovery_cleanup": {"path": relative}}})
    monkeypatch.setattr(s, "process_identity", lambda pid:
                        session["creation_time"] if case == "live_owner" else "DIFFERENT_ARTIFICIAL_CREATION_TIME")
    if case == "stale_owner":
        api._recover(db, {"artificial": True})
        assert db.execute("SELECT state FROM attempts").fetchone()[0] == "INTERRUPTED"
        retry = s.claim(db, sid)
        assert retry["job_id"] == attempt["job_id"] and retry["attempt_no"] == 2
        assert db.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 0
    else:
        with pytest.raises(api.ExpandedError) as caught:
            api._recover(db, {"artificial": True})
        assert caught.value.exit_code == (3 if case == "live_owner" else 5)
        assert db.execute("SELECT state FROM attempts").fetchone()[0] == "RUNNING"

"""Runner-only diagnostics, never benchmark evidence."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from sudoku.runner import (ROOT, RunnerConfig, execute_run, make_schedule,
                           prepare_run, read_json, run_job, write_result)


def diagnostic_worker(gate, state, connection, request):
    gate.wait()
    mode = request["mode"]
    if mode == "startup_hang":
        time.sleep(30)
    if mode == "startup_error":
        connection.send(dict(status="ERROR", error="startup fixture"))
        return
    if mode == "crash":
        os._exit(7)
    start = state.start()
    if mode == "end_near_deadline":
        time.sleep(request["cutoff_seconds"] * 0.7)
    if mode in ("build_hang", "child_hang", "orphan_success"):
        if mode != "build_hang":
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            Path(request["pid_file"]).write_text(str(child.pid))
        if mode != "orphan_success":
            time.sleep(30)
    if mode == "late_end":
        state.end(start + request["cutoff_seconds"] + 0.001, None)
    else:
        elapsed = time.perf_counter() - start
        state.end(time.perf_counter(), dict(build_seconds=elapsed, solve_seconds=0.0, total_seconds=elapsed))
    if mode in ("slow_validation", "end_near_deadline"):
        time.sleep(request["cutoff_seconds"] + 0.15)
    if mode == "validation_hang":
        time.sleep(30)
    result = dict(status="ERROR" if mode == "validation_error" else "UNSAT",
                  raw_status="fixture", solution=None, validation=None, stats=None)
    if mode == "unchecked_sat":
        result["status"] = "SAT"
        result["solution"] = [[1]]
    connection.send(result)
    connection.close()


def job(mode="ok", **kwargs):
    return dict(job_id="diagnostic__sat__pairwise__r1", instance_id="diagnostic",
                method="sat", encoding="pairwise", repetition=1, scope="S80",
                file="unused.json", cutoff_seconds=0.25, mode=mode, **kwargs)


def config(**kwargs):
    return RunnerConfig(cutoff_seconds=0.25, startup_seconds=5,
                        postprocessing_seconds=kwargs.get("postprocessing_seconds", 2))


def test_frozen_schedule():
    jobs = make_schedule()
    assert len(jobs) == len({j["job_id"] for j in jobs}) == 906
    assert jobs == make_schedule()
    assert jobs != make_schedule(RunnerConfig(schedule_seed=12))
    assert sum(j["method"] == "sat" for j in jobs) == 720
    assert sum(j["scope"] == "B16" for j in jobs) == 96
    assert sum(j["scope"] == "C10" for j in jobs) == 90
    assert all(j["cutoff_seconds"] == 10 for j in jobs)


@pytest.mark.parametrize("kwargs", [{"cutoff_seconds": 0}, {"cutoff_seconds": float("nan")},
                                    {"repetitions": True}, {"schedule_seed": 1.2}])
def test_bad_config(kwargs):
    with pytest.raises(ValueError):
        RunnerConfig(**kwargs)


def test_prepare_without_execution(tmp_path):
    output = tmp_path / "kế hoạch runner"
    jobs = prepare_run(output)
    assert len(jobs) == 906
    assert not (output / "results.csv").exists()
    assert read_json(output / "run.json")["dataset_freeze_sha256"]
    with pytest.raises(FileExistsError):
        prepare_run(output)
    schedule = read_json(output / "schedule.json")
    schedule.reverse()
    (output / "schedule.json").write_text(json.dumps(schedule))
    with pytest.raises(ValueError, match="Schedule changed"):
        execute_run(output)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object guard")
@pytest.mark.parametrize("mode,status,phase", [
    ("ok", "UNSAT", "complete"), ("build_hang", "TIMEOUT", "measurement"),
    ("late_end", "TIMEOUT", "measurement"), ("slow_validation", "UNSAT", "complete"),
    ("end_near_deadline", "UNSAT", "complete"),
    ("startup_error", "ERROR", "startup"), ("crash", "ERROR", "startup"),
    ("validation_error", "ERROR", "complete"), ("unchecked_sat", "ERROR", "validation"),
])
def test_guard_modes(mode, status, phase):
    result = run_job(job(mode), config(), _worker=diagnostic_worker)
    assert result["status"] == status, result
    assert result["guard_phase"] == phase, result
    if mode == "build_hang":
        assert all(result[key] is None for key in ("build_seconds", "solve_seconds", "total_seconds"))
    if mode == "slow_validation":
        assert result["total_seconds"] < 0.25


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object guard")
@pytest.mark.parametrize("mode,phase", [("startup_hang", "startup"), ("validation_hang", "postprocessing")])
def test_separate_watchdogs(mode, phase):
    cfg = RunnerConfig(cutoff_seconds=0.25, startup_seconds=1.0, postprocessing_seconds=0.2)
    result = run_job(job(mode), cfg, _worker=diagnostic_worker)
    assert result["status"] == "ERROR", result
    assert result["guard_phase"] == phase, result


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object guard")
@pytest.mark.parametrize("mode", ["child_hang", "orphan_success"])
def test_descendant_terminated(tmp_path, mode):
    import ctypes
    from ctypes import wintypes
    pid_file = tmp_path / "child.pid"
    result = run_job(job(mode, pid_file=str(pid_file)), config(), _worker=diagnostic_worker)
    assert result["status"] == ("TIMEOUT" if mode == "child_hang" else "UNSAT"), result
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


def test_csv_nulls_and_duplicate(tmp_path):
    result = dict(status="TIMEOUT", raw_status=None, guard_phase="measurement")
    write_result(tmp_path, job(), result)
    with (tmp_path / "results.csv").open(newline="", encoding="utf-8") as stream:
        row = next(csv.DictReader(stream))
    assert row["total_seconds"] == row["validation"] == row["clauses"] == ""
    with pytest.raises(ValueError, match="Duplicate"):
        write_result(tmp_path, job(), result)


def test_checked_solution_artifact(tmp_path):
    result = dict(status="SAT", solution=[[1]], validation=dict(valid=True, message=None))
    row = write_result(tmp_path, job(), result)
    assert read_json(tmp_path / row["solution_artifact"])["job_id"] == job()["job_id"]
    assert row["validation"] == "pass"


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object guard")
def test_production_sat_worker_diagnostic(tmp_path):
    # One synthetic empty 4x4 fixture; no dataset pilot or research measurement.
    (tmp_path / "fixture.json").write_text(json.dumps(dict(n=2, grid=[[0]*4 for _ in range(4)])))
    request = job()
    request["file"] = "fixture.json"
    request["cutoff_seconds"] = 10.0
    result = run_job(request, RunnerConfig(), root=tmp_path)
    assert result["status"] == "SAT", result
    assert result["validation"]["valid"] is True
    assert result["total_seconds"] == pytest.approx(result["build_seconds"] + result["solve_seconds"])


def test_end_deadline_race_recheck(monkeypatch):
    # END is published between the first snapshot and the final deadline recheck;
    # result delivery is still pending. The on-time END must win.
    import sudoku.runner as runner
    from unittest.mock import Mock
    snapshots = iter([(10.0, None, None, None, None),
                      (10.0, 10.2, 0.1, 0.1, 0.2),
                      (10.0, 10.2, 0.1, 0.1, 0.2),
                      (10.0, 10.2, 0.1, 0.1, 0.2)])
    state = Mock()
    state.snapshot.side_effect = lambda: next(snapshots)
    connection = Mock()
    connection.poll.return_value = True
    connection.recv.return_value = dict(status="UNSAT")
    monkeypatch.setattr(runner.time, "perf_counter", lambda: 10.3)
    result = runner._monitor(Mock(), connection, state, job(), config(), 9.0)
    assert result["status"] == "UNSAT"
    assert result["total_seconds"] == 0.2


def test_no_end_at_deadline_never_uses_final_result(monkeypatch):
    import sudoku.runner as runner
    from unittest.mock import Mock
    state = Mock()
    state.snapshot.return_value = (10.0, None, None, None, None)
    connection = Mock()
    monkeypatch.setattr(runner.time, "perf_counter", lambda: 10.25)
    result = runner._monitor(Mock(), connection, state, job(), config(), 9.0)
    assert result["status"] == "TIMEOUT"
    connection.recv.assert_not_called()


def test_cutoff_mismatch_rejected():
    with pytest.raises(ValueError, match="cutoff differs"):
        run_job(job(), RunnerConfig())


def test_dependency_change_rejected(tmp_path, monkeypatch):
    import sudoku.runner as runner
    output = tmp_path / "dependency-plan"
    prepare_run(output)
    monkeypatch.setattr(runner, "package_versions", lambda: {"changed": "1.0"})
    with pytest.raises(ValueError, match="Dependencies changed"):
        execute_run(output)


def test_frozen_sat_unsat_disagreement_stops_preserves_row(tmp_path, monkeypatch):
    import sudoku.runner as runner
    output = tmp_path / "disagreement-plan"
    jobs = prepare_run(output)
    monkeypatch.setattr(runner, "run_job", lambda *a, **kw: dict(status="UNSAT", raw_status="fixture", guard_phase="complete"))
    with pytest.raises(RuntimeError, match="UNSAT contradicts"):
        execute_run(output, job_ids=[jobs[0]["job_id"], jobs[1]["job_id"]])
    with (output / "results.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1 and rows[0]["status"] == "UNSAT"
    assert read_json(output / "dataset-disagreement.json")["expected"] == "SAT"

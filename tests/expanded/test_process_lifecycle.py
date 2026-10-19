"""Deterministic lifecycle race and bounded Windows guard diagnostics only."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import multiprocessing.process as mp_process
import os
from pathlib import Path
import threading
import time

import pytest

PATH = Path(__file__).resolve().parents[2]/"scripts/parallel_process_lifecycle.py"
SPEC = importlib.util.spec_from_file_location("parallel_lifecycle_tests", PATH)
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def lifecycle_diagnostic_worker(gate, state, connection, request):
    """Artificial result protocol only; never import a solver or read inputs."""
    gate.wait()
    start = state.start()
    if request["mode"] == "timeout":
        time.sleep(30)
        return
    status = request["mode"]
    solution = [[1, 2, 3, 4], [3, 4, 1, 2], [2, 1, 4, 3], [4, 3, 2, 1]] if status == "SAT" else None
    end = time.perf_counter()
    state.end(end, dict(build_seconds=end-start, solve_seconds=0., total_seconds=end-start))
    connection.send(dict(status=status, raw_status="ARTIFICIAL_LIFECYCLE_NOT_SOLVER", solution=solution,
                         validation={"valid":True} if solution else None, stats=None))
    connection.close()


@pytest.fixture(autouse=True)
def restore_adapter():
    adapter.uninstall()
    yield
    adapter.uninstall()


@pytest.mark.parametrize("protected", [False, True])
def test_start_cleanup_saved_popen_races_close_deterministically(monkeypatch, protected):
    entered, release, close_started, closed = (threading.Event() for _ in range(4))
    failures = []

    class Popen:
        sentinel = 123
        returncode = None
        handle_closed = False
        def poll(self):
            if threading.current_thread().name == "starter":
                # Model Windows Popen.wait after its returncode=None check
                # and before WaitForSingleObject uses the saved handle.
                entered.set()
                assert release.wait(5)
                if self.handle_closed:
                    raise OSError(6, "invalid handle: deterministic saved-popen race")
            self.returncode = 0
            return 0
        def close(self):
            self.handle_closed = True
            closed.set()

    old = mp_process.BaseProcess()
    old._popen = Popen()
    old._sentinel = 123
    new = mp_process.BaseProcess()
    new._Popen = lambda _: Popen()
    monkeypatch.setattr(mp_process, "_children", {old})
    if protected:
        adapter.install()
    def start():
        try:
            new.start()
        except BaseException as exc:
            failures.append(exc)
    def close():
        close_started.set()
        old.close()
    starter = threading.Thread(target=start, name="starter")
    closer = threading.Thread(target=close, name="closer")
    starter.start()
    assert entered.wait(5)
    closer.start()
    assert close_started.wait(5)
    if protected:
        assert not closed.wait(.05), "close must wait while cleanup holds lifecycle lock"
    else:
        assert closed.wait(5)
    release.set()
    starter.join(5)
    closer.join(5)
    assert not starter.is_alive() and not closer.is_alive()
    assert closed.is_set()
    if protected:
        assert failures == []
        new.close()
    else:
        assert len(failures) == 1 and isinstance(failures[0], OSError) and failures[0].errno == 6


def test_install_is_idempotent_and_uninstall_restores_methods():
    original = mp_process.BaseProcess.start
    first = adapter.install()
    wrapped = mp_process.BaseProcess.start
    assert adapter.install() == first
    assert mp_process.BaseProcess.start is wrapped and wrapped is not original
    assert first["pid"] == os.getpid()
    adapter.uninstall()
    assert mp_process.BaseProcess.start is original


def test_blocking_join_releases_lock_so_other_watchdogs_can_poll(monkeypatch):
    polled, release = threading.Event(), threading.Event()
    class Popen:
        returncode = None
        def wait(self, timeout):
            assert timeout == 0
            polled.set()
            if release.is_set():
                self.returncode = 0
            return self.returncode
        def poll(self):
            return self.returncode
    joining = mp_process.BaseProcess()
    joining._popen = Popen()
    unrelated = mp_process.BaseProcess()
    monkeypatch.setattr(mp_process, "_children", {joining})
    adapter.install()
    thread = threading.Thread(target=joining.join)
    thread.start()
    assert polled.wait(5)
    # Would deadlock if the blocking join held the shared lifecycle lock.
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(unrelated.is_alive).result(timeout=1) is False
    release.set()
    thread.join(5)
    assert not thread.is_alive()


def test_join_timeout_preserves_running_state(monkeypatch):
    class Popen:
        returncode = None
        def wait(self, timeout):
            assert timeout == 0
            return None
        def poll(self):
            return None
    process = mp_process.BaseProcess()
    process._popen = Popen()
    monkeypatch.setattr(mp_process, "_children", {process})
    adapter.install()
    start = time.monotonic()
    process.join(.03)
    assert time.monotonic()-start < .5
    assert process.is_alive()


@pytest.mark.skipif(os.name != "nt", reason="Real Windows Job Object diagnostic")
def test_real_windows_32_way_guarded_workers_repeated():
    from sudoku.runner import run_job, RunnerConfig
    from tests.test_runner import job
    from sudoku.model import Puzzle
    from sudoku.validation import check_solution
    adapter.install()
    config = RunnerConfig(cutoff_seconds=.25, startup_seconds=60, postprocessing_seconds=5)
    def invoke(number):
        # Explicit diagnostic worker, unused input path; no solver imports.
        mode = ("SAT", "UNSAT", "timeout")[number%3]
        return run_job(job(mode), config, _worker=lifecycle_diagnostic_worker)
    with ThreadPoolExecutor(max_workers=32) as pool:
        results = list(pool.map(invoke, range(96)))
    assert len(results) == 96
    for number, result in enumerate(results):
        expected = ("SAT", "UNSAT", "TIMEOUT")[number%3]
        assert result["status"] == expected, result
        assert result["guard_phase"] == ("measurement" if expected == "TIMEOUT" else "complete"), result
        if expected == "SAT":
            assert check_solution(Puzzle(2, [[0]*4 for _ in range(4)]), result["solution"]).valid
    assert not mp_process.active_children(), "Diagnostic children must all be joined and closed"

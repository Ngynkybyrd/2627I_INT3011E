"""Production SAT adapter checks; existing independent logic tests stay intact."""

from threading import Event
from types import SimpleNamespace

import pytest

from sudoku import sat
from sudoku.contracts import SolveStatus
from sudoku.model import Puzzle, variable_id
from sudoku.validation import check_solution


FULL = ((1, 2, 3, 4), (3, 4, 1, 2), (2, 1, 4, 3), (4, 3, 2, 1))
BLANK = Puzzle(2, ((0, 0, 0, 0),) * 4)


def model_for(grid=FULL):
    return [variable_id(2, r, c, v) for r, row in enumerate(grid) for c, v in enumerate(row)]


@pytest.fixture
def controlled(monkeypatch):
    """A deterministic clock/native boundary; real parser/CNF/decoder/checker."""
    state = SimpleNamespace(
        now=100.0, load_seconds=0.4, solve_seconds=0.5, raw=True,
        model=model_for(), instances=[], timers=[], events=[],
        load_error=None, solve_error=None, delete_error=None,
        interrupt_during_solve=False,
    )

    class Native:
        def __init__(self):
            state.instances.append(self)
            self.deleted = 0
            self.interrupted = 0
            self.solve_calls = 0

        def append_formula(self, clauses):
            assert clauses
            state.now += state.load_seconds
            if state.load_error:
                raise state.load_error

        def solve_limited(self, *, expect_interrupt):
            assert expect_interrupt is True
            self.solve_calls += 1
            state.now += state.solve_seconds
            if state.interrupt_during_solve:
                state.timers[-1].callback()
            if state.solve_error:
                raise state.solve_error
            return state.raw

        def get_model(self):
            return state.model

        def interrupt(self):
            self.interrupted += 1
            state.events.append("interrupt")

        def delete(self):
            self.deleted += 1
            state.events.append("delete")
            if state.delete_error:
                raise state.delete_error

    class Timer:
        def __init__(self, interval, callback):
            self.interval = interval
            self.callback = callback
            self.cancelled = False
            self.joined = False
            state.timers.append(self)

        def start(self):
            state.events.append("timer_start")

        def cancel(self):
            self.cancelled = True
            state.events.append("timer_cancel")

        def join(self):
            self.joined = True
            state.events.append("timer_join")

    monkeypatch.setattr(sat, "prepare_backend", lambda: None)
    monkeypatch.setattr(sat, "Glucose3", Native)
    monkeypatch.setattr(sat, "Timer", Timer)
    monkeypatch.setattr(sat, "perf_counter", lambda: state.now)
    return state


@pytest.mark.parametrize("n", [2, 3])
@pytest.mark.parametrize("encoding", sat.ENCODINGS)
def test_real_sat_always_passes_independent_checker(n, encoding):
    N = n * n
    full = tuple(tuple((r * n + r // n + c) % N + 1 for c in range(N)) for r in range(N))
    grid = tuple(tuple(0 if (r * N + c) % 3 == 0 else full[r][c] for c in range(N))
                 for r in range(N))
    puzzle = Puzzle(n, grid)
    result = sat.solve_sat(puzzle, encoding)
    assert result.status is SolveStatus.SAT, result.error
    assert result.raw_status == "True"
    assert result.validation.valid and check_solution(puzzle, result.solution).valid
    assert result.stats.exo_groups == 4 * N * N
    assert result.total_seconds == result.build_seconds + result.solve_seconds


@pytest.mark.parametrize("encoding", sat.ENCODINGS)
@pytest.mark.parametrize("grid", [
    ((1, 1, 0, 0),) + ((0, 0, 0, 0),) * 3,
    ((1, 2, 0, 0), (0, 0, 3, 0), (0, 0, 0, 0), (0, 0, 0, 0)),
])
def test_real_unsat_including_nontrivial_clues(encoding, grid):
    result = sat.solve_sat(Puzzle(2, grid), encoding)
    assert result.status is SolveStatus.UNSAT
    assert result.raw_status == "False"
    assert result.solution is None and result.validation is None


@pytest.mark.parametrize("cutoff", [0, -1, True, False, float("nan"), float("inf"),
                                    -float("inf"), "10", None, [], 10**400])
def test_invalid_cutoff_is_api_error(cutoff):
    with pytest.raises(ValueError):
        sat.solve_sat(BLANK, cutoff_seconds=cutoff)


@pytest.mark.parametrize("deadline", [True, False, float("nan"), float("inf"), "10", []])
def test_invalid_deadline_is_api_error(deadline):
    with pytest.raises(ValueError):
        sat.solve_sat(BLANK, deadline=deadline)


@pytest.mark.parametrize("encoding", ["bad", "sequential", "", None, []])
def test_invalid_encoding_is_api_error(encoding):
    with pytest.raises(ValueError):
        sat.solve_sat(BLANK, encoding)


def test_puzzle_must_have_passed_parser():
    with pytest.raises(TypeError):
        sat.solve_sat({"n": 2, "grid": [[0] * 4] * 4})


def test_missing_dependency_is_unavailable_and_not_measured(monkeypatch):
    def unavailable():
        raise ModuleNotFoundError("pysat unavailable")

    def must_not_measure():
        raise AssertionError("dependency import must precede measurement")

    monkeypatch.setattr(sat, "prepare_backend", unavailable)
    monkeypatch.setattr(sat, "perf_counter", must_not_measure)
    result = sat.solve_sat(BLANK)
    assert result.status is SolveStatus.UNAVAILABLE
    assert result.build_seconds is result.solve_seconds is result.total_seconds is None
    assert "ModuleNotFoundError" in result.error


def test_prepare_backend_is_idempotent(monkeypatch):
    sat.prepare_backend()

    def unexpected_import(name):
        raise AssertionError(f"already prepared backend re-imported {name}")

    monkeypatch.setattr(sat, "import_module", unexpected_import)
    sat.prepare_backend()
    sat.prepare_backend()


def test_build_load_solve_timing_and_remaining_budget(controlled):
    result = sat.solve_sat(BLANK, cutoff_seconds=1)
    assert result.status is SolveStatus.SAT
    assert result.build_seconds == pytest.approx(0.4)
    assert result.solve_seconds == pytest.approx(0.5)
    assert result.total_seconds == pytest.approx(0.9)
    assert controlled.timers[0].interval == pytest.approx(0.6)
    assert controlled.events.index("timer_join") < controlled.events.index("delete")


def test_external_deadline_can_only_shorten_budget(controlled):
    result = sat.solve_sat(BLANK, cutoff_seconds=1, deadline=1000)
    assert result.status is SolveStatus.SAT
    assert controlled.timers[0].interval == pytest.approx(0.6)


def test_expired_deadline_skips_build(controlled, monkeypatch):
    def must_not_build(*args):
        raise AssertionError("expired deadline must skip CNF construction")

    monkeypatch.setattr(sat, "build_cnf", must_not_build)
    result = sat.solve_sat(BLANK, deadline=99)
    assert result.status is SolveStatus.TIMEOUT
    assert not controlled.instances and not controlled.timers
    assert result.raw_status is None and result.stats is None
    assert result.solve_seconds == 0


def test_deadline_consumed_in_cnf_skips_native_allocation(controlled, monkeypatch):
    original_build = sat.build_cnf

    def slow_build(*args):
        cnf = original_build(*args)
        controlled.now += 2
        return cnf

    monkeypatch.setattr(sat, "build_cnf", slow_build)
    result = sat.solve_sat(BLANK, cutoff_seconds=1)
    assert result.status is SolveStatus.TIMEOUT
    assert result.build_seconds == 2 and result.solve_seconds == 0
    assert result.stats is not None and not controlled.instances


def test_deadline_consumed_during_loading_cleans_up(controlled):
    result = sat.solve_sat(BLANK, deadline=100.2)
    assert result.status is SolveStatus.TIMEOUT
    assert result.build_seconds == pytest.approx(0.4)
    assert result.solve_seconds == 0
    assert controlled.instances[0].solve_calls == 0
    assert controlled.instances[0].deleted == 1


@pytest.mark.parametrize("raw", [True, False, None])
def test_late_native_result_is_timeout_even_if_sat_or_unsat(controlled, raw):
    controlled.raw = raw
    controlled.solve_seconds = 2
    result = sat.solve_sat(BLANK, cutoff_seconds=1)
    assert result.status is SolveStatus.TIMEOUT
    assert result.raw_status == str(raw) and result.solution is None
    assert result.total_seconds == pytest.approx(2.4)
    assert controlled.instances[0].deleted == 1


def test_unknown_without_time_limit_evidence_is_error(controlled):
    controlled.raw = None
    result = sat.solve_sat(BLANK)
    assert result.status is SolveStatus.ERROR
    assert result.raw_status == "None" and "UNKNOWN" in result.error


def test_unknown_with_recorded_interrupt_is_timeout(controlled):
    controlled.raw = None
    controlled.interrupt_during_solve = True
    result = sat.solve_sat(BLANK)
    assert result.status is SolveStatus.TIMEOUT
    assert controlled.instances[0].interrupted == 1


def test_real_timer_interrupt_and_cleanup(monkeypatch):
    instances = []

    class WaitingNative:
        def __init__(self):
            self.interrupted = Event()
            self.deleted = False
            instances.append(self)

        def append_formula(self, clauses):
            pass

        def solve_limited(self, *, expect_interrupt):
            assert expect_interrupt
            assert self.interrupted.wait(2), "remaining-budget timer did not interrupt"
            return None

        def interrupt(self):
            assert not self.deleted
            self.interrupted.set()

        def delete(self):
            self.deleted = True

    monkeypatch.setattr(sat, "prepare_backend", lambda: None)
    monkeypatch.setattr(sat, "Glucose3", WaitingNative)
    result = sat.solve_sat(BLANK, cutoff_seconds=0.05)
    assert result.status is SolveStatus.TIMEOUT
    assert instances[0].interrupted.is_set() and instances[0].deleted


def test_real_glucose_native_interrupt_on_diagnostic_hard_cnf(monkeypatch):
    # A hard pigeonhole formula isolates the REAL native interrupt boundary.
    # This injected fixture is not Sudoku data and is never used in benchmarks.
    from pysat.examples.genhard import PHP

    sat.prepare_backend()
    cnf = sat.build_cnf(BLANK)
    cnf.clauses = PHP(nof_holes=14).clauses
    monkeypatch.setattr(sat, "build_cnf", lambda *args: cnf)
    result = sat.solve_sat(BLANK, cutoff_seconds=0.03)
    assert result.status is SolveStatus.TIMEOUT
    assert result.raw_status == "None"
    assert result.solve_seconds > 0


def test_callback_after_native_return_does_not_reclassify_result(controlled, monkeypatch):
    class DelayedCallbackTimer:
        def __init__(self, interval, callback):
            self.callback = callback

        def start(self):
            pass

        def cancel(self):
            # Native solve finished at 100.9, before the deadline at 101.
            # A scheduler delay lets the callback fire only during cancellation.
            controlled.now += 1
            self.callback()

        def join(self):
            pass

    monkeypatch.setattr(sat, "Timer", DelayedCallbackTimer)
    result = sat.solve_sat(BLANK, cutoff_seconds=1)
    assert result.status is SolveStatus.SAT
    assert result.total_seconds == pytest.approx(0.9)
    assert controlled.instances[0].interrupted == 1
    assert controlled.instances[0].deleted == 1


def test_failed_timer_join_never_deletes_native_while_callback_may_run(controlled, monkeypatch):
    class UnjoinedTimer:
        def __init__(self, interval, callback):
            pass

        def start(self):
            pass

        def cancel(self):
            pass

        def join(self):
            raise RuntimeError("cannot join interrupt thread")

    monkeypatch.setattr(sat, "Timer", UnjoinedTimer)
    result = sat.solve_sat(BLANK)
    assert result.status is SolveStatus.ERROR
    assert "worker cleanup is required" in result.error
    assert controlled.instances[0].deleted == 0


@pytest.mark.parametrize("model,reason", [
    (model_for()[:-1], "no value selected"),
    (model_for() + [variable_id(2, 0, 0, 2)], "multiple values selected"),
    (None, "model must be an iterable"),
])
def test_bad_native_model_is_decode_error(controlled, model, reason):
    controlled.model = model
    result = sat.solve_sat(BLANK)
    assert result.status is SolveStatus.ERROR
    assert reason in result.error
    assert result.validation.valid is False and result.solution is None
    assert controlled.instances[0].deleted == 1


def test_decodable_invalid_sudoku_is_checker_error(controlled):
    controlled.model = model_for(((1, 1, 1, 1),) * 4)
    result = sat.solve_sat(BLANK)
    assert result.status is SolveStatus.ERROR
    assert result.validation.valid is False and "row" in result.error
    assert result.solution is None


def test_changed_clue_is_checker_error(controlled):
    puzzle = Puzzle(2, ((2, 0, 0, 0),) + ((0, 0, 0, 0),) * 3)
    result = sat.solve_sat(puzzle)
    assert result.status is SolveStatus.ERROR
    assert result.validation.valid is False and "clue" in result.error


def test_checker_exception_is_error(controlled, monkeypatch):
    def checker_crash(*args):
        raise RuntimeError("checker failure")

    monkeypatch.setattr(sat, "check_solution", checker_crash)
    result = sat.solve_sat(BLANK)
    assert result.status is SolveStatus.ERROR
    assert result.validation.valid is False and "checker failure" in result.error


def test_validation_time_is_excluded_and_timer_stopped_first(controlled, monkeypatch):
    actual_check = sat.check_solution

    def slow_checker(*args):
        assert controlled.timers[0].cancelled and controlled.timers[0].joined
        controlled.now += 100
        return actual_check(*args)

    monkeypatch.setattr(sat, "check_solution", slow_checker)
    result = sat.solve_sat(BLANK, cutoff_seconds=1)
    assert result.status is SolveStatus.SAT
    assert result.total_seconds == pytest.approx(0.9)


@pytest.mark.parametrize("phase", ["load", "solve"])
def test_native_errors_are_not_unsat_and_cleanup_runs(controlled, phase):
    setattr(controlled, f"{phase}_error", RuntimeError(f"{phase} failure"))
    result = sat.solve_sat(BLANK)
    assert result.status is SolveStatus.ERROR
    assert f"{phase} failure" in result.error
    assert controlled.instances[0].deleted == 1
    assert result.total_seconds == result.build_seconds + result.solve_seconds


def test_cleanup_failure_is_reported(controlled):
    controlled.delete_error = RuntimeError("delete failure")
    result = sat.solve_sat(BLANK)
    assert result.status is SolveStatus.ERROR
    assert result.solution is None and "delete failure" in result.error


def test_fresh_native_solver_and_timer_for_each_call(controlled):
    for _ in range(3):
        result = sat.solve_sat(BLANK)
        assert result.status is SolveStatus.SAT
    assert len(controlled.instances) == len(controlled.timers) == 3
    assert len({id(native) for native in controlled.instances}) == 3
    assert all(native.deleted == 1 and native.solve_calls == 1 for native in controlled.instances)
    assert all(timer.cancelled and timer.joined for timer in controlled.timers)


@pytest.mark.parametrize("hook", [False, 1, "callback"])
def test_invalid_measurement_hook_is_api_error(hook):
    with pytest.raises(ValueError, match="on_measurement_end"):
        sat.solve_sat(BLANK, on_measurement_end=hook)


@pytest.mark.parametrize("raw", [True, False, None])
def test_measurement_hook_once_before_timer_join_and_cleanup(controlled, raw):
    controlled.raw = raw
    calls = []

    def ended(timestamp, timings):
        assert "timer_join" not in controlled.events
        assert "delete" not in controlled.events
        calls.append((timestamp, dict(timings)))

    result = sat.solve_sat(BLANK, on_measurement_end=ended)
    assert len(calls) == 1
    timestamp, timings = calls[0]
    assert timestamp == pytest.approx(100.9)
    assert timings == {
        "build_seconds": result.build_seconds,
        "solve_seconds": result.solve_seconds,
        "total_seconds": result.total_seconds,
    }
    assert controlled.instances[0].deleted == 1


def test_hook_precedes_slow_callback_decode_checker_and_keeps_measurements(controlled, monkeypatch):
    actual_decode = sat.decode_model
    actual_checker = sat.check_solution
    calls = []

    def ended(timestamp, timings):
        assert not controlled.timers[0].joined
        controlled.events.append("measurement_end")
        calls.append((timestamp, dict(timings)))
        timings["total_seconds"] = 999  # A caller cannot mutate result measurements.
        controlled.now += 100

    def decode(*args):
        assert "measurement_end" in controlled.events
        assert controlled.timers[0].joined
        controlled.events.append("decode")
        return actual_decode(*args)

    def checker(*args):
        assert "decode" in controlled.events
        controlled.events.append("checker")
        controlled.now += 100
        return actual_checker(*args)

    monkeypatch.setattr(sat, "decode_model", decode)
    monkeypatch.setattr(sat, "check_solution", checker)
    result = sat.solve_sat(BLANK, cutoff_seconds=1, on_measurement_end=ended)
    assert result.status is SolveStatus.SAT
    assert result.total_seconds == pytest.approx(0.9)
    assert len(calls) == 1 and calls[0][0] == pytest.approx(100.9)
    assert controlled.events.index("measurement_end") < controlled.events.index("timer_join")
    assert controlled.events.index("checker") < controlled.events.index("delete")


@pytest.mark.parametrize("failure", ["expired", "cnf_error", "cnf_timeout", "load_error",
                                    "load_timeout", "native_error"])
def test_measurement_hook_closes_failed_and_expired_work_once(controlled, monkeypatch, failure):
    original_build = sat.build_cnf
    calls = []

    def build(*args):
        if failure == "cnf_error":
            controlled.now += 0.2
            raise RuntimeError("CNF build failure")
        if failure == "cnf_timeout":
            controlled.now += 2
        return original_build(*args)

    monkeypatch.setattr(sat, "build_cnf", build)
    if failure == "load_error":
        controlled.load_error = RuntimeError("load failure")
    elif failure == "native_error":
        controlled.solve_error = RuntimeError("native failure")

    def ended(timestamp, timings):
        assert "timer_join" not in controlled.events
        assert "delete" not in controlled.events
        calls.append((timestamp, dict(timings)))

    deadline = 99 if failure == "expired" else 100.2 if failure == "load_timeout" else None
    result = sat.solve_sat(BLANK, cutoff_seconds=1, deadline=deadline, on_measurement_end=ended)
    assert len(calls) == 1
    timestamp, timings = calls[0]
    assert timestamp == pytest.approx(100 + result.total_seconds)
    assert timings["total_seconds"] == result.total_seconds
    expected = SolveStatus.TIMEOUT if failure in {"expired", "cnf_timeout", "load_timeout"} else SolveStatus.ERROR
    assert result.status is expected
    assert all(native.deleted == 1 for native in controlled.instances)


@pytest.mark.parametrize("failure", ["sat", "expired", "build_error", "load_error", "native_error"])
def test_callback_failure_is_error_not_retried_and_still_cleans_up(controlled, monkeypatch, failure):
    calls = []
    if failure == "build_error":
        def broken_build(*args):
            raise RuntimeError("original build failure")
        monkeypatch.setattr(sat, "build_cnf", broken_build)
    elif failure == "load_error":
        controlled.load_error = RuntimeError("original load failure")
    elif failure == "native_error":
        controlled.solve_error = RuntimeError("original solve failure")

    def failed_hook(timestamp, timings):
        calls.append((timestamp, dict(timings)))
        controlled.now += 100
        raise RuntimeError("publish failure")

    result = sat.solve_sat(BLANK, deadline=99 if failure == "expired" else None,
                           on_measurement_end=failed_hook)
    assert result.status is SolveStatus.ERROR and result.solution is None
    assert "measurement-end callback failed" in result.error and "publish failure" in result.error
    assert len(calls) == 1
    assert calls[0][1]["total_seconds"] == result.total_seconds
    assert result.total_seconds < 1  # Failed callback work is never solve time.
    assert all(native.deleted == 1 for native in controlled.instances)
    assert all(timer.cancelled and timer.joined for timer in controlled.timers)


@pytest.mark.parametrize("unsat", [False, True])
def test_real_backend_measurement_hook(unsat):
    puzzle = Puzzle(2, ((1, 1, 0, 0),) + ((0, 0, 0, 0),) * 3) if unsat else BLANK
    calls = []
    result = sat.solve_sat(puzzle, on_measurement_end=lambda end, times: calls.append((end, dict(times))))
    assert result.status is (SolveStatus.UNSAT if unsat else SolveStatus.SAT)
    assert len(calls) == 1
    assert calls[0][1]["total_seconds"] == result.total_seconds


def test_callback_failure_is_preserved_if_timer_cleanup_also_fails(controlled):
    calls = []

    def failed_hook(end, timings):
        calls.append(end)

        def failed_join():
            raise RuntimeError("join failure")

        controlled.timers[0].join = failed_join
        raise RuntimeError("publish failure")

    result = sat.solve_sat(BLANK, on_measurement_end=failed_hook)
    assert result.status is SolveStatus.ERROR
    assert "publish failure" in result.error and "join failure" in result.error
    assert len(calls) == 1
    assert controlled.instances[0].deleted == 0

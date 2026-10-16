"""Spawn-safe worker and small synchronized measurement protocol."""
from __future__ import annotations

import math
import time

TIMINGS = ("build_seconds", "solve_seconds", "total_seconds")


class Measurement:
    def __init__(self, context):
        self.lock = context.Lock()
        self.values = context.RawArray("d", [math.nan] * 5)
        self.started = context.Event()
        self.ended = context.Event()

    def start(self):
        with self.lock:
            self.values[0] = time.perf_counter()
            self.started.set()
            return self.values[0]

    def end(self, timestamp, timings):
        with self.lock:
            if not math.isnan(self.values[1]):
                raise RuntimeError("Duplicate measurement END")
            if not math.isfinite(timestamp):
                raise ValueError("Nonfinite END")
            self.values[1] = timestamp
            for index, key in enumerate(TIMINGS, 2):
                value = (timings or {}).get(key)
                self.values[index] = math.nan if value is None else value
            self.ended.set()

    def snapshot(self):
        # A killed publisher cannot leave the parent blocked indefinitely.
        if not self.lock.acquire(timeout=0.05):
            raise RuntimeError("Measurement publisher lock stalled")
        try:
            return tuple(None if math.isnan(x) else x for x in self.values)
        finally:
            self.lock.release()


def worker(gate, state, connection, request):
    """Wait for tree containment, preimport/read, START, solve, checked result."""
    gate.wait()
    from sudoku.contracts import SolveResult, SolveStatus, InvalidInputError
    method, encoding = request["method"], request.get("encoding")
    try:
        from sudoku.model import load_puzzle
        puzzle = load_puzzle(request["input_path"])
        if method == "sat":
            from sudoku.sat import prepare_backend, solve_sat
            prepare_backend()
        else:
            from sudoku.baselines import prepare_backend, solve_baseline
            prepare_backend(method)
        start = state.start()
        kwargs = dict(cutoff_seconds=request["cutoff_seconds"],
                      deadline=start + request["cutoff_seconds"],
                      on_measurement_end=state.end)
        result = (solve_sat(puzzle, encoding, **kwargs) if method == "sat"
                  else solve_baseline(puzzle, method, **kwargs))
    except InvalidInputError as exc:
        result = SolveResult(SolveStatus.INVALID_INPUT, method, encoding, error=str(exc)[:500])
    except (ImportError, OSError) as exc:
        result = SolveResult(SolveStatus.UNAVAILABLE if not state.started.is_set() else SolveStatus.ERROR,
                             method, encoding, error=f"{type(exc).__name__}: {exc}"[:500])
    except Exception as exc:
        result = SolveResult(SolveStatus.ERROR, method, encoding,
                             error=f"{type(exc).__name__}: {exc}"[:500])
    try:
        connection.send(result.to_dict())
    finally:
        connection.close()

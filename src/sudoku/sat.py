"""Generalized Sudoku CNF construction and a checked Glucose3 adapter."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from itertools import combinations
from math import isfinite
from threading import Timer
from time import perf_counter
from typing import Callable, Literal, Mapping, Sequence

from sudoku.contracts import CNFStats, SolveResult, SolveStatus, ValidationResult
from sudoku.decoding import decode_model
from sudoku.model import Puzzle, iter_clues, iter_exo_groups, variable_id
from sudoku.validation import check_solution

Encoding = Literal["pairwise", "seqcounter", "bitwise"]
ENCODINGS: tuple[Encoding, ...] = ("pairwise", "seqcounter", "bitwise")

# Optional dependencies are loaded before solve_sat starts its measurement.
# Standalone CNF APIs retain their existing signatures and lazy-load as needed.
CardEnc = None
EncType = None
Glucose3 = None


def _load_cardinality() -> None:
    global CardEnc, EncType
    if CardEnc is None or EncType is None:
        cardinality = import_module("pysat.card")
        CardEnc, EncType = cardinality.CardEnc, cardinality.EncType


def prepare_backend() -> None:
    """Load PySAT/Glucose3 before measured work; repeated calls are harmless.

    Missing imports/native libraries raise ImportError/OSError here. solve_sat
    maps these to UNAVAILABLE without claiming a measured solve attempt.
    """
    global Glucose3
    _load_cardinality()
    if Glucose3 is None:
        Glucose3 = import_module("pysat.solvers").Glucose3


@dataclass(slots=True)
class EncodedCNF:
    encoding: Encoding
    clauses: list[list[int]]
    stats: CNFStats


def encode_amo(
    literals: Sequence[int], encoding: Encoding, *, top_id: int
) -> tuple[list[list[int]], int]:
    """Encode AMO over distinct positive inputs; return clauses and new top ID.

    top_id reserves ALL previously allocated IDs, including primary variables
    not present in this group. Auxiliaries are allocated strictly above it.
    """
    if encoding not in ENCODINGS:
        raise ValueError(f"unknown AMO encoding: {encoding!r}; choose {ENCODINGS}")
    inputs = list(literals)
    if any(type(lit) is not int or lit <= 0 for lit in inputs):
        raise ValueError("AMO inputs must be positive integer variable IDs")
    if len(set(inputs)) != len(inputs):
        raise ValueError("AMO inputs must be distinct")
    if type(top_id) is not int or top_id < max(inputs, default=0):
        raise ValueError("top_id must reserve every input and previously allocated ID")
    if len(inputs) <= 1:
        return [], top_id
    if encoding == "pairwise":
        return [[-left, -right] for left, right in combinations(inputs, 2)], top_id
    _load_cardinality()
    implementation = {
        "seqcounter": EncType.seqcounter,
        "bitwise": EncType.bitwise,
    }[encoding]
    encoded = CardEnc.atmost(inputs, bound=1, top_id=top_id, encoding=implementation)
    return encoded.clauses, max(top_id, encoded.nv)


def build_cnf(puzzle: Puzzle, encoding: Encoding = "pairwise") -> EncodedCNF:
    """Build ALO + AMO for all four families, then one unit per clue.

    Counts are before solver preprocessing; duplicate clauses are preserved.
    No solver is instantiated and contradictory clues remain valid CNF inputs.
    """
    if not isinstance(puzzle, Puzzle):
        raise TypeError("puzzle must be a validated Puzzle")
    if encoding not in ENCODINGS:
        raise ValueError(f"unknown AMO encoding: {encoding!r}; choose {ENCODINGS}")
    primary = puzzle.N**3
    top_id = primary
    clauses: list[list[int]] = []
    group_count = 0
    for group in iter_exo_groups(puzzle.n):
        clauses.append(list(group))  # ALO is deliberately identical in all encodings.
        amo, top_id = encode_amo(group, encoding, top_id=top_id)
        clauses.extend(amo)
        group_count += 1
    clue_count = 0
    for r, c, value in iter_clues(puzzle):
        clauses.append([variable_id(puzzle.n, r, c, value)])
        clue_count += 1
    stats = CNFStats(
        primary_variables=primary,
        auxiliary_variables=top_id - primary,
        total_variables=top_id,
        clauses=len(clauses),
        exo_groups=group_count,
        clues=clue_count,
    )
    return EncodedCNF(encoding=encoding, clauses=clauses, stats=stats)


class _BudgetExpired(Exception):
    """Internal cooperative deadline check, distinct from solver errors."""


def _finite_number(value: object, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not isfinite(number) or (positive and number <= 0):
        raise ValueError(f"{name} must be finite{' and positive' if positive else ''}")
    return number


def solve_sat(
    puzzle: Puzzle,
    encoding: str = "pairwise",
    *,
    cutoff_seconds: float = 10.0,
    deadline: float | None = None,
    on_measurement_end: Callable[[float, Mapping[str, float | None]], None] | None = None,
) -> SolveResult:
    """Build, solve, decode and independently check one fresh Glucose3 model.

    deadline is absolute perf_counter time in this worker's clock domain.
    A Timer interrupts native solve_limited using only the remaining budget.
    Build checkpoints are cooperative: the runner must still enforce a hard
    worker/process guard, especially during CNF construction/solver loading.
    Decode, independent checking and resource cleanup are outside build+solve.
    on_measurement_end(end_timestamp, timings), if supplied, runs once before
    timer join/decoding/checking/cleanup on every path that entered measurement.
    """
    if not isinstance(puzzle, Puzzle):
        raise TypeError("puzzle must be a validated Puzzle")
    if encoding not in ENCODINGS:
        raise ValueError(f"unknown AMO encoding: {encoding!r}; choose {ENCODINGS}")
    cutoff = _finite_number(cutoff_seconds, "cutoff_seconds", positive=True)
    external_deadline = None if deadline is None else _finite_number(deadline, "deadline")
    if on_measurement_end is not None and not callable(on_measurement_end):
        raise ValueError("on_measurement_end must be callable or None")
    try:
        prepare_backend()
    except (ImportError, OSError) as exc:
        return SolveResult(
            status=SolveStatus.UNAVAILABLE, method="sat", encoding=encoding,
            error=f"{type(exc).__name__}: {exc}",
        )

    start = perf_counter()
    effective_deadline = start + cutoff
    if external_deadline is not None:
        effective_deadline = min(effective_deadline, external_deadline)
    solver = None
    timer = None
    stats = None
    solve_start = None
    solve_end = None
    build_seconds = None
    solve_seconds = None
    raw_status = None
    status = SolveStatus.ERROR
    solution = None
    validation = None
    error = None
    stage = "build"
    interrupt_times: list[float] = []
    interrupt_errors: list[str] = []
    measurement_published = False
    failure_end = None

    def publish_measurement_end(end: float) -> None:
        nonlocal measurement_published, build_seconds, solve_seconds
        if measurement_published:
            return
        # Mark first: even if the callback raises, it must never be retried.
        measurement_published = True
        if solve_start is None:
            build_seconds = end - start
            solve_seconds = 0.0  # Native solve was never entered.
        else:
            build_seconds = solve_start - start
            solve_seconds = end - solve_start
        if on_measurement_end is not None:
            try:
                on_measurement_end(end, {
                    "build_seconds": build_seconds,
                    "solve_seconds": solve_seconds,
                    "total_seconds": build_seconds + solve_seconds,
                })
            except Exception as exc:
                raise RuntimeError(
                    f"measurement-end callback failed: {type(exc).__name__}: {exc}"
                ) from exc

    def check_deadline(message: str) -> None:
        if perf_counter() >= effective_deadline:
            raise _BudgetExpired(message)

    def interrupt() -> None:
        # Joined before solver.delete(), so the callback never touches a freed
        # native object. Record the timestamp to exclude a callback that ran
        # only AFTER the native call had already returned within the deadline.
        interrupt_times.append(perf_counter())
        try:
            solver.interrupt()
        except Exception as exc:
            interrupt_errors.append(f"{type(exc).__name__}: {exc}")

    def stop_timer() -> None:
        nonlocal timer
        if timer is not None:
            timer.cancel()
            timer.join()
            timer = None

    try:
        check_deadline("deadline reached before CNF construction")
        built = build_cnf(puzzle, encoding)
        stats = built.stats
        check_deadline("deadline reached during CNF construction")
        solver = Glucose3()
        solver.append_formula(built.clauses)
        check_deadline("deadline reached during solver creation/loading")
        timer = Timer(max(0.0, effective_deadline - perf_counter()), interrupt)
        timer.daemon = True
        timer.start()
        check_deadline("deadline reached before native solving")
        solve_start = perf_counter()
        build_seconds = solve_start - start
        stage = "solve"
        native_status = solver.solve_limited(expect_interrupt=True)
        solve_end = perf_counter()
        solve_seconds = solve_end - solve_start
        raw_status = str(native_status)
        publish_measurement_end(solve_end)
        stop_timer()
        interrupted_in_solve = bool(interrupt_times and interrupt_times[0] <= solve_end)
        if solve_end >= effective_deadline or interrupted_in_solve:
            status = SolveStatus.TIMEOUT
            error = "build+solve deadline reached"
            if interrupt_errors:
                error += "; interrupt failed: " + "; ".join(interrupt_errors)
        elif native_status is False:
            status = SolveStatus.UNSAT
        elif native_status is True:
            stage = "decode"
            candidate = decode_model(puzzle.n, solver.get_model())
            stage = "validation"
            validation = check_solution(puzzle, candidate)
            if validation.valid:
                status = SolveStatus.SAT
                solution = candidate
            else:
                status = SolveStatus.ERROR
                error = validation.message or "independent checker rejected the solution"
        else:
            status = SolveStatus.ERROR
            error = "Glucose3 returned UNKNOWN without deadline/interruption evidence"
    except _BudgetExpired as exc:
        failure_end = perf_counter() if not measurement_published else None
        status = SolveStatus.TIMEOUT
        error = str(exc)
    except Exception as exc:
        failure_end = perf_counter() if not measurement_published else None
        status = SolveStatus.ERROR
        error = f"{type(exc).__name__}: {exc}"
        if stage in ("decode", "validation"):
            validation = ValidationResult(False, error)
    finally:
        # Failed/expired builds and native exceptions also close measurement
        # before any timer join or native cleanup. Keep the observed exception
        # timestamp so callback work never enters measured elapsed time.
        if not measurement_published:
            try:
                publish_measurement_end(failure_end if failure_end is not None else perf_counter())
            except Exception as exc:
                status, solution = SolveStatus.ERROR, None
                hook_error = f"{type(exc).__name__}: {exc}"
                error = f"{error}; {hook_error}" if error else hook_error
        safe_to_delete = False
        try:
            stop_timer()
            safe_to_delete = True
        except Exception as exc:
            status, solution = SolveStatus.ERROR, None
            cleanup_error = (f"timer cleanup failed: {type(exc).__name__}: {exc}; "
                             "native deletion deferred because the interrupt timer did not join; "
                             "worker cleanup is required")
            error = f"{error}; {cleanup_error}" if error else cleanup_error
        if solver is not None and safe_to_delete:
            try:
                solver.delete()
            except Exception as exc:
                status, solution = SolveStatus.ERROR, None
                cleanup_error = f"solver cleanup failed: {type(exc).__name__}: {exc}"
                error = f"{error}; {cleanup_error}" if error else cleanup_error

    return SolveResult(
        status=status, method="sat", encoding=encoding, raw_status=raw_status,
        solution=solution, build_seconds=build_seconds, solve_seconds=solve_seconds,
        total_seconds=build_seconds + solve_seconds, stats=stats,
        validation=validation, error=error,
    )

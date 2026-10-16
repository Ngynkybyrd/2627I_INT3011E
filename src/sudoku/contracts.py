"""Shared data contracts; solver and checker implementations live elsewhere."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, Sequence

if TYPE_CHECKING:
    from sudoku.model import Puzzle

Grid = tuple[tuple[int, ...], ...]


class SolveStatus(StrEnum):
    SAT = "SAT"
    UNSAT = "UNSAT"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    UNAVAILABLE = "UNAVAILABLE"
    LICENSE_LIMIT = "LICENSE_LIMIT"


class InvalidInputError(ValueError):
    """Malformed puzzle/JSON/file; a contradictory valid puzzle is not this error."""

    status = SolveStatus.INVALID_INPUT


@dataclass(frozen=True, slots=True)
class CNFStats:
    primary_variables: int
    auxiliary_variables: int
    total_variables: int
    clauses: int
    exo_groups: int
    clues: int


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    message: str | None = None


class Checker(Protocol):
    def __call__(
        self, puzzle: Puzzle, solution: Sequence[Sequence[int]]
    ) -> ValidationResult:
        """Check domain, shape, rows, columns, blocks and all original clues."""
        ...


@dataclass(frozen=True, slots=True)
class SolveResult:
    """One run; SAT requires an independent checker to have accepted its solution.

    Missing measurements remain None (not zero), e.g. a worker killed in build.
    Timing is populated by the adapter/runner, not by CNF construction.
    """

    status: SolveStatus
    method: str
    encoding: str | None = None
    raw_status: str | None = None
    solution: Grid | None = None
    build_seconds: float | None = None
    solve_seconds: float | None = None
    total_seconds: float | None = None
    stats: CNFStats | None = None
    validation: ValidationResult | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, SolveStatus):
            raise TypeError("status must be a SolveStatus")
        if self.status is SolveStatus.SAT:
            if self.solution is None or self.validation is None or not self.validation.valid:
                raise ValueError("SAT requires a solution accepted by an independent checker")
        elif self.solution is not None:
            raise ValueError("solution is reserved for checker-accepted SAT results")

    def to_dict(self) -> dict[str, object]:
        """JSON-compatible nested result; CSV flattening belongs to the runner."""
        result = asdict(self)
        result["status"] = self.status.value
        if self.solution is not None:
            result["solution"] = [list(row) for row in self.solution]
        return result

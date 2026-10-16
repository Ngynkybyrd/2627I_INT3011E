"""Generalized Sudoku input and Boolean variable/group definitions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from sudoku.contracts import Grid, InvalidInputError


def _board_size(n: int) -> int:
    if type(n) is not int or n < 2:
        raise InvalidInputError("n must be an integer >= 2 (bool is not an integer input)")
    return n * n


@dataclass(frozen=True, slots=True)
class Puzzle:
    """Immutable validated input. Zero denotes an empty cell; values are 1..N."""

    n: int
    grid: Grid

    def __post_init__(self) -> None:
        N = _board_size(self.n)
        if not isinstance(self.grid, (list, tuple)) or len(self.grid) != N:
            raise InvalidInputError(f"grid must have exactly {N} rows")
        rows = []
        for r, row in enumerate(self.grid):
            if not isinstance(row, (list, tuple)) or len(row) != N:
                raise InvalidInputError(f"grid[{r}] must have exactly {N} values")
            for c, value in enumerate(row):
                if type(value) is not int or not 0 <= value <= N:
                    raise InvalidInputError(f"grid[{r}][{c}] must be an integer in 0..{N}")
            rows.append(tuple(row))
        object.__setattr__(self, "grid", tuple(rows))

    @property
    def N(self) -> int:
        return self.n * self.n

    @property
    def clue_count(self) -> int:
        return sum(value != 0 for row in self.grid for value in row)


def parse_puzzle(data: object) -> Puzzle:
    """Parse a decoded JSON object; extra metadata keys are ignored."""
    if not isinstance(data, dict) or "n" not in data or "grid" not in data:
        raise InvalidInputError("input must be an object with n and grid")
    return Puzzle(n=data["n"], grid=data["grid"])


def parse_json(text: str) -> Puzzle:
    """Parse JSON text. Structural errors raise InvalidInputError, not UNSAT."""
    if not isinstance(text, str):
        raise InvalidInputError("JSON input must be text")
    try:
        data = json.loads(text)
    except (ValueError, RecursionError) as exc:
        raise InvalidInputError(f"invalid JSON: {exc}") from exc
    return parse_puzzle(data)


def load_puzzle(path: str | Path) -> Puzzle:
    """Load UTF-8 JSON (optional BOM); file/decoding errors are INVALID_INPUT."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise InvalidInputError(f"cannot read puzzle: {exc}") from exc
    return parse_json(text)


def variable_id(n: int, r: int, c: int, v: int) -> int:
    """x[r,c,v] -> ID 1..N^3, with 0-based r,c and 1-based v."""
    N = _board_size(n)
    if any(type(index) is not int for index in (r, c, v)):
        raise ValueError("r, c and v must be integers")
    if not (0 <= r < N and 0 <= c < N and 1 <= v <= N):
        raise ValueError("r, c or v is outside the board domain")
    return (r * N + c) * N + v


def variable_coordinates(n: int, variable: int) -> tuple[int, int, int]:
    """Invert a positive primary ID. Reject negative literals/auxiliary IDs."""
    N = _board_size(n)
    if type(variable) is not int or not 1 <= variable <= N**3:
        raise ValueError("variable must be a primary ID in 1..N^3")
    cell, offset = divmod(variable - 1, N)
    r, c = divmod(cell, N)
    return r, c, offset + 1


def iter_exo_groups(n: int) -> Iterator[tuple[int, ...]]:
    """Yield 4N^2 groups: cells, row-values, column-values, block-values.

    The group/literal order is identical for every AMO implementation. No
    redundancy removal, clue propagation, or symmetry breaking occurs here.
    """
    N = _board_size(n)

    def vid(r: int, c: int, v: int) -> int:
        return (r * N + c) * N + v

    for r in range(N):
        for c in range(N):
            yield tuple(vid(r, c, v) for v in range(1, N + 1))
    for r in range(N):
        for v in range(1, N + 1):
            yield tuple(vid(r, c, v) for c in range(N))
    for c in range(N):
        for v in range(1, N + 1):
            yield tuple(vid(r, c, v) for r in range(N))
    for block_r in range(n):
        for block_c in range(n):
            for v in range(1, N + 1):
                yield tuple(
                    vid(block_r * n + dr, block_c * n + dc, v)
                    for dr in range(n)
                    for dc in range(n)
                )


def iter_clues(puzzle: Puzzle) -> Iterator[tuple[int, int, int]]:
    """Nonzero clues in row-major order, without rejecting contradictions."""
    for r, row in enumerate(puzzle.grid):
        for c, value in enumerate(row):
            if value:
                yield r, c, value

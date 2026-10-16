"""Independent Sudoku solution checking, without SAT/model encoding logic."""

from collections.abc import Sequence

from sudoku.contracts import ValidationResult
from sudoku.model import Puzzle


def check_solution(puzzle: Puzzle, solution: Sequence[Sequence[int]]) -> ValidationResult:
    """Return a reason for malformed or invalid solutions; never solve the puzzle.

    Lists and tuples (and ordinary sequence implementations) are accepted.
    Strings, mappings and iterators are not grids. Values must be exact ints.
    """
    N = puzzle.N
    if isinstance(solution, (str, bytes, bytearray)) or not isinstance(solution, Sequence):
        return ValidationResult(False, "solution must be a sequence of rows")
    if len(solution) != N:
        return ValidationResult(False, f"solution must have {N} rows")
    for r, row in enumerate(solution):
        if isinstance(row, (str, bytes, bytearray)) or not isinstance(row, Sequence):
            return ValidationResult(False, f"row {r} must be a sequence")
        if len(row) != N:
            return ValidationResult(False, f"row {r} must have {N} cells")
        for c, value in enumerate(row):
            if type(value) is not int or not 1 <= value <= N:
                return ValidationResult(False, f"cell ({r}, {c}) must be an exact int in 1..{N}")

    expected = set(range(1, N + 1))
    for r, row in enumerate(solution):
        if set(row) != expected:
            return ValidationResult(False, f"row {r} does not contain every value once")
    for c in range(N):
        if {solution[r][c] for r in range(N)} != expected:
            return ValidationResult(False, f"column {c} does not contain every value once")
    for start_r in range(0, N, puzzle.n):
        for start_c in range(0, N, puzzle.n):
            values = {solution[r][c]
                      for r in range(start_r, start_r + puzzle.n)
                      for c in range(start_c, start_c + puzzle.n)}
            if values != expected:
                return ValidationResult(False, f"block ({start_r}, {start_c}) is invalid")
    for r in range(N):
        for c in range(N):
            clue = puzzle.grid[r][c]
            if clue and solution[r][c] != clue:
                return ValidationResult(False, f"clue at ({r}, {c}) was changed")
    return ValidationResult(True)

"""Decode a signed SAT model; this does not certify a Sudoku solution or SAT."""

from collections.abc import Iterable

from sudoku.contracts import Grid
from sudoku.model import variable_coordinates


class DecodeError(ValueError):
    """A SAT model cannot be decoded into exactly one value per cell."""


def decode_model(n: int, model: Iterable[int]) -> Grid:
    """Read positive primary IDs, ignoring signed auxiliary IDs.

    Missing/ambiguous cells and contradictory primary signs are errors.
    A partial model is permitted if every cell has exactly one positive value.
    Call the independent checker after decoding, before publishing success.
    """
    if type(n) is not int or n < 2:
        raise DecodeError("n must be an exact int >= 2")
    N = n * n
    grid = [[0] * N for _ in range(N)]
    signs: dict[int, bool] = {}
    try:
        literals = iter(model)
    except TypeError as exc:
        raise DecodeError("model must be an iterable of signed integer literals") from exc
    for literal in literals:
        if type(literal) is not int or literal == 0:
            raise DecodeError("model literals must be nonzero exact ints")
        variable = abs(literal)
        if variable > N**3:
            continue
        positive = literal > 0
        if variable in signs and signs[variable] != positive:
            raise DecodeError(f"contradictory signs for primary ID {variable}")
        signs[variable] = positive
        if not positive:
            continue
        r, c, v = variable_coordinates(n, variable)
        if grid[r][c] not in (0, v):
            raise DecodeError(f"multiple values selected for cell ({r}, {c})")
        grid[r][c] = v
    for r in range(N):
        for c in range(N):
            if grid[r][c] == 0:
                raise DecodeError(f"no value selected for cell ({r}, {c})")
    return tuple(tuple(row) for row in grid)

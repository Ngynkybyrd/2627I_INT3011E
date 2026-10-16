import pytest

from sudoku.model import Puzzle
from sudoku.validation import check_solution


FULL = ((1, 2, 3, 4), (3, 4, 1, 2), (2, 1, 4, 3), (4, 3, 2, 1))


def blank():
    return Puzzle(2, [[0] * 4 for _ in range(4)])


@pytest.mark.parametrize("solution", [FULL, [list(row) for row in FULL]])
def test_valid_solution(solution):
    assert check_solution(blank(), solution).valid
    assert check_solution(Puzzle(2, FULL), solution).valid


@pytest.mark.parametrize("solution", [None, 5, {}, "1234", b"1234", [], FULL[:-1],
                                      [None] * 4, ["1234"] * 4, [[1] * 3] * 4,
                                      [[1] * 5] * 4, iter(FULL)])
def test_malformed_solution(solution):
    result = check_solution(blank(), solution)
    assert not result.valid and result.message


@pytest.mark.parametrize("value", [0, -1, 5, True, False, 1.0, "1", None])
def test_exact_integer_domain(value):
    grid = [list(row) for row in FULL]
    grid[0][0] = value
    result = check_solution(blank(), grid)
    assert not result.valid and "exact int" in result.message


def test_row_violation():
    grid = [list(row) for row in FULL]
    grid[0][0] = 2
    assert "row" in check_solution(blank(), grid).message


def test_column_violation_with_rows_valid():
    grid = [list(row) for row in FULL]
    grid[1] = grid[0][:]
    assert all(len(set(row)) == 4 for row in grid)
    assert "column" in check_solution(blank(), grid).message


def test_block_violation_with_rows_columns_valid():
    latin = [[(r + c) % 4 + 1 for c in range(4)] for r in range(4)]
    assert all(len({latin[r][c] for r in range(4)}) == 4 for c in range(4))
    assert "block" in check_solution(blank(), latin).message


def test_changed_clue_even_when_sudoku_is_valid():
    clues = [[0] * 4 for _ in range(4)]
    clues[0][0] = 2
    result = check_solution(Puzzle(2, clues), FULL)
    assert not result.valid and "clue" in result.message


@pytest.mark.parametrize("n", (2, 3, 4, 5))
def test_checker_general_sizes_without_solver(n):
    N = n * n
    grid = [[(r * n + r // n + c) % N + 1 for c in range(N)] for r in range(N)]
    puzzle = Puzzle(n, grid)
    assert check_solution(puzzle, grid).valid
    grid[-1][-1] = 0
    assert not check_solution(puzzle, grid).valid

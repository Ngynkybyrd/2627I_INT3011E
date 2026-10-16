"""Production adapter acceptance on common fixtures; no benchmark measurements.

Invalid JSON/objects are rejected at the shared parser boundary: adapter APIs
accept an already validated Puzzle, not arbitrary JSON. Optional runtime/size
restrictions are explicit skips, never evidence of SAT/UNSAT agreement.
"""

import json

import pytest

from sudoku.baselines import METHODS, solve_baseline
from sudoku.contracts import InvalidInputError, SolveStatus
from sudoku.model import Puzzle, parse_json, parse_puzzle
from sudoku.sat import ENCODINGS, solve_sat
from sudoku.validation import check_solution
from tests.oracle_4x4 import solutions_4x4
from tests.test_sat_correctness import CASES


CONFIGURATIONS = [("sat", encoding) for encoding in ENCODINGS] + [(method, None) for method in METHODS]
CONFIG_IDS = [f"{method}-{encoding}" if encoding else method for method, encoding in CONFIGURATIONS]


def solve(puzzle, method, encoding):
    if method == "sat":
        return solve_sat(puzzle, encoding, cutoff_seconds=10.0)
    return solve_baseline(puzzle, method, cutoff_seconds=10.0)


def accept(result, puzzle, expected, record_property):
    record_property("backend_result", json.dumps(result.to_dict(), ensure_ascii=False))
    record_property("expected_status", expected.value)
    if result.status in (SolveStatus.UNAVAILABLE, SolveStatus.LICENSE_LIMIT):
        pytest.skip(f"{result.method}: {result.status}: {result.error}")
    assert result.status is expected, result
    assert result.raw_status, result
    assert result.error is None, result
    assert result.total_seconds == pytest.approx(result.build_seconds + result.solve_seconds)
    if expected is SolveStatus.SAT:
        assert result.solution is not None and result.validation is not None
        assert result.validation.valid
        independent = check_solution(puzzle, result.solution)
        record_property("independent_recheck", independent.valid)
        assert independent.valid, independent.message
    else:
        assert result.solution is None


@pytest.mark.parametrize("method,encoding", CONFIGURATIONS, ids=CONFIG_IDS)
@pytest.mark.parametrize("name,grid,count", CASES, ids=[case[0] for case in CASES])
def test_production_adapters_agree_with_independent_oracle(method, encoding, name, grid, count, record_property):
    puzzle = Puzzle(2, grid)
    oracle = solutions_4x4(grid, limit=2)
    assert len(oracle) == count
    expected = SolveStatus.SAT if oracle else SolveStatus.UNSAT
    accept(solve(puzzle, method, encoding), puzzle, expected, record_property)


@pytest.mark.parametrize("method,encoding", CONFIGURATIONS, ids=CONFIG_IDS)
@pytest.mark.parametrize("conflict", (False, True), ids=("sat9", "unsat9"))
def test_common_nine_by_nine_fixture(method, encoding, conflict, record_property):
    grid = [[(r * 3 + r // 3 + c) % 9 + 1 for c in range(9)] for r in range(9)]
    if conflict:
        grid[0][1] = grid[0][0]
    else:
        for r in range(9):
            grid[r][(r + 1) % 9] = 0
    puzzle = Puzzle(3, grid)
    accept(solve(puzzle, method, encoding), puzzle,
           SolveStatus.UNSAT if conflict else SolveStatus.SAT, record_property)


INVALID_CASES = [
    ("bad_json", "{"),
    ("missing_fields", {}),
    ("bad_n", {"n": 1, "grid": [[0] * 4 for _ in range(4)]}),
    ("wrong_rows", {"n": 2, "grid": [[0] * 4 for _ in range(3)]}),
    ("wrong_columns", {"n": 2, "grid": [[0] * 3 for _ in range(4)]}),
    ("out_of_domain", {"n": 2, "grid": [[5, 0, 0, 0]] + [[0] * 4 for _ in range(3)]}),
    ("bool_value", {"n": 2, "grid": [[True, 0, 0, 0]] + [[0] * 4 for _ in range(3)]}),
]


@pytest.mark.parametrize("method,encoding", CONFIGURATIONS, ids=CONFIG_IDS)
@pytest.mark.parametrize("name,data", INVALID_CASES, ids=[case[0] for case in INVALID_CASES])
def test_invalid_input_stops_before_every_adapter(method, encoding, name, data, monkeypatch, record_property):
    import tests.test_backend_agreement as this_module

    def forbidden(*args, **kwargs):
        raise AssertionError("an adapter received an invalid puzzle")

    monkeypatch.setattr(this_module, "solve_sat", forbidden)
    monkeypatch.setattr(this_module, "solve_baseline", forbidden)
    with pytest.raises(InvalidInputError) as caught:
        puzzle = parse_json(data) if isinstance(data, str) else parse_puzzle(data)
        solve(puzzle, method, encoding)
    assert caught.value.status is SolveStatus.INVALID_INPUT
    record_property("expected_status", SolveStatus.INVALID_INPUT.value)
    record_property("boundary", "shared parser; no adapter called")

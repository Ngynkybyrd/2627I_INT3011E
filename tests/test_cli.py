"""Focused tests for the one-puzzle command-line interface."""

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sudoku.cli import _render_grid, main
from sudoku.contracts import SolveResult, SolveStatus, ValidationResult
from sudoku.model import Puzzle


def solved_four() -> tuple[tuple[int, ...], ...]:
    return ((1, 2, 3, 4), (3, 4, 1, 2), (2, 1, 4, 3), (4, 3, 2, 1))


def call_cli(args: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    code = main(args, stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def test_sat_cli_dispatches_encoding_cutoff_and_emits_json_and_table(tmp_path: Path):
    puzzle_path = tmp_path / "sudoku input.json"
    puzzle_path.write_text(json.dumps({"n": 2, "grid": [[0] * 4 for _ in range(4)]}),
                           encoding="utf-8")
    result = SolveResult(SolveStatus.SAT, "sat", encoding="bitwise",
                         solution=solved_four(), build_seconds=0.1, solve_seconds=0.2,
                         total_seconds=0.3, validation=ValidationResult(True))
    output_path = tmp_path / "result.json"
    with patch("sudoku.cli.solve_sat", return_value=result) as solve:
        code, stdout, stderr = call_cli([
            str(puzzle_path), "--method", "sat", "--encoding", "bitwise",
            "--cutoff", "2.5", "--json-output", str(output_path),
        ])

    solve.assert_called_once_with(Puzzle(2, [[0] * 4 for _ in range(4)]),
                                  "bitwise", cutoff_seconds=2.5)
    assert code == 0
    assert json.loads(stdout)["status"] == "SAT"
    assert json.loads(output_path.read_text(encoding="utf-8"))["solution"][0] == [1, 2, 3, 4]
    assert "Solution:" in stderr and " | " in stderr
    assert "build_seconds: 0.100000" in stderr


def test_baseline_cli_does_not_forward_sat_encoding(tmp_path: Path):
    puzzle_path = tmp_path / "puzzle.json"
    puzzle_path.write_text(json.dumps({"n": 2, "grid": [[0] * 4 for _ in range(4)]}),
                           encoding="utf-8")
    result = SolveResult(SolveStatus.UNAVAILABLE, "gurobi", error="missing runtime")
    with patch("sudoku.cli.solve_baseline", return_value=result) as solve:
        code, stdout, stderr = call_cli([str(puzzle_path), "--method", "gurobi"])
    solve.assert_called_once_with(Puzzle(2, [[0] * 4 for _ in range(4)]),
                                  "gurobi", cutoff_seconds=10.0)
    assert code == 1
    assert json.loads(stdout)["status"] == "UNAVAILABLE"
    assert "Error: missing runtime" in stderr


def test_invalid_json_is_reported_as_invalid_input(tmp_path: Path):
    puzzle_path = tmp_path / "broken.json"
    puzzle_path.write_text("{", encoding="utf-8")
    code, stdout, stderr = call_cli([str(puzzle_path)])
    assert code == 2
    assert json.loads(stdout)["status"] == "INVALID_INPUT"
    assert "invalid JSON" in json.loads(stdout)["error"]
    assert "Status: INVALID_INPUT" in stderr


def test_missing_file_is_invalid_input_and_solver_is_not_called(tmp_path: Path):
    with patch("sudoku.cli.solve_sat") as solve:
        code, stdout, _ = call_cli([str(tmp_path / "missing.json")])
    solve.assert_not_called()
    assert code == 2
    assert json.loads(stdout)["status"] == "INVALID_INPUT"


@pytest.mark.parametrize("cutoff", ["0", "-1", "nan", "inf"])
def test_nonpositive_or_nonfinite_cutoff_is_rejected(cutoff: str, tmp_path: Path):
    with pytest.raises(SystemExit) as caught:
        main([str(tmp_path / "puzzle.json"), "--cutoff", cutoff],
             stdout=io.StringIO(), stderr=io.StringIO())
    assert caught.value.code == 2


def test_encoding_is_rejected_for_baseline(tmp_path: Path):
    with pytest.raises(SystemExit) as caught:
        main([str(tmp_path / "puzzle.json"), "--method", "cpsat", "--encoding", "bitwise"],
             stdout=io.StringIO(), stderr=io.StringIO())
    assert caught.value.code == 2


def test_grid_renderer_supports_two_digit_values_and_block_boundaries():
    row = tuple(range(1, 17))
    grid = tuple(row for _ in range(16))
    rendered = _render_grid(grid, n=4)
    assert " 9 10 11 12 | 13 14 15 16" in rendered
    assert "------------+-------------+-------------+------------" in rendered


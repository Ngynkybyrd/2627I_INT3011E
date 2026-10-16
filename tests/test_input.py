import json

import pytest

from sudoku.contracts import InvalidInputError, SolveStatus
from sudoku.model import load_puzzle, parse_json, parse_puzzle


def blank():
    return [[0] * 4 for _ in range(4)]


INVALID = [None, [], {}, {"n": 2}, {"grid": blank()}]
INVALID += [{"n": n, "grid": blank()} for n in (True, False, 1, 0, -2, 2.0, "2", None)]
INVALID += [{"n": 2, "grid": grid} for grid in (None, {}, [], blank()[:-1], blank() + [[0] * 4],
                                                  [[0] * 3] + blank()[1:], [[0] * 5] + blank()[1:])]
INVALID += [{"n": 2, "grid": [[v, 0, 0, 0]] + blank()[1:]}
            for v in (True, False, -1, 5, 1.0, "1", None)]


@pytest.mark.parametrize("data", INVALID)
def test_invalid_structure_or_domain(data):
    with pytest.raises(InvalidInputError) as caught:
        parse_puzzle(data)
    assert caught.value.status is SolveStatus.INVALID_INPUT


@pytest.mark.parametrize("text", ["{", "", "[]", "null", "NaN", '{"n":2,"grid":[]}'])
def test_invalid_json(text):
    with pytest.raises(InvalidInputError):
        parse_json(text)


def test_file_errors_and_utf8_bom_path_with_spaces(tmp_path):
    with pytest.raises(InvalidInputError):
        load_puzzle(tmp_path / "missing.json")
    with pytest.raises(InvalidInputError):
        load_puzzle(tmp_path)
    path = tmp_path / "đề có dấu cách.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(InvalidInputError):
        load_puzzle(path)
    path.write_bytes(b"\xff")
    with pytest.raises(InvalidInputError):
        load_puzzle(path)
    path.write_text(json.dumps({"n": 2, "grid": blank()}), encoding="utf-8-sig")
    assert load_puzzle(path).clue_count == 0

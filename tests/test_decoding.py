import pytest

from sudoku.decoding import DecodeError, decode_model
from sudoku.model import Puzzle, variable_id
from sudoku.validation import check_solution
from tests.test_validation import FULL


def positive_model():
    return [variable_id(2, r, c, FULL[r][c]) for r in range(4) for c in range(4)]


def test_signed_model_ignores_auxiliary_and_negative_primary():
    positives = positive_model()
    negatives = [-v for v in range(1, 65) if v not in positives]
    assert decode_model(2, iter(negatives + [65, -66, 10000] + positives)) == FULL
    assert decode_model(2, positives + positives) == FULL


@pytest.mark.parametrize("model", [None, [], [-v for v in range(1, 65)], positive_model()[:-1],
                                    positive_model() + [2], positive_model() + [-1],
                                    positive_model() + [0], positive_model() + [True],
                                    positive_model() + [1.0], positive_model() + ["65"]])
def test_reject_malformed_or_missing_or_ambiguous(model):
    with pytest.raises(DecodeError):
        decode_model(2, model)


@pytest.mark.parametrize("n", [True, 1, 0, -1, 2.0, "2", None])
def test_reject_invalid_n(n):
    with pytest.raises(DecodeError):
        decode_model(n, positive_model())


def test_decoder_does_not_certify_sudoku_correctness():
    model = [variable_id(2, r, c, 1) for r in range(4) for c in range(4)]
    grid = decode_model(2, model)
    assert not check_solution(Puzzle(2, [[0] * 4 for _ in range(4)]), grid).valid


@pytest.mark.parametrize("n", (2, 3, 4, 5))
def test_decoder_primary_boundary_on_general_sizes(n):
    N = n * n
    expected = tuple(tuple((r * n + r // n + c) % N + 1 for c in range(N)) for r in range(N))
    model = [variable_id(n, r, c, expected[r][c]) for r in range(N) for c in range(N)]
    model += [N**3 + 1, -(N**3 + 2)]
    assert decode_model(n, model) == expected
    assert check_solution(Puzzle(n, [[0] * N for _ in range(N)]), expected).valid

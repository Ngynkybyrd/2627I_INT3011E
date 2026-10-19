"""Check independent fixtures with existing real parser/checker only.

Passing these tests does NOT mean expanded production modules passed QA.
"""
import hashlib
import json

import pytest

from sudoku.model import Puzzle, parse_json
from sudoku.validation import check_solution
from tests.expanded.reference import (PERSISTENCE_CASES, assert_whole_cycle, canonical,
    content_hash, full, instance_id, job_id, mask, rank, trade_fixture)


@pytest.mark.parametrize("n", (3, 4, 5))
def test_fixture_witness_is_valid(n):
    grid = full(n)
    assert check_solution(Puzzle(n, grid), grid).valid


@pytest.mark.parametrize("n", (4, 5))
def test_complete_proper_cycle_and_involution(n):
    before, after, columns = trade_fixture(n)
    assert before != after
    assert_whole_cycle(n, before, after, 0, 1, columns)
    assert_whole_cycle(n, after, before, 0, 1, columns)


@pytest.mark.parametrize("n", (4, 5))
def test_partial_cycle_and_full_row_swap_are_rejected(n):
    before, after, columns = trade_fixture(n)
    partial = [list(row) for row in before]
    c = columns[0]
    partial[0][c], partial[1][c] = partial[1][c], partial[0][c]
    assert not check_solution(Puzzle(n, [[0]*(n*n) for _ in range(n*n)]), partial).valid
    with pytest.raises(AssertionError):
        assert_whole_cycle(n, before, after, 0, 1, columns[:-1])
    whole_rows = [list(row) for row in before]
    whole_rows[0], whole_rows[1] = whole_rows[1], whole_rows[0]
    assert check_solution(Puzzle(n, [[0]*(n*n) for _ in range(n*n)]), whole_rows).valid
    with pytest.raises(AssertionError):
        assert_whole_cycle(n, before, whole_rows, 0, 1, tuple(range(n*n)))


@pytest.mark.parametrize("n", (4, 5))
@pytest.mark.parametrize("percent", (20, 30, 40, 50, 60))
def test_mask_witness_clue_rounding_and_replay(n, percent):
    _, root, _ = trade_fixture(n)
    root_id = f"e2-main-N{n*n}-row_cycle-r000000"
    grid = mask(n, root, percent, root_id)
    assert grid == mask(n, root, percent, root_id)
    puzzle = Puzzle(n, grid)
    assert puzzle.clue_count == (percent*(n*n)**2 + 50)//100
    assert check_solution(puzzle, root).valid


def test_canonical_bytes_ids_and_dedup_ignore_serialization_metadata():
    grid = full(3)
    a = json.dumps({"n": 3, "grid": grid, "rating": "hard"}, indent=4)
    b = json.dumps({"rating": "easy", "grid": grid, "n": 3})
    parsed = [parse_json(text) for text in (a, b)]
    assert canonical(parsed[0].n, parsed[0].grid) == canonical(parsed[1].n, parsed[1].grid)
    assert canonical(3, grid).startswith(b'{"grid":') and canonical(3, grid).endswith(b"\n")
    assert hashlib.sha256(a.encode()).hexdigest() != hashlib.sha256(b.encode()).hexdigest()
    identity = instance_id(3, grid)
    assert identity == "e2-main-N9-" + content_hash(3, grid)
    assert identity != instance_id(3, grid, "pilot")


def test_job_namespace_baseline_sentinel_and_repetitions():
    iid = instance_id(3, full(3))
    assert job_id("x", iid, "cpsat", None, 1) == job_id("x", iid, "cpsat", "", 1)
    assert len({job_id(exp, iid, "sat", enc, rep) for exp in ("a", "b")
                for enc in ("pairwise", "seqcounter", "bitwise") for rep in (1, 2, 3)}) == 18


def test_utf8_fixture_path_and_lossless_seed_string(tmp_path):
    path = tmp_path / "đề có dấu cách.json"
    path.write_bytes(b"\xef\xbb\xbf" + canonical(3, full(3)))
    from sudoku.model import load_puzzle
    assert load_puzzle(path).grid == full(3)
    decimal_seed = str(int(rank("fixture|N25", "root")[:16], 16))
    assert json.loads(json.dumps({"derived_seed": decimal_seed}))["derived_seed"] == decimal_seed


def test_fault_corpus_is_explicit_about_commits_and_retry():
    assert len({case["id"] for case in PERSISTENCE_CASES}) == len(PERSISTENCE_CASES) == 15
    committed = [case for case in PERSISTENCE_CASES if case["primary"] == 1]
    assert committed and all(case["retry"] == "never" for case in committed)

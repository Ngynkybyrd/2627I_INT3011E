"""Small real expanded_data helper checks; no source download/witness solving."""
import hashlib
import importlib

import pytest

from sudoku.model import Puzzle
from sudoku.validation import check_solution
from tests.expanded.reference import assert_whole_cycle, canonical, full, mask, rank


@pytest.fixture
def data():
    return importlib.import_module("sudoku.expanded_data")


@pytest.mark.parametrize("n", (3, 4, 5))
def test_real_canonical_hash_rank_and_seed(data, n):
    grid = full(n)
    expected = canonical(n, grid)
    assert data.canonical_puzzle_bytes(n, grid) == expected
    assert data.content_sha256(n, grid) == hashlib.sha256(expected).hexdigest()
    assert data.rank("fixture", "đề") == rank("fixture", "đề")
    assert data.derived_seed("fixture", "đề") == str(int(rank("fixture", "đề")[:16], 16))


@pytest.mark.parametrize("n", (4, 5))
def test_real_proper_trade_against_independent_audit(data, n):
    original = full(n)
    cycles = data.whole_row_cycles(n, original, 0, 1)
    assert cycles
    cycle = cycles[0]
    result = data.trade_row_cycle(n, original, 0, 1, cycle["columns"])
    assert_whole_cycle(n, original, result, 0, 1, cycle["columns"])
    assert tuple(map(tuple, data.trade_row_cycle(n, result, 0, 1, cycle["columns"]))) == original
    for bad in (cycle["columns"][:-1], list(range(n*n)), cycle["columns"] + cycle["columns"]):
        with pytest.raises(data.DataError):
            data.trade_row_cycle(n, original, 0, 1, bad)
    with pytest.raises(data.DataError):
        data.whole_row_cycles(n, original, 0, n)


@pytest.mark.parametrize("n", (4, 5))
@pytest.mark.parametrize("percent", (20, 30, 40, 50, 60))
def test_real_mask_matches_independent_rank_witness_and_metadata(data, n, percent):
    root_id = f"e2-main-N{n*n}-permutation-r000000"
    root = {"n": n, "N": n*n, "root_id": root_id, "grid": full(n)}
    result = data.generate_mask(root, percent, "main", set(), [])
    assert tuple(map(tuple, result["grid"])) == mask(n, root["grid"], percent, root_id)
    assert result["actual_clues"] == Puzzle(n, result["grid"]).clue_count
    assert result["clue_percent_requested"] == percent and result["resample_index"] == 0
    assert check_solution(Puzzle(n, result["grid"]), root["grid"]).valid


@pytest.mark.parametrize("n", (4, 5))
def test_real_mask_collision_resamples_or_fails_explicitly(data, n):
    root = {"n": n, "N": n*n, "root_id": f"e2-main-N{n*n}-permutation-r000000", "grid": full(n)}
    first = data.generate_mask(root, 30, "main", set(), [])
    logs = []
    second = data.generate_mask(root, 30, "main", {first["content_sha256"]}, logs, max_attempts=2)
    assert second["resample_index"] == 1 and second["content_sha256"] != first["content_sha256"]
    assert logs[0]["reason"] == "duplicate_puzzle" and logs[0]["root_id"] == root["root_id"]
    with pytest.raises(data.DataError):
        data.generate_mask(root, 30, "main", {first["content_sha256"]}, [], max_attempts=1)


@pytest.mark.parametrize("n", (4, 5))
@pytest.mark.parametrize("family", ("permutation", "row_cycle"))
def test_real_root_slot_identity_witness_and_trade_provenance(data, n, family):
    base = full(n)
    root = data.generate_root(n, family, "main", 7, base, checked_utc="2026-10-19T11:00:00+00:00")
    assert root["root_id"] == f"e2-main-N{n*n}-{family}-r000007"
    assert root["root_content_sha256"] == hashlib.sha256(canonical(n, root["grid"])).hexdigest()
    assert isinstance(root["derived_seed"], str) and root["derived_seed"].isdecimal()
    assert root["witness_validation"]["valid"] and check_solution(Puzzle(n, root["grid"]), root["grid"]).valid
    if family == "row_cycle":
        trade = root["trade"]
        permuted = data.permute_grid(n, base, root["seed_label"])
        assert data.content_sha256(n, permuted) == trade["base_content_sha256"]
        assert_whole_cycle(n, permuted, root["grid"], trade["row_a"], trade["row_b"], trade["columns"])
    else:
        assert root["trade"] is None
    logs = []
    with pytest.raises(data.DataError):
        data.generate_root(n, family, "main", 7, base, {root["root_content_sha256"]}, logs, max_attempts=1)
    assert logs[0]["root_id"] == root["root_id"] and logs[0]["reason"] == "duplicate_root"


@pytest.mark.parametrize("percent", (True, 30.0, "30", 0, 100))
def test_real_invalid_density(data, percent):
    root = {"n": 4, "N": 16, "root_id": "fixture", "grid": full(4)}
    with pytest.raises(data.DataError):
        data.generate_mask(root, percent, "main", set(), [])


@pytest.mark.parametrize("relative", ("../escape", "/absolute", "inputs\\escape", "C:/escape", "", "."))
def test_real_contained_path_rejects_escape(data, tmp_path, relative):
    with pytest.raises(data.DataError):
        data.contained_path(tmp_path, relative)


def test_real_public_dedup_first_owner_old_exclusion_and_pilot_disjoint(data, tmp_path):
    sources = {}
    old_grid = [[v % 9 + 1 for v in row] for row in full(3)]
    # Reserve eight other exact valid grids; all source rows remain artificial.
    old_hash = data.content_sha256(3, old_grid)
    grids = []
    for shift in range(9):
        grid = [[(v - 1 + shift) % 9 + 1 for v in row] for row in full(3)]
        if data.content_sha256(3, grid) != old_hash:
            grids.append(grid)
    shared = grids[0]
    for index, group in enumerate(data.GROUPS):
        path = tmp_path / f"{group}.txt"
        rows = [old_grid] + grids[2*index:2*index+2] + [shared]
        path.write_text("\n".join(f"{line:012x} {''.join(str(v) for row in grid for v in row)} 7.500"
                                  for line, grid in enumerate(rows, 1)) + "\n", encoding="ascii")
        sources[group] = data.parse_public_file(path, group, source_url="fixture://not-research-source")
        assert all(row["rating_original"] == "7.500" for row in sources[group])
    selected, logs = data.select_public(sources, {old_hash}, main_per_group=1, pilot_per_group=1)
    hashes = [row["content_sha256"] for phase in ("main", "pilot") for row in selected[phase]]
    assert len(hashes) == len(set(hashes)) == 8 and old_hash not in hashes
    assert all(len(selected[phase]) == 4 for phase in ("main", "pilot"))
    assert logs and any(row["owner"].get("source") == "old_S80" for row in logs)
    replay, _ = data.select_public(sources, {old_hash}, main_per_group=1, pilot_per_group=1)
    assert replay == selected
    with pytest.raises(data.DataError):
        data.select_public(sources, {old_hash}, main_per_group=2, pilot_per_group=1)

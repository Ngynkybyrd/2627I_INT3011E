"""Generator invariants, collision recovery, and dataset byte reproducibility."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_data", ROOT / "scripts/prepare_data.py")
data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(data)


def test_generalized_completed_grid_beyond_benchmark_sizes():
    grid = data.completed_grid(6)
    assert len(grid) == 36
    assert data.check_solution(data.Puzzle(6, grid), grid).valid
    for bad in (1, True, 2.0):
        with pytest.raises(ValueError):
            data.completed_grid(bad)


def test_generation_counts_clues_and_witness_separation():
    records, outputs, _ = data.synthetic_records()
    assert len(records) == 60
    assert len({row["content_sha256"] for row in records}) == 60
    expected = {4: [5, 8, 11], 9: [24, 41, 57], 16: [77, 128, 179], 25: [188, 313, 438]}
    for N, counts in expected.items():
        for density, count in zip((0.3, 0.5, 0.7), counts):
            group = [row for row in records if row["N"] == N and row["clue_density_requested"] == density]
            assert len(group) == 5 and {row["seed"] for row in group} == set(range(5))
            assert {row["clue_count"] for row in group} == {count}
    for row in records:
        payload = json.loads(outputs[row["file"]])
        assert set(payload) == {"n", "grid"}
        witness = json.loads(outputs[row["witness_file"]])["solution"]
        assert data.check_solution(data.Puzzle(**payload), witness).valid


def test_duplicate_seed_is_incremented_and_logged():
    first, _ = data.candidate(2, 30, 0)
    records, _, collisions = data.synthetic_records({data.fingerprint(first)})
    assert records[0]["seed"] == 0 and records[0]["actual_seed"] > 0
    assert collisions[0]["rejected_seed"] == 0
    assert collisions[0]["puzzle_sha256"] == data.fingerprint(first)
    assert len({row["content_sha256"] for row in records}) == 60


def test_utf8_path_regeneration_scopes_and_public_unchanged(tmp_path):
    target = tmp_path / "dữ liệu có dấu"
    for relative in ("data/public", "diagnostics/public-normalization"):
        shutil.copytree(ROOT / relative, target / relative)
    shutil.copyfile(ROOT / "diagnostics/public-selection.csv", target / "diagnostics/public-selection.csv")
    before = {p.name: p.read_bytes() for p in (target / "data/public").glob("*.json")}
    generated = data.prepare(target)
    assert generated == data.prepare(target, check=True)
    assert generated == data.build_outputs(ROOT, use_validation=False, frozen=False)
    assert before == {p.name: p.read_bytes() for p in (target / "data/public").glob("*.json")}
    scopes = json.loads(generated["data/scopes.json"])
    assert [len(scopes[key]) for key in ("S80", "B16", "C10")] == [80, 16, 10]
    assert scopes["B16"][-4:] == scopes["C10"][-4:] == data.FIRST_FOUR
    assert scopes["frozen"] is False
    manifest = json.loads(generated["data/manifest.json"])
    assert sum(row["sat_status"] == "NOT_CHECKED" for row in manifest["records"]) == 20
    # A modified input must be rejected, not silently overwritten.
    path = target / manifest["records"][0]["file"]
    path.write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        data.prepare(target)


def test_public_validation_and_freeze_reproducible_and_tamper_rejected(tmp_path):
    if not (ROOT / "data/public-validation.json").exists():
        pytest.skip("Production public verification has not been performed yet")
    target = tmp_path / "khóa dữ liệu"
    for relative in ("data/public", "data/source", "diagnostics/public-normalization"):
        shutil.copytree(ROOT / relative, target / relative)
    shutil.copyfile(ROOT / "diagnostics/public-selection.csv", target / "diagnostics/public-selection.csv")
    # Recreate the provisional outputs, then promote using existing production evidence.
    data.prepare(target)
    shutil.copyfile(ROOT / "data/public-validation.json", target / "data/public-validation.json")
    for instance_id in [row["instance_id"] for row in data.public_records(target)[0]]:
        name = f"data/witnesses/{instance_id}.json"
        shutil.copyfile(ROOT / name, target / name)
    promoted = data.finalize_data(target)
    assert promoted == data.build_outputs(ROOT)
    assert (target / "data/freeze.json").read_bytes() == (ROOT / "data/freeze.json").read_bytes()
    assert promoted == data.prepare(target, check=True)
    manifest = json.loads(promoted["data/manifest.json"])
    assert manifest["frozen"] is True
    assert len(manifest["records"]) == 80
    assert all(row["sat_status"] == "SAT" for row in manifest["records"])
    evidence = json.loads((target / "data/public-validation.json").read_bytes())
    evidence["records"][0]["result"]["solution"][0][0] = 0
    (target / "data/public-validation.json").write_bytes(data.json_bytes(evidence))
    with pytest.raises(ValueError, match="independent checker"):
        data.prepare(target, check=True)

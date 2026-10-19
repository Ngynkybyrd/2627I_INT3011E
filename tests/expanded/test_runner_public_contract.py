"""Pending real expanded_runner: run only after that module is handed off.

No importorskip/xfail. A missing implementation is an execution dependency,
not a passing test. Existing v1 tests are not edited.
"""
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def api():
    return importlib.import_module("sudoku.expanded_runner")


PUBLIC = ("validate_expanded_dataset", "prepare_expanded", "pilot_expanded", "run_expanded",
          "resume_expanded", "expanded_status", "export_expanded")


@pytest.mark.parametrize("name", PUBLIC)
def test_public_api_and_error_contract(api, name):
    assert callable(getattr(api, name))
    error = api.ExpandedError("fixture-only", exit_code=3)
    assert error.exit_code == 3 and "fixture-only" in str(error)


@pytest.mark.parametrize("version", (1, 3, "2", True, None))
def test_incompatible_dataset_version_refused(api, tmp_path, version):
    data = tmp_path / "dataset"
    data.mkdir()
    (data / "dataset.json").write_text(json.dumps({"schema_version": version, "artificial": True}), encoding="utf-8")
    with pytest.raises(api.ExpandedError) as caught:
        api.validate_expanded_dataset(data)
    assert caught.value.exit_code == 2


@pytest.mark.parametrize("bad_name", ("missing", "đường dẫn có dấu"))
def test_missing_dataset_file_is_public_error(api, tmp_path, bad_name):
    with pytest.raises(api.ExpandedError) as caught:
        api.validate_expanded_dataset(tmp_path / bad_name)
    assert caught.value.exit_code == 2


def test_malformed_utf8_is_public_error(api, tmp_path):
    data = tmp_path / "dataset"
    data.mkdir()
    (data / "dataset.json").write_bytes(b"\xff")
    with pytest.raises(api.ExpandedError) as caught:
        api.validate_expanded_dataset(data)
    assert caught.value.exit_code == 2


def test_status_does_not_create_missing_experiment(api, tmp_path):
    experiment = tmp_path / "not-prepared"
    with pytest.raises(api.ExpandedError):
        api.expanded_status(str(experiment))
    assert not experiment.exists()


def test_export_does_not_create_success_for_missing_experiment(api, tmp_path):
    output = tmp_path / "export"
    with pytest.raises(api.ExpandedError):
        api.export_expanded(tmp_path / "missing", output, complete_blocks=True)
    assert not output.exists()


def test_reusing_v1_as_dataset_or_experiment_does_not_mutate_it(api, tmp_path):
    old = tmp_path / "old-v1"
    old.mkdir()
    originals = {"run.json": b'{"schema_version":1}\n', "results.csv": b"schema_version,run_id\n1,old\n"}
    for name, payload in originals.items():
        (old / name).write_bytes(payload)
    with pytest.raises(api.ExpandedError):
        api.validate_expanded_dataset(old)
    with pytest.raises(api.ExpandedError):
        api.expanded_status(old)
    assert {p.name: p.read_bytes() for p in old.iterdir()} == originals

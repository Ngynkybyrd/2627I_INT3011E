"""Actual expanded producer/API/storage/export/analysis on artificial witnesses.

No SAT solver, source download, witness search, pilot or benchmark is called.
"""
import csv
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from sudoku import expanded_data as data, expanded_runner as api, expanded_storage as storage

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def analysis_module():
    spec = importlib.util.spec_from_file_location("qa_analyze_expanded", ROOT / "scripts/analyze_expanded.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def produced(tmp_path_factory):
    output = tmp_path_factory.mktemp("artificial-producer") / "new-output"
    evidence = data.smoke_artificial(output, ROOT)
    assert evidence["solver_calls"] == evidence["network_calls"] == 0
    assert evidence["artificial"]
    return {phase: Path(path) for phase, path in evidence["datasets"].items()}


@pytest.fixture
def prepared(produced, tmp_path):
    matrix = {"schema_version": 2, "rows": [
        {"N": N, "configuration": method, "method": method, "encoding": None, "eligible": True}
        for N in (9, 16, 25) for method in ("cpsat", "highs")]}
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    experiment = tmp_path / "artificial-experiment"
    receipt = api.prepare_expanded(produced["main"], experiment, ROOT / "configs/expanded/main.json", matrix_path, phase="main")
    index = api.validate_expanded_dataset(produced["main"])
    assert receipt["planned_jobs"] == 6 * len(index["records"])
    return experiment, index, receipt


@pytest.mark.parametrize("phase", ("main", "pilot"))
def test_actual_producer_is_accepted_by_independent_runner_validator(produced, phase):
    index = api.validate_expanded_dataset(produced[phase])
    assert index["artificial"] and index["phase"] == phase
    assert index["counts"]["instances"] == (24 if phase == "main" else 28)


def fill(experiment, index, *, mixed=False, partial=False):
    """Commit artificial observed fixtures through the real storage API."""
    db = storage.connect(experiment)
    try:
        sid = storage.new_session(db, "2099-01-01T00:00:00+00:00", "QA artificial result injection; no solver")
        first = storage.claim(db, sid)
        storage.interrupt(db, first["attempt_id"], "QA history fixture; no worker launched")
        mixed_key = (first["instance_id"], first["configuration"])
        n = 0
        while (attempt := storage.claim(db, sid)) is not None:
            record = index["records"][attempt["instance_id"]]
            timeout = mixed and (attempt["instance_id"], attempt["configuration"]) == mixed_key and attempt["repetition"] == 2
            total = 0.03 + attempt["repetition"] * 0.01
            result = {"status": "TIMEOUT" if timeout else "SAT", "method": attempt["method"], "encoding": None,
                      "raw_status": "ARTIFICIAL_NOT_SOLVER", "guard_phase": "measurement" if timeout else "complete",
                      "stats": None, "error": None}
            if not timeout:
                result.update(solution=read(Path(index["dataset_dir"]) / record["witness_file"])["grid"],
                              validation={"valid": True, "message": None}, build_seconds=0.01,
                              solve_seconds=total-0.01, total_seconds=total)
            assert not storage.finish(db, attempt["attempt_id"], result, record, index["dataset_dir"], 0.1)
            n += 1
            if partial:
                break
        storage.integrity(db)
        return n, mixed_key
    finally:
        db.close()


@pytest.mark.parametrize("mixed", (False, True))
def test_producer_to_complete_export_and_actual_analysis(prepared, tmp_path, mixed):
    experiment, index, receipt = prepared
    count, mixed_key = fill(experiment, index, mixed=mixed)
    status = api.expanded_status(experiment)
    assert status["completed_jobs"] == count == receipt["planned_jobs"]
    assert status["qa_complete_blocks"] == 1 and status["interrupted_attempts"] == 1
    output = tmp_path / "new-export"
    export = api.export_expanded(experiment, output, complete_blocks=True)
    assert export["selected_jobs"] == count
    metadata = read(output / "export.json")
    assert metadata["artificial"] and not metadata["report_ready"]
    assert len(rows(output / "results.csv")) == count
    summary = analysis_module().analyze_expanded(output, tmp_path / "new-analysis")
    assert summary["artificial"] and not summary["report_ready"]
    assert summary["coverage"]["observed_primary_jobs"] == count
    assert summary["coverage"]["historical_interrupted_attempts"] == 1
    instances = rows(tmp_path / "new-analysis/instances.csv")
    target = next(r for r in instances if (r["instance_id"], r["configuration"]) == mixed_key)
    if mixed:
        assert target["mixed_status"] == "True" and target["runtime_eligible"] == "False"
        assert target["median_total_seconds"] == ""
        assert float(target["par2_seconds"]) == pytest.approx((0.04 + 20 + 0.06)/3)
    else:
        assert target["runtime_eligible"] == "True" and float(target["median_total_seconds"]) == pytest.approx(0.05)


def test_partial_block_not_promoted_and_export_does_not_rewrite_db(prepared, tmp_path):
    experiment, index, _ = prepared
    fill(experiment, index, partial=True)
    before = api.expanded_status(experiment)
    output = tmp_path / "only-complete"
    receipt = api.export_expanded(experiment, output, complete_blocks=True)
    assert receipt["selected_jobs"] == 0 and receipt["selected_blocks"] == []
    assert rows(output / "results.csv") == []
    assert api.expanded_status(experiment)["completed_jobs"] == before["completed_jobs"] == 1
    partial = tmp_path / "all-partial"
    api.export_expanded(experiment, partial)
    assert len(rows(partial / "results.csv")) == 1 and not read(partial / "export.json")["report_ready"]


@pytest.mark.parametrize("field", ("source_sha256", "machine", "packages"))
def test_resume_fingerprint_mismatch_refused_before_attempt(prepared, monkeypatch, field):
    experiment, _, _ = prepared
    original = api._fingerprint
    def changed(artificial):
        value = original(artificial)
        value[field] = {"QA_mutation": "different"}
        return value
    monkeypatch.setattr(api, "_fingerprint", changed)
    with pytest.raises(api.ExpandedError, match="fingerprint"):
        api.resume_expanded(experiment, reason="QA mismatch", stop_starting_at="2099-01-01T00:00:00+00:00")
    assert api.expanded_status(experiment)["attempt_counts"] == {}


@pytest.mark.parametrize("artifact", ("matrix.json", "schedule.json", "experiment.json"))
def test_corrupt_experiment_artifact_refused_without_attempt(prepared, artifact):
    experiment, _, _ = prepared
    path = experiment / artifact
    value = read(path)
    if isinstance(value, list):
        value.reverse()
    else:
        value["qa_corruption"] = True
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(api.ExpandedError):
        api.resume_expanded(experiment, reason="QA tamper", stop_starting_at="2099-01-01T00:00:00+00:00")
    assert api.expanded_status(experiment)["attempt_counts"] == {}


@pytest.mark.parametrize("artifact", ("input", "schema"))
def test_frozen_producer_tamper_is_rejected(produced, tmp_path, artifact):
    copied = tmp_path / "dữ liệu bản sao"
    shutil.copytree(produced["main"], copied)
    if artifact == "schema":
        path = copied / "freeze.json"
        value = read(path); value["schema_version"] = 1
        path.write_text(json.dumps(value), encoding="utf-8")
    else:
        first = json.loads((copied / "manifest.jsonl").read_text(encoding="utf-8").splitlines()[0])
        with (copied / first["input_file"]).open("ab") as stream:
            stream.write(b" ")
    with pytest.raises(api.ExpandedError):
        api.validate_expanded_dataset(copied)


def cli(*args):
    return subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "scripts/run_expanded.py"), *map(str, args)],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20)


def test_real_cli_status_export_and_artificial_run_gate(prepared, tmp_path):
    experiment, _, receipt = prepared
    status = cli("status", "--experiment", experiment, "--json")
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["planned_jobs"] == receipt["planned_jobs"]
    export = cli("export", "--experiment", experiment, "--output", tmp_path / "cli-export")
    assert export.returncode == 0, export.stderr
    blocked = cli("run", "--experiment", experiment, "--stop-starting-at", "2099-01-01T00:00:00+00:00")
    assert blocked.returncode == 2 and "Artificial" in blocked.stderr and "Traceback" not in blocked.stderr
    assert api.expanded_status(experiment)["attempt_counts"] == {}


def test_real_cli_prepare_creates_new_artificial_experiment(produced, prepared, tmp_path):
    experiment = tmp_path / "CLI dữ liệu mới"
    result = cli("prepare", "--dataset", produced["main"], "--experiment", experiment,
                 "--config", ROOT / "configs/expanded/main.json", "--matrix", tmp_path / "matrix.json", "--phase", "main")
    assert result.returncode == 0, result.stderr
    status = cli("status", "--experiment", experiment, "--json")
    assert status.returncode == 0 and json.loads(status.stdout)["completed_jobs"] == 0
    manifest = read(experiment / "experiment.json")
    assert manifest["artificial"] and manifest["phase"] == "main"


def test_public_second_writer_busy_before_attempt_and_readers_allowed(prepared, tmp_path):
    experiment, _, _ = prepared
    with storage.WriterLock(experiment):
        status = cli("status", "--experiment", experiment, "--json")
        assert status.returncode == 0, status.stderr
        blocked = cli("resume", "--experiment", experiment, "--reason", "QA busy writer",
                      "--stop-starting-at", "2099-01-01T00:00:00+00:00")
        assert blocked.returncode == 3 and "Traceback" not in blocked.stderr
    assert api.expanded_status(experiment)["attempt_counts"] == {}


def test_invalid_database_version_refused_by_status(prepared):
    experiment, _, _ = prepared
    db = storage.connect(experiment)
    db.execute("PRAGMA user_version=1")
    db.close()
    with pytest.raises(api.ExpandedError, match="version"):
        api.expanded_status(experiment)


def test_export_refuses_existing_destination_without_overwrite(prepared, tmp_path):
    experiment, _, _ = prepared
    output = tmp_path / "already-exported"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_bytes(b"unchanged")
    with pytest.raises(api.ExpandedError, match="already exists"):
        api.export_expanded(experiment, output)
    assert sentinel.read_bytes() == b"unchanged" and list(output.iterdir()) == [sentinel]

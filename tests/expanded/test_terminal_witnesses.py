"""Witness collector QA: artificial injected workers only; never a solver call."""
import importlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

from sudoku import expanded_data as data
from tests.expanded.reference import full

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def draft_source(tmp_path_factory):
    output = tmp_path_factory.mktemp("artificial-witness-draft")
    sources, receipts = {}, []
    for group in data.GROUPS:
        source = output / f"{group}.txt"
        lines = []
        for ordinal in range(3):
            selected = set(data.ranked(range(81), f"QA|{group}|{ordinal}")[:24+ordinal])
            grid = [[full(3)[r][c] if r*9+c in selected else 0 for c in range(9)] for r in range(9)]
            digits = "".join(str(v) for row in grid for v in row)
            lines.append(f"{data.sha256(digits.encode())[:12]} {digits} 7.500\n")
        source.write_text("".join(lines), encoding="ascii")
        sources[group] = data.parse_public_file(source, group, source_url=f"artificial://qa/{group}")
        receipts.append({"file": source.name, "cache_file": str(source), "dataset_file": "sources/"+source.name,
                         "url": f"artificial://qa/{group}", "sha256": data.sha256(source.read_bytes())})
    old_hashes, _, old_freeze = data.old_dataset_exclusions(ROOT)
    selected, logs = data.select_public(sources, old_hashes, main_per_group=1, pilot_per_group=2)
    bases = {n*n: {"grid": full(n), "file": "ARTIFICIAL-KNOWN-PATTERN",
                    "sha256": data.content_sha256(n, full(n))} for n in (4, 5)}
    paths = data._assemble(output / "datasets", selected, bases, old_hashes, old_freeze,
        artificial=True, main_roots={16:1,25:1}, main_batches=1, public_witness=None,
        provenance={"source_commit": None, "sources": receipts, "license_reference": None,
                    "note": "ARTIFICIAL QA sources, no download/solve"}, dedup_log=logs,
        checked_utc="2026-10-19T00:00:00+00:00", inputs_only=True)
    return Path(paths["main"])


@pytest.fixture
def witness(draft_source, tmp_path, monkeypatch):
    w = importlib.import_module("sudoku.expanded_witnesses")
    from sudoku import sat, baselines, runner
    def forbidden(*args, **kwargs):
        raise AssertionError("Real solver or production run_job forbidden in collector QA")
    for module, names in ((sat, ("solve_sat", "prepare_backend")),
                          (baselines, ("solve_baseline", "prepare_backend")), (runner, ("run_job",))):
        for name in names: monkeypatch.setattr(module, name, forbidden)
    directory = tmp_path / "DRAFT dữ liệu"
    shutil.copytree(draft_source, directory)
    return w, directory, tmp_path / "evidence", tmp_path / "finalized"


def fake_worker(calls, status="SAT", bad=False):
    def worker(job, config, **kwargs):
        calls.append(job["instance_id"])
        assert config.cutoff_seconds == job["cutoff_seconds"] == 30.0
        assert job["scope"] == "expanded-witness-acquisition-not-benchmark"
        result = {"status": status, "method": "sat", "encoding": "pairwise",
                  "raw_status": "ARTIFICIAL_QA_NOT_A_SOLVER", "guard_phase": "complete"}
        if status == "SAT":
            result.update(solution=[[1]*9 for _ in range(9)] if bad else full(3),
                          validation={"valid": True}, build_seconds=0.1, solve_seconds=0.2, total_seconds=0.3)
        elif status == "TIMEOUT": result["guard_phase"] = "measurement"
        return result
    return worker


def test_default_dryrun_has_zero_workers_and_creates_no_checkpoint(witness):
    w, directory, evidence, output = witness
    result = w.complete_witnesses(directory, evidence, output)
    assert result["state"] == "DRY_RUN" and result["solver_calls"] == 0
    assert result["public_inputs"] == 4 and not evidence.exists() and not output.exists()


def test_artificial_execution_without_private_worker_is_refused(witness):
    w, directory, evidence, output = witness
    with pytest.raises(w.WitnessError, match="artificial"):
        w.complete_witnesses(directory, evidence, output, execute=True)
    assert not evidence.exists() and not output.exists()


def test_fake_worker_finalize_preserves_exact_ids_and_resume_never_reexecutes_sat(witness):
    w, directory, evidence, output = witness
    calls = []
    worker = fake_worker(calls)
    before = data._read_jsonl(directory / "manifest.jsonl")
    result = w.complete_witnesses(directory, evidence, output, execute=True, _run_job=worker)
    expected = [r["instance_id"] for r in before if r["source"] == "sudoku_exchange"]
    assert result["state"] == "COMPLETE" and result["verified_sat"] == 4 and calls == expected
    after = data._read_jsonl(output / "manifest.jsonl")
    assert [(r["instance_id"],r["input_sha256"]) for r in before] == [(r["instance_id"],r["input_sha256"]) for r in after]
    assert (directory / "batches.json").read_bytes() == (output / "batches.json").read_bytes()
    assert data.read_json(output / "dataset.json")["artificial"] is True
    assert not (directory / "freeze.json").exists()
    repeated = w.complete_witnesses(directory, evidence, output, execute=True, _run_job=worker)
    assert repeated["state"] == "COMPLETE" and repeated["reused_output"] and calls == expected


@pytest.mark.parametrize("point", ("after_raw_log", "before_result_commit", "after_result_commit"))
def test_durable_sat_after_interrupt_is_adopted_without_second_worker(witness, point):
    w, directory, evidence, output = witness
    calls = []
    worker = fake_worker(calls)
    def interrupt(stage, attempt):
        if stage == point: raise KeyboardInterrupt("artificial fault point")
    first = w.complete_witnesses(directory, evidence, output, execute=True, _run_job=worker, _hook=interrupt)
    assert first["state"] == "PAUSED" and len(calls) == 1
    second = w.complete_witnesses(directory, evidence, output, execute=True, _run_job=worker)
    assert second["state"] == "COMPLETE" and len(calls) == len(set(calls)) == 4


@pytest.mark.parametrize("status", ("TIMEOUT", "ERROR", "UNSAT", "UNAVAILABLE", "LICENSE_LIMIT"))
def test_terminal_failure_retained_not_retried_or_finalized(witness, status):
    w, directory, evidence, output = witness
    calls = []; worker = fake_worker(calls, status)
    first = w.complete_witnesses(directory, evidence, output, execute=True, _run_job=worker)
    second = w.complete_witnesses(directory, evidence, output, execute=True, _run_job=worker)
    assert first["state"] == second["state"] == "HALTED" and len(calls) == 1
    assert second["admitted_status_counts"] == {status:1} and not output.exists()


def test_checker_rejects_false_sat_without_output(witness):
    w, directory, evidence, output = witness
    calls = []
    result = w.complete_witnesses(directory, evidence, output, execute=True, _run_job=fake_worker(calls, bad=True))
    assert result["state"] == "HALTED" and result["admitted_status_counts"] == {"ERROR":1}
    assert len(calls) == 1 and not output.exists()


@pytest.mark.parametrize("tamper", ("fingerprint", "input_order", "input_hash", "raw_hash"))
def test_resume_refuses_hash_or_exact_plan_mutation(witness, monkeypatch, tamper):
    w, directory, evidence, output = witness
    calls = []; worker = fake_worker(calls)
    def pause(stage, attempt):
        if stage == "after_result_commit": raise KeyboardInterrupt()
    assert w.complete_witnesses(directory, evidence, output, execute=True, _run_job=worker, _hook=pause)["state"] == "PAUSED"
    if tamper == "fingerprint":
        original = w._fingerprint
        def changed(*args, **kwargs):
            value = original(*args, **kwargs); value["code_sha256"] = {"changed": "0"*64}; return value
        monkeypatch.setattr(w, "_fingerprint", changed)
    elif tamper == "raw_hash":
        with next((evidence / "attempts").glob("*/result.json")).open("ab") as stream: stream.write(b" ")
    else:
        db = sqlite3.connect(evidence / "witnesses.sqlite3")
        db.execute("UPDATE inputs SET ordinal=ordinal+100" if tamper == "input_order" else "UPDATE inputs SET input_sha256=?", () if tamper == "input_order" else ("0"*64,))
        db.commit(); db.close()
    with pytest.raises(w.WitnessError):
        w.complete_witnesses(directory, evidence, output, execute=True, _run_job=worker)
    assert len(calls) == 1 and not output.exists()


def test_live_collector_lock_is_not_stolen(witness):
    w, directory, evidence, output = witness
    evidence.mkdir()
    with w.WitnessWriterLock(evidence):
        with pytest.raises(w.WitnessError) as caught:
            w.complete_witnesses(directory, evidence, output, execute=True, _run_job=fake_worker([]))
        assert caught.value.exit_code == 3
    assert not (evidence / "witnesses.sqlite3").exists() and not output.exists()


def test_launched_interruption_requires_explicit_truthful_artificial_cleanup(witness):
    w, directory, evidence, output = witness
    calls = []
    normal = fake_worker(calls)
    interrupted = []
    def worker(*args, **kwargs):
        if not interrupted:
            interrupted.append(True)
            raise KeyboardInterrupt("ARTIFICIAL worker; no process was launched")
        return normal(*args, **kwargs)
    assert w.complete_witnesses(directory, evidence, output, execute=True, _run_job=worker)["state"] == "PAUSED"
    with pytest.raises(w.WitnessError, match="unknown.*cleanup"):
        w.complete_witnesses(directory, evidence, output, execute=True, _run_job=worker)
    with pytest.raises(w.WitnessError, match="--reason"):
        w.complete_witnesses(directory, evidence, output, execute=True, _run_job=worker,
                             resume_interrupted=True, reason=None)
    assert calls == []
    result = w.complete_witnesses(directory, evidence, output, execute=True, _run_job=worker,
        resume_interrupted=True, reason="ARTIFICIAL fixture: no process existed; explicit private recovery test")
    assert result["state"] == "COMPLETE" and result["interrupted_attempts"] == 1 and len(calls) == 4


@pytest.mark.parametrize("mutation", ("missing", "duplicate", "reordered"))
def test_finalizer_rejects_nonexact_id_sets_without_publishing(witness, mutation):
    w, directory, evidence, output = witness
    assert w.complete_witnesses(directory, evidence, output, execute=True, _run_job=fake_worker([]))["state"] == "COMPLETE"
    proof = data.read_json(evidence / "public-evidence.json")
    if mutation == "missing": proof["records"].pop()
    elif mutation == "duplicate": proof["records"][1] = dict(proof["records"][0])
    else: proof["records"].reverse()
    target = output.with_name("must-not-finalize")
    with pytest.raises(data.DataError, match="exact locked public ID order"):
        data.finalize_staged_inputs(directory, target, proof)
    assert not target.exists()


def test_cli_default_dryrun_is_safe_and_explicit_execute_rejects_artificial(witness):
    _, directory, evidence, output = witness
    command = [sys.executable, "-B", "-X", "utf8", str(ROOT / "scripts/complete_expanded_witnesses.py"),
               "--dataset", str(directory), "--evidence-dir", str(evidence), "--output", str(output)]
    dry = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert dry.returncode == 0, dry.stderr
    assert json.loads(dry.stdout)["state"] == "DRY_RUN" and not evidence.exists() and not output.exists()
    blocked = subprocess.run(command+["--execute"], capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert blocked.returncode == 2 and "artificial" in blocked.stderr and "Traceback" not in blocked.stderr

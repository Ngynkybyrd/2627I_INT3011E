"""Independent conditional-gate tests. No real release/root gate is written.

Positive predicates use an artificial isolated root and private verifier injection.
No CLI flag or production source is changed to bypass research admission.
"""
from contextlib import nullcontext
import hashlib
import importlib
import json
from pathlib import Path

import pytest


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def gates(monkeypatch):
    g = importlib.import_module("sudoku.expanded_local_gates")
    from sudoku import sat, baselines, runner
    def forbidden(*args, **kwargs):
        raise AssertionError("Auditor must not import/start solver or worker")
    for module, names in ((sat, ("prepare_backend", "solve_sat")),
                          (baselines, ("prepare_backend", "solve_baseline")), (runner, ("run_job",))):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    return g


@pytest.fixture
def private_release(gates, tmp_path, monkeypatch):
    # Fictional authority only for private predicate tests; never the real
    # diagnostics/expansion/root-wave3/code-release.json or actual root receipts.
    source = tmp_path / "artificial-source.txt"
    source.write_bytes(b"ARTIFICIAL UNIT NOT RELEASED CODE")
    xml = tmp_path / "artificial-regression.xml"
    xml.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="artificial-unit"/></testsuite>', encoding="utf-8")
    relative = lambda p: str(p.relative_to(gates.ROOT)).replace("\\", "/")
    authority = tmp_path / "artificial-authority-unit.json"
    payload = {"schema_version": 2, "status": "PASS", "approved_explicit_terminal_execution": True,
               "protected_execution_files": 32, "protected_data_files": 169, "existing_two_pdfs_unchanged": True,
               "source_sha256": {relative(source): sha(source)},
               "regression": {"scope": "full", "path": relative(xml), "sha256": sha(xml), "tests": 1}}
    write(authority, payload)
    monkeypatch.setattr(gates, "RELEASE_PATH", authority)
    monkeypatch.setattr(gates, "release_source_paths", lambda: [relative(source)])
    return authority, payload, source, xml


def test_private_release_predicates_pass_on_explicit_artificial_unit(gates, private_release):
    authority, _, _, _ = private_release
    receipt = gates._release(authority)
    assert receipt["regression"]["tests"] == 1 and receipt["regression"]["scope"] == "full"


@pytest.mark.parametrize("mutation", ("approval", "schema", "status", "source_coverage", "source_hash", "missing_source", "xml_hash", "count", "partial_scope"))
def test_private_release_refuses_fake_or_incomplete_evidence(gates, private_release, mutation):
    authority, payload, source, _ = private_release
    if mutation == "approval": payload["approved_explicit_terminal_execution"] = False
    elif mutation == "schema": payload["schema_version"] = 1
    elif mutation == "status": payload["status"] = "FAIL"
    elif mutation == "source_coverage": payload["source_sha256"] = {}
    elif mutation == "source_hash": source.write_bytes(b"CHANGED")
    elif mutation == "missing_source": source.unlink()
    elif mutation == "xml_hash": payload["regression"]["sha256"] = "0"*64
    elif mutation == "count": payload["regression"]["tests"] = 2
    elif mutation == "partial_scope": payload["regression"]["scope"] = "targeted"
    write(authority, payload)
    with pytest.raises((gates.ExpandedError, OSError)):
        gates._release(authority)


@pytest.mark.parametrize("xml_text", (
    '<testsuite tests="1"><testcase name="x"><failure/></testcase></testsuite>',
    '<testsuite tests="1"><testcase name="x"><error/></testcase></testsuite>',
    '<testsuite tests="1"><testcase name="x"><skipped/></testcase></testsuite>',
    '<testsuite tests="1"><testcase name="x"><skipped type="pytest.xfail"/></testcase></testsuite>',
    '<testsuite tests="1" errors="1"><testcase name="x"/></testsuite>',
    '<testsuite tests="1" skipped="1"><testcase name="x"/></testsuite>',
    '<testsuite tests="0"/>', '<not-valid-xml',
))
def test_real_xml_predicate_refuses_failure_skip_xfail_or_hidden_setup_error(gates, private_release, xml_text):
    authority, payload, _, xml = private_release
    xml.write_text(xml_text, encoding="utf-8")
    payload["regression"]["sha256"] = sha(xml)
    write(authority, payload)
    with pytest.raises(gates.ExpandedError):
        gates._release(authority)


def test_private_release_wrong_subject_path_is_refused(gates, private_release, tmp_path):
    authority, payload, _, _ = private_release
    other = tmp_path / "other-authority.json"
    write(other, payload)
    with pytest.raises(gates.ExpandedError, match="root wave3"):
        gates._release(other)


@pytest.mark.parametrize("artificial,phase,pilot", ((True, "pilot", None), (False, "other", None),
                                                   (False, "main", None), (False, "pilot", "wrong-pilot")))
def test_public_authorizer_refuses_artificial_or_wrong_phase_before_release(gates, tmp_path, monkeypatch, artificial, phase, pilot):
    directory = tmp_path / "experiment"
    directory.mkdir()
    write(directory / "experiment.json", {"artificial": artificial, "phase": phase})
    monkeypatch.setattr(gates, "_release", lambda path: (_ for _ in ()).throw(AssertionError("release must not be reached")))
    with pytest.raises(gates.ExpandedError):
        gates.authorize_expanded_local(directory, tmp_path / "missing", pilot_experiment=pilot)
    assert list(directory.iterdir()) == [directory / "experiment.json"]


class FakeCursor:
    def __init__(self, row=None): self.row = row
    def fetchone(self): return self.row


class PilotPredicateDB:
    def __init__(self, state, unfinished): self.state, self.unfinished = state, unfinished
    def execute(self, query):
        if "SELECT state FROM experiment" in query: return FakeCursor((self.state,))
        if "FROM jobs WHERE state!=" in query: return FakeCursor((1,) if self.unfinished else None)
        return FakeCursor()
    def close(self): pass


@pytest.mark.parametrize("mutation", ("artificial", "phase", "matrix", "environment", "partial", "unfinished"))
def test_private_pilot_predicate_rejects_wrong_subject_environment_or_partial(gates, tmp_path, monkeypatch, mutation):
    main = {"matrix": {"rows": []}, "fingerprint": {"source": "unit"}}
    pilot = {"phase": "pilot", "artificial": False, **main}
    if mutation == "artificial": pilot["artificial"] = True
    elif mutation == "phase": pilot["phase"] = "main"
    elif mutation == "matrix": pilot["matrix"] = {"rows": ["different"]}
    elif mutation == "environment": pilot["fingerprint"] = {"source": "different"}
    db = PilotPredicateDB("PAUSED" if mutation == "partial" else "COMPLETED", mutation == "unfinished")
    monkeypatch.setattr(gates.storage, "WriterLock", lambda path: nullcontext())
    monkeypatch.setattr(gates.storage, "connect", lambda *args, **kwargs: db)
    monkeypatch.setattr(gates, "_load", lambda *args, **kwargs: (pilot, {}))
    monkeypatch.setattr(gates, "_gates", lambda *args: (_ for _ in ()).throw(AssertionError("rejected pilot reached gate receipts")))
    with pytest.raises(gates.ExpandedError):
        gates._pilot_audit(tmp_path, main, {}, {})


def test_pilot_expected_jobs_uses_matrix_not_claimed_count(gates):
    rows = [{"N": N, "eligible": i < (8 if N == 9 else 5)} for N in (9, 16, 25) for i in range(8)]
    assert gates.manifest_pilot_job_count({"rows": rows}) == 164


@pytest.fixture
def collector_root_receipt(gates, tmp_path):
    from sudoku import expanded_witnesses as witnesses
    # Mirror the stronger root receipt: expanded artifacts + tests + all 32
    # execution-frozen paths in source_sha256, with separate freeze checking.
    paths = set(gates.release_source_paths()) | {
        str(p.relative_to(gates.ROOT)).replace("\\", "/") for p in (gates.ROOT / "tests").rglob("*.py")}
    freeze = json.loads((gates.ROOT / "results/raw/main-20261016-01/execution-freeze.json").read_text(encoding="utf-8"))
    assert len(freeze["files_sha256"]) == 32
    for path, expected in freeze["files_sha256"].items():
        assert sha(gates.ROOT / path) == expected
        paths.add(path.replace("\\", "/"))
    payload = {"schema_version":2, "status":"PASS", "approved_explicit_terminal_execution":True,
               "protected_execution_files":32, "protected_data_files":169, "existing_two_pdfs_unchanged":True,
               "source_sha256": {path:sha(gates.ROOT / path) for path in sorted(paths)},
               "scope":"ARTIFICIAL private root-shaped receipt; never actual release"}
    authority = tmp_path / "ARTIFICIAL-root-shaped-unit-authority.json"
    write(authority, payload)
    return witnesses, authority, payload


def test_collector_accepts_root_verifier_source_map_plus_protected_v1(gates, collector_root_receipt):
    witnesses, authority, _ = collector_root_receipt
    assert witnesses._release(gates.ROOT, authority)


@pytest.mark.parametrize("guard", ("runner.py", "runner_process.py", "runner_worker.py", "sat.py",
                                   "model.py", "validation.py", "decoding.py", "contracts.py"))
def test_collector_rejects_missing_protected_guard_dependency(gates, collector_root_receipt, guard):
    witnesses, authority, payload = collector_root_receipt
    del payload["source_sha256"]["src/sudoku/"+guard]
    write(authority, payload)
    with pytest.raises(witnesses.WitnessError, match="collector/guard dependencies"):
        witnesses._release(gates.ROOT, authority)


def test_collector_rejects_changed_protected_guard_hash(gates, collector_root_receipt):
    witnesses, authority, payload = collector_root_receipt
    payload["source_sha256"]["src/sudoku/runner.py"] = "0"*64
    write(authority, payload)
    with pytest.raises(witnesses.WitnessError, match="source changed"):
        witnesses._release(gates.ROOT, authority)


@pytest.fixture
def isolated_public_authority(gates, tmp_path, monkeypatch):
    """Private predicate injection into an artificial root; no CLI/research bypass."""
    root = tmp_path / "ARTIFICIAL-ROOT-NOT-PROJECT"
    root.mkdir()
    directory = root / "unit-experiment"
    directory.mkdir()
    monkeypatch.setattr(gates, "ROOT", root)
    release = {"path": "FICTIONAL-PRIVATE-VERIFIER", "sha256": "b"*64,
               "regression": {"tests": 1, "scope": "artificial unit, not actual release"}}
    monkeypatch.setattr(gates, "_release", lambda path: release)
    monkeypatch.setattr(gates, "_preflight", lambda manifest: {"unit_only": True, "native_files_checked": 0})
    class PreparedDB:
        def execute(self, query):
            if "SELECT state" in query: return FakeCursor(("PREPARED",))
            if "COUNT(*)" in query: return FakeCursor((0,))
            return FakeCursor()
        def close(self): pass
    monkeypatch.setattr(gates.storage, "connect", lambda *args, **kwargs: PreparedDB())
    monkeypatch.setattr(gates, "_pilot_audit", lambda *args: {"pilot_scientific_sha256": "d"*64, "unit_only": True})
    return root, directory, release


@pytest.mark.parametrize("phase", ("pilot", "main"))
def test_private_positive_receipts_bind_subject_hashes_and_never_claim_cleanup(gates, isolated_public_authority, monkeypatch, phase):
    root, directory, release = isolated_public_authority
    manifest = {"experiment_id": "ARTIFICIAL-UNIT-"+phase, "phase": phase, "artificial": False,
                "scientific_sha256": ("a" if phase == "pilot" else "c")*64,
                "gate_refs_path": "unit-gates/subject.json"}
    write(directory / "experiment.json", manifest)
    index = {"dataset_id": "FICTIONAL-UNIT", "dataset_dir": str(directory / "FICTIONAL-DATASET"),
             "freeze_sha256": "f"*64, "counts": {"unit":1}}
    monkeypatch.setattr(gates, "_load", lambda *args: (manifest, index))
    def private_verify(subject):
        path = root / subject["gate_refs_path"]
        gate = json.loads(path.read_text())
        assert gate["experiment_id"] == subject["experiment_id"]
        assert gate["scientific_sha256"] == subject["scientific_sha256"]
        assert gate["code_release"]["sha256"] == release["sha256"]
        for name, ref in gate["gates"].items():
            receipt = root / ref["path"]
            assert sha(receipt) == ref["sha256"]
            body = json.loads(receipt.read_text())
            assert body["experiment_id"] == subject["experiment_id"]
            assert body["scientific_sha256"] == subject["scientific_sha256"]
            assert "cleanup_verified" not in body
        return {"path": subject["gate_refs_path"], "sha256": sha(path), "gates": gate["gates"]}
    monkeypatch.setattr(gates, "_gates", private_verify)
    result = gates.authorize_expanded_local(directory, "PRIVATE-INJECTED-NOT-A-RELEASE",
                                            pilot_experiment="FICTIONAL-PILOT" if phase == "main" else None)
    assert result["solver_calls"] == 0 and result["phase"] == phase
    gate = json.loads((root / manifest["gate_refs_path"]).read_text())
    expected = {"dataset", "qa", "preflight"} | ({"pilot", "execution_freeze"} if phase == "main" else set())
    assert set(gate["gates"]) == expected and "recovery_cleanup" not in gate["gates"]


def test_release_changed_before_publication_never_publishes_gate(gates, isolated_public_authority, monkeypatch):
    root, directory, release = isolated_public_authority
    manifest = {"experiment_id": "ARTIFICIAL-UNIT", "phase": "pilot", "artificial": False,
                "scientific_sha256": "a"*64, "gate_refs_path": "unit-gates/subject.json"}
    write(directory / "experiment.json", manifest)
    monkeypatch.setattr(gates, "_load", lambda *args: (manifest, {"dataset_id":"unit", "dataset_dir":str(directory / "FICTIONAL-DATASET"), "freeze_sha256":"f"*64, "counts":{}}))
    calls = []
    def changing_authority(path):
        calls.append(path)
        return release if len(calls) == 1 else {**release, "sha256":"0"*64}
    monkeypatch.setattr(gates, "_release", changing_authority)
    with pytest.raises(gates.ExpandedError, match="changed during audit"):
        gates.authorize_expanded_local(directory, "PRIVATE-INJECTED-NOT-RELEASE")
    assert len(calls) == 2 and not (root / manifest["gate_refs_path"]).exists()

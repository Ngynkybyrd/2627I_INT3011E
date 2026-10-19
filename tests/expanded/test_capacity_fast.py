"""Fast variant delta checks; no solver or research preflight execution."""
import ast
import importlib.util
from pathlib import Path
import sqlite3

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    path = ROOT/"scripts"/(name+".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fast_capacity_cache_precedes_load_and_retains_all_deep_checks():
    path = ROOT/"scripts/run_expanded_capacity_fast.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    run = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run")
    writer = next(node for node in ast.walk(run) if isinstance(node, ast.With) and "WriterLock" in ast.unparse(node.items[0].context_expr))
    assert ast.unparse(writer.body[0]) == "db = storage.connect(directory)"
    assert ast.unparse(writer.body[1]) == "db.execute('PRAGMA cache_size=-262144')"
    load_calls = [node for node in ast.walk(writer) if isinstance(node, ast.Call) and ast.unparse(node.func) == "api._load"]
    assert len(load_calls) == 1 and not load_calls[0].keywords
    assert writer.body[1].lineno < load_calls[0].lineno
    text = path.read_text(encoding="utf-8-sig")
    assert 'file=sys.stderr, flush=True' in text
    assert "preflight start" in text and "preflight complete" in text


def test_cache_budget_applies_to_readonly_connection_without_database_mutation(tmp_path):
    path = tmp_path/"small.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY,value TEXT)")
    connection.executemany("INSERT INTO sample(value) VALUES(?)", [(str(i),) for i in range(100)])
    connection.commit()
    connection.close()
    before = path.read_bytes()
    connection = sqlite3.connect(path.as_uri()+"?mode=ro", uri=True)
    connection.execute("PRAGMA cache_size=-262144")
    assert connection.execute("PRAGMA cache_size").fetchone()[0] == -262144
    assert connection.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 100
    connection.close()
    assert path.read_bytes() == before


def test_fast_ramp_exact_requested_ladder_stage_budget_and_coordinator_binding():
    ramp = load("run_capacity_ramp_fast")
    manifest = dict(experiment_id="test", scientific_sha256="a"*64)
    subject = ramp.policy_subject(manifest)
    assert ramp.LADDER == subject["allowed_ladder"] == [8, 24, 40]
    assert subject["stage_jobs"] == 160
    assert subject["profile"] == "capacity-ramp-fast-v1"
    assert ramp.COORDINATOR.name == "run_expanded_capacity_fast.py"
    assert subject["coordinator_sha256"] == ramp.capacity.sha(ramp.COORDINATOR)
    assert ramp.capacity.PROFILE == "parallel-throughput-capacity-fast-v1"
    text = (ROOT/"scripts/run_capacity_ramp_fast.py").read_text(encoding="utf-8-sig")
    assert "stage_jobs=320" not in text and "stage_jobs=160" in text


def test_fast_policy_rejects_old_ladder_and_old_stage_budget(tmp_path, monkeypatch):
    ramp = load("run_capacity_ramp_fast")
    monkeypatch.setattr(ramp, "ROOT", tmp_path)
    manifest = dict(experiment_id="test", scientific_sha256="a"*64)
    path = tmp_path/"policy.json"
    for key, wrong in (("allowed_ladder", [8, 16, 24, 32, 40, 56, 72, 100]), ("stage_jobs", 320)):
        subject = ramp.policy_subject(manifest)
        subject[key] = wrong
        ramp.capacity.write(path, subject)
        with pytest.raises(ramp.capacity.ExpandedError, match="subject mismatch"):
            ramp.verify_policy(manifest, path, ramp.capacity.sha(path))

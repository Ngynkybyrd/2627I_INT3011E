"""Exact-error recovery policy; no solver or live experiment access."""
import importlib.util
import json
import sqlite3
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("handle_recovery",ROOT/"scripts/run_expanded_capacity_recovery.py")
import sys
sys.path.insert(0,str(ROOT/"scripts"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

@pytest.fixture
def db(tmp_path,monkeypatch):
    c=sqlite3.connect(":memory:");c.row_factory=sqlite3.Row
    c.executescript("CREATE TABLE experiment(experiment_id,manifest_json,state,halt_reason);CREATE TABLE attempts(attempt_id,job_id,state);CREATE TABLE results(attempt_id,status,result_json);CREATE TABLE sessions(ended_utc);CREATE TABLE events(type);")
    c.execute("INSERT INTO experiment(experiment_id,manifest_json,state) VALUES(?,?,?)",("example",json.dumps({"scientific_sha256":"x"}),"HALTED"))
    result=dict(status="ERROR",guard_phase="guard",error="OSError: [WinError 6] The handle is invalid",build_seconds=None,solve_seconds=None,total_seconds=None,validation=None)
    raw=json.dumps(result)
    c.execute("INSERT INTO attempts VALUES('a','j','FINISHED')")
    c.execute("INSERT INTO results VALUES('a','ERROR',?)",(raw,))
    ack=dict(accepted_by="root",accepted=True,experiment_id="example",scientific_sha256="x",acknowledged_fatal_results=[dict(attempt_id="a",job_id="j",status="ERROR",result_json=raw)])
    path=tmp_path/"ack.json";path.write_text(json.dumps(ack),encoding="utf-8")
    monkeypatch.setattr(m,"RECOVERY_RECEIPT",path);monkeypatch.setattr(m,"RECOVERY_SHA256",m.sha(path))
    yield c
    c.close()

def test_exact_error_is_preserved_and_closed_halted_run_can_resume(db):
    before=list(db.execute("SELECT * FROM results"))[0]
    m.check_resumable(db)
    assert tuple(db.execute("SELECT * FROM results").fetchone())==tuple(before)
    assert db.execute("SELECT state FROM experiment").fetchone()[0]=="HALTED"

@pytest.mark.parametrize("table,sql",[("attempts","INSERT INTO attempts VALUES('b','j2','RUNNING')"),("sessions","INSERT INTO sessions VALUES(NULL)"),("events","INSERT INTO events VALUES('REJECTED_OBSERVATION')"),("results","INSERT INTO attempts VALUES('b','j2','FINISHED'); INSERT INTO results VALUES('b','ERROR','{}')")])
def test_unresolved_or_new_fatal_blocks_resume(db,table,sql):
    db.executescript(sql)
    with pytest.raises(m.ExpandedError):m.check_resumable(db)

def test_acknowledgment_is_hash_bound(db):
    m.RECOVERY_RECEIPT.write_text("{}",encoding="utf-8")
    with pytest.raises(m.ExpandedError,match="changed"):m.check_resumable(db)

def test_changed_raw_error_blocks_resume(db):
    db.execute("UPDATE results SET result_json='{}'")
    with pytest.raises(m.ExpandedError,match="Unacknowledged"):m.check_resumable(db)

def test_completed_state_cannot_be_resumed(db):
    db.execute("UPDATE experiment SET state='COMPLETED'")
    with pytest.raises(m.ExpandedError):m.check_resumable(db)


def test_final_receipt_is_explicitly_completed_with_preserved_error(db,tmp_path,monkeypatch):
    db.executescript("CREATE TABLE jobs(job_id,repetition,instance_id);CREATE TABLE primary_attempt(job_id,attempt_id);CREATE TABLE instances(instance_id,batch_id);ALTER TABLE attempts ADD COLUMN session_id;UPDATE attempts SET session_id='s1';INSERT INTO jobs VALUES('j',1,'i');INSERT INTO primary_attempt VALUES('j','a');INSERT INTO instances VALUES('i','b');")
    (tmp_path/"session-manifests").mkdir()
    (tmp_path/"session-manifests/s1.json").write_text(json.dumps(dict(profile="old",timing_policy="resource-contended")))
    loaded=[]
    monkeypatch.setattr(m.api,"_load",lambda directory,connection:loaded.append(True))
    monkeypatch.setattr(m.storage,"event",lambda *args,**kwargs:None)
    manifest=dict(experiment_id="example",scientific_sha256="x",config=dict(repetitions=3))
    scope=dict(selected_repetitions=[1],target_jobs=1,effective_repetitions=1,original_manifest_repetitions=3)
    m.finalize_scope(tmp_path,db,"newsession",manifest,scope,1)
    receipt=json.loads((tmp_path/"scope-completions/newsession.json").read_text())
    assert loaded==[True]
    assert receipt["scope_state"]=="COMPLETED_WITH_ERROR"
    assert receipt["error_free"] is False
    assert receipt["preserved_errors"][0]["attempt_id"]=="a"
    assert db.execute("SELECT state FROM experiment").fetchone()[0]=="HALTED"
    assert db.execute("SELECT status FROM results").fetchone()[0]=="ERROR"

"""Focused in-memory rolling exporter tests; no benchmark/solver or real backup."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import uuid

import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("rolling_export",ROOT/"scripts/export_expanded_rolling.py")
rolling=importlib.util.module_from_spec(spec); spec.loader.exec_module(rolling)
from sudoku.model import Puzzle


def observation():
    grid=[[1,2,3,4],[3,4,1,2],[2,1,4,3],[4,3,2,1]]
    puzzle=Puzzle(2,grid); aid=str(uuid.uuid4())
    payload=rolling.canonical(2,grid)
    result=dict(status="SAT",method="cpsat",encoding=None,build_seconds=.1,solve_seconds=.2,total_seconds=.3,
        guard_phase="complete",validation=dict(valid=True),raw_status="OPTIMAL",stats=None,error=None)
    row=dict(job_id="fake-job",attempt_job_id="fake-job",attempt_id=aid,primary_attempt_id=aid,attempt_no=1,
        attempt_state="FINISHED",job_state="TERMINAL",method="cpsat",encoding="",status="SAT",
        attempt_wall_seconds=.4,started_utc="2026-10-19T00:00:00+00:00",ended_utc="2026-10-19T00:00:01+00:00",
        result_json=rolling.packed(result),payload=payload,solution_hash=rolling.digest(payload),solution_attempt_id=aid,checker_json=rolling.packed(result["validation"]))
    return row,dict(n=2,N=4,actual_clues=16),puzzle,result


def test_independent_sat_witness_passes_without_receipt():
    row,record,puzzle,_=observation()
    assert rolling.check_observation(row,record,puzzle)["status"]=="SAT"


@pytest.mark.parametrize("failure",["missing_primary","wrong_job","unfinished","wrong_identity","nonfinite","timing_sum","over_cutoff","cleanup","checker","blob_hash","grid","fatal","raw_replay"])
def test_bad_selected_observation_cannot_be_published(failure):
    row,record,puzzle,result=observation()
    if failure=="missing_primary": row["primary_attempt_id"]=None
    if failure=="wrong_job": row["attempt_job_id"]="other"
    if failure=="unfinished": row["attempt_state"]="RUNNING"
    if failure=="wrong_identity": result["method"]="highs"
    if failure=="nonfinite": result["solve_seconds"]=float("nan")
    if failure=="timing_sum": result["total_seconds"]=.4
    if failure=="over_cutoff": result.update(build_seconds=1.,solve_seconds=10.,total_seconds=11.)
    if failure=="cleanup": result["guard_phase"]="cleanup"
    if failure=="checker": result["validation"]["valid"]=False
    if failure=="blob_hash": row["solution_hash"]="wrong"
    if failure=="grid":
        row["payload"]=rolling.canonical(2,[[1]*4 for _ in range(4)]); row["solution_hash"]=rolling.digest(row["payload"])
    if failure=="fatal": row["status"]=result["status"]="UNSAT"
    if failure=="raw_replay": result["raw_status"]="ARTIFICIAL FIXTURE"
    row["result_json"]=json.dumps(result)
    with pytest.raises((rolling.RollingError,ValueError)):
        rolling.check_observation(row,record,puzzle)


def test_timeout_is_kept_without_invented_timing_or_witness():
    row,record,puzzle,result=observation()
    row.update(status="TIMEOUT",payload=None,solution_hash=None,solution_attempt_id=None,checker_json=None)
    result.update(status="TIMEOUT",build_seconds=None,solve_seconds=None,total_seconds=None,guard_phase="measurement",validation=None)
    row["result_json"]=rolling.packed(result)
    checked=rolling.check_observation(row,record,puzzle)
    assert checked["status"]=="TIMEOUT" and checked["total_seconds"] is None
    row["payload"]=b"{}"
    with pytest.raises(rolling.RollingError): rolling.check_observation(row,record,puzzle)


@pytest.mark.parametrize("encoding,aux,amo",[("pairwise",0,6),("seqcounter",3,8),("bitwise",2,8)])
def test_cnf_counts_are_independently_checked(encoding,aux,amo):
    row,record,puzzle,result=observation()
    row.update(method="sat",encoding=encoding)
    result.update(method="sat",encoding=encoding,stats=dict(primary_variables=64,auxiliary_variables=64*aux,total_variables=64+64*aux,clauses=64*(1+amo)+16))
    row["result_json"]=rolling.packed(result)
    assert rolling.check_observation(row,record,puzzle)["status"]=="SAT"
    result["stats"]["clauses"]+=1; row["result_json"]=rolling.packed(result)
    with pytest.raises(rolling.RollingError): rolling.check_observation(row,record,puzzle)


def test_profiles_remain_separate():
    assert rolling.describe_profile({})==("original-sequential",1,"sequential")
    assert rolling.describe_profile(dict(profile="parallel-throughput-v1",workers=4,timing_policy="resource-contended",reporting_policy="separate-by-session"))==("parallel-throughput-v1",4,"resource-contended")


@pytest.mark.parametrize("metadata",[dict(workers=4),dict(profile="unknown"),dict(profile="parallel-throughput-v1",workers=1,timing_policy="resource-contended",reporting_policy="separate-by-session"),dict(profile="parallel-throughput-v1",workers=4,timing_policy="isolated",reporting_policy="separate-by-session")])
def test_ambiguous_or_mislabeled_profile_rejected(metadata):
    with pytest.raises(rolling.RollingError): rolling.describe_profile(metadata)


def test_reject_artificial_before_backup_or_destination_creation(tmp_path,monkeypatch):
    exp=tmp_path/"fake"; exp.mkdir(); out=tmp_path/"output"
    rolling.write(exp/"experiment.json",dict(schema_version=2,artificial=True))
    rolling.write(exp/"dataset-index.json",dict(schema_version=2,artificial=True))
    monkeypatch.setattr(rolling.sqlite3,"connect",lambda *_a,**_k:pytest.fail("Must not backup an artificial experiment"))
    with pytest.raises(rolling.RollingError,match="Artificial"): rolling.export_rolling(exp,out)
    assert not out.exists() and not list(tmp_path.glob("output.incomplete-*"))


def test_export_fields_preserve_core_and_add_profile_columns():
    assert rolling.FIELDS[:len(rolling.CSV_FIELDS)]==rolling.CSV_FIELDS
    assert rolling.FIELDS[-4:]==["session_id","profile","workers","timing_policy"]


def test_failed_snapshot_verification_never_leaves_pass_receipt(tmp_path,monkeypatch):
    exp=tmp_path/"fake"; exp.mkdir(); out=tmp_path/"output"
    rolling.write(exp/"experiment.json",dict(artificial=True))
    rolling.write(exp/"dataset-index.json",dict(artificial=True))
    db=rolling.sqlite3.connect(exp/"experiment.sqlite3"); db.execute("CREATE TABLE fixture(value)"); db.close()
    monkeypatch.setattr(rolling,"expected_plan",lambda *_args:None)  # Test-only negative seam, no valid real authorization.
    def reject(*_args): raise rolling.RollingError("injected missing primary")
    monkeypatch.setattr(rolling,"verify_snapshot",reject)
    with pytest.raises(rolling.RollingError,match="missing primary"): rolling.export_rolling(exp,out)
    assert not out.exists()
    staging=list(tmp_path.glob("output.incomplete-*"))
    assert len(staging)==1 and not (staging[0]/"snapshot.json").exists()
    assert rolling.read(staging[0]/"failure.json")["qa_passed"] is False


def test_backup_pins_consistent_wal_read_while_fixture_writer_continues(tmp_path):
    import threading
    dbpath=tmp_path/"fake-live.sqlite3"
    db=rolling.sqlite3.connect(dbpath)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE fixture(value INTEGER)")
    db.executemany("INSERT INTO fixture VALUES(0)",[() for _ in range(1000)])
    db.commit(); db.close()
    stop=threading.Event(); ready=threading.Event(); errors=[]
    def writer():
        conn=rolling.sqlite3.connect(dbpath)
        try:
            while not stop.is_set():
                conn.execute("UPDATE fixture SET value=value+1"); conn.commit(); ready.set(); stop.wait(.005)
        except Exception as exc: errors.append(exc)
        finally: conn.close()
    thread=threading.Thread(target=writer); thread.start()
    try:
        assert ready.wait(2)
        rolling.make_backup(dbpath,tmp_path/"snapshot.sqlite3")
        snapshot=rolling.sqlite3.connect(tmp_path/"snapshot.sqlite3")
        try:
            assert snapshot.execute("SELECT COUNT(*),COUNT(DISTINCT value) FROM fixture").fetchone()==(1000,1)
        finally: snapshot.close()
    finally: stop.set(); thread.join(3)
    assert not errors and not thread.is_alive()


def test_first_three_selector_uses_frozen_ids_and_derived_denominator():
    # Pure metadata fixture: never passed to export_rolling or written as real.
    cells=[]
    configurations=[("sat","pairwise"),("sat","seqcounter"),("sat","bitwise"),("cpsat",None),("highs",None),("gurobi",None),("cplex_mip",None),("cpoptimizer",None)]
    for size in (9,16,25):
        for method,encoding in configurations:
            cells.append(dict(N=size,method=method,encoding=encoding,configuration=method+(":"+encoding if encoding else ""),eligible=size==9 or method in ("sat","cpsat","highs")))
    records={}; batches=[]
    for number in range(1,101):
        bid=f"b{number:03d}"; ids=[]
        for size,width in ((9,100),(16,50),(25,10)):
            for ordinal in range(width):
                iid=f"IN_MEMORY_FAKE-{bid}-{size}-{ordinal}"; ids.append(iid)
                records[iid]=dict(instance_id=iid,batch_id=bid,N=size)
        batches.append(dict(batch_id=bid,ordinal=number,instance_ids=ids))
    config=dict(repetitions=3,cutoff_seconds=10)
    matrix=dict(rows=cells)
    manifest=dict(schema_version=2,artificial=False,phase="main",dataset_id="IN_MEMORY_FAKE",experiment_id="IN_MEMORY_FAKE",config=config,matrix=matrix,
        config_sha256=rolling.digest(rolling.packed(config).encode()),matrix_sha256=rolling.digest(rolling.packed(matrix).encode()))
    manifest["scientific_sha256"]=rolling.digest(rolling.packed(manifest).encode())
    index=dict(schema_version=2,artificial=False,phase="main",dataset_id="IN_MEMORY_FAKE",records=records,batches=batches,counts=dict(instances=16000,batches=100))
    selected,subset,jobs,target=rolling.expected_plan(manifest,index)
    assert [b["batch_id"] for b in selected]==["b001","b002","b003"]
    assert len(subset)==480 and len(jobs)==3300 and target==110000
    assert all(job["repetition"]==1 for job in jobs.values())
    index["batches"][0],index["batches"][3]=index["batches"][3],index["batches"][0]
    with pytest.raises(rolling.RollingError): rolling.expected_plan(manifest,index)

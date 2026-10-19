"""Focused fake final-export checks; no solver, benchmark or real export."""
import importlib.util,json,pathlib,uuid
import pytest

ROOT=pathlib.Path(__file__).resolve().parents[2]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
f=load("final_export",ROOT/"scripts/export_expanded_final.py")
fixture=load("rolling_fixture",ROOT/"tests/expanded/test_rolling_export.py")


def error():
    row,record,puzzle,_=fixture.observation()
    result=dict(status="ERROR",method="sat",encoding="seqcounter",error="OSError: [WinError 6] The handle is invalid",guard_phase="guard",build_seconds=None,solve_seconds=None,total_seconds=None,stats=None,validation=None,raw_status=None)
    row.update(status="ERROR",method="sat",encoding="seqcounter",result_json=f.r.packed(result),payload=None,solution_attempt_id=None)
    record.update(N=16,batch_id="b099")
    declared={k:row[k] for k in ("attempt_id","job_id","status","result_json")}
    return row,record,puzzle,declared


def test_exact_error_retained_without_timing_or_cleanup_reclassification():
    row,record,puzzle,declared=error();result=f.check_row(row,record,puzzle,declared)
    assert result["status"]=="ERROR" and result["guard_phase"]=="guard" and result["total_seconds"] is None


@pytest.mark.parametrize("change",["job","attempt","payload","cleanup","timing","batch","worker_identity"])
def test_error_cannot_be_silently_replaced_or_generalized(change):
    row,record,puzzle,declared=error()
    if change=="job":row["job_id"]="other"
    if change=="attempt":row["attempt_id"]=str(uuid.uuid4())
    if change=="payload":row["payload"]=b"{}"
    if change in ("cleanup","timing","worker_identity"):
        raw=json.loads(row["result_json"])
        if change=="cleanup":raw["guard_phase"]="cleanup"
        if change=="timing":raw["total_seconds"]=0.
        if change=="worker_identity":raw["encoding"]="bitwise"
        row["result_json"]=f.r.packed(raw)
        declared=dict(declared,result_json=row["result_json"])  # Even a broadened ack cannot waive classification.
    if change=="batch":record["batch_id"]="b098"
    with pytest.raises(f.r.RollingError):f.check_row(row,record,puzzle,declared)


def test_sat_invalid_grid_and_raw_identity_are_still_independent():
    row,record,puzzle,_=fixture.observation()
    assert f.check_row(row,record,puzzle,{})["status"]=="SAT"
    row["payload"]=f.r.canonical(2,[[1]*4 for _ in range(4)]);row["solution_hash"]=f.r.digest(row["payload"])
    with pytest.raises(f.r.RollingError):f.check_row(row,record,puzzle,{})


def test_timeout_preserves_missing_runtime_and_refuses_cleanup_or_solution():
    row,record,puzzle,result=fixture.observation()
    row.update(status="TIMEOUT",payload=None,solution_attempt_id=None,checker_json=None,solution_hash=None)
    result.update(status="TIMEOUT",build_seconds=None,solve_seconds=None,total_seconds=None,guard_phase="measurement",validation=None)
    row["result_json"]=f.r.packed(result)
    checked=f.check_row(row,record,puzzle,{})
    assert checked["status"]=="TIMEOUT" and checked["total_seconds"] is None
    result["guard_phase"]="cleanup";row["result_json"]=f.r.packed(result)
    with pytest.raises(f.r.RollingError):f.check_row(row,record,puzzle,{})


@pytest.mark.parametrize("workers",[8,24,40,32])
def test_actual_capacity_workers_preserved(workers):
    saved=dict(profile="parallel-throughput-capacity-fast-v1",workers=workers,timing_policy="resource-contended",reporting_policy="separate-by-session",selected_repetitions=[1],effective_repetitions=1,target_jobs=110000)
    assert f.profile(saved)[1]==workers
    saved["selected_repetitions"]=[1,2]
    with pytest.raises(f.r.RollingError):f.profile(saved)


def test_sequential_never_relabelled_as_current32workers():
    assert f.profile({})==("original-sequential",1,"sequential")
    with pytest.raises(f.r.RollingError):f.profile(dict(workers=32))


def test_artificial_rejected_before_snapshot_backup(tmp_path,monkeypatch):
    exp=tmp_path/"fake";exp.mkdir();out=tmp_path/"out"
    f.r.write(exp/"experiment.json",dict(artificial=True));f.r.write(exp/"dataset-index.json",dict(artificial=True))
    monkeypatch.setattr(f.r,"make_backup",lambda *_args:pytest.fail("No artificial final backup"))
    with pytest.raises(f.r.RollingError):f.export_final(exp,out)
    assert not out.exists()


def test_contract_defines_embedded_solution_and_declared_error():
    contract=f.r.read(f.CONTRACT)
    assert contract["quality"]==f.QUALITY and contract["error_free"] is False
    assert contract["selection"]["expected_statuses"]==dict(SAT=109664,TIMEOUT=335,ERROR=1)
    assert contract["selection"]["excluded_historical_repetitions"]=={"2":324,"3":343}
    assert contract["solution_ref"]["format"]=="sqlite:snapshot.sqlite3#solutions/<attempt_id>"


def test_final_plan_covers_all100_batches_and_refuses_missing_duplicate_extra_ids():
    matrix=f.r.read(ROOT/"configs/expanded/matrix.json");config=dict(repetitions=3,cutoff_seconds=10.)
    manifest=dict(schema_version=2,artificial=False,phase="main",dataset_id="IN_MEMORY_ONLY",experiment_id="IN_MEMORY_ONLY",matrix=matrix,config=config)
    for name in ("matrix","config"):manifest[name+"_sha256"]=f.r.digest(f.r.packed(manifest[name]).encode())
    manifest["scientific_sha256"]=f.r.digest(f.r.packed(manifest).encode())
    records={};batches=[]
    for i in range(1,101):
        bid=f"b{i:03d}";ids=[]
        for n,count in ((9,100),(16,50),(25,10)):
            for j in range(count):
                iid=f"FAKE-{bid}-{n}-{j}";ids.append(iid);records[iid]=dict(N=n,batch_id=bid)
        batches.append(dict(batch_id=bid,ordinal=i,instance_ids=ids))
    index=dict(schema_version=2,artificial=False,phase="main",dataset_id="IN_MEMORY_ONLY",records=records,batches=batches)
    jobs=f.plan(manifest,index)
    assert len(jobs)==110000 and {j["batch_id"] for j in jobs.values()}=={f"b{i:03d}" for i in range(1,101)}
    assert all(j["repetition"]==1 for j in jobs.values()) and max(j["ordinal"] for j in jobs.values())<=330000
    for mode in ("missing","duplicate","extra"):
        old=batches[-1]["instance_ids"][:]
        if mode=="missing":batches[-1]["instance_ids"].pop()
        if mode=="duplicate":batches[-1]["instance_ids"][-1]=batches[0]["instance_ids"][0]
        if mode=="extra":records["EXTRA"]=dict(N=9,batch_id="b100")
        with pytest.raises(f.r.RollingError):f.plan(manifest,index)
        batches[-1]["instance_ids"]=old;records.pop("EXTRA",None)

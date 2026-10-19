"""Small artificial metric checks; no export/live DB or solver access."""
import importlib.util
import json
import csv
import hashlib
import sqlite3
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("final08",ROOT/"scripts/analyze_final_report.py")
tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)


@pytest.fixture
def rows():
    return json.loads((ROOT/"diagnostics/expansion/final-analysis/fixture-observations.json").read_text(encoding="utf-8"))["observations"]


def test_error_timeout_not_silently_removed(rows):
    result=tool.summarize_observations(rows)
    assert result["observed_primary"]==9 and result["status_counts"]=={"SAT":7,"TIMEOUT":1,"ERROR":1}
    assert result["effective_repetitions"]==1 and not result["median_of_repetitions_computed"]
    for r in result["strata"]:
        if r["SAT"]==0:assert r["median_single_run_seconds"] is None
    assert next(r for r in rows if r["status"]=="ERROR")["total_seconds"] is None
    assert next(r for r in rows if r["status"]=="TIMEOUT")["total_seconds"] is None


def test_profiles_and_operational_trials_not_pooled(rows):
    paired=tool.matched_single_run_pairs(rows)
    assert len(paired)==2 and {tuple(p["instance_ids"]) for p in paired}=={("A",),("C",)}
    assert all(p["workers"] not in (24,40) for p in paired)
    assert all(p["median_single_run_ratio"]==2 for p in paired)


def test_type7_over_single_instance_times():
    assert tool.quantile_type7([],.95) is None
    assert tool.quantile_type7([2],.95)==2
    assert tool.quantile_type7([1,2,3,4],.95)==pytest.approx(3.85)


def test_duplicate_and_nonfinite_rejected(rows):
    with pytest.raises(ValueError,match="Duplicate"):tool.summarize_observations(rows+[rows[0]])
    rows[0]["total_seconds"]=float("nan")
    with pytest.raises(ValueError,match="timing"):tool.summarize_observations(rows)


def test_real_reader_remains_gated(tmp_path):
    output=tmp_path/"not-created"
    with pytest.raises(RuntimeError,match="WAITING_FOR_EXPORT"):tool.analyze_final_report(tmp_path,output)
    assert not output.exists()


def test_posthoc_noncompletion_and_puzzle_denominators(rows):
    spec=importlib.util.spec_from_file_location("derived_final",ROOT/"diagnostics/expansion/final-analysis/finish_figures.py")
    derived=importlib.util.module_from_spec(spec);spec.loader.exec_module(derived)
    before=json.dumps(rows,sort_keys=True)
    non,puzzles=derived.derived_counts(rows)
    assert sum(r["non_completed"] for r in non)==2
    assert sum(r["TIMEOUT"] for r in non)==1 and sum(r["ERROR"] for r in non)==1
    assert sum(r["attempted_unique_puzzles"] for r in puzzles)==5
    assert sum(r["puzzles_with_any_primary_SAT"] for r in puzzles)==4
    assert sum(r["puzzles_without_any_primary_SAT"] for r in puzzles)==1
    assert json.dumps(rows,sort_keys=True)==before
    points=derived.completion_points([dict(N=16,configuration="SC",noncompletion_fraction=.02),dict(N=16,configuration="PW",noncompletion_fraction=0)],16,["PW","SC","commercial"])
    assert points==[(1,0),(2,2)]  # sorted categories; absent commercial is not zero-filled.


@pytest.fixture
def export_fixture(tmp_path):
    p=tmp_path/"ARTIFICIAL-export";p.mkdir();contract=json.loads((ROOT/"diagnostics/expansion/final-export/CONTRACT.json").read_text())
    contract["selection"].update(expected_jobs=3,expected_instances=1,expected_statuses={"SAT":1,"TIMEOUT":1,"ERROR":1},excluded_historical_repetitions={"2":0,"3":0})
    def save(name,value): (p/name).write_text(json.dumps(value)+"\n",encoding="utf-8")
    save("CONTRACT.json",contract);save("source-freeze.json",dict(artificial=True,frozen=True))
    grid=[[1,2,3,4],[3,4,1,2],[2,1,4,3],[4,3,2,1]];payload=tool._canonical(dict(n=2,grid=grid));h=hashlib.sha256(payload).hexdigest()
    rec=dict(instance_id="i1",n=2,N=4,actual_clues=16,input_sha256=h,witness_sha256=h,content_sha256=h,witness_content_sha256=h,source="synthetic",source_group=None,family="permutation",root_id="root1",uniqueness="unverified",clue_percent_requested=100)
    manifest=dict(experiment_id="ARTIFICIAL-final",scientific_sha256="a"*64,config=dict(repetitions=3),dataset_freeze_sha256=tool._sha(p/"source-freeze.json"))
    save("source-manifest.json",manifest);save("source-index.json",dict(freeze_sha256=manifest["dataset_freeze_sha256"],records={"i1":rec}))
    (p/"instances.jsonl").write_text(json.dumps(rec)+"\n",encoding="utf-8")
    save("session.json",dict(artificial=True,workers=32));save("profiles.json",{"s1":dict(profile="parallel",workers=32,timing_policy="resource-contended",source_session_manifest="session.json",source_session_manifest_sha256=tool._sha(p/"session.json"))})
    db=sqlite3.connect(p/"inputs.sqlite3");db.execute("CREATE TABLE inputs(instance_id TEXT,block_side INTEGER,board_side INTEGER,input_payload BLOB,input_sha256 TEXT,input_canonical_sha256 TEXT,witness_payload BLOB,witness_sha256 TEXT,witness_canonical_sha256 TEXT)")
    db.execute("INSERT INTO inputs VALUES(?,?,?,?,?,?,?,?,?)",("i1",2,4,payload,h,h,payload,h,h));db.commit();db.close()
    db=sqlite3.connect(p/"snapshot.sqlite3");db.executescript('''PRAGMA user_version=2;
    CREATE TABLE experiment(manifest_json TEXT); CREATE TABLE jobs(job_id TEXT,instance_id TEXT,method TEXT,encoding TEXT,repetition INTEGER,ordinal INTEGER);
    CREATE TABLE attempts(attempt_id TEXT,attempt_no INTEGER,session_id TEXT);CREATE TABLE primary_attempt(job_id TEXT,attempt_id TEXT);
    CREATE TABLE results(attempt_id TEXT,status TEXT,result_json TEXT);CREATE TABLE solutions(attempt_id TEXT,payload BLOB,sha256 TEXT,checker_json TEXT);''')
    db.execute("INSERT INTO experiment VALUES(?)",(json.dumps(manifest),))
    fields="schema_version experiment_id dataset_id phase batch_id job_id attempt_id attempt_no instance_id method encoding repetition block_side board_side source source_group rating_original rating_value family root_id clue_percent_requested actual_clues input_sha256 cutoff_seconds status raw_status build_seconds solve_seconds total_seconds attempt_wall_seconds checkpoint_seconds primary_variables auxiliary_variables total_variables clauses validation validation_message solution_ref solution_sha256 guard_phase error session_id profile workers timing_policy".split();rows=[]
    for number,(method,encoding,status) in enumerate((("sat","pairwise","SAT"),("cpsat","","TIMEOUT"),("sat","seqcounter","ERROR")),1):
        jid=f"j{number}";aid=f"a{number}";timings=dict(build_seconds=.01 if status=="SAT" else None,solve_seconds=.02 if status=="SAT" else None,total_seconds=.03 if status=="SAT" else None)
        guard="complete" if status=="SAT" else "guard" if status=="ERROR" else "measurement"
        error="OSError: [WinError 6] The handle is invalid" if status=="ERROR" else None
        result=dict(status=status,**timings,validation=dict(valid=True) if status=="SAT" else None,guard_phase=guard,error=error)
        db.execute("INSERT INTO jobs VALUES(?,?,?,?,1,?)",(jid,"i1",method,encoding,number));db.execute("INSERT INTO attempts VALUES(?,1,'s1')",(aid,));db.execute("INSERT INTO primary_attempt VALUES(?,?)",(jid,aid));db.execute("INSERT INTO results VALUES(?,?,?)",(aid,status,json.dumps(result)))
        if status=="SAT":db.execute("INSERT INTO solutions VALUES(?,?,?,?)",(aid,payload,h,json.dumps(dict(valid=True))))
        row=dict.fromkeys(fields,"");row.update(job_id=jid,attempt_id=aid,attempt_no=1,batch_id="b099",instance_id="i1",method=method,encoding=encoding,repetition=1,status=status,**timings,session_id="s1",profile="parallel",workers=32,timing_policy="resource-contended",validation="pass" if status=="SAT" else "",guard_phase=guard,error=error,solution_ref=f"sqlite:snapshot.sqlite3#solutions/{aid}" if status=="SAT" else "",solution_sha256=h if status=="SAT" else "")
        rows.append(row)
    db.commit();db.close()
    with (p/"results.csv").open("w",encoding="utf-8",newline="") as stream:w=csv.DictWriter(stream,fieldnames=fields);w.writeheader();w.writerows(rows)
    receipt=dict(schema_version=1,kind=contract["receipt_kind"],status="PASS",**{k:contract[k] for k in ("quality","error_free","selected_scope_observed_complete","original_three_repetition_experiment_complete")},selected_repetitions=[1],effective_repetitions=1,original_repetitions=3,expected_jobs=3,observed_jobs=3,selected_instances=1,primary_counts={"SAT":1,"TIMEOUT":1,"ERROR":1},source_experiment_id=manifest["experiment_id"],source_scientific_sha256=manifest["scientific_sha256"],declared_error=dict(job_id="j3",attempt_id="a3",batch_id="b099",result_json=json.dumps(result)),files_sha256={x.name:tool._sha(x) for x in p.iterdir() if x.is_file()})
    save("snapshot.json",receipt)
    return p,contract


def test_reader_accepts_declared_error_and_sqlite_witness(export_fixture):
    p,contract=export_fixture;result=tool._read_final_snapshot(p,contract)
    assert result["state"]=="READER_VALIDATED_WITH_DECLARED_ERROR"
    assert [r["status"] for r in result["observations"]]==["SAT","TIMEOUT","ERROR"]
    assert result["receipt"]["error_free"] is False


def test_reader_rejects_hash_and_wrong_quality(export_fixture):
    p,contract=export_fixture;m=tool._json(p/"snapshot.json");m["error_free"]=True;(p/"snapshot.json").write_text(json.dumps(m))
    with pytest.raises(ValueError,match="quality/error"):tool._read_final_snapshot(p,contract)
    m["error_free"]=False;(p/"snapshot.json").write_text(json.dumps(m));(p/"results.csv").write_text("tampered")
    with pytest.raises(ValueError,match="hash mismatch"):tool._read_final_snapshot(p,contract)


def test_declared_error_requires_exact_identity(export_fixture):
    p,contract=export_fixture;m=tool._json(p/"snapshot.json");m["declared_error"]["job_id"]="prefix-j3-suffix";(p/"snapshot.json").write_text(json.dumps(m))
    with pytest.raises(ValueError,match="exact identity"):tool._read_final_snapshot(p,contract)


@pytest.mark.parametrize("key,value",[("guard_phase","cleanup"),("error","a different failure")])
def test_error_guard_raw_tamper(export_fixture,key,value):
    p,contract=export_fixture
    with (p/"results.csv").open(newline="") as f:r=csv.DictReader(f);fields=r.fieldnames;rows=list(r)
    rows[-1][key]=value
    with (p/"results.csv").open("w",newline="") as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    m=tool._json(p/"snapshot.json");m["files_sha256"]["results.csv"]=tool._sha(p/"results.csv");(p/"snapshot.json").write_text(json.dumps(m))
    with pytest.raises(ValueError,match="guard/error"):tool._read_final_snapshot(p,contract)

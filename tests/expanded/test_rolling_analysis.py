"""Focused artificial rolling-reader tests. No workers, solving or real snapshots."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("rolling08",ROOT/"scripts/analyze_rolling_report.py")
tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False)+"\n",encoding="utf-8")


def write_rows(path,rows):
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=tool.CORE+tool.EXTRA);w.writeheader();w.writerows(rows)


def reseal(path):
    m=tool.load(path/"snapshot.json")
    m["files_sha256"]={name:tool.sha(path/name) for name in ("results.csv","instances.jsonl","snapshot.sqlite3","source-manifest.json","source-index.json","profiles.json")}
    write(path/"snapshot.json",m)


@pytest.fixture
def fixture(tmp_path):
    snapshot=tmp_path/"ARTIFICIAL-snapshot";snapshot.mkdir();dataset=tmp_path/"dữ liệu";dataset.mkdir()
    records={};grids={};batches=[]
    for offset in range(4):
        grid=[[(3*(r%3)+r//3+c+offset)%9+1 for c in range(9)] for r in range(9)]
        puzzle=[[grid[r][c] if r*9+c<20 else 0 for c in range(9)] for r in range(9)]
        iid=f"ARTIFICIAL-i{offset}";bid=f"b{offset+1:03d}"
        write(dataset/(iid+".json"),dict(n=3,grid=puzzle))
        records[iid]=dict(instance_id=iid,batch_id=bid,n=3,N=9,input_file=iid+".json",input_sha256=tool.sha(dataset/(iid+".json")),source="sudoku_exchange",source_group="easy_#%",rating_original="1.2",family=None,root_id=None,clue_percent_requested=None,actual_clues=20)
        grids[iid]=grid;batches.append(dict(batch_id=bid,ordinal=offset+1,instance_ids=[iid]))
    manifest=dict(schema_version=2,experiment_id="ARTIFICIAL-wave",dataset_id="ARTIFICIAL-dataset",phase="main",artificial=True,scientific_sha256="a"*64,dataset_freeze_sha256="b"*64,config=dict(repetitions=3,cutoff_seconds=10),matrix=dict(rows=[dict(N=9,method=m,encoding=e,eligible=True) for m,e in (("sat","pairwise"),("cpsat",None))]))
    index=dict(dataset_id=manifest["dataset_id"],freeze_sha256=manifest["dataset_freeze_sha256"],dataset_dir=str(dataset),records=records,batches=batches)
    write(snapshot/"source-manifest.json",manifest);write(snapshot/"source-index.json",index)
    profiles=dict(s1=dict(profile="original_sequential",workers=1,timing_policy="isolated_single_worker",source_session_manifest_sha256="c"*64),s2=dict(profile="parallel",workers=4,timing_policy="resource_contended",source_session_manifest_sha256="d"*64))
    write(snapshot/"profiles.json",profiles)
    selected=list(records)[:3]
    (snapshot/"instances.jsonl").write_text("".join(json.dumps(records[i])+"\n" for i in selected),encoding="utf-8")
    db=sqlite3.connect(snapshot/"snapshot.sqlite3")
    db.executescript('''PRAGMA user_version=2;
    CREATE TABLE experiment(experiment_id TEXT,manifest_json TEXT);
    CREATE TABLE instances(instance_id TEXT,batch_id TEXT);
    CREATE TABLE jobs(job_id TEXT,instance_id TEXT,method TEXT,encoding TEXT,repetition INTEGER,ordinal INTEGER);
    CREATE TABLE attempts(attempt_id TEXT,attempt_no INTEGER,session_id TEXT);
    CREATE TABLE results(attempt_id TEXT,status TEXT,result_json TEXT);
    CREATE TABLE solutions(attempt_id TEXT,payload BLOB,sha256 TEXT);
    CREATE TABLE primary_attempt(job_id TEXT,attempt_id TEXT);
    ''')
    db.execute("INSERT INTO experiment VALUES(?,?)",(manifest["experiment_id"],json.dumps(manifest)))
    rows=[]
    for k,iid in enumerate(selected):
        record=records[iid];db.execute("INSERT INTO instances VALUES(?,?)",(iid,record["batch_id"]))
        for method,encoding in (("sat","pairwise"),("cpsat","")):
            ordinal=len(rows)+1;jid=f"j-{ordinal}";aid=f"a-{ordinal}"
            sid="s1" if k==0 or k==2 and method=="sat" else "s2"
            status="TIMEOUT" if k==1 and method=="sat" else "SAT"
            total=.01 if method=="sat" else .02
            result=dict(status=status,build_seconds=total*.3 if status=="SAT" else None,solve_seconds=total*.7 if status=="SAT" else None,total_seconds=total if status=="SAT" else None,validation=dict(valid=True) if status=="SAT" else None,guard_phase="complete" if status=="SAT" else "measurement")
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,1,?)",(jid,iid,method,encoding,ordinal));db.execute("INSERT INTO attempts VALUES(?,1,?)",(aid,sid));db.execute("INSERT INTO results VALUES(?,?,?)",(aid,status,json.dumps(result)));db.execute("INSERT INTO primary_attempt VALUES(?,?)",(jid,aid))
            solution_hash=""
            if status=="SAT":
                payload=(json.dumps(dict(n=3,grid=grids[iid]))+"\n").encode();solution_hash=hashlib.sha256(payload).hexdigest()
                db.execute("INSERT INTO solutions VALUES(?,?,?)",(aid,payload,solution_hash))
            row=dict.fromkeys(tool.CORE+tool.EXTRA,"")
            row.update(schema_version=2,experiment_id=manifest["experiment_id"],dataset_id=manifest["dataset_id"],phase="main",batch_id=record["batch_id"],job_id=jid,attempt_id=aid,attempt_no=1,instance_id=iid,method=method,encoding=encoding,repetition=1,block_side=3,board_side=9,**{key:record[key] for key in ("source","source_group","rating_original","family","root_id","clue_percent_requested","actual_clues","input_sha256")},cutoff_seconds=10,status=status,build_seconds=result["build_seconds"],solve_seconds=result["solve_seconds"],total_seconds=result["total_seconds"],validation="pass" if status=="SAT" else "",solution_sha256=solution_hash,guard_phase=result["guard_phase"],session_id=sid,**{key:profiles[sid][key] for key in ("profile","workers","timing_policy")})
            rows.append(row)
    db.commit();db.close();write_rows(snapshot/"results.csv",rows)
    write(snapshot/"snapshot.json",dict(schema_version=1,kind="VERIFIED_ROLLING_SNAPSHOT",full_experiment_complete=False,source_experiment_id=manifest["experiment_id"],source_scientific_sha256=manifest["scientific_sha256"],created_utc="2026-10-19T14:00:00+00:00",selected_repetitions=[1],effective_repetitions=1,original_repetitions=3,target_jobs=110000,target_instances=16000,selected_batch_ids=["b001","b002","b003"],expected_jobs=6,observed_jobs=6,selected_instances=3,qa_passed=True,files_sha256={}))
    reseal(snapshot)
    return snapshot,tmp_path/"pytest-output"


def test_single_repeat_profile_pair_and_receipt(fixture):
    source,output=fixture
    before={p.name:tool.sha(p) for p in source.iterdir() if p.is_file()}
    result=tool.analyze_rolling(source,output)
    assert result["kind"]=="VERIFIED_SUBSET" and not result["full_experiment_complete"]
    assert result["status_counts"]=={"SAT":5,"TIMEOUT":1} and result["effective_repetitions"]==1
    assert before=={p.name:tool.sha(p) for p in source.iterdir() if p.is_file()}
    with (output/"matched-pairs.csv").open(newline="",encoding="utf-8") as stream:paired=list(csv.DictReader(stream))
    assert len(paired)==1 and paired[0]["matched_instances"]=="1" and json.loads(paired[0]["instance_ids"])==["ARTIFICIAL-i0"]
    assert float(paired[0]["median_single_run_a_over_b"])==2
    with (output/"instances.csv").open(newline="",encoding="utf-8") as stream:instances=list(csv.DictReader(stream))
    timeout=next(r for r in instances if r["status"]=="TIMEOUT")
    assert timeout["total_seconds"]=="" and float(timeout["par2_seconds"])==20
    receipt=tool.load(output/"analysis-hashes.json")
    assert "analysis-hashes.json" not in receipt["files_sha256"]
    assert all(tool.sha(output/name)==value for name,value in receipt["files_sha256"].items())
    assert r"easy\_\#\%" in (output/"runtime.tex").read_text(encoding="utf-8")
    assert "tikzpicture" in (output/"coverage-tikz.tex").read_text(encoding="utf-8")
    with pytest.raises(ValueError,match="NEW"):tool.analyze_rolling(source,output)


@pytest.mark.parametrize("field,value",[("qa_passed",False),("selected_repetitions",[1,2]),("effective_repetitions",3),("full_experiment_complete",True),("selected_batch_ids",["b002","b003","b004"]),("expected_jobs",7)])
def test_reject_unverified_or_wrong_scope(fixture,field,value):
    source,output=fixture;m=tool.load(source/"snapshot.json");m[field]=value;write(source/"snapshot.json",m)
    with pytest.raises(ValueError):tool.analyze_rolling(source,output)
    assert not output.exists()


def test_reject_hash_corruption(fixture):
    source,output=fixture
    with (source/"results.csv").open("a",encoding="utf-8") as stream:stream.write("\n")
    with pytest.raises(ValueError,match="hash mismatch"):tool.analyze_rolling(source,output)


def test_profile_metadata_mismatch(fixture):
    source,output=fixture;p=tool.load(source/"profiles.json");p["s2"]["workers"]=1;write(source/"profiles.json",p);reseal(source)
    with pytest.raises(ValueError,match="profile/workers"):tool.analyze_rolling(source,output)


def test_primary_csv_mismatch(fixture):
    source,output=fixture;rows=tool.read_csv(source/"results.csv");rows[0]["session_id"]="s2";write_rows(source/"results.csv",rows);reseal(source)
    with pytest.raises(ValueError,match="session identity"):tool.analyze_rolling(source,output)


def test_reject_missing_primary(fixture):
    source,output=fixture;rows=tool.read_csv(source/"results.csv");write_rows(source/"results.csv",rows[:-1]);reseal(source)
    with pytest.raises(ValueError,match="missing jobs"):tool.analyze_rolling(source,output)


def test_checker_catches_wrong_clues(fixture):
    source,output=fixture;db=sqlite3.connect(source/"snapshot.sqlite3")
    row=db.execute("SELECT attempt_id,payload FROM solutions LIMIT 1").fetchone();grid=json.loads(row[1]);grid["grid"][0][0]=0
    payload=json.dumps(grid).encode();newsha=hashlib.sha256(payload).hexdigest();db.execute("UPDATE solutions SET payload=?,sha256=? WHERE attempt_id=?",(payload,newsha,row[0]));db.commit();db.close()
    rows=tool.read_csv(source/"results.csv")
    next(r for r in rows if r["attempt_id"]==row[0])["solution_sha256"]=newsha
    write_rows(source/"results.csv",rows);reseal(source)
    with pytest.raises(ValueError,match="checker failed"):tool.analyze_rolling(source,output)


def test_live_directory_rejected(tmp_path):
    with pytest.raises(ValueError,match="Verified snapshot"):tool.analyze_rolling(tmp_path,tmp_path.parent/"outside-output")

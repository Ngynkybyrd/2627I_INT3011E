"""Freeze and independently verify the predeclared first3 main batches, rep1.

Read-only source access, one SQLite backup, no runner/solver imports or calls.
Only a verified real subset is published; failed staging never has a PASS receipt.
"""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import csv
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sqlite3
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from sudoku.expanded_common import CSV_FIELDS
from sudoku.model import Puzzle
from sudoku.validation import check_solution

FIELDS=CSV_FIELDS+"session_id profile workers timing_policy".split()
SELECTOR="first 3 frozen dataset-index batches by ordinal; repetition1 only"


class RollingError(Exception):
    pass


def need(value,message):
    if not value: raise RollingError(message)


def packed(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)


def digest(data): return hashlib.sha256(data).hexdigest()


def sha(path):
    with Path(path).open("rb") as stream: return hashlib.file_digest(stream,"sha256").hexdigest()


def make_backup(source,destination):
    live=sqlite3.connect(Path(source).resolve().as_uri()+"?mode=ro",uri=True,timeout=5,isolation_level=None)
    snapshot=sqlite3.connect(destination)
    started=time.monotonic()
    try:
        # Pin a WAL read snapshot before page-stepping. Without this, continuous
        # live commits can repeatedly restart sqlite3_backup_step indefinitely.
        live.execute("BEGIN")
        live.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        def progress(_status,_remaining,_total):
            need(time.monotonic()-started<45,"SQLite backup exceeded bounded read window")
        live.backup(snapshot,pages=256,sleep=.01,progress=progress)
    finally:
        snapshot.close(); live.close()


def read(path): return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path,value):
    with Path(path).open("x",encoding="utf-8",newline="\n") as stream: stream.write(packed(value)+"\n")


def inside(directory,relative):
    need(isinstance(relative,str) and relative and not Path(relative).is_absolute(),"Invalid relative evidence path")
    directory=Path(directory).resolve(); path=(directory/relative).resolve()
    need(path.is_relative_to(directory),"Evidence path escapes its root")
    return path


def finite(value): return type(value) in (int,float) and math.isfinite(value) and value>=0


def canonical(n,grid): return (packed(dict(n=n,grid=grid))+"\n").encode("utf-8")


def timestamp(value):
    dt=datetime.fromisoformat(value)
    need(dt.tzinfo is not None,"Timestamp lacks UTC offset")
    return dt


def expected_plan(manifest,index):
    need(manifest.get("schema_version")==index.get("schema_version")==2,"Wrong schema")
    need(manifest.get("artificial") is False and index.get("artificial") is False,"Artificial snapshot cannot be report evidence")
    need(manifest["phase"]==index["phase"]=="main" and manifest["dataset_id"]==index["dataset_id"],"Wrong dataset subject")
    need(manifest["config"]["repetitions"]==3 and manifest["config"]["cutoff_seconds"]==10,"Frozen protocol differs")
    need(index["counts"]==dict(instances=16000,batches=100) and len(index["records"])==16000 and len(index["batches"])==100,"Wrong original target")
    need(manifest["scientific_sha256"]==digest(packed({k:v for k,v in manifest.items() if k not in ("created_utc","scientific_sha256")}).encode()),"Scientific manifest digest mismatch")
    need(digest(packed(manifest["config"]).encode())==manifest["config_sha256"] and digest(packed(manifest["matrix"]).encode())==manifest["matrix_sha256"],"Config/matrix digest mismatch")
    eligible=defaultdict(list)
    for row in manifest["matrix"]["rows"]:
        if row["eligible"]: eligible[row["N"]].append(row)
    need(len({(r["N"],r["configuration"]) for r in manifest["matrix"]["rows"]})==24,"Duplicate/incomplete matrix")
    expected_configs={9:{"sat:pairwise","sat:seqcounter","sat:bitwise","cpsat","highs","gurobi","cplex_mip","cpoptimizer"},16:{"sat:pairwise","sat:seqcounter","sat:bitwise","cpsat","highs"},25:{"sat:pairwise","sat:seqcounter","sat:bitwise","cpsat","highs"}}
    need({n:{r["configuration"] for r in cells} for n,cells in eligible.items()}==expected_configs,"Eligibility differs from frozen scope")
    assigned=[]
    for number,batch in enumerate(index["batches"],1):
        need(batch["ordinal"]==number and batch["batch_id"]==f"b{number:03d}","Batch ordering is not frozen ordinal order")
        need(len(batch["instance_ids"])==160,"Wrong batch instance count")
        for iid in batch["instance_ids"]:
            need(iid in index["records"] and index["records"][iid]["batch_id"]==batch["batch_id"],"Batch/instance relation differs")
        assigned.extend(batch["instance_ids"])
    need(len(assigned)==len(set(assigned))==len(index["records"]),"Duplicate or missing dataset member")
    selected=index["batches"][:3]
    records={iid:index["records"][iid] for b in selected for iid in b["instance_ids"]}
    target=sum(len(eligible[r["N"]]) for r in index["records"].values())
    expected={}
    for iid,r in records.items():
        for cell in eligible[r["N"]]:
            encoding=cell.get("encoding") or ""
            need(cell["configuration"]==cell["method"]+(":"+encoding if encoding else ""),"Invalid configuration identity")
            jid="j2-"+digest(packed([manifest["experiment_id"],iid,cell["method"],encoding,1]).encode())
            expected[jid]=dict(instance_id=iid,batch_id=r["batch_id"],method=cell["method"],encoding=encoding,configuration=cell["configuration"],repetition=1)
    need(target==110000 and len(records)==480 and len(expected)==3300,"Derived rolling denominator differs; never fill missing jobs")
    return selected,records,expected,target


def verify_inputs(manifest,index,records,staging):
    dataset=Path(manifest["dataset_dir"]).resolve()
    need(dataset==Path(index["dataset_dir"]).resolve(),"Dataset path identity differs")
    need(sha(dataset/"freeze.json")==manifest["dataset_freeze_sha256"]==index["freeze_sha256"],"Dataset freeze changed")
    freeze=read(dataset/"freeze.json")
    need(freeze.get("frozen") is True and freeze.get("all_witness_check_pass") is True and freeze.get("artificial") is False,"Dataset was not finalized with real witnesses")
    need(freeze["dataset_id"]==manifest["dataset_id"],"Freeze subject differs")
    hashes=freeze["files_sha256"]
    for filename in ("dataset.json","manifest.jsonl","batches.json","roots.jsonl","provenance.json"):
        need(sha(dataset/filename)==hashes[filename],"Frozen dataset metadata changed: "+filename)
    frozen_batches=read(dataset/"batches.json")
    need((frozen_batches if isinstance(frozen_batches,list) else frozen_batches["batches"])==index["batches"],"Frozen batches differ from source index")
    selected_manifest={}
    with (dataset/"manifest.jsonl").open(encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                row=json.loads(line)
                if row["instance_id"] in records:
                    need(row["instance_id"] not in selected_manifest,"Duplicate source manifest record")
                    selected_manifest[row["instance_id"]]=row
    need(selected_manifest==records,"Selected index records differ from frozen manifest")
    frozen_sources={p.replace("\\","/"):h for p,h in manifest["fingerprint"]["source_sha256"].items()}
    for relative in ("src/sudoku/model.py","src/sudoku/validation.py","src/sudoku/contracts.py"):
        need(sha(ROOT/relative)==frozen_sources[relative],"Frozen checker/model source differs")
    puzzles={}; groups=defaultdict(list)
    (staging/"inputs").mkdir(); (staging/"witnesses").mkdir()
    for iid,r in records.items():
        need(r["dataset_id"]==manifest["dataset_id"] and r["phase"]=="main" and r["schema_version"]==2,"Instance subject differs")
        need(r["N"]==r["n"]**2 and r["N"] in (9,16,25),"Instance n/N mismatch")
        puzzle=None; witness=None
        for field,hashfield,outdir in (("input_file","input_sha256","inputs"),("witness_file","witness_sha256","witnesses")):
            data=inside(dataset,r[field]).read_bytes()
            need(digest(data)==r[hashfield]==hashes[r[field]],"Frozen selected input/witness hash differs")
            raw=json.loads(data.decode("utf-8-sig")); parsed=Puzzle(raw["n"],raw["grid"])
            need(parsed.n==r["n"],"Input/witness dimensions differ")
            (staging/outdir/(iid+".json")).write_bytes(data)
            if outdir=="inputs": puzzle=parsed
            else: witness=parsed
        need(puzzle.clue_count==r["actual_clues"] and digest(canonical(puzzle.n,puzzle.grid))==r["content_sha256"],"Canonical input/clue mismatch")
        need(iid==f"e2-main-N{r['N']}-{r['content_sha256']}","Noncanonical instance identity")
        need(check_solution(puzzle,witness.grid).valid and digest(canonical(witness.n,witness.grid))==r["witness_content_sha256"],"Independent original witness check failed")
        need(r["witness_validation"]["valid"] is True and r["witness_validation"]["checker_code_sha256"]==sha(ROOT/"src/sudoku/validation.py"),"Original witness checker evidence differs")
        if r["source"]=="synthetic": groups[r["root_id"]].append(r)
        puzzles[iid]=puzzle
    for rid,children in groups.items():
        need(len(children)==5 and sorted(c["clue_percent_requested"] for c in children)==[20,30,40,50,60],"Root cluster masks incomplete")
        root=index["roots"][rid]
        root_bytes=inside(dataset,root["grid_file"]).read_bytes()
        need(digest(root_bytes)==hashes[root["grid_file"]]==root["grid_sha256"],"Selected root hash differs")
        raw=json.loads(root_bytes); grid=Puzzle(raw["n"],raw["grid"])
        content=digest(canonical(grid.n,grid.grid))
        need(check_solution(grid,grid.grid).valid and content==root["root_content_sha256"],"Selected root invalid")
        need(len({c["batch_id"] for c in children})==1 and all(c["root_content_sha256"]==c["witness_content_sha256"]==content for c in children),"Root linkage/same-batch mismatch")
    for batch in index["batches"][:3]:
        rows=[records[i] for i in batch["instance_ids"]]
        need(Counter(r["source_group"] for r in rows if r["N"]==9)=={g:25 for g in ("easy","medium","hard","diabolical")},"Selected public strata unbalanced")
        for size,width in ((16,5),(25,1)):
            need(Counter((r["family"],r["clue_percent_requested"]) for r in rows if r["N"]==size)=={(f,p):width for f in ("permutation","row_cycle") for p in (20,30,40,50,60)},"Selected synthetic strata unbalanced")
    shutil.copyfile(dataset/"freeze.json",staging/"source-freeze.json")
    return puzzles


def check_observation(row,record,puzzle):
    result=json.loads(row["result_json"])
    need(str(uuid.UUID(row["attempt_id"]))==row["attempt_id"] and uuid.UUID(row["attempt_id"]).version==4,"Invalid attempt UUID4")
    need(type(row["attempt_no"]) is int and row["attempt_no"]>=1,"Invalid attempt number")
    need(row["attempt_state"]=="FINISHED" and row["job_state"]=="TERMINAL","Selected job/attempt not finished")
    need(row["attempt_job_id"]==row["job_id"] and row["primary_attempt_id"]==row["attempt_id"],"Primary/attempt/job identity mismatch")
    need(result.get("status")==row["status"] and row["status"] in ("SAT","TIMEOUT"),"Fatal/mismatched selected terminal status")
    need(result.get("method")==row["method"] and (result.get("encoding") or "")==row["encoding"],"Raw result configuration identity mismatch")
    packed(result)  # Reject all non-JSON and NaN/Inf raw observations.
    need(not any(x in str(result.get("raw_status","")).upper() for x in ("ARTIFICIAL","FIXTURE","REPLAY")),"Replay/artificial raw observation")
    need(finite(row["attempt_wall_seconds"]),"Invalid controller wall duration")
    need(timestamp(row["ended_utc"])>=timestamp(row["started_utc"]),"Attempt timestamps reversed")
    values=[result.get(k) for k in ("build_seconds","solve_seconds","total_seconds")]
    need(all(v is None or finite(v) for v in values),"Invalid measured duration")
    b,s,t=values
    if all(v is not None for v in values): need(abs(b+s-t)<=1e-7*max(1,t),"Timing sum mismatch")
    validation=result.get("validation")
    need(validation is None or (isinstance(validation,dict) and validation.get("valid") is True),"Failed raw checker evidence")
    stats=result.get("stats")
    if stats is not None:
        need(row["method"]=="sat" and all(type(stats.get(k)) is int and stats[k]>=0 for k in ("primary_variables","auxiliary_variables","total_variables","clauses")),"Invalid SAT counts/baseline CNF leakage")
        n=record["N"]; groups=4*n*n; bits=(n-1).bit_length()
        aux,amo={"pairwise":(0,n*(n-1)//2),"seqcounter":(n-1,3*n-4),"bitwise":(bits,n*bits)}[row["encoding"]]
        need(stats["primary_variables"]==n**3 and stats["auxiliary_variables"]==groups*aux and stats["total_variables"]==n**3+groups*aux and stats["clauses"]==groups*(1+amo)+record["actual_clues"],"SAT count formula mismatch")
    if row["status"]=="SAT":
        need(not result.get("error"),"SAT carries an error")
        need(all(v is not None for v in values) and t<=10 and result.get("guard_phase")=="complete","SAT outside timing/protocol guard")
        need(validation is not None and validation["valid"] is True,"SAT lacks raw checker evidence")
        need(row["method"]!="sat" or stats is not None,"SAT lacks CNF counts")
        need(row["solution_attempt_id"]==row["attempt_id"] and row["payload"] is not None and digest(row["payload"])==row["solution_hash"],"SAT blob identity/hash mismatch")
        need(json.loads(row["checker_json"])==validation,"Stored checker evidence differs")
        solution=json.loads(row["payload"])
        need(solution["n"]==record["n"] and canonical(record["n"],solution["grid"])==row["payload"],"SAT blob noncanonical/wrong dimensions")
        need(check_solution(puzzle,solution["grid"]).valid,"Independent stored SAT grid/clue check failed")
    else:
        need(result.get("guard_phase") in ("measurement","complete"),"TIMEOUT outside measurement; cleanup failure cannot be included")
        need(row["payload"] is None and row["solution_attempt_id"] is None and result.get("solution") is None,"TIMEOUT carries a solution")
    return result


def describe_profile(saved):
    profile=saved.get("profile","original-sequential")
    if profile=="original-sequential":
        workers=1; policy="sequential"
        need(saved.get("workers",1)==1 and saved.get("timing_policy","sequential")==policy,"Ambiguous sequential session profile")
    else:
        need(profile=="parallel-throughput-v1" and saved.get("workers")==4 and saved.get("timing_policy")=="resource-contended" and saved.get("reporting_policy")=="separate-by-session","Unknown/mislabeled concurrent profile")
        workers=4; policy="resource-contended"
    return profile,workers,policy


def session_profile(experiment,manifest,sid,session,staging):
    need(str(uuid.UUID(sid))==sid and uuid.UUID(sid).version==4,"Invalid session UUID4")
    source=experiment/"session-manifests"/(sid+".json")
    data=source.read_bytes(); saved=json.loads(data)
    need(saved.get("session_id")==sid and saved.get("scientific_manifest")==manifest,"Session/scientific manifest identity differs")
    profile,workers,policy=describe_profile(saved)
    for key in ("dataset","qa","preflight","pilot","execution_freeze"):
        ref=saved["gate_refs"]["gates"][key]
        need(ref.get("accepted") is True and ref.get("accepted_by")=="root" and sha(inside(ROOT,ref["path"]))==ref["sha256"],"Session gate evidence changed/not root accepted")
    if workers==4:
        auth=saved["authorization"]; raw=inside(ROOT,auth["path"]).read_bytes(); receipt=json.loads(raw)
        need(digest(raw)==auth["sha256"] and receipt==auth["receipt"],"Parallel authorization hash/content differs")
        need(receipt.get("accepted") is True and receipt.get("accepted_by")=="root" and receipt.get("experiment_id")==manifest["experiment_id"] and receipt.get("scientific_sha256")==manifest["scientific_sha256"],"Parallel authorization subject differs")
        need(receipt.get("profile")==profile and receipt.get("workers")==workers and receipt.get("timing_policy")==policy and receipt.get("script_sha256")==saved["script_sha256"],"Parallel authorized profile/script differs")
        if "selected_repetitions" in saved:
            need(saved["selected_repetitions"]==receipt.get("selected_repetitions")==[1] and saved.get("effective_repetitions")==1 and saved.get("target_jobs")==110000,"Effective repetition scope differs")
        target=staging/"session-manifests"/(sid+"-authorization.json"); target.write_bytes(raw)
    target=staging/"session-manifests"/(sid+".json"); target.write_bytes(data)
    return dict(session_id=sid,profile=profile,workers=workers,timing_policy=policy,reporting_policy="separate-by-session",
        source_session_manifest="session-manifests/"+sid+".json",source_session_manifest_sha256=digest(data),source_path=str(source),
        historical_script_sha256=saved.get("script_sha256"),session_started_utc=session["started_utc"])


def verify_snapshot(db,experiment,staging,manifest,index):
    selected,records,expected,target=expected_plan(manifest,index)
    need(db.execute("PRAGMA user_version").fetchone()[0]==2 and db.execute("PRAGMA quick_check").fetchone()[0]=="ok","SQLite snapshot integrity/schema failure")
    need(not db.execute("PRAGMA foreign_key_check").fetchall(),"SQLite snapshot foreign key failure")
    exp=db.execute("SELECT * FROM experiment").fetchall()
    need(len(exp)==1 and exp[0]["experiment_id"]==manifest["experiment_id"] and json.loads(exp[0]["manifest_json"])==manifest,"Snapshot DB/scientific manifest differs")
    need({r[0]:r[1] for r in db.execute("SELECT repetition,COUNT(*) FROM jobs GROUP BY repetition")}=={1:target,2:target,3:target},"Original database job coverage differs")
    need(db.execute("SELECT COUNT(*) FROM instances").fetchone()[0]==16000,"Original DB instance coverage differs")
    bids=[b["batch_id"] for b in selected]; marks=",".join("?" for _ in bids)
    jobs=[dict(r) for r in db.execute(f"""SELECT j.*,i.batch_id FROM jobs j JOIN instances i USING(instance_id)
        WHERE i.batch_id IN ({marks}) AND j.repetition=1 ORDER BY j.ordinal""",bids)]
    need({j["job_id"] for j in jobs}==set(expected) and len(jobs)==len(expected),"Selected scheduled jobs missing/extra/duplicated")
    for job in jobs: need(all(job[k]==v for k,v in expected[job["job_id"]].items()),"Selected schedule/config identity differs")
    for row in db.execute(f"SELECT * FROM instances WHERE batch_id IN ({marks})",bids):
        r=records.get(row["instance_id"])
        need(r is not None and json.loads(row["manifest_record_json"])==r and (row["block_side"],row["board_side"],row["content_sha256"])==(r["n"],r["N"],r["content_sha256"]),"Snapshot selected instance metadata differs")
    for batch in selected:
        b=db.execute("SELECT * FROM batches WHERE batch_id=?",(batch["batch_id"],)).fetchone()
        n=sum(j["batch_id"]==batch["batch_id"] for j in jobs)
        need(b is not None and b["ordinal"]==batch["ordinal"] and b["expected_instances"]==len(batch["instance_ids"]) and b["expected_jobs"]==n*3,"Snapshot original batch denominator differs")
    query=f"""SELECT j.job_id,j.instance_id,j.method,j.encoding,j.repetition,j.ordinal,j.state AS job_state,i.batch_id,
        p.attempt_id AS primary_attempt_id,a.attempt_id,a.job_id AS attempt_job_id,a.attempt_no,a.session_id,
        a.state AS attempt_state,a.started_utc,a.ended_utc,a.attempt_wall_seconds,r.status,r.result_json,r.solution_attempt_id,
        s.payload,s.sha256 AS solution_hash,s.checker_json FROM jobs j JOIN instances i USING(instance_id)
        LEFT JOIN primary_attempt p USING(job_id) LEFT JOIN attempts a ON a.attempt_id=p.attempt_id
        LEFT JOIN results r ON r.attempt_id=p.attempt_id LEFT JOIN solutions s ON s.attempt_id=p.attempt_id
        WHERE i.batch_id IN ({marks}) AND j.repetition=1 ORDER BY j.ordinal"""
    observations=[dict(r) for r in db.execute(query,bids)]
    need(len(observations)==len(expected) and all(r["attempt_id"] is not None for r in observations),"Selected primary results incomplete; no rolling receipt")
    running=db.execute(f"""SELECT 1 FROM attempts a JOIN jobs j USING(job_id) JOIN instances i USING(instance_id)
        WHERE i.batch_id IN ({marks}) AND j.repetition=1 AND a.state='RUNNING' LIMIT 1""",bids).fetchone()
    need(running is None,"Selected jobs still have running attempts")
    rejected=db.execute(f"""SELECT 1 FROM events e JOIN jobs j USING(job_id) JOIN instances i USING(instance_id)
        WHERE i.batch_id IN ({marks}) AND j.repetition=1 AND e.type IN ('HALTED','REJECTED_OBSERVATION') LIMIT 1""",bids).fetchone()
    need(rejected is None,"Selected job has fatal/rejected evidence")
    puzzles=verify_inputs(manifest,index,records,staging)
    checkpoints={}
    for r in db.execute(f"""SELECT e.attempt_id,e.details_json FROM events e JOIN attempts a USING(attempt_id)
        JOIN jobs j USING(job_id) JOIN instances i USING(instance_id) WHERE i.batch_id IN ({marks}) AND j.repetition=1 AND e.type='CHECKPOINT'""",bids):
        value=json.loads(r["details_json"])["checkpoint_seconds"]
        need(r["attempt_id"] not in checkpoints and finite(value),"Invalid/duplicate checkpoint telemetry")
        checkpoints[r["attempt_id"]]=value
    profiles={}; exported=[]; counts=Counter()
    (staging/"solutions").mkdir(); (staging/"session-manifests").mkdir()
    for r in observations:
        record=records[r["instance_id"]]; result=check_observation(r,record,puzzles[r["instance_id"]])
        sid=r["session_id"]; session=db.execute("SELECT * FROM sessions WHERE session_id=?",(sid,)).fetchone()
        need(session is not None and timestamp(session["started_utc"])<=timestamp(r["started_utc"]),"Attempt session/time identity differs")
        if session["ended_utc"]: need(timestamp(session["ended_utc"])>=timestamp(r["ended_utc"]),"Attempt ends after session")
        if sid not in profiles: profiles[sid]=session_profile(experiment,manifest,sid,session,staging)
        profile=profiles[sid]
        out=dict.fromkeys(FIELDS)
        out.update(schema_version=2,experiment_id=manifest["experiment_id"],dataset_id=manifest["dataset_id"],phase="main",cutoff_seconds=10.0)
        out.update({k:r[k] for k in ("batch_id","job_id","attempt_id","attempt_no","instance_id","method","encoding","repetition","attempt_wall_seconds","session_id")})
        out.update(block_side=record["n"],board_side=record["N"],checkpoint_seconds=checkpoints.get(r["attempt_id"]))
        for key in ("source","source_group","rating_original","rating_value","family","root_id","clue_percent_requested","actual_clues","input_sha256"): out[key]=record[key]
        for key in ("status","raw_status","build_seconds","solve_seconds","total_seconds","guard_phase","error"): out[key]=result.get(key)
        for key in ("primary_variables","auxiliary_variables","total_variables","clauses"): out[key]=(result.get("stats") or {}).get(key)
        if result.get("validation") is not None: out.update(validation="pass",validation_message=result["validation"].get("message"))
        for key in ("profile","workers","timing_policy"): out[key]=profile[key]
        if r["status"]=="SAT":
            relative=f"solutions/{r['attempt_id']}.json"; (staging/relative).write_bytes(r["payload"])
            out.update(solution_ref=relative,solution_sha256=r["solution_hash"])
        exported.append(out); counts[r["status"]]+=1
    with (staging/"results.csv").open("x",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=FIELDS); writer.writeheader(); writer.writerows(exported)
    with (staging/"instances.jsonl").open("x",encoding="utf-8",newline="\n") as stream:
        for batch in selected:
            for iid in batch["instance_ids"]: stream.write(packed(records[iid])+"\n")
    write(staging/"profiles.json",profiles)
    return dict(selected_batch_ids=bids,expected_jobs=len(expected),observed_jobs=len(observations),selected_instances=len(records),target_jobs=target,
        target_instances=len(index["records"]),primary_counts=dict(counts),source_state_at_snapshot=exp[0]["state"],
        profile_counts={sid:sum(r["session_id"]==sid for r in observations) for sid in profiles},
        last_event_id=db.execute("SELECT COALESCE(MAX(event_id),0) FROM events").fetchone()[0])


def export_rolling(experiment_dir,output_dir):
    experiment=Path(experiment_dir).resolve(); output=Path(output_dir).resolve()
    need(not output.exists(),"Snapshot destination already exists; never overwrite")
    need(not output.is_relative_to(experiment),"Snapshot must be outside the live experiment")
    manifest_bytes=(experiment/"experiment.json").read_bytes(); index_bytes=(experiment/"dataset-index.json").read_bytes()
    manifest=json.loads(manifest_bytes); index=json.loads(index_bytes)
    expected_plan(manifest,index)  # Reject artificial/incorrect scope before backup.
    staging=output.with_name(output.name+".incomplete-"+uuid.uuid4().hex); staging.mkdir(parents=True)
    try:
        (staging/"source-manifest.json").write_bytes(manifest_bytes); (staging/"source-index.json").write_bytes(index_bytes)
        make_backup(experiment/"experiment.sqlite3",staging/"snapshot.sqlite3")
        need(not (staging/"snapshot.sqlite3-wal").exists(),"Backup left unresolved WAL")
        db=sqlite3.connect((staging/"snapshot.sqlite3").as_uri()+"?mode=ro&immutable=1",uri=True)
        db.row_factory=sqlite3.Row
        try: evidence=verify_snapshot(db,experiment,staging,manifest,index)
        finally: db.close()
        need((experiment/"experiment.json").read_bytes()==manifest_bytes and (experiment/"dataset-index.json").read_bytes()==index_bytes,"Immutable source metadata changed during verification")
        hashes={str(p.relative_to(staging)).replace("\\","/"):sha(p) for p in sorted(staging.rglob("*")) if p.is_file()}
        receipt=dict(schema_version=1,kind="VERIFIED_ROLLING_SNAPSHOT",qa_passed=True,status="PASS",scope="VERIFIED_SUBSET",full_experiment_complete=False,
            source_experiment_id=manifest["experiment_id"],source_scientific_sha256=manifest["scientific_sha256"],created_utc=datetime.now(timezone.utc).isoformat(),
            selected_repetitions=[1],effective_repetitions=1,original_repetitions=3,selector=SELECTOR,
            source_experiment_dir=str(experiment),files_sha256=hashes,sqlite_snapshot_contains_excluded_rows=True,
            timing_policy="Separate by session/profile; parallel is resource-contended; no median3 or isolated speedup claim",
            evidence=dict(backup="one SQLite backup API snapshot; closed before verification",checker="independent selected input/witness and all stored SAT grid checks",
                exporter_sha256=sha(__file__),policy_path="docs/rolling-report-plan-20261019.md",policy_sha256=sha(ROOT/"docs/rolling-report-plan-20261019.md")),**evidence)
        write(staging/"snapshot.json",receipt)
        receipt_hash=sha(staging/"snapshot.json")
        need(not output.exists(),"Snapshot destination appeared during export")
        staging.rename(output)
        return dict(output_dir=str(output),snapshot_sha256=receipt_hash,**evidence,status="PASS")
    except Exception as exc:
        # Do not leave a PASS-looking receipt in a failed/partially published tree.
        receipt=staging/"snapshot.json"
        if receipt.exists():
            unpublished=read(receipt); unpublished.update(status="FAIL",qa_passed=False,kind="UNPUBLISHED_ROLLING_SNAPSHOT")
            receipt.write_text(packed(unpublished)+"\n",encoding="utf-8")
            receipt.rename(staging/"unpublished-receipt.json")
        write(staging/"failure.json",dict(status="FAIL",qa_passed=False,error=f"{type(exc).__name__}: {exc}"))
        raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment",type=Path,required=True); parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try: result=export_rolling(args.experiment,args.output)
    except Exception as exc:
        print(f"Rolling export rejected: {type(exc).__name__}: {exc}",file=sys.stderr); return 2
    print(packed(result)); return 0


if __name__=="__main__": raise SystemExit(main())

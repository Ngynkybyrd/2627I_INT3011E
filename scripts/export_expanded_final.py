"""Self-contained all-rep1 final snapshot, retaining the exact declared ERROR."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import argparse,csv,importlib.util,json,pathlib,shutil,sqlite3,sys,uuid

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("rolling_helpers",ROOT/"scripts/export_expanded_rolling.py")
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
need=r.need
QUALITY="VERIFIED_WITH_DECLARED_INFRASTRUCTURE_ERROR"
CONTRACT=ROOT/"diagnostics/expansion/final-export/CONTRACT.json"
ROOT_EVIDENCE=ROOT/"diagnostics/expansion/root-wave3"


def plan(manifest,index):
    need(manifest["schema_version"]==index["schema_version"]==2 and manifest["artificial"] is False and index["artificial"] is False,"Real schema2 dataset required")
    need(manifest["phase"]==index["phase"]=="main" and manifest["dataset_id"]==index["dataset_id"],"Dataset subject mismatch")
    need(manifest["config"]["repetitions"]==3 and manifest["config"]["cutoff_seconds"]==10,"Original protocol changed")
    need(manifest["scientific_sha256"]==r.digest(r.packed({k:v for k,v in manifest.items() if k not in ("scientific_sha256","created_utc")}).encode()),"Scientific hash changed")
    for key in ("config","matrix"):need(r.digest(r.packed(manifest[key]).encode())==manifest[key+"_sha256"],"Config/matrix hash changed")
    cells=defaultdict(list)
    for cell in manifest["matrix"]["rows"]:
        if cell["eligible"]:cells[cell["N"]].append(cell)
    allowed9={"sat:pairwise","sat:seqcounter","sat:bitwise","cpsat","highs","gurobi","cplex_mip","cpoptimizer"}
    allowedlarge={"sat:pairwise","sat:seqcounter","sat:bitwise","cpsat","highs"}
    need({n:{c["configuration"] for c in group} for n,group in cells.items()}=={9:allowed9,16:allowedlarge,25:allowedlarge},"Wrong frozen eligible matrix")
    need(len(manifest["matrix"]["rows"])==24 and sum(len(c) for c in cells.values())==18,"Duplicate/missing matrix cells")
    need(len(index["records"])==16000 and len(index["batches"])==100,"Wrong original data coverage")
    expected={};ordinal=0;assigned=[]
    for number,batch in enumerate(index["batches"],1):
        need(batch["batch_id"]==f"b{number:03d}" and batch["ordinal"]==number and len(batch["instance_ids"])==160,"Frozen batch changed")
        jobs=[];assigned.extend(batch["instance_ids"])
        for iid in batch["instance_ids"]:
            record=index["records"][iid];need(record["batch_id"]==batch["batch_id"],"Batch membership changed")
            for cell in cells[record["N"]]:
                encoding=cell.get("encoding") or ""
                need(cell["configuration"]==cell["method"]+(":"+encoding if encoding else ""),"Configuration identity changed")
                for rep in (1,2,3):
                    jid="j2-"+r.digest(r.packed([manifest["experiment_id"],iid,cell["method"],encoding,rep]).encode())
                    jobs.append(dict(job_id=jid,instance_id=iid,method=cell["method"],encoding=encoding,repetition=rep,configuration=cell["configuration"],batch_id=batch["batch_id"]))
        jobs.sort(key=lambda j:(r.digest(f"20261019|schedule|main|{batch['batch_id']}|{j['job_id']}".encode()),j["job_id"]))
        for job in jobs:
            ordinal+=1
            if job["repetition"]==1:expected[job["job_id"]]=dict(job,ordinal=ordinal)
    need(len(assigned)==len(set(assigned))==16000 and set(assigned)==set(index["records"]),"Duplicate/missing instance identity")
    need(len(expected)==110000 and ordinal==330000,"Wrong derived job denominator")
    return expected


def inputs(manifest,index,staging):
    source=pathlib.Path(manifest["dataset_dir"]);freeze=r.read(source/"freeze.json")
    need(r.sha(source/"freeze.json")==manifest["dataset_freeze_sha256"]==index["freeze_sha256"],"Dataset freeze changed")
    need(freeze["frozen"] is True and freeze["all_witness_check_pass"] is True and freeze["artificial"] is False,"Unfrozen/artificial witness dataset")
    hashes=freeze["files_sha256"];records=index["records"]
    metadata={"freeze.json":"source-freeze.json","dataset.json":"source-dataset.json","manifest.jsonl":"instances.jsonl","roots.jsonl":"source-roots.jsonl","batches.json":"source-batches.json","provenance.json":"source-provenance.json"}
    for name,dest in metadata.items():
        if name!="freeze.json":need(r.sha(source/name)==hashes[name],"Frozen metadata hash mismatch: "+name)
        shutil.copyfile(source/name,staging/dest)
    frozen_records={v["instance_id"]:v for v in (json.loads(line) for line in (staging/"instances.jsonl").read_text(encoding="utf-8-sig").splitlines() if line)}
    need(frozen_records==records,"Index records differ from frozen records")
    frozen_batches=r.read(staging/"source-batches.json");need((frozen_batches if isinstance(frozen_batches,list) else frozen_batches["batches"])==index["batches"],"Frozen batches differ")
    sources={k.replace("\\","/"):v for k,v in manifest["fingerprint"]["source_sha256"].items()}
    for name in ("src/sudoku/model.py","src/sudoku/validation.py","src/sudoku/contracts.py"):need(r.sha(ROOT/name)==sources[name],"Checker/model source changed")
    db=sqlite3.connect(staging/"inputs.sqlite3")
    db.execute("CREATE TABLE inputs(instance_id TEXT PRIMARY KEY,block_side INTEGER,board_side INTEGER,input_payload BLOB,input_sha256 TEXT,input_canonical_sha256 TEXT,witness_payload BLOB,witness_sha256 TEXT,witness_canonical_sha256 TEXT)")
    puzzles={};groups=defaultdict(list)
    try:
        for iid,record in records.items():
            payloads=[];parsed=[]
            for pathkey,hashkey in (("input_file","input_sha256"),("witness_file","witness_sha256")):
                data=r.inside(source,record[pathkey]).read_bytes();need(r.digest(data)==record[hashkey]==hashes[record[pathkey]],"Input/witness hash mismatch")
                raw=json.loads(data);parsed.append(r.Puzzle(raw["n"],raw["grid"]));payloads.append(data)
            p,w=parsed;content=r.digest(r.canonical(p.n,p.grid));wcontent=r.digest(r.canonical(w.n,w.grid))
            need(p.n==w.n==record["n"] and p.N==record["N"] and p.clue_count==record["actual_clues"],"Input dimensions/clues differ")
            need(content==record["content_sha256"] and iid==f"e2-main-N{p.N}-{content}" and wcontent==record["witness_content_sha256"],"Canonical input/witness identity differs")
            need(r.check_solution(p,w.grid).valid and record["witness_validation"]["valid"] is True and record["witness_validation"]["checker_code_sha256"]==sources["src/sudoku/validation.py"],"Independent acquisition witness/checker failure")
            if record["source"]=="synthetic":
                need(record["root_content_sha256"]==wcontent and p.clue_count==(record["clue_percent_requested"]*p.N*p.N+50)//100,"Synthetic root/mask differs")
                groups[record["root_id"]].append(record)
            db.execute("INSERT INTO inputs VALUES(?,?,?,?,?,?,?,?,?)",(iid,p.n,p.N,payloads[0],record["input_sha256"],content,payloads[1],record["witness_sha256"],wcontent));puzzles[iid]=p
        for rid,children in groups.items():
            root=index["roots"][rid];data=r.inside(source,root["grid_file"]).read_bytes();raw=json.loads(data);grid=r.Puzzle(raw["n"],raw["grid"])
            need(r.digest(data)==hashes[root["grid_file"]]==root["grid_sha256"] and r.check_solution(grid,grid.grid).valid,"Frozen root hash/checker failure")
            need(r.digest(r.canonical(grid.n,grid.grid))==root["root_content_sha256"] and all(c["root_content_sha256"]==root["root_content_sha256"] for c in children),"Root content relationship mismatch")
            need(len(children)==5 and sorted(c["clue_percent_requested"] for c in children)==[20,30,40,50,60] and len({c["batch_id"] for c in children})==1,"Incomplete/split root cluster")
        db.commit();need(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","Packaged input integrity failure")
    finally:db.close()
    return puzzles


def copy_ref(staging,path,expected=None):
    path=pathlib.Path(path);data=path.read_bytes();h=r.digest(data)
    need(expected is None or h==expected,"Evidence reference changed: "+str(path))
    relative="evidence/refs/"+h+path.suffix
    target=staging/relative
    if not target.exists():target.write_bytes(data)
    return dict(path=relative,sha256=h),json.loads(data) if path.suffix==".json" else None


def root_evidence(manifest,staging):
    result={};refs={}
    for name in ("final-recovery-acceptance.json","final-recovery-data-audit.json","recovery-final-status.json","handle-error-recovery-ack.json","handle-error-diagnostic-retry.json"):
        data=(ROOT_EVIDENCE/name).read_bytes();(staging/"evidence"/name).write_bytes(data);result[name]=json.loads(data);refs[name]=dict(path="evidence/"+name,sha256=r.digest(data))
    need(result["final-recovery-data-audit.json"]["status"]=="PASS","Root final data audit not PASS")
    ack=result["handle-error-recovery-ack.json"]
    need(ack["accepted"] is True and ack["accepted_by"]=="root" and ack["experiment_id"]==manifest["experiment_id"] and ack["scientific_sha256"]==manifest["scientific_sha256"],"Wrong/unaccepted declared-error subject")
    need(len(ack["acknowledged_fatal_results"])==1,"Wrong declared error count")
    status=result["recovery-final-status.json"];sid=status["last_session"]["session_id"]
    need(status["rep1_done"]==110000 and status["rep1_pending"]==status["running_attempts"]==status["open_sessions"]==0,"Root completion incomplete")
    return result,refs,sid


def profile(saved):
    name=saved.get("profile","original-sequential");workers=saved.get("workers",1);timing=saved.get("timing_policy","sequential")
    if name=="original-sequential":need(workers==1 and timing=="sequential","Wrong sequential workers/policy")
    else:
        need(name in ("parallel-throughput-v1","parallel-throughput-capacity-v1","parallel-throughput-capacity-fast-v1","parallel-throughput-capacity-recovery-v2") and type(workers) is int and 1<workers<=100 and timing=="resource-contended" and saved["reporting_policy"]=="separate-by-session","Unknown/invalid parallel profile")
        if name=="parallel-throughput-v1":need(workers==4,"Wrong original parallel worker count")
        if "selected_repetitions" in saved:need(saved["selected_repetitions"]==[1] and saved["effective_repetitions"]==1 and saved["target_jobs"]==110000,"Wrong effective scope")
    return name,workers,timing


def profiles(db,experiment,manifest,staging):
    out={}
    for row in db.execute("SELECT DISTINCT a.session_id FROM primary_attempt p JOIN attempts a USING(attempt_id) JOIN jobs j USING(job_id) WHERE j.repetition=1"):
        sid=row[0];source=experiment/"session-manifests"/(sid+".json");data=source.read_bytes();saved=json.loads(data)
        need(saved["session_id"]==sid and saved["scientific_manifest"]==manifest,"Session/scientific subject differs")
        session=db.execute("SELECT * FROM sessions WHERE session_id=?",(sid,)).fetchone();need(session["ended_utc"] is not None,"Unclosed selected session")
        name,workers,timing=profile(saved);gate_refs={}
        for key in ("dataset","qa","preflight","pilot","execution_freeze"):
            ref=saved["gate_refs"]["gates"][key];need(ref["accepted"] is True and ref["accepted_by"]=="root","Unaccepted session gate")
            gate_refs[key],_=copy_ref(staging,r.inside(ROOT,ref["path"]),ref["sha256"])
        authref=None
        if workers>1:
            auth=saved["authorization"];authref,receipt=copy_ref(staging,r.inside(ROOT,auth["path"]),auth["sha256"])
            need(receipt==auth["receipt"] and receipt["accepted"] is True and receipt["accepted_by"]=="root" and receipt["experiment_id"]==manifest["experiment_id"] and receipt["scientific_sha256"]==manifest["scientific_sha256"],"Authorization subject/hash differs")
            need((receipt["profile"],receipt["workers"],receipt["timing_policy"],receipt["script_sha256"])==(name,workers,timing,saved["script_sha256"]),"Authorized worker/profile/script differs")
        relative="session-manifests/"+sid+".json";(staging/relative).write_bytes(data)
        metrics=source.with_name(sid+".metrics.json")
        if metrics.exists():shutil.copyfile(metrics,staging/"session-manifests"/metrics.name)
        out[sid]=dict(session_id=sid,profile=name,workers=workers,timing_policy=timing,reporting_policy="separate-by-session",source_session_manifest=relative,source_session_manifest_sha256=r.digest(data),gate_refs=gate_refs,authorization=authref,lifecycle_fix=saved.get("lifecycle_fix"),historical_script_sha256=saved.get("script_sha256"),started_utc=session["started_utc"],ended_utc=session["ended_utc"])
    return out


def check_row(row,record,puzzle,declared):
    if row["status"]!="ERROR":return r.check_observation(row,record,puzzle)
    need({k:row[k] for k in ("attempt_id","job_id","status","result_json")}==declared,"Unexpected/nonexact ERROR; export must fail")
    need(row["attempt_state"]=="FINISHED" and row["job_state"]=="TERMINAL" and row["attempt_job_id"]==row["job_id"] and row["primary_attempt_id"]==row["attempt_id"],"Declared ERROR identity/state differs")
    result=json.loads(row["result_json"])
    need(record["N"]==16 and record["batch_id"]=="b099" and result["method"]==row["method"]=="sat" and result["encoding"]==row["encoding"]=="seqcounter","Declared ERROR configuration differs")
    need(result["guard_phase"]=="guard" and result["error"]=="OSError: [WinError 6] The handle is invalid" and all(result[k] is None for k in ("build_seconds","solve_seconds","total_seconds","stats","validation","raw_status")),"Wrong infrastructure ERROR/timing classification")
    need(row["solution_attempt_id"] is None and row["payload"] is None and r.finite(row["attempt_wall_seconds"]),"ERROR cannot carry a solution or invalid wall time")
    return result


def verify(db,experiment,staging,manifest,index):
    expected=plan(manifest,index)
    need(db.execute("PRAGMA user_version").fetchone()[0]==2 and db.execute("PRAGMA integrity_check").fetchone()[0]=="ok" and not db.execute("PRAGMA foreign_key_check").fetchall(),"Raw snapshot SQLite integrity/FK failure")
    exp=db.execute("SELECT * FROM experiment").fetchall();need(len(exp)==1 and json.loads(exp[0]["manifest_json"])==manifest and exp[0]["experiment_id"]==manifest["experiment_id"],"Snapshot scientific identity changed")
    need(not db.execute("SELECT 1 FROM attempts WHERE state='RUNNING'").fetchone() and not db.execute("SELECT 1 FROM sessions WHERE ended_utc IS NULL").fetchone(),"Active attempt/open session")
    need({x[0]:x[1] for x in db.execute("SELECT repetition,COUNT(*) FROM jobs GROUP BY repetition")}=={1:110000,2:110000,3:110000},"Original jobs changed")
    excluded={str(x[0]):x[1] for x in db.execute("SELECT j.repetition,COUNT(*) FROM primary_attempt p JOIN jobs j USING(job_id) WHERE j.repetition!=1 GROUP BY j.repetition")};need(excluded=={"2":324,"3":343},"Unexpected excluded historical scope")
    observed_jobs={}
    for row in db.execute("SELECT j.*,i.batch_id FROM jobs j JOIN instances i USING(instance_id) WHERE j.repetition=1"):
        job=dict(row);need(job["job_id"] in expected and all(job[k]==v for k,v in expected[job["job_id"]].items()) and job["state"]=="TERMINAL","Missing/extra/incorrect schedule identity or pending rep1")
        observed_jobs[job["job_id"]]=job
    need(set(observed_jobs)==set(expected),"Missing expected job ID")
    need(db.execute("SELECT COUNT(*) FROM instances").fetchone()[0]==16000,"DB instance coverage differs")
    for row in db.execute("SELECT * FROM instances"):
        record=index["records"].get(row["instance_id"]);need(record is not None and json.loads(row["manifest_record_json"])==record and (row["block_side"],row["board_side"],row["content_sha256"],row["batch_id"])==(record["n"],record["N"],record["content_sha256"],record["batch_id"]),"DB frozen instance differs")
    need(db.execute("""SELECT COUNT(*) FROM attempts a JOIN jobs j USING(job_id) LEFT JOIN results r USING(attempt_id) LEFT JOIN primary_attempt p ON p.attempt_id=a.attempt_id
        WHERE j.repetition=1 AND ((a.state='FINISHED' AND (r.attempt_id IS NULL OR p.attempt_id IS NULL)) OR (a.state!='FINISHED' AND r.attempt_id IS NOT NULL))""").fetchone()[0]==0,"Unprimary/duplicate terminal or nonterminal result")
    evidence,evidence_refs,completion_sid=root_evidence(manifest,staging)
    completion_path=experiment/"scope-completions"/(completion_sid+".json");completion= r.read(completion_path);shutil.copyfile(completion_path,staging/"evidence/completion.json")
    need(completion["scope_state"]=="COMPLETED_WITH_ERROR" and completion["error_free"] is False and completion["all_selected_jobs_observed"] is True and completion["scope_remaining_jobs"]==0 and completion["scope_completed_jobs"]==110000 and completion["selected_repetitions"]==[1],"Wrong completion scope/quality")
    declared=evidence["handle-error-recovery-ack.json"]["acknowledged_fatal_results"][0];need(completion["preserved_errors"]==[declared],"Completion does not preserve exact declared error")
    puzzles=inputs(manifest,index,staging);contexts=profiles(db,experiment,manifest,staging)
    checkpoints={}
    for row in db.execute("SELECT e.attempt_id,e.details_json FROM events e JOIN attempts a USING(attempt_id) JOIN jobs j USING(job_id) WHERE j.repetition=1 AND e.type='CHECKPOINT'"):
        value=json.loads(row[1])["checkpoint_seconds"];need(row[0] not in checkpoints and r.finite(value),"Invalid duplicate checkpoint telemetry");checkpoints[row[0]]=value
    query="""SELECT j.job_id,j.instance_id,j.method,j.encoding,j.repetition,j.ordinal,j.state AS job_state,i.batch_id,
        p.attempt_id AS primary_attempt_id,a.attempt_id,a.job_id AS attempt_job_id,a.attempt_no,a.session_id,a.state AS attempt_state,a.started_utc,a.ended_utc,a.attempt_wall_seconds,
        r.status,r.result_json,r.solution_attempt_id,s.payload,s.sha256 AS solution_hash,s.checker_json FROM jobs j JOIN instances i USING(instance_id)
        LEFT JOIN primary_attempt p USING(job_id) LEFT JOIN attempts a ON a.attempt_id=p.attempt_id LEFT JOIN results r ON r.attempt_id=p.attempt_id
        LEFT JOIN solutions s ON s.attempt_id=p.attempt_id WHERE j.repetition=1 ORDER BY j.ordinal"""
    counts=Counter();by_size=defaultdict(Counter);by_config=defaultdict(Counter);sessions=Counter();seen=set()
    with (staging/"results.csv").open("x",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=r.FIELDS);writer.writeheader()
        for raw in db.execute(query):
            row=dict(raw);need(row["attempt_id"] is not None and row["job_id"] not in seen,"Missing/duplicate primary")
            record=index["records"][row["instance_id"]];result=check_row(row,record,puzzles[row["instance_id"]],declared);context=contexts[row["session_id"]]
            need(r.timestamp(context["started_utc"])<=r.timestamp(row["started_utc"])<=r.timestamp(row["ended_utc"])<=r.timestamp(context["ended_utc"]),"Session/attempt chronology differs")
            out=dict.fromkeys(r.FIELDS);out.update(schema_version=2,experiment_id=manifest["experiment_id"],dataset_id=manifest["dataset_id"],phase="main",cutoff_seconds=10.0,block_side=record["n"],board_side=record["N"],checkpoint_seconds=checkpoints.get(row["attempt_id"]))
            for key in ("batch_id","job_id","attempt_id","attempt_no","instance_id","method","encoding","repetition","attempt_wall_seconds","session_id"):out[key]=row[key]
            for key in ("source","source_group","rating_original","rating_value","family","root_id","clue_percent_requested","actual_clues","input_sha256"):out[key]=record[key]
            for key in ("status","raw_status","build_seconds","solve_seconds","total_seconds","guard_phase","error"):out[key]=result.get(key)
            for key in ("primary_variables","auxiliary_variables","total_variables","clauses"):out[key]=(result.get("stats") or {}).get(key)
            for key in ("profile","workers","timing_policy"):out[key]=context[key]
            if result.get("validation") is not None:out.update(validation="pass",validation_message=result["validation"].get("message"))
            if row["status"]=="SAT":out.update(solution_ref="sqlite:snapshot.sqlite3#solutions/"+row["attempt_id"],solution_sha256=row["solution_hash"])
            writer.writerow(out);seen.add(row["job_id"]);counts[row["status"]]+=1;by_size[record["N"]][row["status"]]+=1;by_config[(record["N"],observed_jobs[row["job_id"]]["configuration"])][row["status"]]+=1;sessions[row["session_id"]]+=1
    need(seen==set(expected) and counts=={"SAT":109664,"TIMEOUT":335,"ERROR":1},"Incomplete/unexpected final primary status counts")
    for n,values in ((9,{"SAT":80000}),(16,{"SAT":24998,"TIMEOUT":1,"ERROR":1}),(25,{"SAT":4666,"TIMEOUT":334})):need(by_size[n]==values,"Status counts by board size differ")
    retry=evidence["handle-error-diagnostic-retry.json"];error_record=index["records"][observed_jobs[declared["job_id"]]["instance_id"]]
    need(retry["kind"]=="SUPPLEMENTAL_DIAGNOSTIC_NOT_PRIMARY" and retry["original_error_retained"] is True and retry["job_id"]==declared["job_id"] and retry["result"]["status"]=="SAT" and r.check_solution(puzzles[error_record["instance_id"]],retry["result"]["solution"]).valid,"Diagnostic evidence identity/checker differs")
    r.write(staging/"profiles.json",contexts)
    return dict(expected_jobs=len(expected),observed_jobs=len(seen),selected_instances=len(puzzles),primary_counts=dict(counts),by_size={str(k):dict(v) for k,v in by_size.items()},by_configuration=[dict(N=n,configuration=c,counts=dict(v)) for (n,c),v in sorted(by_config.items())],session_counts=dict(sessions),excluded_primary_counts=excluded,declared_error=dict(declared,batch_id="b099",classification="premeasurement guard infrastructure error; not cleanup failure",ack_evidence=evidence_refs["handle-error-recovery-ack.json"],diagnostic_retry_evidence=evidence_refs["handle-error-diagnostic-retry.json"],diagnostic_retry_included_in_primary=False),root_evidence=evidence_refs,source_state=exp[0]["state"])


def export_final(experiment_dir,output_dir):
    experiment=pathlib.Path(experiment_dir).resolve();output=pathlib.Path(output_dir).resolve();need(not output.exists() and not output.is_relative_to(experiment),"Destination must be NEW and outside live source")
    mb=(experiment/"experiment.json").read_bytes();ib=(experiment/"dataset-index.json").read_bytes();manifest=json.loads(mb);index=json.loads(ib)
    need(manifest.get("artificial") is False and index.get("artificial") is False,"Artificial final evidence forbidden")
    stage=output.with_name(output.name+".incomplete-"+uuid.uuid4().hex);stage.mkdir(parents=True)
    try:
        (stage/"source-manifest.json").write_bytes(mb);(stage/"source-index.json").write_bytes(ib);shutil.copyfile(CONTRACT,stage/"CONTRACT.json")
        (stage/"evidence/refs").mkdir(parents=True);(stage/"session-manifests").mkdir()
        r.make_backup(experiment/"experiment.sqlite3",stage/"snapshot.sqlite3")
        db=sqlite3.connect((stage/"snapshot.sqlite3").as_uri()+"?mode=ro&immutable=1",uri=True);db.row_factory=sqlite3.Row
        try:summary=verify(db,experiment,stage,manifest,index)
        finally:db.close()
        need((experiment/"experiment.json").read_bytes()==mb and (experiment/"dataset-index.json").read_bytes()==ib,"Immutable source metadata changed")
        hashes={str(p.relative_to(stage)).replace("\\","/"):r.sha(p) for p in sorted(stage.rglob("*")) if p.is_file()}
        receipt=dict(schema_version=1,kind="VERIFIED_FINAL_REP1_SNAPSHOT",status="PASS",qa_passed=True,quality=QUALITY,error_free=False,selected_scope_observed_complete=True,original_three_repetition_experiment_complete=False,selected_repetitions=[1],effective_repetitions=1,original_repetitions=3,source_experiment_id=manifest["experiment_id"],source_scientific_sha256=manifest["scientific_sha256"],created_utc=datetime.now(timezone.utc).isoformat(),files_sha256=hashes,producer_sha256=r.sha(__file__),rolling_helper_sha256=r.sha(ROOT/"scripts/export_expanded_rolling.py"),**summary)
        r.write(stage/"snapshot.json",receipt);h=r.sha(stage/"snapshot.json");need(not output.exists(),"Destination appeared during verification");stage.rename(output)
        return dict(status="PASS",quality=QUALITY,output_dir=str(output),snapshot_sha256=h,expected_jobs=110000,observed_jobs=summary["observed_jobs"],primary_counts=summary["primary_counts"],selected_instances=summary["selected_instances"])
    except Exception as exc:
        r.write(stage/"failure.json",dict(status="FAIL",qa_passed=False,error=f"{type(exc).__name__}: {exc}"));raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--experiment",type=pathlib.Path,required=True);parser.add_argument("--output",type=pathlib.Path,required=True);args=parser.parse_args(argv)
    try:result=export_final(args.experiment,args.output)
    except Exception as exc:print(f"Final snapshot rejected: {type(exc).__name__}: {exc}",file=sys.stderr);return 2
    print(r.packed(result));return 0


if __name__=="__main__":raise SystemExit(main())

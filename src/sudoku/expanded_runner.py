"""Public schema2 API. All actual execution is gated; v1 stays unchanged."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import os
import platform
import shutil
import signal
import socket
import statistics
import sys
import threading
import time
from itertools import zip_longest
from sudoku.expanded_common import *
from sudoku.expanded_validation import validate_expanded_dataset, validate_config, validate_matrix
from sudoku import expanded_storage as storage


def _schedule(index, experiment_id, config, matrix):
    eligible=defaultdict(list)
    for row in matrix["rows"]:
        if row["eligible"]:
            eligible[row["N"]].append(row)
    jobs=[]
    for batch in index["batches"]:
        group=[]
        for iid in batch["instance_ids"]:
            record=index["records"][iid]
            require(bool(eligible[record["N"]]),"Instance has no eligible configuration")
            for cell in eligible[record["N"]]:
                for rep in range(1,config["repetitions"]+1):
                    encoding=cell.get("encoding") or ""
                    job_id="j2-"+digest(dumps([experiment_id,iid,cell["method"],encoding,rep]).encode("utf-8"))
                    group.append(dict(job_id=job_id,instance_id=iid,batch_id=batch["batch_id"],configuration=cell["configuration"],method=cell["method"],encoding=encoding,repetition=rep))
        group.sort(key=lambda j:(rank(f"schedule|{index['phase']}|{batch['batch_id']}",j["job_id"]),j["job_id"]))
        jobs.extend(group)
    for ordinal,job in enumerate(jobs,1):
        job["ordinal"]=ordinal
    return jobs


def _fingerprint(artificial):
    from sudoku.runner import machine_info, package_versions
    sources=list((ROOT/"src/sudoku").rglob("*.py"))
    sources += [ROOT/p for p in ("scripts/run_expanded.py","scripts/analyze_expanded.py","scripts/prepare_expanded_data.py","scripts/authorize_expanded_local.py","docs/expanded-contract.md","docs/expanded-acceptance.md","docs/expanded-terminal-policy.md","requirements.txt","pyproject.toml") if (ROOT/p).exists()]
    natives={}
    if not artificial:
        native_file=ROOT/"diagnostics/expansion/env/native-runtime.json"
        for item in read(native_file):
            if any(token in item["path"].lower() for token in ("pysolver","pysat","ortools","highs","cplex","cpoptimizer","gurobi","scipy")):
                path=Path(sys.prefix)/item["path"]
                natives[str(path)]=sha(path)
        for item in read(ROOT/"diagnostics/expansion/env/environment.json")["interpreter_files"]:
            natives[item["path"]]=sha(item["path"])
    return dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(sources)},
                python_executable=sys.executable,machine=machine_info(),packages=package_versions(),
                native_sha256=natives,solver_environment={k:os.environ.get(k) for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS")},
                threads=1,architecture=platform.machine())


@public
def prepare_expanded(dataset_dir, experiment_dir, config_path, matrix_path, *, phase):
    index=validate_expanded_dataset(dataset_dir)
    require(phase==index["phase"],"Dataset/config phase mismatch")
    config,matrix=read(config_path),read(matrix_path)
    validate_config(config,phase); validate_matrix(matrix,index["artificial"])
    output=Path(experiment_dir).resolve()
    require(not output.exists(),"Experiment directory already exists")
    if index["artificial"]:
        require(not output.is_relative_to(ROOT/"results"),"Artificial experiments cannot use results/")
    else:
        base=ROOT/("results/expanded" if phase=="main" else "diagnostics/expansion/pilot")
        require(output.is_relative_to(base.resolve()),"Real experiment output namespace mismatch")
    jobs=_schedule(index,output.name,config,matrix)
    schedule_hash=digest((dumps(jobs)+"\n").encode("utf-8"))
    fingerprint=_fingerprint(index["artificial"])
    manifest=dict(schema_version=2,experiment_id=output.name,phase=phase,artificial=index["artificial"],
        dataset_id=index["dataset_id"],dataset_dir=index["dataset_dir"],dataset_freeze_sha256=index["freeze_sha256"],
        config=config,matrix=matrix,fingerprint=fingerprint,schedule_sha256=schedule_hash,
        config_sha256=digest(dumps(config).encode()),matrix_sha256=digest(dumps(matrix).encode()),
        gate_refs_path=f"diagnostics/expansion/gates/{output.name}.json",created_utc=stamp())
    manifest["scientific_sha256"]=digest(dumps({k:v for k,v in manifest.items() if k!="created_utc"}).encode())
    output.mkdir(parents=True,exist_ok=False)
    write(output/"experiment.json",manifest); write(output/"schedule.json",jobs)
    write(output/"matrix.json",matrix); write(output/"dataset-index.json",index)
    storage.initialize(output,manifest,index,jobs)
    return dict(experiment_id=output.name,state="PREPARED",phase=phase,planned_jobs=len(jobs),planned_blocks=len(index["batches"]),exit_code=0)


def _load(directory, db, *, verify_fingerprint=True, verify_results=True):
    manifest=read(directory/"experiment.json")
    row=db.execute("SELECT * FROM experiment").fetchone()
    require(row is not None and json.loads(row["manifest_json"])==manifest,"Experiment manifest tampered",5)
    require(db.execute("SELECT COUNT(*) FROM experiment").fetchone()[0]==1 and row["experiment_id"]==manifest["experiment_id"]==directory.name,"Experiment identity mismatch",5)
    require(manifest["schema_version"]==2,"Experiment version mismatch")
    subject={k:v for k,v in manifest.items() if k not in ("created_utc","scientific_sha256")}
    require(digest(dumps(subject).encode())==manifest["scientific_sha256"],"Scientific manifest hash mismatch",5)
    require(digest(dumps(manifest["config"]).encode())==manifest["config_sha256"] and digest(dumps(manifest["matrix"]).encode())==manifest["matrix_sha256"],"Config/matrix digest mismatch",5)
    index=validate_expanded_dataset(manifest["dataset_dir"])
    require((index["dataset_id"],index["phase"],index["artificial"])==(manifest["dataset_id"],manifest["phase"],manifest["artificial"]),"Frozen dataset subject/artificial marker mismatch",5)
    require(index["freeze_sha256"]==manifest["dataset_freeze_sha256"],"Dataset freeze mismatch",5)
    validate_config(manifest["config"],manifest["phase"])
    validate_matrix(manifest["matrix"],manifest["artificial"])
    require(read(directory/"matrix.json")==manifest["matrix"],"Matrix changed",5)
    jobs=_schedule(index,manifest["experiment_id"],manifest["config"],manifest["matrix"])
    require(sha(directory/"schedule.json")==manifest["schedule_sha256"]==digest((dumps(jobs)+"\n").encode("utf-8")),"Schedule changed",5)
    db_jobs=db.execute("SELECT job_id,instance_id,configuration,method,encoding,repetition,ordinal FROM jobs ORDER BY ordinal")
    for row,job in zip_longest(db_jobs,jobs):
        require(row is not None and job is not None and dict(row)=={k:v for k,v in job.items() if k!="batch_id"},"Database schedule changed",5)
    counts=Counter(j["batch_id"] for j in jobs)
    expected=[(b["batch_id"],b["ordinal"],len(b["instance_ids"]),counts[b["batch_id"]]) for b in index["batches"]]
    require([tuple(r) for r in db.execute("SELECT batch_id,ordinal,expected_instances,expected_jobs FROM batches ORDER BY ordinal")]==expected,"Database batches changed",5)
    require(db.execute("SELECT COUNT(*) FROM instances").fetchone()[0]==len(index["records"]),"Database instance count changed",5)
    for row in db.execute("SELECT * FROM instances"):
        r=index["records"].get(row["instance_id"])
        require(r is not None and json.loads(row["manifest_record_json"])==r and row["content_sha256"]==r["content_sha256"] and (row["block_side"],row["board_side"],row["batch_id"])==(r["n"],r["N"],r["batch_id"]),"Database dataset changed",5)
    storage.integrity(db)
    if verify_fingerprint:
        require(_fingerprint(manifest["artificial"])==manifest["fingerprint"],"Code/environment fingerprint changed; new experiment required",5)
    if verify_results:
        for _ in storage.checked_primary_results(db,index): pass
    return manifest,index


def _gates(manifest, *, recovery=False):
    require(not manifest["artificial"],"Artificial experiment cannot execute a solver")
    path=contained(ROOT,manifest["gate_refs_path"])
    require(path.exists(),"Root-accepted gate references missing; no worker started")
    gate=read(path)
    require(gate.get("schema_version")==2 and gate.get("experiment_id")==manifest["experiment_id"] and gate.get("scientific_sha256")==manifest["scientific_sha256"],"Gate subject mismatch")
    if gate.get("policy")=="conditional-local-root-wave3-v1":
        ref=gate["code_release"]
        require(sha(contained(ROOT,ref["path"]))==ref["sha256"],"Conditional root code release changed")
    required={"dataset","qa","preflight"}
    if manifest["phase"]=="main": required|={"pilot","execution_freeze"}
    if recovery: required.add("recovery_cleanup")
    refs=gate["gates"]
    for key in required:
        ref=refs.get(key,{})
        require(ref.get("accepted_by")=="root" and ref.get("accepted") is True,f"Root gate not accepted: {key}")
        target=contained(ROOT,ref["path"])
        require(sha(target)==ref["sha256"],f"Gate evidence hash mismatch: {key}")
    return dict(path=manifest["gate_refs_path"],sha256=sha(path),gates=refs)


def _recover(db, manifest):
    running=db.execute("SELECT a.*,s.host,s.pid,s.creation_time FROM attempts a JOIN sessions s USING(session_id) WHERE a.state='RUNNING'").fetchall()
    if running:
        refs=_gates(manifest,recovery=True)  # v1 hides worker PID: explicit cleanup evidence.
        evidence=read(contained(ROOT,refs["gates"]["recovery_cleanup"]["path"]))
        expected=[dict(attempt_id=r["attempt_id"],session_id=r["session_id"],pid=r["pid"],creation_time=r["creation_time"]) for r in running]
        require(evidence.get("cleanup_verified") is True and sorted(evidence.get("orphans",[]),key=lambda r:r["attempt_id"])==sorted(expected,key=lambda r:r["attempt_id"]),"Cleanup evidence does not cover current orphan attempts",5)
        storage.event(db,"RECOVERY_EVIDENCE",refs)
    for row in running:
        require(row["host"]==socket.gethostname(),"Cannot recover a different host",5)
        require(storage.process_identity(row["pid"])!=row["creation_time"],"Previous owner is still alive",3)
    for row in running:
        storage.interrupt(db,row["attempt_id"],"orphan recovered after OS lock + owner identity + root tree-cleanup evidence")


def _pilot_wall_estimates(manifest):
    """Optional, hash-bound root evidence; status never turns this into a run gate."""
    if manifest["artificial"] or manifest["phase"]!="main": return {},None
    path=contained(ROOT,manifest["gate_refs_path"])
    if not path.exists(): return {},None
    gate=read(path)
    require(gate.get("schema_version")==2 and gate.get("experiment_id")==manifest["experiment_id"] and gate.get("scientific_sha256")==manifest["scientific_sha256"],"Pilot ETA gate subject mismatch")
    ref=gate.get("gates",{}).get("pilot")
    if not ref or ref.get("accepted") is not True or ref.get("accepted_by")!="root": return {},None
    target=contained(ROOT,ref["path"])
    require(sha(target)==ref["sha256"],"Pilot ETA evidence hash mismatch")
    estimates={}
    for row in read(target).get("wall_estimates",[]):
        key=(row["N"],row["configuration"]); value=row["median_attempt_wall_seconds"]
        require(row["N"] in (9,16,25) and row["configuration"] in CONFIGURATIONS and finite(value) and key not in estimates,"Invalid/duplicate pilot wall estimate")
        estimates[key]=value
    return estimates,dict(path=ref["path"],sha256=ref["sha256"])


def _run(directory, *, expected_phase=None, resume=False, reason="new run", stop_starting_at=None):
    directory=Path(directory).resolve(); stop=deadline(stop_starting_at)
    require(not resume or bool(reason.strip()),"Resume requires a reason")
    require(not resume or (stop_starting_at is not None and stop>datetime.now(timezone.utc)),"Resume requires an explicit future deadline")
    require((directory/"experiment.json").is_file() and (directory/"experiment.sqlite3").is_file(),"Prepared schema2 experiment required")
    with storage.WriterLock(directory):
        db=storage.connect(directory); sid=None; active=None
        stopped=threading.Event(); old_signal=None
        heartbeat_stop=threading.Event(); heartbeat_errors=[]; thread=None
        try:
            manifest,index=_load(directory,db)
            require(expected_phase is None or manifest["phase"]==expected_phase,"Wrong execution command for phase")
            refs=_gates(manifest)
            state=db.execute("SELECT state FROM experiment").fetchone()[0]
            fatal=db.execute("SELECT 1 FROM results WHERE status NOT IN ('SAT','TIMEOUT') LIMIT 1").fetchone()
            rejected=db.execute("SELECT 1 FROM events WHERE type='REJECTED_OBSERVATION' LIMIT 1").fetchone()
            require(state!="COMPLETED" and rejected is None and (state!="HALTED" or (resume and fatal is None)),f"Cannot execute {state} experiment",5)
            if not resume:
                require(db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==0,"Prior attempts exist; explicit resume required")
            else:
                _recover(db,manifest)
            sid=storage.new_session(db,stop.isoformat(),reason)
            storage.event(db,"GATES_VERIFIED",refs,session=sid)
            (directory/"session-manifests").mkdir(exist_ok=True)
            write(directory/"session-manifests"/(sid+".json"),dict(scientific_manifest=manifest,session_id=sid,gate_refs=refs,stop_starting_at=stop.isoformat()))
            db.execute("UPDATE experiment SET state='RUNNING',halt_reason=NULL")
            heartbeat_ready=threading.Event()
            def heartbeat():
                connection=None
                try:
                    connection=storage.connect(directory)
                    heartbeat_ready.set()
                    while not heartbeat_stop.wait(2):
                        connection.execute("UPDATE sessions SET heartbeat_utc=? WHERE session_id=?",(stamp(),sid))
                except Exception as exc:
                    heartbeat_errors.append(str(exc)); stopped.set()
                finally:
                    heartbeat_ready.set()
                    if connection: connection.close()
            thread=threading.Thread(target=heartbeat,daemon=True); thread.start()
            require(heartbeat_ready.wait(6) and not heartbeat_errors,"Heartbeat could not start",5)
            if threading.current_thread() is threading.main_thread():
                old_signal=signal.signal(signal.SIGINT,lambda *_:stopped.set())
            from sudoku.runner import run_job,RunnerConfig
            cfg=manifest["config"]
            runner_config=RunnerConfig(cutoff_seconds=cfg["cutoff_seconds"],repetitions=cfg["repetitions"],schedule_seed=cfg["schedule_seed"],startup_seconds=cfg["startup_seconds"],postprocessing_seconds=cfg["postprocessing_seconds"])
            pause_reason=None
            while True:
                if stopped.is_set() or datetime.now(timezone.utc)>=stop:
                    pause_reason="stop requested/deadline"; break
                if shutil.disk_usage(directory).free<cfg["disk_reserve_bytes"]:
                    pause_reason="disk reserve"; break
                require(_gates(manifest)==refs,"Accepted gate references changed during session",5)
                active=storage.claim(db,sid)
                if active is None:
                    db.execute("UPDATE experiment SET state='COMPLETED'"); break
                if stopped.is_set() or datetime.now(timezone.utc)>=stop:
                    storage.interrupt(db,active["attempt_id"],"not_launched_deadline"); active=None
                    pause_reason="stop before launch"; break
                record=index["records"][active["instance_id"]]
                request=dict(active,encoding=active["encoding"] or None,scope="expanded-v2",cutoff_seconds=10.0,
                    file=os.path.relpath(contained(index["dataset_dir"],record["input_file"]),ROOT))
                start=time.perf_counter()
                result=run_job(request,runner_config,root=ROOT)
                fatal=storage.finish(db,active["attempt_id"],result,record,index["dataset_dir"],time.perf_counter()-start)
                active=None
                if fatal: break
            if pause_reason:
                db.execute("UPDATE experiment SET state='PAUSED',halt_reason=?",(pause_reason,))
            if heartbeat_errors:
                raise ExpandedError("Heartbeat persistence failure: "+heartbeat_errors[0],5)
        except BaseException as exc:
            if sid:
                # run_job's finally has finished before this handler; preserve interrupted work.
                try:
                    if active:
                        attempt=db.execute("SELECT state FROM attempts WHERE attempt_id=?",(active["attempt_id"],)).fetchone()
                        if attempt and attempt["state"]=="RUNNING": storage.interrupt(db,active["attempt_id"],type(exc).__name__)
                    db.execute("UPDATE experiment SET state='HALTED',halt_reason=?",(str(exc)[:500],))
                    storage.event(db,"HALTED",{"error":str(exc)[:500]},session=sid)
                except Exception:
                    write(directory/"uncommitted-failure.json",{"error":str(exc)[:500],"active_attempt":active,"utc":stamp()})
            raise
        finally:
            if old_signal is not None: signal.signal(signal.SIGINT,old_signal)
            heartbeat_stop.set()
            if thread: thread.join(timeout=6)
            if sid:
                db.execute("UPDATE sessions SET ended_utc=?,heartbeat_utc=? WHERE session_id=?",(stamp(),stamp(),sid))
                storage.event(db,"SESSION_ENDED",session=sid)
            db.close()
    snapshot=expanded_status(directory)
    return {key:snapshot[key] for key in ("experiment_id","state","completed_jobs","completed_blocks","remaining_jobs","reason","exit_code")}


@public
def pilot_expanded(experiment_dir, *, stop_starting_at=None):
    return _run(experiment_dir,expected_phase="pilot",stop_starting_at=stop_starting_at)


@public
def run_expanded(experiment_dir, *, stop_starting_at=None):
    return _run(experiment_dir,expected_phase="main",stop_starting_at=stop_starting_at)


@public
def resume_expanded(experiment_dir, *, reason, stop_starting_at):
    return _run(experiment_dir,resume=True,reason=reason,stop_starting_at=stop_starting_at)


@public
def expanded_status(experiment_dir):
    directory=Path(experiment_dir).resolve()
    db=storage.connect(directory,readonly=True)
    try:
        require(db.execute("PRAGMA user_version").fetchone()[0]==2,"Database version mismatch")
        db.execute("BEGIN")
        exp=dict(db.execute("SELECT * FROM experiment").fetchone())
        manifest=json.loads(exp["manifest_json"])
        running=exp["state"]=="RUNNING"
        if not running: storage.integrity(db,full=False)
        counts={r[0]:r[1] for r in db.execute("SELECT r.status,COUNT(*) FROM primary_attempt p JOIN results r USING(attempt_id) GROUP BY r.status")}
        attempts={r[0]:r[1] for r in db.execute("SELECT state,COUNT(*) FROM attempts GROUP BY state")}
        total=db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]; complete=sum(counts.values())
        quality=storage.assess_blocks(db,check_quality=not running)
        blocks=sum(b["execution_complete"] for b in quality.values())
        qa=None if running else sum(b["qa_complete"] for b in quality.values())
        active=[dict(r) for r in db.execute("SELECT attempt_id,job_id,started_utc FROM attempts WHERE state='RUNNING'")]
        session=db.execute("SELECT * FROM sessions ORDER BY started_utc DESC LIMIT 1").fetchone()
        elapsed=0 if session is None else (datetime.fromisoformat(session["ended_utc"] or stamp())-datetime.fromisoformat(session["started_utc"])).total_seconds()
        remaining=[tuple(r) for r in db.execute("SELECT i.board_side,j.configuration,COUNT(*) FROM jobs j JOIN instances i USING(instance_id) WHERE j.state!='TERMINAL' GROUP BY i.board_side,j.configuration")]
        histories={}
        for size,configuration,_ in remaining:
            # The sole controller commits frozen ordinal order. Read only the
            # latest 50 terminal jobs per stratum via an index, then their one
            # finished attempt; never scan/parse the complete attempt history.
            values=[r[0] for r in db.execute("""SELECT a.attempt_wall_seconds FROM
                (SELECT j.job_id FROM jobs j JOIN instances i USING(instance_id)
                 WHERE j.configuration=? AND j.state='TERMINAL' AND i.board_side=?
                 ORDER BY j.ordinal DESC LIMIT 50) recent
                JOIN attempts a USING(job_id) WHERE a.state='FINISHED' AND a.attempt_wall_seconds IS NOT NULL""",(configuration,size))]
            if values and all(finite(value) for value in values): histories[size,configuration]=values
        pilot_error=None
        try: pilot,pilot_ref=_pilot_wall_estimates(manifest)
        except (ExpandedError,OSError,ValueError,KeyError,TypeError) as exc:
            pilot,pilot_ref={},None; pilot_error=str(exc)[:500]
        estimates={key:statistics.median(values) for key,values in histories.items()}
        basis=[]
        for size,c,n in remaining:
            key=(size,c)
            basis.append(dict(N=size,configuration=c,remaining_jobs=n,source="recent_attempts" if key in estimates else "accepted_pilot" if key in pilot else "missing",
                median_attempt_wall_seconds=estimates.get(key,pilot.get(key))))
        covered=sum(row["remaining_jobs"] for row in basis if row["source"]!="missing")
        eta=sum(row["remaining_jobs"]*row["median_attempt_wall_seconds"] for row in basis if row["source"]!="missing") if covered==total-complete else None
        if eta is not None and not finite(eta): eta=None
        observed_wall=sum(sum(values) for values in histories.values())
        recent_rate=sum(map(len,histories.values()))/observed_wall if observed_wall else None
        if recent_rate is not None and not finite(recent_rate): recent_rate=None
        result=dict(experiment_id=exp["experiment_id"],state=exp["state"],phase=manifest["phase"],artificial=manifest["artificial"],
            completed_jobs=complete,completed_blocks=blocks,qa_complete_blocks=qa,remaining_jobs=total-complete,planned_jobs=total,
            primary_counts=counts,attempt_counts=attempts,interrupted_attempts=attempts.get("INTERRUPTED",0),active=active,
            progress_diagnostic_only=True,qa_assessed=not running,
            session_elapsed_wall_seconds=elapsed,free_disk_bytes=shutil.disk_usage(directory).free,
            storage_bytes={**{name: (directory/name).stat().st_size if (directory/name).exists() else 0 for name in ("experiment.sqlite3","experiment.sqlite3-wal")},
                "logs":sum(p.stat().st_size for p in directory.rglob("*.log") if p.is_file())},
            eta_seconds=eta,eta_covered_remaining_jobs=covered,eta_basis="latest up to50 attempt-wall observations per N/config, then hash-bound root-accepted pilot; missing strata=>null; no promise",
            eta_strata=basis,eta_pilot_reference=pilot_ref,eta_pilot_evidence_error=pilot_error,
            recent_wall_jobs_per_second=recent_rate,
            reason=exp["halt_reason"],exit_code=4 if exp["state"]=="PAUSED" else 5 if exp["state"]=="HALTED" else 0)
        db.execute("COMMIT")
        return result
    finally: db.close()


@public
def export_expanded(experiment_dir, output_dir, *, complete_blocks=False):
    from sudoku.expanded_export import export_snapshot
    return export_snapshot(experiment_dir,output_dir,complete_blocks=complete_blocks)

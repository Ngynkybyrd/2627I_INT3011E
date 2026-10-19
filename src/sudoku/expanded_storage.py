"""Durable schema2 state machine and Windows writer ownership."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import os
import socket
import sqlite3
import time
import uuid
from sudoku.expanded_common import *
from sudoku.model import load_puzzle
from sudoku.validation import check_solution

DDL = """
CREATE TABLE experiment(experiment_id TEXT PRIMARY KEY, manifest_json TEXT NOT NULL, state TEXT NOT NULL, halt_reason TEXT);
CREATE TABLE batches(batch_id TEXT PRIMARY KEY, ordinal INTEGER UNIQUE NOT NULL, expected_instances INTEGER NOT NULL, expected_jobs INTEGER NOT NULL, qa_state TEXT NOT NULL DEFAULT 'PENDING', qa_reason TEXT);
CREATE TABLE instances(instance_id TEXT PRIMARY KEY, content_sha256 TEXT UNIQUE NOT NULL, batch_id TEXT NOT NULL REFERENCES batches, block_side INTEGER NOT NULL, board_side INTEGER NOT NULL, manifest_record_json TEXT NOT NULL);
CREATE TABLE jobs(job_id TEXT PRIMARY KEY, instance_id TEXT NOT NULL REFERENCES instances, configuration TEXT NOT NULL, method TEXT NOT NULL, encoding TEXT NOT NULL, repetition INTEGER NOT NULL, ordinal INTEGER UNIQUE NOT NULL, state TEXT NOT NULL DEFAULT 'PENDING' CHECK(state IN ('PENDING','RUNNING','TERMINAL')), UNIQUE(instance_id,method,encoding,repetition));
CREATE TABLE sessions(session_id TEXT PRIMARY KEY, host TEXT NOT NULL, pid INTEGER NOT NULL, creation_time TEXT NOT NULL, started_utc TEXT NOT NULL, ended_utc TEXT, stop_starting_at TEXT NOT NULL, heartbeat_utc TEXT NOT NULL, reason TEXT NOT NULL);
CREATE TABLE attempts(attempt_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs, attempt_no INTEGER NOT NULL, session_id TEXT NOT NULL REFERENCES sessions, state TEXT NOT NULL CHECK(state IN ('RUNNING','INTERRUPTED','FINISHED')), started_utc TEXT NOT NULL, ended_utc TEXT, attempt_wall_seconds REAL, interruption_reason TEXT, UNIQUE(job_id,attempt_no));
CREATE UNIQUE INDEX one_running_per_job ON attempts(job_id) WHERE state='RUNNING';
CREATE TABLE results(attempt_id TEXT PRIMARY KEY REFERENCES attempts, status TEXT NOT NULL, result_json TEXT NOT NULL CHECK(json_valid(result_json)), solution_attempt_id TEXT REFERENCES solutions(attempt_id) DEFERRABLE INITIALLY DEFERRED, CHECK((status='SAT' AND solution_attempt_id IS NOT NULL AND solution_attempt_id=attempt_id) OR (status!='SAT' AND solution_attempt_id IS NULL)));
CREATE TABLE solutions(attempt_id TEXT PRIMARY KEY REFERENCES results(attempt_id) DEFERRABLE INITIALLY DEFERRED, payload BLOB NOT NULL, sha256 TEXT NOT NULL, checker_json TEXT NOT NULL);
CREATE TABLE primary_attempt(job_id TEXT PRIMARY KEY REFERENCES jobs, attempt_id TEXT UNIQUE NOT NULL REFERENCES results);
CREATE TABLE events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, utc TEXT NOT NULL, session_id TEXT REFERENCES sessions, job_id TEXT REFERENCES jobs, attempt_id TEXT REFERENCES attempts, type TEXT NOT NULL, details_json TEXT NOT NULL);
CREATE INDEX job_pending_ordinal ON jobs(state,ordinal);
CREATE INDEX attempt_job ON attempts(job_id,attempt_no);
CREATE INDEX instance_batch ON instances(batch_id);
CREATE INDEX event_attempt_type ON events(attempt_id,type,event_id);
CREATE INDEX job_configuration_state_ordinal ON jobs(configuration,state,ordinal DESC);
CREATE INDEX result_status ON results(status);
CREATE INDEX attempt_state ON attempts(state);
CREATE TRIGGER primary_identity BEFORE INSERT ON primary_attempt BEGIN SELECT CASE WHEN (SELECT job_id FROM attempts WHERE attempt_id=NEW.attempt_id)!=NEW.job_id THEN RAISE(ABORT,'primary identity mismatch') END; END;
CREATE TRIGGER solution_sat BEFORE INSERT ON solutions BEGIN SELECT CASE WHEN (SELECT status FROM results WHERE attempt_id=NEW.attempt_id)!='SAT' THEN RAISE(ABORT,'nonSAT solution') END; END;
"""


def connect(directory, *, readonly=False, create=False):
    path = Path(directory) / "experiment.sqlite3"
    require(create or path.is_file(),"Experiment database does not exist")
    db = sqlite3.connect(path.as_uri()+"?mode=ro" if readonly else str(path), uri=readonly, timeout=5, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    if not readonly:
        require(db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal", "WAL unavailable",5)
        db.execute("PRAGMA synchronous=FULL")
        require(db.execute("PRAGMA synchronous").fetchone()[0] == 2, "FULL durability unavailable",5)
    return db


@contextmanager
def transaction(db):
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def event(db, kind, details=None, *, session=None, job=None, attempt=None):
    db.execute("INSERT INTO events(utc,session_id,job_id,attempt_id,type,details_json) VALUES(?,?,?,?,?,?)",
               (stamp(),session,job,attempt,kind,dumps(details or {})))


def initialize(directory, manifest, index, jobs):
    require(not (Path(directory)/"experiment.sqlite3").exists(),"Database already exists")
    db = connect(directory,create=True)
    try:
        db.executescript(DDL)
        for table in ("results","solutions","primary_attempt"):
            for operation in ("UPDATE","DELETE"):
                db.execute(f"CREATE TRIGGER immutable_{table}_{operation} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'immutable raw record'); END")
        db.execute("PRAGMA user_version=2")
        with transaction(db):
            db.execute("INSERT INTO experiment VALUES(?,?,?,NULL)",(manifest["experiment_id"],dumps(manifest),"PREPARED"))
            counts = Counter(index["records"][j["instance_id"]]["batch_id"] for j in jobs)
            db.executemany("INSERT INTO batches(batch_id,ordinal,expected_instances,expected_jobs) VALUES(?,?,?,?)",
                [(b["batch_id"],b["ordinal"],len(b["instance_ids"]),counts[b["batch_id"]]) for b in index["batches"]])
            db.executemany("INSERT INTO instances VALUES(?,?,?,?,?,?)",[(r["instance_id"],r["content_sha256"],r["batch_id"],r["n"],r["N"],dumps(r)) for r in index["records"].values()])
            db.executemany("INSERT INTO jobs(job_id,instance_id,configuration,method,encoding,repetition,ordinal) VALUES(?,?,?,?,?,?,?)",[(j["job_id"],j["instance_id"],j["configuration"],j["method"],j["encoding"],j["repetition"],j["ordinal"]) for j in jobs])
            event(db,"PREPARED",{"jobs":len(jobs)})
        integrity(db)
    finally:
        db.close()


from collections import Counter


def integrity(db, *, full=True):
    require(db.execute("PRAGMA user_version").fetchone()[0] == 2,"Database version mismatch",5)
    if full:
        require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and not db.execute("PRAGMA foreign_key_check").fetchall(),"SQLite integrity failure",5)
    bad = db.execute("""SELECT a.attempt_id FROM attempts a LEFT JOIN results r USING(attempt_id)
        WHERE (a.state='FINISHED' AND r.attempt_id IS NULL) OR (a.state!='FINISHED' AND r.attempt_id IS NOT NULL) LIMIT 1""").fetchone()
    require(bad is None,"Attempt/result inconsistency",5)
    bad = db.execute("""SELECT j.job_id FROM jobs j LEFT JOIN primary_attempt p USING(job_id)
       WHERE (j.state='TERMINAL' AND p.attempt_id IS NULL) OR (j.state!='TERMINAL' AND p.attempt_id IS NOT NULL) LIMIT 1""").fetchone()
    require(bad is None,"Primary/job inconsistency",5)
    bad = db.execute("""SELECT a.attempt_id FROM attempts a LEFT JOIN primary_attempt p USING(attempt_id)
       LEFT JOIN jobs j ON a.job_id=j.job_id
       WHERE (a.state='FINISHED' AND (p.attempt_id IS NULL OR p.job_id!=a.job_id))
          OR (a.state='RUNNING' AND j.state!='RUNNING') LIMIT 1""").fetchone()
    require(bad is None,"Attempt/primary identity inconsistency",5)
    bad = db.execute("""SELECT j.job_id FROM jobs j LEFT JOIN attempts a ON a.job_id=j.job_id AND a.state='RUNNING'
       WHERE j.state='RUNNING' AND a.attempt_id IS NULL LIMIT 1""").fetchone()
    require(bad is None,"Running job has no running attempt",5)
    bad = db.execute("""SELECT r.attempt_id FROM results r LEFT JOIN solutions s ON s.attempt_id=r.attempt_id
       WHERE (r.status='SAT' AND (s.attempt_id IS NULL OR r.solution_attempt_id IS NOT r.attempt_id))
          OR (r.status!='SAT' AND (s.attempt_id IS NOT NULL OR r.solution_attempt_id IS NOT NULL)) LIMIT 1""").fetchone()
    require(bad is None,"Result/solution inconsistency",5)
    bad=db.execute("""SELECT attempt_id FROM attempts WHERE state='FINISHED' AND
        (attempt_wall_seconds IS NULL OR typeof(attempt_wall_seconds) NOT IN ('integer','real') OR
         attempt_wall_seconds<0 OR attempt_wall_seconds>1.7976931348623157e308) LIMIT 1""").fetchone()
    require(bad is None,"Invalid finished attempt wall duration",5)
    bad=db.execute("""SELECT r.attempt_id FROM results r JOIN attempts a USING(attempt_id) JOIN jobs j USING(job_id)
        WHERE r.status IS NOT json_extract(r.result_json,'$.status')
           OR j.method IS NOT json_extract(r.result_json,'$.method')
           OR j.encoding!=COALESCE(json_extract(r.result_json,'$.encoding'),'') LIMIT 1""").fetchone()
    require(bad is None,"Stored result identity/status mismatch",5)


def process_identity(pid):
    require(os.name == "nt", "Writer process identity requires Windows")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:
        error=ctypes.get_last_error()
        require(error==87,f"Cannot establish process identity: WinError {error}",5)
        return None
    try:
        times=[wintypes.FILETIME() for _ in range(4)]
        require(kernel.GetProcessTimes(handle,*[ctypes.byref(t) for t in times]),"Process time query failed",5)
        return str((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)
    finally:
        kernel.CloseHandle(handle)


class WriterLock:
    def __init__(self, directory):
        self.directory=Path(directory)
        self.stream=None
    def __enter__(self):
        require(os.name=="nt","Writer lock requires Windows")
        import msvcrt
        path=self.directory/"writer.lock"
        try:
            with path.open("xb") as stream:
                stream.write(b"0")
        except FileExistsError:
            pass
        self.stream=path.open("r+b",buffering=0)
        try:
            msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
        except OSError as exc:
            self.stream.close(); self.stream=None
            raise ExpandedError("Experiment writer is busy; lock not stolen",3) from exc
        return self
    def __exit__(self,*args):
        import msvcrt
        self.stream.seek(0)
        msvcrt.locking(self.stream.fileno(),msvcrt.LK_UNLCK,1)
        self.stream.close()


def new_session(db, stop, reason):
    sid=str(uuid.uuid4()); now=stamp()
    db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,NULL,?,?,?)",(sid,socket.gethostname(),os.getpid(),process_identity(os.getpid()),now,stop,now,reason))
    return sid


def claim(db, session):
    with transaction(db):
        job=db.execute("SELECT * FROM jobs WHERE state='PENDING' ORDER BY ordinal LIMIT 1").fetchone()
        if job is None:
            return None
        aid=str(uuid.uuid4())
        number=db.execute("SELECT COALESCE(MAX(attempt_no),0)+1 FROM attempts WHERE job_id=?",(job["job_id"],)).fetchone()[0]
        db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,NULL,NULL,NULL)",(aid,job["job_id"],number,session,"RUNNING",stamp()))
        db.execute("UPDATE jobs SET state='RUNNING' WHERE job_id=? AND state='PENDING'",(job["job_id"],))
        event(db,"CLAIM",session=session,job=job["job_id"],attempt=aid)
    return dict(job,attempt_id=aid,attempt_no=number)


def interrupt(db, attempt_id, reason):
    with transaction(db):
        row=db.execute("SELECT * FROM attempts WHERE attempt_id=?",(attempt_id,)).fetchone()
        require(row is not None and row["state"]=="RUNNING","Only running attempt can be interrupted",5)
        db.execute("UPDATE attempts SET state='INTERRUPTED',ended_utc=?,interruption_reason=? WHERE attempt_id=?",(stamp(),reason,attempt_id))
        db.execute("UPDATE jobs SET state='PENDING' WHERE job_id=?",(row["job_id"],))
        event(db,"INTERRUPTED",{"reason":reason},session=row["session_id"],job=row["job_id"],attempt=attempt_id)


def check_result(result, record, dataset_dir, *, _puzzle=None):
    result=dict(result)
    status=result.get("status")
    require(status in ("SAT","UNSAT","TIMEOUT","ERROR","INVALID_INPUT","UNAVAILABLE","LICENSE_LIMIT"),"Unknown result status",5)
    for key in ("build_seconds","solve_seconds","total_seconds"):
        require(result.get(key) is None or finite(result[key]),"Invalid measured timing",5)
    b,s,t=(result.get(k) for k in ("build_seconds","solve_seconds","total_seconds"))
    if all(v is not None for v in (b,s,t)):
        require(abs(b+s-t)<=1e-7*max(1,t),"Timing sum mismatch",5)
    if status=="SAT":
        require(all(v is not None for v in (b,s,t)) and t<=10 and result.get("guard_phase")=="complete","SAT outside cutoff/complete phase",5)
        puzzle=_puzzle if _puzzle is not None else load_puzzle(contained(dataset_dir,record["input_file"]))
        checked=check_solution(puzzle,result.get("solution"))
        if not checked.valid or not (result.get("validation") or {}).get("valid"):
            result["rejected_solution"]=result.get("solution")
            result.update(status="ERROR",solution=None,validation={"valid":False,"message":checked.message},error="Independent result validation failed")
        if result["status"]=="SAT" and result.get("method")=="sat":
            stats=result.get("stats") or {}; n=record["N"]
            require(all(type(stats.get(k)) is int and stats[k]>=0 for k in ("primary_variables","auxiliary_variables","total_variables","clauses")),"Missing/invalid SAT CNF counts",5)
            require(stats["primary_variables"]==n**3 and stats["total_variables"]==stats["primary_variables"]+stats["auxiliary_variables"] and stats["clauses"]>0,"CNF size mismatch",5)
            if result.get("encoding")=="pairwise":
                require(stats["auxiliary_variables"]==0 and stats["clauses"]==4*n*n*(1+n*(n-1)//2)+record["actual_clues"],"Pairwise clause mismatch",5)
        elif result["status"]=="SAT":
            require(result.get("stats") is None,"Baseline must not carry SAT counts",5)
    if status=="TIMEOUT":
        require(result.get("guard_phase") in ("measurement","complete"),"Timeout outside measurement",5)
    dumps(result)  # Reject other NaN/Inf/non-JSON payloads after precise checks.
    return result


def finish(db, attempt_id, result, record, dataset_dir, wall_seconds, *, _before_commit=None):
    original_observation=diagnostic_value(result)
    try:
        result=check_result(result,record,dataset_dir)
    except (ExpandedError,TypeError,ValueError,AttributeError) as exc:
        # Keep the rejected raw observation while preventing it from becoming SAT.
        result=dict(status="ERROR",method=result.get("method"),encoding=result.get("encoding"),
            raw_status=diagnostic_value(result.get("raw_status")),raw_observation=diagnostic_value(result),validation={"valid":False,"message":str(exc)},
            guard_phase="validation",error=str(exc),solution=None)
    require(finite(wall_seconds),"Invalid wall duration",5)
    status=result["status"]; solution=result.pop("solution",None)
    payload=canonical(record["n"],solution) if status=="SAT" else None
    fatal=status not in ("SAT","TIMEOUT") or result.get("guard_phase")=="cleanup"
    start=time.perf_counter()
    # Reject identity before publishing any result, but retain the adapter's exact
    # claimed identity and finite-safe raw evidence in a durable audit event.
    a=db.execute("SELECT * FROM attempts WHERE attempt_id=?",(attempt_id,)).fetchone()
    require(a is not None and a["state"]=="RUNNING","Attempt already terminal/missing",5)
    job=db.execute("SELECT method,encoding,instance_id FROM jobs WHERE job_id=?",(a["job_id"],)).fetchone()
    mismatch=None
    if result.get("method")!=job["method"] or (result.get("encoding") or "")!=job["encoding"]:
        mismatch="Adapter result configuration mismatch"
    elif record["instance_id"]!=job["instance_id"]:
        mismatch="Result instance identity mismatch"
    if mismatch:
        with transaction(db):
            event(db,"REJECTED_OBSERVATION",dict(reason=mismatch,raw_observation=original_observation,
                expected_identity=dict(job)),session=a["session_id"],job=a["job_id"],attempt=attempt_id)
            db.execute("UPDATE experiment SET state='HALTED',halt_reason=?",(mismatch,))
        raise ExpandedError(mismatch,5)
    with transaction(db):
        a=db.execute("SELECT * FROM attempts WHERE attempt_id=?",(attempt_id,)).fetchone()
        require(a is not None and a["state"]=="RUNNING","Attempt already terminal/missing",5)
        job=db.execute("SELECT method,encoding,instance_id FROM jobs WHERE job_id=?",(a["job_id"],)).fetchone()
        require(result.get("method")==job["method"] and (result.get("encoding") or "")==job["encoding"],"Adapter result configuration mismatch",5)
        require(record["instance_id"]==job["instance_id"],"Result instance identity mismatch",5)
        db.execute("INSERT INTO results VALUES(?,?,?,?)",(attempt_id,status,dumps(result),attempt_id if payload else None))
        if payload:
            db.execute("INSERT INTO solutions VALUES(?,?,?,?)",(attempt_id,payload,digest(payload),dumps(result["validation"])))
        db.execute("UPDATE attempts SET state='FINISHED',ended_utc=?,attempt_wall_seconds=? WHERE attempt_id=?",(stamp(),wall_seconds,attempt_id))
        db.execute("UPDATE jobs SET state='TERMINAL' WHERE job_id=?",(a["job_id"],))
        db.execute("INSERT INTO primary_attempt VALUES(?,?)",(a["job_id"],attempt_id))
        event(db,"FINISHED",{"status":status},session=a["session_id"],job=a["job_id"],attempt=attempt_id)
        if fatal:
            db.execute("UPDATE experiment SET state='HALTED',halt_reason=?",(f"{status}: {a['job_id']}",))
        if _before_commit:
            _before_commit()
    elapsed=time.perf_counter()-start
    event(db,"CHECKPOINT",{"checkpoint_seconds":elapsed},attempt=attempt_id)
    return fatal


def assess_blocks(db, *, check_quality=True):
    """Derived from committed immutable records; export additionally rechecks grids."""
    # One grouped pass, instead of scanning the complete job table per block.
    if not check_quality:
        totals={r[0]:r[1] for r in db.execute("""SELECT i.batch_id,COUNT(*) FROM primary_attempt p
            JOIN jobs j USING(job_id) JOIN instances i USING(instance_id) GROUP BY i.batch_id""")}
        return {b["batch_id"]:dict(execution_complete=totals.get(b["batch_id"],0)==b["expected_jobs"],qa_complete=None,reason="not assessed by running progress")
            for b in db.execute("SELECT * FROM batches ORDER BY ordinal")}
    totals={r["batch_id"]:r for r in db.execute("""SELECT i.batch_id,COUNT(*) AS completed,
        SUM(CASE WHEN r.status NOT IN ('SAT','TIMEOUT') THEN 1 ELSE 0 END) AS fatal,
        SUM(CASE WHEN r.status='SAT' AND json_extract(r.result_json,'$.validation.valid') IS NOT 1 THEN 1 ELSE 0 END) AS invalid
        FROM primary_attempt p JOIN jobs j USING(job_id) JOIN instances i USING(instance_id)
        JOIN results r USING(attempt_id) GROUP BY i.batch_id""")}
    running={r[0]:r[1] for r in db.execute("""SELECT i.batch_id,COUNT(*) FROM attempts a
        JOIN jobs j USING(job_id) JOIN instances i USING(instance_id) WHERE a.state='RUNNING' GROUP BY i.batch_id""")}
    halted=db.execute("SELECT state FROM experiment").fetchone()[0]=="HALTED"
    result={}
    for b in db.execute("SELECT * FROM batches ORDER BY ordinal"):
        counts=totals.get(b["batch_id"])
        complete=counts is not None and counts["completed"]==b["expected_jobs"]
        reason=None if complete else "incomplete jobs"
        if complete and counts["fatal"]: reason="fatal/noneligible terminal status"
        if complete and counts["invalid"]: reason="unvalidated SAT"
        if running.get(b["batch_id"]): reason="unresolved running attempt"
        if halted: reason="experiment HALTED; QA release required"
        result[b["batch_id"]]=dict(execution_complete=complete,qa_complete=reason is None,reason=reason)
    return result


def checked_primary_results(db, index):
    """Deep audit once at resume/export, with each input parsed at most once."""
    puzzles={}
    query="""SELECT j.*,i.batch_id,a.attempt_id,a.attempt_no,a.attempt_wall_seconds,
      r.status,r.result_json,s.payload,s.sha256 AS solution_hash FROM primary_attempt p
      JOIN jobs j USING(job_id) JOIN instances i USING(instance_id)
      JOIN attempts a ON p.attempt_id=a.attempt_id JOIN results r ON r.attempt_id=a.attempt_id
      LEFT JOIN solutions s ON s.attempt_id=a.attempt_id ORDER BY j.ordinal"""
    for row in db.execute(query):
        r=dict(row); record=index["records"][r["instance_id"]]
        result=json.loads(r["result_json"])
        require(result.get("method")==r["method"] and (result.get("encoding") or "")==r["encoding"],"Stored result configuration identity mismatch",5)
        if r["status"]=="SAT":
            require(r["payload"] is not None and digest(r["payload"])==r["solution_hash"],"Solution blob hash mismatch",5)
            solution=json.loads(r["payload"])
            require(solution["n"]==record["n"] and canonical(record["n"],solution["grid"])==r["payload"],"Solution canonical/dimension identity mismatch",5)
            result["solution"]=solution["grid"]
            if r["instance_id"] not in puzzles:
                puzzles[r["instance_id"]]=load_puzzle(contained(index["dataset_dir"],record["input_file"]))
            checked=check_result(result,record,index["dataset_dir"],_puzzle=puzzles[r["instance_id"]])
            require(checked["status"]=="SAT","Stored solution failed independent recheck",5)
        else:
            require(r["payload"] is None,"NonSAT has witness",5)
            check_result(result,record,index["dataset_dir"])
        require(result["status"]==r["status"],"Result status mismatch",5)
        r["result"]=result
        yield r

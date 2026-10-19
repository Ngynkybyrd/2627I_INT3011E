"""Checkpointed witness acquisition, separate from the 10-second benchmark.

No execution without execute=True. Production uses run_job's Windows hard guard,
SAT pairwise and a 30-second witness-only budget. Never reselect input puzzles.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import sys
import time

from sudoku import expanded_data as data
from sudoku.model import load_puzzle
from sudoku.validation import check_solution

ROOT = Path(__file__).resolve().parents[2]
WITNESS_CUTOFF_SECONDS = 30.0
APPLICATION_ID = 1163342423
CODE_FILES = ("expanded_witnesses.py", "expanded_data.py", "runner.py", "runner_process.py",
              "runner_worker.py", "sat.py", "model.py", "validation.py", "decoding.py", "contracts.py")


class WitnessError(ValueError):
    def __init__(self, message, exit_code=5):
        super().__init__(message)
        self.exit_code = exit_code


def _public(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except WitnessError:
            raise
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            raise WitnessError(f"{type(exc).__name__}: {exc}") from exc
    return wrapper


def _require(condition, message, code=5):
    if not condition:
        raise WitnessError(message, code)


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path, value):
    """One writer owns the namespace; preserve any prior final artifact."""
    path = Path(path)
    raw = data.json_bytes(value)
    if path.exists():
        _require(path.read_bytes() == raw, f"Refusing to overwrite raw evidence: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _diagnostic(value):
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite_float": repr(value)}
    if value is None or type(value) in (str, int, float, bool):
        return value
    if isinstance(value, dict):
        return {str(k): _diagnostic(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_diagnostic(v) for v in value]
    return {"unsupported_type": type(value).__name__}


class WitnessWriterLock:
    """OS-held lock; a stale filename never authorizes stealing a live writer."""
    def __init__(self, directory):
        self.path = Path(directory) / "witness-writer.lock"
        self.stream = None

    def __enter__(self):
        try:
            with self.path.open("xb") as stream:
                stream.write(b"0")
        except FileExistsError:
            pass
        self.stream = self.path.open("r+b", buffering=0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.stream.close()
            self.stream = None
            raise WitnessError("Witness writer is busy; lock not stolen", 3) from exc
        return self

    def __exit__(self, *args):
        try:
            if os.name == "nt":
                import msvcrt
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_UN)
        finally:
            self.stream.close()


@contextmanager
def _transaction(db):
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def _connect(path, readonly=False):
    db = sqlite3.connect(path.as_uri() + "?mode=ro" if readonly else str(path),
                         uri=readonly, isolation_level=None, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    if not readonly:
        _require(db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal", "WAL unavailable")
        db.execute("PRAGMA synchronous=FULL")
        _require(db.execute("PRAGMA synchronous").fetchone()[0] == 2, "FULL durability unavailable")
    return db


def _fingerprint(directory, fake):
    native = {}
    try:
        distribution = importlib.metadata.distribution("python-sat")
        version = distribution.version
        for item in distribution.files or []:
            if Path(str(item)).suffix.lower() in (".pyd", ".dll", ".so"):
                path = Path(distribution.locate_file(item))
                native[str(item)] = data.sha256(path.read_bytes())
    except importlib.metadata.PackageNotFoundError:
        version = None
    script = ROOT / "scripts/complete_expanded_witnesses.py"
    return {"purpose": "public-witness-acquisition-not-benchmark", "schema_version": 2,
            "dataset_dir": str(directory), "dataset_id": data.read_json(directory / "dataset.json")["dataset_id"],
            "inputs_receipt_sha256": data.sha256((directory / "inputs-receipt.json").read_bytes()),
            "method": "sat", "encoding": "pairwise", "cutoff_seconds": WITNESS_CUTOFF_SECONDS,
            "startup_seconds": 60.0, "postprocessing_seconds": 30.0,
            "worker_mode": "artificial_fake" if fake else "production_run_job",
            "code_sha256": {name: data.sha256(Path(__file__).with_name(name).read_bytes()) for name in CODE_FILES},
            "cli_sha256": data.sha256(script.read_bytes()),
            "environment": {"python": sys.version, "executable": str(Path(sys.executable).resolve()),
                            "platform": platform.platform(), "python_sat": version, "native_sha256": native}}


def _initialize(db, fingerprint, records):
    db.executescript("""
    CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE inputs(instance_id TEXT PRIMARY KEY,ordinal INTEGER UNIQUE NOT NULL,input_sha256 TEXT NOT NULL);
    CREATE TABLE attempts(attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,instance_id TEXT NOT NULL REFERENCES inputs,
      attempt_no INTEGER NOT NULL,state TEXT NOT NULL CHECK(state IN ('RUNNING','INTERRUPTED','FINISHED')),
      launched INTEGER NOT NULL DEFAULT 0,started_utc TEXT NOT NULL,ended_utc TEXT,reason TEXT,
      raw_log TEXT,raw_log_sha256 TEXT,raw_json TEXT,observed_status TEXT,admitted_status TEXT,
      witness BLOB,witness_sha256 TEXT,validation_json TEXT,wall_seconds REAL,
      UNIQUE(instance_id,attempt_no));
    CREATE UNIQUE INDEX terminal_once ON attempts(instance_id) WHERE state='FINISHED';
    CREATE UNIQUE INDEX one_running ON attempts(instance_id) WHERE state='RUNNING';
    CREATE TABLE events(event_id INTEGER PRIMARY KEY AUTOINCREMENT,utc TEXT NOT NULL,kind TEXT NOT NULL,details TEXT NOT NULL);
    CREATE TRIGGER immutable_finished_update BEFORE UPDATE ON attempts WHEN OLD.state='FINISHED'
      BEGIN SELECT RAISE(ABORT,'finished witness attempt is immutable'); END;
    CREATE TRIGGER immutable_attempt_delete BEFORE DELETE ON attempts BEGIN SELECT RAISE(ABORT,'attempt history is immutable'); END;
    """)
    db.execute("PRAGMA user_version=1")
    db.execute(f"PRAGMA application_id={APPLICATION_ID}")
    with _transaction(db):
        db.execute("INSERT INTO metadata VALUES('fingerprint',?)", (data.json_bytes(fingerprint).decode(),))
        db.executemany("INSERT INTO inputs VALUES(?,?,?)", [(r["instance_id"], i, r["input_sha256"])
                                                            for i, r in enumerate(records, 1)])


def _event(db, kind, details):
    db.execute("INSERT INTO events(utc,kind,details) VALUES(?,?,?)", (_utc(), kind, data.json_bytes(details).decode()))


def _admit(raw, record, directory):
    """Never alter raw statuses; admission failure is stored separately as ERROR."""
    status = raw.get("status") if isinstance(raw, dict) else None
    try:
        _require(status in ("SAT", "UNSAT", "TIMEOUT", "ERROR", "INVALID_INPUT", "UNAVAILABLE", "LICENSE_LIMIT"), "Unknown witness result status")
        _require(raw.get("method") == "sat" and raw.get("encoding") == "pairwise", "Witness result method/encoding mismatch")
        for key in ("build_seconds", "solve_seconds", "total_seconds"):
            value = raw.get(key)
            _require(value is None or type(value) in (int, float) and math.isfinite(value) and value >= 0,
                     "Invalid witness timing")
        b, s, total = (raw.get(k) for k in ("build_seconds", "solve_seconds", "total_seconds"))
        if all(v is not None for v in (b, s, total)):
            _require(abs(b + s - total) <= 1e-7 * max(1, total), "Witness timing sum differs")
        if status != "SAT":
            return status, None, {"valid": False, "message": "No admitted SAT witness"}
        _require(all(v is not None for v in (b, s, total)) and total <= WITNESS_CUTOFF_SECONDS
                 and raw.get("guard_phase") == "complete", "SAT outside witness budget or incomplete cleanup")
        path = data.contained_path(directory, record["input_file"])
        _require(data.sha256(path.read_bytes()) == record["input_sha256"], "Witness input changed during execution")
        puzzle = load_puzzle(path)
        checked = check_solution(puzzle, raw.get("solution"))
        _require(checked.valid and isinstance(raw.get("validation"), dict) and raw["validation"].get("valid") is True,
                 "Independent witness checker rejected solution")
        witness = data.canonical_puzzle_bytes(puzzle.n, raw["solution"])
        return "SAT", witness, {"valid": True, "checker_code_sha256": data.sha256(data.CHECKER.read_bytes())}
    except (WitnessError, ValueError, TypeError, KeyError, OSError) as exc:
        return "ERROR", None, {"valid": False, "message": str(exc)}


def _raw_path(evidence_dir, attempt_id):
    return evidence_dir / "attempts" / f"a{attempt_id:08d}" / "result.json"


def _envelope(attempt, record, fingerprint_hash, raw, wall):
    safe_raw = _diagnostic(raw)
    if not isinstance(safe_raw, dict):
        safe_raw = {"invalid_worker_payload": safe_raw, "status": None}
    return {"schema_version": 2, "attempt_id": attempt["attempt_id"], "attempt_no": attempt["attempt_no"],
            "instance_id": record["instance_id"], "input_sha256": record["input_sha256"],
            "fingerprint_sha256": fingerprint_hash, "raw_result": safe_raw,
            "raw_result_sha256": data.sha256(data.json_bytes(safe_raw)), "attempt_wall_seconds": wall}


def _check_envelope(value, attempt, record, fingerprint_hash):
    expected = {"schema_version": 2, "attempt_id": attempt["attempt_id"], "attempt_no": attempt["attempt_no"],
                "instance_id": record["instance_id"], "input_sha256": record["input_sha256"],
                "fingerprint_sha256": fingerprint_hash}
    _require(all(value.get(k) == v for k, v in expected.items()), "Raw witness log identity/fingerprint mismatch")
    _require(value["raw_result_sha256"] == data.sha256(data.json_bytes(value["raw_result"])), "Raw result checksum mismatch")
    wall = value["attempt_wall_seconds"]
    _require(type(wall) in (float, int) and math.isfinite(wall) and wall >= 0, "Invalid witness wall time")


def _finish(db, attempt, record, directory, evidence_dir, fingerprint_hash, envelope, hook=None):
    _check_envelope(envelope, attempt, record, fingerprint_hash)
    admitted, witness, validation = _admit(envelope["raw_result"], record, directory)
    path = _raw_path(evidence_dir, attempt["attempt_id"])
    observed = envelope["raw_result"].get("status")
    if observed is not None and not isinstance(observed, str):
        observed = data.json_bytes(observed).decode().strip()
    with _transaction(db):
        cursor = db.execute("""UPDATE attempts SET state='FINISHED',ended_utc=?,raw_log=?,raw_log_sha256=?,raw_json=?,
          observed_status=?,admitted_status=?,witness=?,witness_sha256=?,validation_json=?,wall_seconds=?
          WHERE attempt_id=? AND state IN ('RUNNING','INTERRUPTED')""",
          (_utc(), path.relative_to(evidence_dir).as_posix(), data.sha256(path.read_bytes()),
           data.json_bytes(envelope["raw_result"]).decode(), observed, admitted,
           witness, data.sha256(witness) if witness is not None else None, data.json_bytes(validation).decode(),
           envelope["attempt_wall_seconds"], attempt["attempt_id"]))
        _require(cursor.rowcount == 1, "Witness attempt changed while checkpointing")
        _event(db, "CHECKPOINT", {"attempt_id": attempt["attempt_id"], "admitted_status": admitted})
        if hook:
            hook("before_result_commit", attempt)
    return admitted


def _audit(db, records, directory, evidence_dir, fingerprint):
    _require(db.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
             and db.execute("PRAGMA user_version").fetchone()[0] == 1, "Wrong witness database namespace/version")
    _require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
             and not db.execute("PRAGMA foreign_key_check").fetchall(), "Witness database integrity failure")
    stored = db.execute("SELECT value FROM metadata WHERE key='fingerprint'").fetchone()
    _require(stored is not None and json.loads(stored[0]) == fingerprint, "Witness code/data/config/environment fingerprint changed")
    planned = [(r["instance_id"], i, r["input_sha256"]) for i, r in enumerate(records, 1)]
    _require([tuple(r) for r in db.execute("SELECT instance_id,ordinal,input_sha256 FROM inputs ORDER BY ordinal")] == planned,
             "Witness input namespace/order/hash differs")
    index = {r["instance_id"]: r for r in records}
    fingerprint_hash = data.sha256(data.json_bytes(fingerprint))
    for attempt in db.execute("SELECT * FROM attempts ORDER BY attempt_id"):
        _require(attempt["instance_id"] in index, "Unknown witness attempt identity")
        _require(type(attempt["attempt_no"]) is int and attempt["attempt_no"] >= 1
                 and attempt["launched"] in (0, 1), "Corrupt witness attempt numbering/launch flag")
        if attempt["state"] != "FINISHED":
            continue
        record = index[attempt["instance_id"]]
        path = data.contained_path(evidence_dir, attempt["raw_log"])
        _require(path == _raw_path(evidence_dir, attempt["attempt_id"]), "Raw log path namespace differs")
        _require(data.sha256(path.read_bytes()) == attempt["raw_log_sha256"], "Committed raw log is missing/corrupt")
        envelope = data.read_json(path)
        _check_envelope(envelope, attempt, record, fingerprint_hash)
        _require(data.json_bytes(envelope["raw_result"]).decode() == attempt["raw_json"], "DB/raw result mismatch")
        status, witness, validation = _admit(envelope["raw_result"], record, directory)
        observed = envelope["raw_result"].get("status")
        if observed is not None and not isinstance(observed, str):
            observed = data.json_bytes(observed).decode().strip()
        _require(status == attempt["admitted_status"] and observed == attempt["observed_status"], "Stored witness status differs")
        _require(witness == attempt["witness"] and (data.sha256(witness) if witness is not None else None) == attempt["witness_sha256"],
                 "Committed witness payload/hash mismatch")
        _require(json.loads(attempt["validation_json"]) == validation, "Stored checker evidence differs")


def _summary(db, total):
    counts = {r[0]: r[1] for r in db.execute("SELECT admitted_status,COUNT(*) FROM attempts WHERE state='FINISHED' GROUP BY admitted_status")}
    return {"public_inputs": total, "admitted_status_counts": counts, "verified_sat": counts.get("SAT", 0),
            "remaining_inputs": total - sum(counts.values()),
            "attempts": db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0],
            "interrupted_attempts": db.execute("SELECT COUNT(*) FROM attempts WHERE state='INTERRUPTED'").fetchone()[0]}


def _matching_output(directory, output):
    summary = data.verify_dataset(output)
    before = data._read_jsonl(directory / "manifest.jsonl")
    after = data._read_jsonl(output / "manifest.jsonl")
    _require([(r["instance_id"], r["input_sha256"]) for r in before] == [(r["instance_id"], r["input_sha256"]) for r in after],
             "Existing output does not match staged ID/hash order")
    _require((directory / "batches.json").read_bytes() == (output / "batches.json").read_bytes()
             and (output / "staging-origin.json").read_bytes() == (directory / "inputs-receipt.json").read_bytes(),
             "Existing output has a different stage origin/batch plan")
    return summary


def _release(root, path):
    release_hash = data.sha256(Path(path).read_bytes())
    release = data.read_json(path)
    _require(release.get("approved_explicit_terminal_execution") is True,
             "Root has not approved explicit terminal execution")
    hashes = release.get("source_sha256")
    _require(isinstance(hashes, dict) and bool(hashes), "Code release source hashes missing")
    required = {"src/sudoku/" + name for name in CODE_FILES} | {"scripts/complete_expanded_witnesses.py"}
    _require(required <= set(hashes), "Code release does not cover witness collector/guard dependencies")
    for name, expected in hashes.items():
        path = data.contained_path(root, name)
        _require(data.sha256(path.read_bytes()) == expected, f"Code release source changed: {name}")
    return release_hash


@_public
def complete_witnesses(dataset_dir, evidence_dir, output_dir, *, execute=False, root=ROOT,
                       resume_interrupted=False, reason=None, code_release=None, on_progress=None,
                       _run_job=None, _hook=None):
    """Dry-run by default; only explicit execute starts production hard-guarded jobs."""
    directory, evidence_dir, output = (Path(p).resolve() for p in (dataset_dir, evidence_dir, output_dir))
    root = Path(root).resolve()
    _require(directory.is_relative_to(root), "DRAFT must be inside the project for run_job paths", 2)
    for left, right in ((directory, evidence_dir), (directory, output), (evidence_dir, output)):
        _require(not left.is_relative_to(right) and not right.is_relative_to(left), "DRAFT/evidence/output must be separate namespaces", 2)
    info = data.verify_inputs(directory)
    fake = _run_job is not None
    _require(not fake or info["artificial"], "Fake worker injection is artificial-only", 2)
    _require(not _hook or info["artificial"], "Fault injection is artificial-only", 2)
    _require(not execute or not info["artificial"] or fake, "Production witness execution rejects artificial datasets", 2)
    _require(not resume_interrupted or bool(reason and reason.strip()), "Interrupted retry needs --reason", 2)
    release_path = Path(code_release).resolve() if code_release else root / "diagnostics/expansion/root-wave3/code-release.json"
    if execute and not fake:
        _require(release_path == root / "diagnostics/expansion/root-wave3/code-release.json",
                 "Execution requires the canonical root-owned code release receipt")
    release_hash = _release(root, release_path) if execute and not fake else None
    fingerprint = _fingerprint(directory, fake)
    fingerprint_hash = data.sha256(data.json_bytes(fingerprint))
    records = [r for r in data._read_jsonl(directory / "manifest.jsonl") if r["source"] == "sudoku_exchange"]
    database = evidence_dir / "witnesses.sqlite3"
    summary = {"public_inputs": len(records), "verified_sat": 0, "remaining_inputs": len(records), "attempts": 0,
               "interrupted_attempts": 0, "admitted_status_counts": {}}
    if database.exists():
        db = _connect(database, readonly=True)
        try:
            db.execute("BEGIN")
            _audit(db, records, directory, evidence_dir, fingerprint)
            summary = _summary(db, len(records))
        finally:
            db.close()
    matching = _matching_output(directory, output) if output.exists() else None
    base = {"schema_version": 2, "dataset_id": info["dataset_id"], "artificial": info["artificial"],
            "witness_cutoff_seconds": WITNESS_CUTOFF_SECONDS, "benchmark_cutoff_seconds": 10.0,
            "fingerprint_sha256": fingerprint_hash, "output_reusable": matching is not None}
    base["code_release_sha256"] = release_hash
    if not execute:
        return {**base, **summary, "state": "DRY_RUN", "solver_calls": 0}
    evidence_dir.mkdir(parents=True, exist_ok=True)
    with WitnessWriterLock(evidence_dir):
        _require(database.exists() or not any(p.name != "witness-writer.lock" for p in evidence_dir.iterdir()),
                 "Evidence directory is not a new/known witness namespace")
        db = _connect(database)
        try:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadata'").fetchone():
                _initialize(db, fingerprint, records)
            _audit(db, records, directory, evidence_dir, fingerprint)
            _event(db, "SESSION_STARTED", {"code_release_sha256": release_hash,
                                           "worker_mode": fingerprint["worker_mode"], "reason": reason})
            index = {r["instance_id"]: r for r in records}
            # Adopt durable post-cleanup raw results after a crash before the SQLite commit.
            for old in db.execute("SELECT * FROM attempts WHERE state!='FINISHED' ORDER BY attempt_id").fetchall():
                raw_path = _raw_path(evidence_dir, old["attempt_id"])
                if raw_path.exists():
                    _finish(db, old, index[old["instance_id"]], directory, evidence_dir, fingerprint_hash, data.read_json(raw_path))
                else:
                    _require(not old["launched"] or fake and resume_interrupted,
                             "Launched witness has unknown process-tree cleanup; recovery not proven, stopping")
                    with _transaction(db):
                        db.execute("UPDATE attempts SET state='INTERRUPTED',ended_utc=COALESCE(ended_utc,?),reason=COALESCE(reason,?) WHERE attempt_id=?",
                                   (_utc(), reason or "Stopped before worker launch", old["attempt_id"]))
                        _event(db, "INTERRUPTED_RECOVERY", {"attempt_id": old["attempt_id"], "reason": reason,
                                                         "cleanup_evidence": "artificial_fake_no_process" if fake and old["launched"] else "not_launched"})
            if any(status != "SAT" for status in _summary(db, len(records))["admitted_status_counts"]):
                return {**base, **_summary(db, len(records)), "state": "HALTED", "reason": "Terminal nonSAT/invalid witness retained; no automatic retry"}
            if matching is not None:
                return {**base, **_summary(db, len(records)), "state": "COMPLETE", "reused_output": True}
            if _run_job is None:
                from sudoku.runner import run_job
                _run_job = run_job
            from sudoku.runner import RunnerConfig
            config = RunnerConfig(cutoff_seconds=WITNESS_CUTOFF_SECONDS, repetitions=1,
                                  schedule_seed=data.MASTER_SEED, startup_seconds=60.0, postprocessing_seconds=30.0)
            for record in records:
                if db.execute("SELECT 1 FROM attempts WHERE instance_id=? AND state='FINISHED'", (record["instance_id"],)).fetchone():
                    continue
                _require(data.sha256(data.contained_path(directory, record["input_file"]).read_bytes()) == record["input_sha256"], "Input changed before witness launch")
                with _transaction(db):
                    number = db.execute("SELECT COALESCE(MAX(attempt_no),0)+1 FROM attempts WHERE instance_id=?", (record["instance_id"],)).fetchone()[0]
                    aid = db.execute("INSERT INTO attempts(instance_id,attempt_no,state,started_utc) VALUES(?,?,'RUNNING',?)",
                                     (record["instance_id"], number, _utc())).lastrowid
                    _event(db, "CLAIM", {"attempt_id": aid, "instance_id": record["instance_id"]})
                attempt = dict(attempt_id=aid, attempt_no=number, instance_id=record["instance_id"])
                job = {"job_id": "w2-" + data.sha256(data.json_bytes([record["instance_id"], record["input_sha256"], "sat", "pairwise", 30])),
                       "instance_id": record["instance_id"], "file": str(data.contained_path(directory, record["input_file"]).relative_to(root)),
                       "method": "sat", "encoding": "pairwise", "cutoff_seconds": WITNESS_CUTOFF_SECONDS,
                       "repetition": 1, "scope": "expanded-witness-acquisition-not-benchmark"}
                _atomic_json(evidence_dir / "attempts" / f"a{aid:08d}" / "request.json", {**attempt, "job": job, "fingerprint_sha256": fingerprint_hash})
                try:
                    if _hook:
                        _hook("after_claim", attempt)
                    with _transaction(db):
                        db.execute("UPDATE attempts SET launched=1 WHERE attempt_id=?", (aid,))
                    started = time.perf_counter()
                    raw = _run_job(job, config, root=root)
                    envelope = _envelope(attempt, record, fingerprint_hash, raw, time.perf_counter() - started)
                    _atomic_json(_raw_path(evidence_dir, aid), envelope)
                    if _hook:
                        _hook("after_raw_log", attempt)
                    status = _finish(db, attempt, record, directory, evidence_dir, fingerprint_hash, envelope, _hook)
                    if _hook:
                        _hook("after_result_commit", attempt)
                except KeyboardInterrupt:
                    with _transaction(db):
                        db.execute("UPDATE attempts SET state='INTERRUPTED',ended_utc=?,reason=? WHERE attempt_id=? AND state='RUNNING'",
                                   (_utc(), "Controller interrupted; cleanup may need explicit confirmation", aid))
                        _event(db, "PAUSED", {"attempt_id": aid})
                    return {**base, **_summary(db, len(records)), "state": "PAUSED", "reason": "Interrupted; durable SAT checkpoints retained"}
                if status != "SAT":
                    return {**base, **_summary(db, len(records)), "state": "HALTED", "reason": f"{status}; raw result retained, no retry/reselection"}
                if on_progress:
                    on_progress({**base, **_summary(db, len(records)), "state": "RUNNING"})
            _audit(db, records, directory, evidence_dir, fingerprint)
            proofs = []
            for row in db.execute("SELECT * FROM attempts WHERE state='FINISHED' ORDER BY (SELECT ordinal FROM inputs WHERE inputs.instance_id=attempts.instance_id)"):
                record = index[row["instance_id"]]
                raw = json.loads(row["raw_json"])
                proof = {"instance_id": row["instance_id"], "input_sha256": record["input_sha256"], "result": raw}
                if fake:
                    proof.update(sat_evidence="checked_generator_witness", solution=raw["solution"])
                proofs.append(proof)
            evidence = {"schema_version": 2, "dataset_id": info["dataset_id"], "artificial": info["artificial"],
                        "adapter_code_sha256": fingerprint["code_sha256"]["sat.py"],
                        "purpose": "Witness acquisition, not benchmark observations", "cutoff_seconds": WITNESS_CUTOFF_SECONDS,
                        "fingerprint_sha256": fingerprint_hash, "worker_mode": fingerprint["worker_mode"], "records": proofs}
            _atomic_json(evidence_dir / "public-evidence.json", evidence)
            data.finalize_staged_inputs(directory, output, evidence)
            return {**base, **_summary(db, len(records)), "state": "COMPLETE", "reused_output": False}
        finally:
            db.close()

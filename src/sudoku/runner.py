"""Sequential benchmark runner; planning never calls a solver."""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import math
import multiprocessing as mp
import os
import platform
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from sudoku.runner_process import JobObject
from sudoku.runner_worker import Measurement, TIMINGS, worker

ROOT = Path(__file__).resolve().parents[2]
ENCODINGS = ("pairwise", "seqcounter", "bitwise")
SCOPES = {"sat": "S80", "cpsat": "B16", "highs": "B16", "gurobi": "C10",
          "cplex_mip": "C10", "cpoptimizer": "C10"}
CSV_FIELDS = (
    "schema_version", "run_id", "job_id", "instance_id", "method", "encoding",
    "repetition", "scope", "cutoff_seconds", "status", "raw_status",
    "build_seconds", "solve_seconds", "total_seconds", "primary_variables",
    "auxiliary_variables", "total_variables", "clauses", "validation",
    "validation_message", "solution_artifact", "error", "guard_phase",
)


@dataclass(frozen=True)
class RunnerConfig:
    cutoff_seconds: float = 10.0
    repetitions: int = 3
    schedule_seed: int = 20261016
    startup_seconds: float = 60.0
    postprocessing_seconds: float = 30.0

    def __post_init__(self):
        for key in ("cutoff_seconds", "startup_seconds", "postprocessing_seconds"):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be finite and positive")
        if type(self.repetitions) is not int or self.repetitions < 1:
            raise ValueError("repetitions must be a positive integer")
        if type(self.schedule_seed) is not int:
            raise ValueError("schedule_seed must be an integer")


def read_json(path):
    # Python's JSON preserves the distinct manifest keys n and N.
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package_versions():
    versions = {}
    for name in ("python-sat", "ortools", "scipy", "highspy", "gurobipy", "cplex", "docplex"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def machine_info():
    info = dict(python=platform.python_version(), platform=platform.platform(),
                processor=platform.processor(), logical_cpus=os.cpu_count(), ram_bytes=None)
    if os.name == "nt":
        import ctypes
        class Memory(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (key, ctypes.c_uint64) for key in ("total", "available", "page_total", "page_available",
                                                  "virtual_total", "virtual_available", "extended")]
        memory = Memory()
        memory.length = ctypes.sizeof(memory)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            info["ram_bytes"] = memory.total
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            info["processor"] = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    return info


def verify_dataset(root=ROOT):
    root = Path(root).resolve()
    freeze = read_json(root / "data/freeze.json")
    if freeze.get("frozen") is not True:
        raise ValueError("Dataset is not frozen")
    for relative, digest in freeze["files_sha256"].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or sha256(path) != digest:
            raise ValueError(f"Dataset freeze mismatch: {relative}")
    scopes = read_json(root / "data/scopes.json")
    for scope, count in (("S80", 80), ("B16", 16), ("C10", 10)):
        ids = scopes[scope]
        if len(ids) != count or len(set(ids)) != count or ids != freeze[scope]:
            raise ValueError(f"Invalid frozen scope {scope}")
    if not set(scopes["C10"]) < set(scopes["B16"]) < set(scopes["S80"]):
        raise ValueError("Expected C10 subset B16 subset S80")
    records = read_json(root / "data/manifest.json")["records"]
    index = {r["instance_id"]: r for r in records}
    if len(index) != 80 or len(records) != 80 or set(index) != set(scopes["S80"]):
        raise ValueError("Manifest/scope mismatch")
    for record in records:
        if record["N"] != record["n"] ** 2:
            raise ValueError("Manifest n/N mismatch")
    return scopes, index


def make_schedule(config=RunnerConfig(), *, root=ROOT):
    scopes, index = verify_dataset(root)
    jobs = []
    for method, scope in SCOPES.items():
        for encoding in ENCODINGS if method == "sat" else (None,):
            for instance_id in scopes[scope]:
                for repetition in range(1, config.repetitions + 1):
                    jobs.append(dict(job_id=f"{instance_id}__{method}__{encoding or 'none'}__r{repetition}",
                                     instance_id=instance_id, method=method, encoding=encoding,
                                     repetition=repetition, scope=scope,
                                     file=index[instance_id]["file"], cutoff_seconds=config.cutoff_seconds))
    random.Random(config.schedule_seed).shuffle(jobs)
    return jobs


def _failure(request, status, phase, message, snapshot=None):
    result = dict(status=status, method=request["method"], encoding=request.get("encoding"),
                  raw_status=None, solution=None, stats=None, validation=None,
                  error=message, guard_phase=phase)
    result.update(dict.fromkeys(TIMINGS))
    if snapshot is not None:
        result.update(zip(TIMINGS, snapshot[2:]))
    return result


def _monitor(process, connection, state, request, config, launched):
    snapshot = (None,) * 5
    while True:
        snapshot = state.snapshot()  # Final recheck is performed even at the deadline.
        start, end = snapshot[:2]
        now = time.perf_counter()
        deadline = None if start is None else start + config.cutoff_seconds
        if end is not None and (start is None or end < start):
            return _failure(request, "ERROR", "protocol", "Invalid END timestamp", snapshot)
        if start is None:
            phase, limit = "startup", launched + config.startup_seconds
        elif end is None:
            phase, limit = "measurement", deadline
        elif end > deadline:
            return _failure(request, "TIMEOUT", "measurement", "Measurement END exceeded deadline", snapshot)
        else:
            phase, limit = "postprocessing", end + config.postprocessing_seconds
        if now >= limit:
            # Snapshot after observing the deadline closes END/event notification races.
            latest = state.snapshot()
            if latest != snapshot:
                continue
            status = "TIMEOUT" if phase == "measurement" else "ERROR"
            return _failure(request, status, phase, f"{phase} watchdog expired", snapshot)
        if connection.poll(min(0.01, max(0, limit - now))):
            try:
                result = connection.recv()
            except EOFError:
                return _failure(request, "ERROR", phase, "Worker exited without result", snapshot)
            latest = state.snapshot()
            start, end = latest[:2]
            if end is not None and (start is None or end < start):
                return _failure(request, "ERROR", "protocol", "Invalid END timestamp", latest)
            if end is not None and start is not None and end > start + config.cutoff_seconds:
                return _failure(request, "TIMEOUT", "measurement", "Late END", latest)
            if end is None:
                # Premeasurement failures are not runtime observations. An error
                # during measured work with no hook cannot escape an elapsed cutoff.
                if start is not None and time.perf_counter() >= start + config.cutoff_seconds:
                    return _failure(request, "TIMEOUT", "measurement", "No END at deadline", latest)
                if result.get("status") not in ("ERROR", "INVALID_INPUT", "UNAVAILABLE", "LICENSE_LIMIT"):
                    return _failure(request, "ERROR", "protocol", "Result missing END", latest)
                if any(result.get(key) is not None for key in TIMINGS):
                    return _failure(request, "ERROR", "protocol", "Timings without END", latest)
            elif time.perf_counter() >= end + config.postprocessing_seconds:
                return _failure(request, "ERROR", "postprocessing", "Postprocessing watchdog expired", latest)
            if result.get("status") == "SAT" and (not result.get("solution") or not (result.get("validation") or {}).get("valid")):
                return _failure(request, "ERROR", "validation", "SAT lacks checked solution", latest)
            if end is not None:
                result.update(zip(TIMINGS, latest[2:]))
            result["guard_phase"] = "complete" if start is not None else "startup"
            return result
        if not process.is_alive():
            if connection.poll():
                continue
            return _failure(request, "ERROR", phase, "Worker exited without result", snapshot)


def run_job(job, config=RunnerConfig(), *, root=ROOT, _worker=worker):
    """Run one isolated job. _worker is solely a diagnostic injection seam."""
    if job.get("cutoff_seconds") != config.cutoff_seconds:
        raise ValueError("Job cutoff differs from runner config")
    request = dict(job, input_path=str(Path(root) / job["file"]), cutoff_seconds=config.cutoff_seconds)
    context = mp.get_context("spawn")
    gate, state = context.Event(), Measurement(context)
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(gate, state, sender, request))
    tree = None
    result = None
    try:
        tree = JobObject()
        launched = time.perf_counter()
        process.start()
        sender.close()
        tree.assign(process.pid)
        gate.set()  # No backend import, input reading or descendants before containment.
        result = _monitor(process, receiver, state, request, config, launched)
    except Exception as exc:
        result = _failure(request, "ERROR", "guard", f"{type(exc).__name__}: {exc}"[:500])
    finally:
        try:
            if tree is not None:
                tree.terminate_and_wait()
            if process.pid is not None:
                # Assignment failure occurs with the gate still closed: no descendants.
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    raise RuntimeError("Worker survived cleanup")
        except Exception as exc:
            result = _failure(request, "ERROR", "cleanup", f"Process cleanup failed: {exc}"[:500])
        finally:
            if tree is not None:
                try:
                    tree.close()
                except Exception as exc:
                    result = _failure(request, "ERROR", "cleanup", str(exc)[:500])
            receiver.close()
            sender.close()
            if process.pid is not None and not process.is_alive():
                process.close()
    return result


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def prepare_run(output_dir, config=RunnerConfig(), *, root=ROOT):
    """Create a new immutable plan directory, refusing an existing directory."""
    root, output = Path(root), Path(output_dir)
    jobs = make_schedule(config, root=root)
    evidence = {}
    for relative in ("diagnostics/smoke_results.json", "diagnostics/solvers/versions.json",
                     "diagnostics/environment-integration.md", "diagnostics/solvers/availability.md"):
        path = root / relative
        if path.exists():
            evidence[relative] = dict(sha256=sha256(path), content=path.read_text(encoding="utf-8-sig"))
    metadata = dict(schema_version=1, run_id=output.name, config=asdict(config),
                    dataset_freeze_sha256=sha256(root / "data/freeze.json"),
                    code_sha256={str(p.relative_to(root)): sha256(p) for p in sorted((root / "src/sudoku").rglob("*.py"))},
                    machine=machine_info(), packages=package_versions(),
                    environment_evidence=evidence,
                    note="Prepared schedule only; not pilot evidence or RUN-012 approval")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "run.json", metadata)
    write_json(output / "schedule.json", jobs)
    return jobs


def write_result(output_dir, job, result):
    """Append one row; publish SAT witness before the row referencing it."""
    output = Path(output_dir)
    row = dict.fromkeys(CSV_FIELDS)
    row.update(schema_version=1, run_id=output.name,
               **{k: job[k] for k in ("job_id", "instance_id", "method", "encoding", "repetition", "scope", "cutoff_seconds")})
    row.update({key: result.get(key) for key in ("status", "raw_status", *TIMINGS, "error", "guard_phase")})
    stats = result.get("stats") or {}
    row.update({key: stats.get(key) for key in ("primary_variables", "auxiliary_variables", "total_variables", "clauses")})
    validation = result.get("validation")
    if validation is not None:
        row["validation"] = "pass" if validation["valid"] else "fail"
        row["validation_message"] = validation.get("message")
    csv_path = output / "results.csv"
    if csv_path.exists():
        with csv_path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != list(CSV_FIELDS):
                raise ValueError("CSV schema mismatch")
            if any(old["job_id"] == job["job_id"] for old in reader):
                raise ValueError("Duplicate result job_id")
    if result["status"] == "SAT":
        if not result.get("solution") or not (validation or {}).get("valid"):
            raise ValueError("Cannot store unchecked SAT")
        relative = f"solutions/{job['job_id']}.json"
        (output / "solutions").mkdir(exist_ok=True)
        write_json(output / relative, dict(job_id=job["job_id"], instance_id=job["instance_id"],
                                         solution=result["solution"], validation=validation))
        row["solution_artifact"] = relative
    exists = csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(row)
        stream.flush()
    return row


def execute_run(output_dir, *, root=ROOT, job_ids=None):
    """Explicit execution only; existing results are never resumed implicitly."""
    output, root = Path(output_dir), Path(root)
    metadata = read_json(output / "run.json")
    config = RunnerConfig(**metadata["config"])
    if package_versions() != metadata["packages"] or platform.python_version() != metadata["machine"]["python"]:
        raise ValueError("Dependencies changed after planning; create a new run")
    verify_dataset(root)
    if sha256(root / "data/freeze.json") != metadata["dataset_freeze_sha256"]:
        raise ValueError("Dataset freeze changed after planning")
    current = {str(p.relative_to(root)): sha256(p) for p in sorted((root / "src/sudoku").rglob("*.py"))}
    if current != metadata["code_sha256"]:
        raise ValueError("Code changed after planning; create a new run")
    jobs = read_json(output / "schedule.json")
    if jobs != make_schedule(config, root=root):
        raise ValueError("Schedule changed after planning")
    if job_ids is not None:
        requested = list(job_ids)
        if len(set(requested)) != len(requested) or not set(requested) <= {j["job_id"] for j in jobs}:
            raise ValueError("Unknown or duplicate job IDs")
        jobs = [j for j in jobs if j["job_id"] in set(requested)]
    if (output / "results.csv").exists():
        raise ValueError("Results already exist; use a separate run and explicit missing-job list")
    write_json(output / "executed-job-ids.json", [j["job_id"] for j in jobs])
    for job in jobs:
        result = run_job(job, config, root=root)
        write_result(output, job, result)
        # All frozen S80 inputs have independently checked SAT witnesses.
        # Preserve the contradictory observation, but do not continue using it.
        if result.get("status") == "UNSAT":
            write_json(output / "dataset-disagreement.json", dict(
                job_id=job["job_id"], method=job["method"], encoding=job["encoding"],
                expected="SAT", observed="UNSAT", action="stop batch; investigate configuration"))
            raise RuntimeError("UNSAT contradicts frozen dataset SAT evidence; batch stopped")
        if result.get("guard_phase") == "cleanup":
            raise RuntimeError("Cleanup failed; refusing to start another worker")
    return len(jobs)

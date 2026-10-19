"""Root-policy-bound capacity stages and final selected-scope throughput run."""
from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
COORDINATOR = ROOT / "scripts/run_expanded_capacity.py"
spec = importlib.util.spec_from_file_location("capacity_coordinator", COORDINATOR)
capacity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capacity)
LADDER = [8, 16, 24, 32, 40, 56, 72, 100]


def policy_subject(manifest):
    return dict(schema_version=1, accepted=True, accepted_by="root",
                driver_sha256=capacity.sha(__file__), coordinator_sha256=capacity.sha(COORDINATOR),
                experiment_id=manifest["experiment_id"], scientific_sha256=manifest["scientific_sha256"],
                allowed_ladder=LADDER, selected_repetitions=[1], target_jobs=110000,
                min_available_ram_mb=6144, worker_memory_reserve_mb_initial=256,
                stage_jobs=320, allow_final_run=True, profile="capacity-ramp-v1")


def verify_policy(manifest, path, expected_sha):
    path = Path(path).resolve()
    capacity.require(path.is_relative_to(ROOT), "Root policy must be in project root")
    capacity.require(capacity.sha(path) == expected_sha, "Root policy SHA256 mismatch", 5)
    policy = capacity.read(path)
    capacity.require(all(capacity.dumps(policy.get(k)) == capacity.dumps(v)
                         for k, v in policy_subject(manifest).items()), "Root policy subject mismatch", 5)
    return dict(path=str(path.relative_to(ROOT)), sha256=expected_sha)


def best_stage(stages):
    valid = [s for s in stages if s["metrics"]["new_jobs"] > 0 and not s.get("resource_stopped")]
    capacity.require(bool(valid), "No safe capacity stage completed", 5)
    maximum = max(s["metrics"]["jobs_per_second"] for s in valid)
    return min((s for s in valid if s["metrics"]["jobs_per_second"] >= maximum*.95),
               key=lambda s: (s["metrics"]["effective_memory_cap"], s["requested_workers"]))


def next_stage_decision(stages):
    current = stages[-1]
    metric = current["metrics"]
    if current.get("resource_stopped") or metric["ram_throttle_count"]:
        return False, "resource admission throttled"
    if len(stages) > 1:
        previous_best = max(s["metrics"]["jobs_per_second"] for s in stages[:-1])
        if metric["jobs_per_second"] < .85*previous_best:
            return False, "throughput below 85 percent of previous best"
    if len(stages) >= 3:
        tail = stages[-3:]
        plateau = all(tail[i]["metrics"]["jobs_per_second"] < tail[i-1]["metrics"]["jobs_per_second"]*1.05
                      and tail[i]["cpu_percent"] >= 85 for i in (1, 2))
        if plateau:
            return False, "two saturated stages with less than five percent improvement"
    if current["requested_workers"] >= 40:
        improving = len(stages) < 2 or metric["jobs_per_second"] > max(s["metrics"]["jobs_per_second"] for s in stages[:-1])
        if current["cpu_percent"] >= 85 or current["min_available_mb"] < 10240 or not improving:
            return False, "above-40 resource or improvement gate"
    return True, "continue"


def next_reserve(stages):
    forty = next((s for s in stages if s["requested_workers"] == 40), None)
    if forty and forty["min_available_mb"] >= 12288 and forty["cpu_percent"] < 85 and not forty["metrics"]["ram_throttle_count"]:
        return 128
    return 256


def cpu_times():
    from ctypes import wintypes
    idle, kernel, user = (wintypes.FILETIME() for _ in range(3))
    capacity.require(ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)), "CPU time query failed", 5)
    value = lambda x: (x.dwHighDateTime << 32) | x.dwLowDateTime
    return value(idle), value(kernel)+value(user)


def cpu_percent(previous, current):
    idle = current[0]-previous[0]
    total = current[1]-previous[1]
    return max(0, min(100, 100*(total-idle)/total)) if total > 0 else 0


def progress(experiment):
    db = capacity.storage.connect(experiment, readonly=True)
    try:
        completed = db.execute("SELECT COUNT(*) FROM primary_attempt p JOIN jobs j USING(job_id) WHERE j.repetition=1").fetchone()[0]
        active = db.execute("SELECT COUNT(*) FROM attempts WHERE state='RUNNING'").fetchone()[0]
        return completed, active
    finally:
        db.close()


def immutable_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(capacity.dumps(value)+"\n")


def invoke(experiment, output, manifest, policy_ref, workers, reserve, *, stage_jobs, stop_file, tag):
    verify_policy(manifest, ROOT/policy_ref["path"], policy_ref["sha256"])
    scope = dict(selected_repetitions=[1], target_jobs=110000, effective_repetitions=1,
                 original_manifest_repetitions=manifest["config"]["repetitions"])
    authorization = capacity.authorization_subject(manifest, workers, scope,
        min_available_ram_mb=6144, authorized_workers_max=100, worker_memory_reserve_mb=reserve)
    authorization["delegated_root_policy_ref"] = policy_ref
    authorization_path = output / (tag+".authorization.json")
    immutable_json(authorization_path, authorization)
    args = [sys.executable, str(COORDINATOR), "--experiment", str(experiment), "--execute", "--workers", str(workers),
            "--authorized-workers-max", "100", "--min-available-ram-mb", "6144", "--worker-memory-reserve-mb", str(reserve),
            "--repetition", "1", "--stop-starting-at", "2099-01-01T00:00:00+00:00", "--stop-file", str(stop_file),
            "--authorization", str(authorization_path), "--authorization-sha256", capacity.sha(authorization_path)]
    if stage_jobs is not None:
        args += ["--max-jobs", str(stage_jobs)]
    env = dict(os.environ)
    env.update({k:"1" for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")})
    before = set((experiment / "session-manifests").glob("*.metrics.json"))
    log_path = output / (tag+".stdout.log")
    samples = []
    resource_stopped = False
    interrupted = False
    def stop(*_):
        nonlocal interrupted
        interrupted = True
        stop_file.touch(exist_ok=True)
    previous_signal = signal.signal(signal.SIGINT, stop)
    try:
        with log_path.open("x", encoding="utf-8") as log:
            previous_cpu = cpu_times()
            child = subprocess.Popen(args, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, shell=False)
            last_display = 0
            while child.poll() is None:
                try:
                    time.sleep(5)
                    current_cpu = cpu_times()
                    cpu = cpu_percent(previous_cpu, current_cpu)
                    previous_cpu = current_cpu
                    available = capacity.available_physical_mb()
                    completed, active = progress(experiment)
                    samples.append(dict(utc=capacity.stamp(), cpu_percent=cpu, available_mb=available, active=active, completed=completed))
                    if available < 6144:
                        resource_stopped = True
                        stop_file.touch(exist_ok=True)
                    if stage_jobs is not None or time.monotonic()-last_display >= 30:
                        print(f"{tag}: {completed}/110000; active={active}; CPU={cpu:.1f}%; available RAM={available:.0f} MB", flush=True)
                        last_display = time.monotonic()
                except BaseException:
                    # Never abandon an admitted child: request a pause and
                    # continue waiting for its guard cleanup and durable commits.
                    stop_file.touch(exist_ok=True)
                    interrupted = True
            code = child.wait()
    finally:
        signal.signal(signal.SIGINT, previous_signal)
    capacity.require(code in (0, 4), f"Capacity child failed with exit {code}; inspect {log_path}", 5)
    paths = set((experiment / "session-manifests").glob("*.metrics.json"))-before
    capacity.require(len(paths) == 1, "Expected one capacity metrics session", 5)
    metrics_path = paths.pop()
    metrics = capacity.read(metrics_path)
    active_samples = [s for s in samples if s["active"] > 0]
    used = active_samples or samples
    cpu = sum(s["cpu_percent"] for s in used)/len(used) if used else 100
    minimum = min([metrics["min_available_mb"]]+[s["available_mb"] for s in samples])
    stage = dict(requested_workers=workers, reserve_mb=reserve, exit_code=code, metrics=metrics,
                 cpu_percent=cpu, min_available_mb=minimum, resource_stopped=resource_stopped,
                 interrupted=interrupted, samples=samples, metrics_source=str(metrics_path),
                 metrics_sha256=capacity.sha(metrics_path), log_path=str(log_path))
    immutable_json(output / (tag+".stage.json"), stage)
    print(f"{tag}: requested={workers}, memory cap={metrics['effective_memory_cap']}, observed peak={metrics['peak_inflight']}, throughput={metrics['jobs_per_second']:.4f} jobs/s", flush=True)
    capacity.require(not any(k not in ("SAT", "TIMEOUT") for k in metrics["statuses"]), "Fatal result in capacity session", 5)
    return stage


def run(experiment, policy_path, policy_sha256, *, execute=False):
    experiment = Path(experiment).resolve()
    manifest = capacity.read(experiment / "experiment.json")
    ref = verify_policy(manifest, policy_path, policy_sha256)
    if not execute:
        return dict(execute=False, policy=ref, required_policy=policy_subject(manifest))
    capacity.require(os.name == "nt", "Capacity ramp requires Windows")
    # Deep validation and ordinary coordinator gates still run for every child.
    db = capacity.storage.connect(experiment, readonly=True)
    try:
        capacity.check_resumable(db)
        capacity.require(capacity.selected_scope(db, manifest, 1)["target_jobs"] == 110000, "Policy target count mismatch", 5)
    finally:
        db.close()
    output = ROOT / "diagnostics/expansion/capacity" / ("ramp-"+time.strftime("%Y%m%d-%H%M%S")+"-"+str(os.getpid()))
    output.mkdir(parents=True, exist_ok=False)
    stages = []
    reason = "ladder exhausted"
    for workers in LADDER:
        capacity.require(capacity.sha(__file__) == capacity.read(policy_path)["driver_sha256"] and
                         capacity.sha(COORDINATOR) == capacity.read(policy_path)["coordinator_sha256"] and
                         capacity.sha(policy_path) == policy_sha256, "Frozen ramp/policy changed", 5)
        reserve = next_reserve(stages) if workers > 40 else 256
        stage = invoke(experiment, output, manifest, ref, workers, reserve, stage_jobs=320,
                       stop_file=output/(f"workers-{workers}.stop.request"), tag=f"workers-{workers}")
        stages.append(stage)
        if stage["interrupted"]:
            return dict(state="PAUSED", reason="operator stop", output=str(output), exit_code=4)
        if stage["exit_code"] == 0:
            return dict(state="SELECTED_SCOPE_COMPLETED", output=str(output), exit_code=0)
        keep_going, reason = next_stage_decision(stages)
        if stage["metrics"]["effective_memory_cap"] < workers:
            can_relax_next = workers == 40 and next_reserve(stages) == 128
            if not can_relax_next:
                keep_going, reason = False, "effective RAM cap below requested workers"
        if not keep_going:
            break
    best = best_stage(stages)
    final_workers = best["metrics"]["effective_memory_cap"]
    immutable_json(output/"selection.json", dict(reason=reason, selected_workers=final_workers, selected_stage=best,
                                                policy=ref, selection_policy="within five percent of best throughput prefers smaller memory cap"))
    stable_stop = ROOT/"diagnostics/expansion/capacity-final-stop.request"
    capacity.require(not stable_stop.exists(), "Final stop request exists; operator must explicitly clear it before launch", 4)
    print(f"Selected {final_workers} workers; final stop file: {stable_stop}", flush=True)
    final = invoke(experiment, output, manifest, ref, final_workers, best["reserve_mb"], stage_jobs=None,
                   stop_file=stable_stop, tag="final")
    return dict(state="COMPLETED" if final["exit_code"] == 0 else "PAUSED", selected_workers=final_workers,
                output=str(output), exit_code=final["exit_code"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run(args.experiment, args.policy, args.policy_sha256, execute=args.execute)
        print(json.dumps(result, indent=2))
        return result.get("exit_code", 0)
    except (capacity.ExpandedError, OSError, ValueError) as exc:
        print(json.dumps(dict(error=str(exc), exit_code=getattr(exc, "exit_code", 5))), file=sys.stderr)
        return getattr(exc, "exit_code", 5)


if __name__ == "__main__":
    raise SystemExit(main())

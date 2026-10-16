"""Single-launch main supervisor. Status/logs survive the initiating chat."""
import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from sudoku.runner import execute_run, read_json, sha256


def stamp():
    return datetime.now(timezone.utc).isoformat()


def save_status(output, status):
    temporary = output / "supervisor-status.tmp"
    temporary.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output / "supervisor-status.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    output = args.run.resolve()
    # Kept permanently, even on failure. A second launch must never resume/restart.
    with (output / "supervisor-launch.lock").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(dict(pid=os.getpid(), started_utc=stamp())))
    status = dict(state="STARTING", pid=os.getpid(), started_utc=stamp(),
                  command=[sys.executable, *sys.argv], planned_jobs=906,
                  progress_csv=str(output / "results.csv"),
                  run_sha256=sha256(output / "run.json"),
                  schedule_sha256=sha256(output / "schedule.json"),
                  freeze_sha256=sha256(output / "execution-freeze.json"))
    save_status(output, status)
    try:
        freeze = read_json(output / "execution-freeze.json")
        for relative, expected in freeze["files_sha256"].items():
            if sha256(ROOT / relative) != expected:
                raise RuntimeError(f"Execution freeze changed: {relative}")
        status["state"] = "RUNNING"
        save_status(output, status)
        print(f"{stamp()} RUNNING pid={os.getpid()} planned=906", flush=True)
        count = execute_run(output)
        with (output / "results.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if count != 906 or len(rows) != 906 or len({row["job_id"] for row in rows}) != 906:
            raise RuntimeError("Final row/job count mismatch")
        changed = [relative for relative, expected in freeze["files_sha256"].items()
                   if sha256(ROOT / relative) != expected]
        if changed:
            raise RuntimeError(f"Execution freeze changed during batch: {changed}")
        status.update(state="COMPLETED", completed_jobs=count, exit_code=0,
                      results_sha256=sha256(output / "results.csv"),
                      note="Batch finished; RUN-012 acceptance and analysis still required")
        code = 0
    except BaseException as exc:
        status.update(state="FAILED", exit_code=1, error=f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
        code = 1
    status["finished_utc"] = stamp()
    save_status(output, status)
    print(f"{stamp()} {status['state']}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

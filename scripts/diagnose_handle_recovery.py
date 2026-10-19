"""Supplemental diagnostic only: never replace an immutable primary result."""
from pathlib import Path
import json
import os
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import parallel_process_lifecycle as lifecycle
from sudoku.runner import RunnerConfig, run_job
from sudoku.expanded_storage import check_result


def main():
    experiment = ROOT / "results/expanded/wave3-20261019-212023-main"
    connection = sqlite3.connect((experiment / "experiment.sqlite3").as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    job = dict(connection.execute("SELECT j.*,i.manifest_record_json FROM jobs j JOIN instances i USING(instance_id) WHERE j.job_id=?", ("j2-6054d701e2cbc4ec139d5734fe37b447896ee918133a1dd0d7a4b5c9b21e9a84",)).fetchone())
    connection.close()
    record = json.loads(job.pop("manifest_record_json"))
    manifest = json.loads((experiment / "experiment.json").read_text(encoding="utf-8-sig"))
    job.update(file=os.path.relpath(Path(manifest["dataset_dir"]) / record["input_file"], ROOT), scope="supplemental-handle-diagnostic", cutoff_seconds=10.0)
    installed = lifecycle.install()
    result = run_job(job, RunnerConfig(repetitions=1), root=ROOT)
    checked = check_result(result, record, manifest["dataset_dir"])
    output = ROOT / "diagnostics/expansion/root-wave3/handle-error-diagnostic-retry.json"
    output.write_text(json.dumps(dict(kind="SUPPLEMENTAL_DIAGNOSTIC_NOT_PRIMARY", original_error_retained=True, job_id=job["job_id"], lifecycle=installed, result=checked), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(status=checked["status"], guard_phase=checked.get("guard_phase"), validation=checked.get("validation"), primary_unchanged=True)))
    return 0 if checked["status"] in ("SAT", "TIMEOUT") else 1


if __name__ == "__main__":
    raise SystemExit(main())

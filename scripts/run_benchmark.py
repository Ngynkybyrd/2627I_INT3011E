"""Prepare by default; --execute is required to call any solvers."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sudoku.runner import RunnerConfig, execute_run, prepare_run, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/benchmark.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="Execute an already prepared plan")
    parser.add_argument("--job-ids", type=Path, help="Explicit JSON list, execution only")
    args = parser.parse_args()
    if args.execute:
        count = execute_run(args.output, job_ids=read_json(args.job_ids) if args.job_ids else None)
        print(f"Completed {count} jobs")
    else:
        if args.job_ids:
            parser.error("--job-ids requires --execute")
        jobs = prepare_run(args.output, RunnerConfig(**read_json(args.config)))
        print(f"Prepared {len(jobs)} jobs; no solver was run")


if __name__ == "__main__":
    main()

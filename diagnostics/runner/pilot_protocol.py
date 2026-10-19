"""Authorized 55-job diagnostic pilot only. Never runs the main 906 jobs."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import csv
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from sudoku.runner import (RunnerConfig, execute_run, prepare_run, read_json,
                           sha256, verify_dataset, write_json)
from sudoku.model import load_puzzle
from sudoku.validation import check_solution


def select_ids():
    scopes, index = verify_dataset(ROOT)
    selected = []
    for size in (4, 9, 16, 25):
        candidates = [index[i] for i in scopes["B16"]
                      if index[i]["source"] == "synthetic" and index[i]["N"] == size
                      and index[i]["clue_density_requested"] == 0.3]
        selected.append(min(candidates, key=lambda r: (r["actual_seed"], r["instance_id"]))["instance_id"])
    selected.append(next(i for i in scopes["B16"] if index[i]["source"] == "public_sudoku_exchange_hard"))
    return selected, scopes["C10"]


def audit(output):
    metadata = read_json(output / "run.json")
    requested = read_json(output / "pilot-job-ids.json")
    _, index = verify_dataset(ROOT)
    with (output / "results.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len({r["job_id"] for r in rows}) == 55
    assert {r["job_id"] for r in rows} == set(requested)
    assert read_json(output / "executed-job-ids.json") == requested
    counts = defaultdict(Counter)
    checked = 0
    for row in rows:
        counts[row["method"] + (":" + row["encoding"] if row["encoding"] else "")][row["status"]] += 1
        assert row["repetition"] == "1" and float(row["cutoff_seconds"]) == 10.0
        if row["status"] == "SAT":
            assert row["validation"] == "pass" and row["solution_artifact"]
            artifact = read_json(output / row["solution_artifact"])
            assert artifact["job_id"] == row["job_id"]
            assert artifact["instance_id"] == row["instance_id"]
            puzzle = load_puzzle(ROOT / index[row["instance_id"]]["file"])
            assert check_solution(puzzle, artifact["solution"]).valid
            checked += 1
            b, s, total = (float(row[k]) for k in ("build_seconds", "solve_seconds", "total_seconds"))
            assert b >= 0 and s >= 0 and abs(b+s-total) < 1e-8 and total <= 10.0
        assert row["guard_phase"] != "cleanup"
    code_after = {str(p.relative_to(ROOT)): sha256(p) for p in sorted((ROOT / "src/sudoku").rglob("*.py"))}
    summary = dict(label="pilot only; not final performance results", total_jobs=55,
                   independently_rechecked_sat=checked,
                   counts={key: dict(value) for key, value in counts.items()},
                   dataset_freeze_unchanged=sha256(ROOT / "data/freeze.json") == metadata["dataset_freeze_sha256"],
                   code_unchanged_during_pilot=code_after == metadata["code_sha256"],
                   code_after_sha256=code_after, results_sha256=sha256(output / "results.csv"),
                   cutoff_recommendation_seconds=10.0,
                   completed_utc=datetime.now(timezone.utc).isoformat())
    write_json(output / "pilot-audit.json", summary)
    print(summary, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.audit_only:
        audit(output)
        return
    selected, commercial = select_ids()
    # Selection is computed before seeing any result, independent of runtime.
    config = RunnerConfig()
    jobs = prepare_run(output, config)
    ids = [j["job_id"] for j in jobs if j["repetition"] == 1 and
           ((j["method"] in ("sat", "cpsat", "highs") and j["instance_id"] in selected)
            or (j["method"] in ("gurobi", "cplex_mip", "cpoptimizer") and j["instance_id"] in commercial))]
    assert len(ids) == 55 and len(set(ids)) == 55
    write_json(output / "pilot-selection.json", dict(label="pilot only", selected_five=selected,
               commercial_C10=commercial, jobs=55, repetition=1, cutoff_seconds=10,
               rule="min(actual_seed, instance_id), density30 per N in B16; first public B16; all C10",
               selected_utc=datetime.now(timezone.utc).isoformat()))
    write_json(output / "pilot-job-ids.json", ids)
    print(f"Locked {selected}; C10={len(commercial)}; executing exactly {len(ids)} pilot jobs", flush=True)
    try:
        execute_run(output, job_ids=ids)
    except Exception as exc:
        write_json(output / "pilot-failure.json", dict(error=f"{type(exc).__name__}: {exc}",
                   note="Preserve this plan; any retry requires a new directory and reason"))
        raise
    audit(output)


if __name__ == "__main__":
    main()

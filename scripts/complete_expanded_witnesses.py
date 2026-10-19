"""Dry-run by default. --execute explicitly acquires witnesses with a 30s hard guard."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sudoku.expanded_witnesses import WitnessError, complete_witnesses


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume-interrupted", action="store_true")
    parser.add_argument("--reason")
    parser.add_argument("--code-release", type=Path)
    parser.add_argument("--progress-every", type=int, default=25)
    args = parser.parse_args()
    if args.progress_every < 1:
        parser.error("--progress-every must be positive")
    def progress(value):
        if value["verified_sat"] % args.progress_every == 0 or value["remaining_inputs"] == 0:
            print(json.dumps(value, ensure_ascii=False, sort_keys=True), flush=True)
    try:
        result = complete_witnesses(args.dataset, args.evidence_dir, args.output, execute=args.execute,
                                    resume_interrupted=args.resume_interrupted, reason=args.reason,
                                    code_release=args.code_release, on_progress=progress)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 4 if result["state"] == "PAUSED" else 5 if result["state"] == "HALTED" else 0
    except (WitnessError, ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Witness acquisition error: {exc}", file=sys.stderr)
        return getattr(exc, "exit_code", 5)


if __name__ == "__main__":
    raise SystemExit(main())

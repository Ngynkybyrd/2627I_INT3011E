"""Expanded dataset producer tools; smoke is artificial and never runs solvers."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sudoku.expanded_data import (DataError, cache_sources, generate_datasets, smoke_artificial,
                                  stage_inputs, verify_dataset, verify_inputs)


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    smoke = commands.add_parser("smoke", help="Small artificial fixtures, no solver/network")
    smoke.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify", help="Verify a frozen dataset; no solver/network")
    verify.add_argument("--dataset", type=Path, required=True)
    stage = commands.add_parser("stage-inputs", help="Fetch/select inputs only; no public witness solving or freeze")
    stage.add_argument("--cache", type=Path, default=ROOT / "data/expanded/source-cache")
    stage.add_argument("--output", type=Path, required=True, help="New staging parent for main/pilot DRAFT datasets")
    verify_stage = commands.add_parser("verify-inputs", help="Verify DRAFT input integrity only; no public solving")
    verify_stage.add_argument("--dataset", type=Path, required=True)
    cache = commands.add_parser("cache-sources", help="Download four pinned source files and license/readme")
    cache.add_argument("--cache", type=Path, default=ROOT / "data/expanded/source-cache")
    generate = commands.add_parser("generate", help="Full main+pilot data/witness creation; only after coordinator QA release")
    generate.add_argument("--output", type=Path, default=ROOT / "data/expanded")
    generate.add_argument("--cache", type=Path, default=ROOT / "data/expanded/source-cache")
    args = parser.parse_args()
    try:
        if args.command == "smoke":
            result = smoke_artificial(args.output, ROOT)
        elif args.command == "verify":
            result = verify_dataset(args.dataset)
        elif args.command == "stage-inputs":
            result = stage_inputs(ROOT, args.output, args.cache)
        elif args.command == "verify-inputs":
            result = verify_inputs(args.dataset)
        elif args.command == "cache-sources":
            result = cache_sources(args.cache)
        else:
            result = generate_datasets(ROOT, args.output, args.cache)
    except (DataError, OSError, ValueError, KeyError) as exc:
        print(f"Expanded data error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

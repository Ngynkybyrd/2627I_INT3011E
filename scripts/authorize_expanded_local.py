"""Audit conditional root release and publish local gates; never solve."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment",type=Path,required=True)
    parser.add_argument("--code-release",type=Path,required=True)
    parser.add_argument("--pilot-experiment",type=Path)
    args=parser.parse_args(argv)
    from sudoku.expanded_common import ExpandedError
    from sudoku.expanded_local_gates import authorize_expanded_local
    try:
        result=authorize_expanded_local(args.experiment,args.code_release,pilot_experiment=args.pilot_experiment)
    except ExpandedError as exc:
        print(str(exc),file=sys.stderr); return exc.exit_code
    print(json.dumps(result,ensure_ascii=False,allow_nan=False)); return 0


if __name__=="__main__": raise SystemExit(main())

"""Normalize the locked 20 public records; no solving or dataset80 freeze."""

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sudoku.model import load_puzzle, parse_puzzle

SOURCE_HASH = "abcff1512411e601abd5e861c60add5be5d877739b6faa249ee86960f5ad85e9"
SELECTION_HASH = "13f6ff47669498070f53a1404ed1f0492b2d740a461401b3605b9d1bd988c96a"
FIRST_FOUR = [
    "public-se-hard-L069940", "public-se-hard-L293964",
    "public-se-hard-L269904", "public-se-hard-L215069",
]


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def prepare(output_dir, diagnostics_dir, check=False):
    source = (ROOT / "data/source/sudoku-exchange-hard.txt").read_bytes()
    selection = (ROOT / "diagnostics/public-selection.csv").read_bytes()
    if sha256(source) != SOURCE_HASH or sha256(selection) != SELECTION_HASH:
        raise ValueError("Locked source or selection checksum differs; refusing to reselect")
    rows = list(csv.DictReader(io.StringIO(selection.decode("utf-8"))))
    if len(rows) != 20 or len({row["puzzle_digits"] for row in rows}) != 20:
        raise ValueError("Expected exactly 20 distinct locked puzzles")
    if [row["proposed_instance_id"] for row in rows[:4]] != FIRST_FOUR:
        raise ValueError("First four B16/C10 public IDs differ")
    source_lines = source.decode("ascii").splitlines()
    outputs = {}
    index_rows = []
    for rank, row in enumerate(rows, 1):
        line_number = int(row["source_line"])
        instance_id = row["proposed_instance_id"]
        digits = row["puzzle_digits"]
        expected_id = f"public-se-hard-L{line_number:06d}"
        if int(row["sample_rank"]) != rank or instance_id != expected_id:
            raise ValueError("Locked rank or source-line ID differs")
        source_fields = source_lines[line_number - 1].split()
        if source_fields != [row["source_id"], digits, row["source_rating_unverified"]]:
            raise ValueError(f"{instance_id}: source record differs")
        if row["puzzle_ascii_sha256"] != sha256(digits.encode("ascii")):
            raise ValueError(f"{instance_id}: puzzle hash differs")
        if row["seed"] != "20261016" or row["proposed_b16_c10"] != ("yes" if rank <= 4 else "no"):
            raise ValueError(f"{instance_id}: selection metadata differs")
        if row["sat_checked"] != "no" or row["uniqueness_checked"] != "no":
            raise ValueError("This normalization step does not accept SAT/uniqueness claims")
        payload = {"n": 3, "grid": [list(map(int, digits[start:start + 9])) for start in range(0, 81, 9)]}
        puzzle = parse_puzzle(payload)
        if puzzle.clue_count != int(row["clue_count"]):
            raise ValueError(f"{instance_id}: clue count differs")
        raw = json_bytes(payload)
        outputs[output_dir / f"{instance_id}.json"] = raw
        index_rows.append({
            "sample_rank": rank, "instance_id": instance_id,
            "file": f"data/public/{instance_id}.json",
            "source_line": line_number, "source_id": row["source_id"],
            "source_commit": "d8c8ebaee0c08c412cfba96af1923dfa61c83317",
            "puzzle_ascii_sha256": row["puzzle_ascii_sha256"],
            "json_sha256": sha256(raw), "clue_count": puzzle.clue_count,
            "proposed_b16_c10": rank <= 4,
            "structural_validation": "load_puzzle",
            "sat_checked": False, "uniqueness_checked": False,
        })
    index = {
        "scope": "20 public records only; not dataset80 manifest or freeze",
        "source_sha256": SOURCE_HASH, "selection_sha256": SELECTION_HASH,
        "seed": 20261016, "records": index_rows,
    }
    outputs[diagnostics_dir / "index.json"] = json_bytes(index)
    # Check all existing paths before writing anything; do not overwrite changes.
    for path, raw in outputs.items():
        if path.exists() and path.read_bytes() != raw:
            raise ValueError(f"Refusing to overwrite different bytes: {path}")
        if check and not path.exists():
            raise ValueError(f"Missing normalized output: {path}")
    if not check:
        for path, raw in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                with path.open("xb") as stream:
                    stream.write(raw)
    expected_names = {f"{row['instance_id']}.json" for row in index_rows}
    if {path.name for path in output_dir.glob("*.json")} != expected_names:
        raise ValueError("Output directory must contain exactly the 20 locked JSON inputs")
    for row in index_rows:
        path = output_dir / f"{row['instance_id']}.json"
        puzzle = load_puzzle(path)
        digits = "".join(str(value) for grid_row in puzzle.grid for value in grid_row)
        if puzzle.n != 3 or puzzle.N != 9 or sha256(digits.encode("ascii")) != row["puzzle_ascii_sha256"]:
            raise ValueError(f"{path}: parser round-trip differs")
    print("PASS: 20 UTF-8 JSON inputs, load_puzzle round-trip, locked source/order/IDs, byte-for-byte regeneration")
    print("PASS: first four public proposals for B16/C10 unchanged; SAT/uniqueness unchecked")
    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify existing files without writing")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/public")
    parser.add_argument("--diagnostics-dir", type=Path, default=ROOT / "diagnostics/public-normalization")
    args = parser.parse_args()
    prepare(args.output_dir, args.diagnostics_dir, args.check)

"""Select source records only; does not create solver input or verify Sudoku SAT."""

import argparse
import csv
import hashlib
import random
import re
import sys
from pathlib import Path


def select(source: Path):
    raw = source.read_bytes()
    records = []
    seen = set()
    duplicates = 0
    lines = raw.decode("ascii").splitlines()
    for line_number, line in enumerate(lines, start=1):
        fields = line.split()
        if len(fields) != 3:
            raise ValueError(f"Line {line_number}: expected three fields")
        source_id, digits, rating = fields
        if not re.fullmatch(r"[0-9a-f]{12}", source_id):
            raise ValueError(f"Line {line_number}: invalid source ID")
        if not re.fullmatch(r"[0-9]{81}", digits):
            raise ValueError(f"Line {line_number}: expected 81 digits")
        if not re.fullmatch(r"\d+\.\d", rating):
            raise ValueError(f"Line {line_number}: invalid source rating")
        if digits in seen:
            duplicates += 1
            continue
        seen.add(digits)
        records.append((line_number, source_id, digits, rating))
    chosen = random.Random(20261016).sample(records, 20)
    result = []
    for rank, (line_number, source_id, digits, rating) in enumerate(chosen, 1):
        result.append({
            "sample_rank": rank,
            "proposed_instance_id": f"public-se-hard-L{line_number:06d}",
            "source_line": line_number,
            "source_id": source_id,
            "puzzle_digits": digits,
            "clue_count": sum(digit != "0" for digit in digits),
            "source_rating_unverified": rating,
            "seed": 20261016,
            "proposed_b16_c10": "yes" if rank <= 4 else "no",
            "puzzle_ascii_sha256": hashlib.sha256(digits.encode("ascii")).hexdigest(),
            "sat_checked": "no",
            "uniqueness_checked": "no",
        })
    summary = {
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "lines": len(lines),
        "unique_puzzles": len(records),
        "duplicates_removed": duplicates,
        "python_version": sys.version.split()[0],
    }
    return result, summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows, summary = select(args.source)
    # Exclusive creation protects another chat's output and any previous selection.
    with args.output.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    for key, value in summary.items():
        print(f"{key}={value}")
    print("proposed_b16_c10=" + ",".join(row["proposed_instance_id"] for row in rows[:4]))

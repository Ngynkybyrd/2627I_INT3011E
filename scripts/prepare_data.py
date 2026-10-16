"""Reproduce dataset inputs/index and verify its evidence-backed freeze; no solving."""

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sudoku.model import Puzzle, load_puzzle
from sudoku.validation import check_solution

PUBLIC_INDEX_HASH = "8f1f236de4e365029fcdfd971fc24472fcb5b980134a380ed396d14480bcbccd"
SELECTION_HASH = "13f6ff47669498070f53a1404ed1f0492b2d740a461401b3605b9d1bd988c96a"
FIRST_FOUR = ["public-se-hard-L069940", "public-se-hard-L293964",
              "public-se-hard-L269904", "public-se-hard-L215069"]


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def puzzle_bytes(puzzle):
    return json_bytes({"n": puzzle.n, "grid": [list(row) for row in puzzle.grid]})


def fingerprint(puzzle):
    # Include n, so a content checksum cannot conflate different board dimensions.
    return sha256(puzzle_bytes(puzzle))


def assert_witness(puzzle, solution):
    validation = check_solution(puzzle, solution)
    if not validation.valid:
        raise ValueError(f"Generated witness failed independent checker: {validation.message}")


def completed_grid(n):
    # Use the shared validator for exact integer n and n >= 2 before allocation.
    if type(n) is not int or n < 2:
        raise ValueError("n must be an exact integer >= 2")
    N = n * n
    grid = [[(n * (r % n) + r // n + c) % N + 1 for c in range(N)] for r in range(N)]
    full = Puzzle(n, grid)
    assert_witness(full, grid)
    return grid


def permute_grid(grid, n, rng):
    N = n * n
    values = list(range(1, N + 1))
    rng.shuffle(values)

    def grouped_order():
        groups = list(range(n))
        rng.shuffle(groups)
        order = []
        for group in groups:
            offsets = list(range(n))
            rng.shuffle(offsets)
            order.extend(group * n + offset for offset in offsets)
        return order

    rows, columns = grouped_order(), grouped_order()
    result = [[values[grid[r][c] - 1] for c in columns] for r in rows]
    assert_witness(Puzzle(n, result), result)
    return result


def candidate(n, density_percent, seed):
    rng = random.Random(f"{n}:{density_percent}:{seed}")
    solution = permute_grid(completed_grid(n), n, rng)
    N = n * n
    clue_count = (density_percent * N * N + 50) // 100
    positions = set(rng.sample(range(N * N), clue_count))
    puzzle = Puzzle(n, [[solution[r][c] if r * N + c in positions else 0
                         for c in range(N)] for r in range(N)])
    assert_witness(puzzle, solution)
    return puzzle, solution


def synthetic_records(existing_fingerprints=()):
    seen = set(existing_fingerprints)
    records, outputs, collisions = [], {}, []
    for n in (2, 3, 4, 5):
        for density in (30, 50, 70):
            for requested_seed in range(5):
                instance_id = f"synthetic-N{n*n:02d}-p{density}-s{requested_seed}"
                for attempt in range(1000):
                    actual_seed = requested_seed + attempt
                    puzzle, solution = candidate(n, density, actual_seed)
                    checksum = fingerprint(puzzle)
                    if checksum not in seen:
                        seen.add(checksum)
                        break
                    collisions.append({"instance_id": instance_id, "rejected_seed": actual_seed,
                                       "puzzle_sha256": checksum, "reason": "duplicate_content"})
                else:
                    raise ValueError(f"{instance_id}: exhausted 1000 deterministic seed attempts")
                input_file = f"data/synthetic/{instance_id}.json"
                witness_file = f"data/witnesses/{instance_id}.json"
                raw, witness_raw = puzzle_bytes(puzzle), json_bytes({"n": n, "solution": solution})
                outputs[input_file] = raw
                outputs[witness_file] = witness_raw
                records.append({
                    "instance_id": instance_id, "file": input_file, "source": "synthetic",
                    "n": n, "N": puzzle.N, "clue_density_requested": density / 100,
                    "clue_count": puzzle.clue_count, "seed": requested_seed,
                    "actual_seed": actual_seed, "resample_attempts": attempt,
                    "rng_key": f"{n}:{density}:{actual_seed}", "sha256": sha256(raw),
                    "content_sha256": checksum, "witness_file": witness_file,
                    "witness_sha256": sha256(witness_raw),
                    "sat_status": "SAT", "sat_evidence": "independent_checker_validated_witness",
                    "uniqueness": "unverified",
                })
    return records, outputs, collisions


def public_records(project_root):
    index_raw = (project_root / "diagnostics/public-normalization/index.json").read_bytes()
    selection_raw = (project_root / "diagnostics/public-selection.csv").read_bytes()
    if sha256(index_raw) != PUBLIC_INDEX_HASH or sha256(selection_raw) != SELECTION_HASH:
        raise ValueError("Locked public index/selection differs")
    source_rows = json.loads(index_raw)["records"]
    if len(source_rows) != 20 or [row["instance_id"] for row in source_rows[:4]] != FIRST_FOUR:
        raise ValueError("Expected 20 locked public records with unchanged first four IDs")
    records, seen = [], set()
    for rank, row in enumerate(source_rows, 1):
        instance_id = row["instance_id"]
        path = project_root / f"data/public/{instance_id}.json"
        raw = path.read_bytes()
        puzzle = load_puzzle(path)
        checksum = fingerprint(puzzle)
        if sha256(raw) != row["json_sha256"] or checksum in seen:
            raise ValueError(f"{instance_id}: public bytes changed or duplicate")
        if puzzle.n != 3 or puzzle.clue_count != row["clue_count"]:
            raise ValueError(f"{instance_id}: public metadata differs")
        seen.add(checksum)
        records.append({
            "instance_id": instance_id, "file": f"data/public/{instance_id}.json",
            "source": "public_sudoku_exchange_hard", "n": 3, "N": 9,
            "clue_density_requested": None, "clue_count": puzzle.clue_count,
            "seed": 20261016, "actual_seed": 20261016, "sample_rank": rank,
            "source_line": row["source_line"], "source_id": row["source_id"],
            "source_commit": row["source_commit"],
            "source_url": "https://raw.githubusercontent.com/grantm/sudoku-exchange-puzzle-bank/"
                          + row["source_commit"] + "/hard.txt",
            "sha256": sha256(raw), "content_sha256": checksum,
            "sat_status": "NOT_CHECKED", "sat_evidence": None, "uniqueness": "unverified",
        })
    return records, seen


def apply_public_validation(project_root, public):
    evidence_path = project_root / "data/public-validation.json"
    if not evidence_path.exists():
        return False
    evidence = json.loads(evidence_path.read_bytes())
    rows = evidence["records"]
    if [row["instance_id"] for row in rows] != [row["instance_id"] for row in public]:
        raise ValueError("Public validation IDs/order differ from locked selection")
    if evidence["encoding"] != "pairwise" or evidence["method"] != "sat":
        raise ValueError("Unexpected public validation method/encoding")
    for record, checked in zip(public, rows):
        if checked["input_sha256"] != record["sha256"]:
            raise ValueError("Public validation input hash mismatch")
        result = checked["result"]
        if (result["status"] != "SAT" or not result.get("validation", {}).get("valid")
                or result.get("method") != "sat" or result.get("encoding") != "pairwise"):
            raise ValueError(f"{record['instance_id']}: production SAT validation incomplete")
        puzzle = load_puzzle(project_root / record["file"])
        assert_witness(puzzle, result["solution"])
        path = f"data/witnesses/{record['instance_id']}.json"
        raw = (project_root / path).read_bytes()
        if sha256(raw) != checked["witness_sha256"]:
            raise ValueError("Public witness hash mismatch")
        witness = json.loads(raw)
        if witness["n"] != 3 or witness["solution"] != result["solution"]:
            raise ValueError("Public witness differs from production result")
        assert_witness(puzzle, witness["solution"])
        record.update(sat_status="SAT", sat_evidence="production_solve_sat_pairwise_and_independent_checker",
                      validation_file="data/public-validation.json", witness_file=path,
                      witness_sha256=sha256(raw))
    return True


def build_outputs(project_root=ROOT, *, use_validation=True, frozen=None):
    public, seen = public_records(project_root)
    synthetic, outputs, collisions = synthetic_records(seen)
    validated = apply_public_validation(project_root, public) if use_validation else False
    if frozen is None:
        frozen = (project_root / "data/freeze.json").exists()
    if frozen and not validated:
        raise ValueError("Cannot freeze dataset without all 20 public validations")
    all_records = synthetic + public
    if len(all_records) != 80 or len({row["content_sha256"] for row in all_records}) != 80:
        raise ValueError("Expected 80 distinct instance contents")
    chosen = []
    for N in (4, 9, 16, 25):
        for density in (0.3, 0.5, 0.7):
            group = [row for row in synthetic if row["N"] == N and row["clue_density_requested"] == density]
            chosen.append(min(group, key=lambda row: (row["actual_seed"], row["instance_id"])))
    s80 = [row["instance_id"] for row in all_records]
    b16 = [row["instance_id"] for row in chosen] + FIRST_FOUR
    c10 = [row["instance_id"] for row in chosen if row["N"] in (4, 9)] + FIRST_FOUR
    if len(b16) != 16 or len(c10) != 10 or not set(c10) < set(b16) < set(s80):
        raise ValueError("Scope membership failed")
    state = {"frozen": frozen, "public_sat_validation": "pass_all_20" if validated else "pending_DATA-007",
             "note": "Dataset-only freeze; code/benchmark not frozen" if frozen else
                     "Pre-measurement candidate lists; no final dataset freeze"}
    outputs["data/manifest.json"] = json_bytes({**state, "records": all_records})
    outputs["data/scopes.json"] = json_bytes({**state, "selection_rule":
        "Synthetic: min(actual_seed, instance_id) per size/density; public: first four locked samples",
        "S80": s80, "B16": b16, "C10": c10})
    outputs["diagnostics/dataset/generation.json"] = json_bytes({
        **state, "python_version": sys.version.split()[0],
        "rng": "random.Random(f'{n}:{density_percent}:{actual_seed}')",
        "clue_rounding": "(density_percent*N*N+50)//100 = floor(ratio*N*N+0.5)",
        "synthetic_count": 60, "public_count": 20,
        "synthetic_full_and_masked_witness_checker": "pass_all_60",
        "duplicate_rejections": collisions,
        "public_selection_sha256": SELECTION_HASH,
        "public_normalization_index_sha256": PUBLIC_INDEX_HASH,
    })
    return outputs


def freeze_record(project_root, outputs):
    files = {name: sha256(raw) for name, raw in outputs.items()}
    manifest = json.loads(outputs["data/manifest.json"])
    for row in manifest["records"]:
        for key in ("file", "witness_file"):
            name = row[key]
            files[name] = sha256((project_root / name).read_bytes())
    for name in ("data/public-validation.json", "diagnostics/public-selection.csv",
                 "diagnostics/public-normalization/index.json", "data/source/sudoku-exchange-hard.txt",
                 "data/source/sudoku-exchange-LICENSE.txt", "data/source/sudoku-exchange-README.md"):
        files[name] = sha256((project_root / name).read_bytes())
    scopes = json.loads(outputs["data/scopes.json"])
    return json_bytes({"frozen": True, "scope": "dataset only; not code or RUN-012 benchmark freeze",
                       "uniqueness": "unverified", "files_sha256": dict(sorted(files.items())),
                       "S80": scopes["S80"], "B16": scopes["B16"], "C10": scopes["C10"]})


def finalize_data(project_root=ROOT):
    """Only promote known generated metadata after all production validations pass."""
    if (project_root / "data/freeze.json").exists():
        return prepare(project_root, check=True)
    old = build_outputs(project_root, use_validation=False, frozen=False)
    new = build_outputs(project_root, frozen=True)
    for name, raw in old.items():
        if (project_root / name).read_bytes() != raw:
            raise ValueError(f"Cannot promote modified provisional output: {name}")
    lock = freeze_record(project_root, new)
    # Only the three generated metadata files change; inputs/witnesses stay byte-identical.
    for name, raw in new.items():
        if raw != old[name]:
            (project_root / name).write_bytes(raw)
    with (project_root / "data/freeze.json").open("xb") as stream:
        stream.write(lock)
    return prepare(project_root, check=True)


def prepare(project_root=ROOT, check=False):
    outputs = build_outputs(project_root)
    # Complete preflight: preserve all existing files with different bytes.
    for relative, raw in outputs.items():
        path = project_root / relative
        if path.exists() and path.read_bytes() != raw:
            raise ValueError(f"Refusing to overwrite different bytes: {path}")
        if check and not path.is_file():
            raise ValueError(f"Missing generated file: {path}")
    for relative, raw in outputs.items():
        path = project_root / relative
        if not check and not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(raw)
    for row in json.loads(outputs["data/manifest.json"])["records"]:
        puzzle = load_puzzle(project_root / row["file"])
        if row["source"] == "synthetic":
            witness = json.loads((project_root / row["witness_file"]).read_bytes())["solution"]
            assert_witness(puzzle, witness)
    freeze_path = project_root / "data/freeze.json"
    if freeze_path.exists() and freeze_path.read_bytes() != freeze_record(project_root, outputs):
        raise ValueError("Frozen dataset checksum/ID list differs")
    print("PASS: 60 synthetic + 20 unchanged public; parser, checker witnesses, checksums, S80/B16/C10=80/16/10")
    print("DATASET FROZEN; code/benchmark not frozen; uniqueness unverified" if freeze_path.exists()
          else "NOT FROZEN; see manifest public SAT validation state; uniqueness unverified")
    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Regenerate in memory and compare; no writes")
    args = parser.parse_args()
    prepare(check=args.check)

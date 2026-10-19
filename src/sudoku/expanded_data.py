"""Version-2 Sudoku data construction. No benchmark or v1 dataset mutation.

Public helpers return JSON-compatible records (except explicit grid/bytes helpers).
Real generation creates both disjoint phases; smoke uses only artificial witnesses.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from sudoku.model import Puzzle, load_puzzle, parse_puzzle
from sudoku.validation import check_solution

MASTER_SEED = 20261019
COMMIT = "d8c8ebaee0c08c412cfba96af1923dfa61c83317"
GROUPS = ("easy", "medium", "hard", "diabolical")
FAMILIES = ("permutation", "row_cycle")
PERCENTS = (20, 30, 40, 50, 60)
GENERATOR_VERSION = "expanded-data-v2.1"
SOURCE_BASE = f"https://raw.githubusercontent.com/grantm/sudoku-exchange-puzzle-bank/{COMMIT}/"
PINNED_KNOWN_HASHES = {
    "hard.txt": "abcff1512411e601abd5e861c60add5be5d877739b6faa249ee86960f5ad85e9",
    "LICENSE.txt": "0f3ab60214dbfacca972a724efd3b0b3248b65b02d9874e95ed3f412f232c385",
    "README.md": "494477eae319136793973e81d74ace35dcea91e3dbb40de1f53bc4a9ef03117e",
}
CHECKER = Path(__file__).with_name("validation.py")


class DataError(ValueError):
    """Dataset gate failure; never a request to reduce quotas or replace samples."""


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def canonical_puzzle_bytes(n: int, grid) -> bytes:
    puzzle = Puzzle(n, grid)
    return json_bytes({"n": puzzle.n, "grid": [list(row) for row in puzzle.grid]})


def content_sha256(n: int, grid) -> str:
    return sha256(canonical_puzzle_bytes(n, grid))


def rank(label: str, item: str) -> str:
    return sha256(f"{MASTER_SEED}|{label}|{item}".encode("utf-8"))


def derived_seed(label: str, item: str = "") -> str:
    return str(int(rank(label, item)[:16], 16))


def ranked(items, label, key=str):
    return sorted(items, key=lambda item: (rank(label, key(item)), key(item)))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def contained_path(directory, relative):
    base = Path(directory).resolve()
    if not isinstance(relative, str) or "\\" in relative or ":" in relative:
        raise DataError("Dataset path must be a relative POSIX path")
    name = Path(relative)
    if name.is_absolute() or ".." in name.parts:
        raise DataError("Dataset path traversal rejected")
    path = (base / name).resolve()
    if not path.is_relative_to(base) or path == base:
        raise DataError("Dataset path escapes directory")
    return path


def _check(n, grid, solution, checked_utc=None):
    validation = check_solution(Puzzle(n, grid), solution)
    if not validation.valid:
        raise DataError(f"Independent checker rejected witness: {validation.message}")
    return {"valid": True, "checker_code_sha256": sha256(CHECKER.read_bytes()),
            "checked_utc": checked_utc or datetime.now(timezone.utc).isoformat()}


def pattern_grid(n):
    if type(n) is not int or n < 2:
        raise DataError("n must be an exact integer >=2")
    N = n * n
    grid = [[(n * (r % n) + r // n + c) % N + 1 for c in range(N)] for r in range(N)]
    _check(n, grid, grid)
    return grid


def permute_grid(n, base, label):
    _check(n, base, base)
    N = n * n
    values = ranked(range(1, N + 1), label + "|values")

    def order(axis):
        groups = ranked(range(n), label + "|" + axis + "|groups")
        return [g * n + offset for g in groups
                for offset in ranked(range(n), label + f"|{axis}|within|{g}")]

    rows, columns = order("rows"), order("columns")
    result = [[values[base[r][c] - 1] for c in columns] for r in rows]
    _check(n, result, result)
    return result


def whole_row_cycles(n, grid, row_a, row_b):
    """Return disjoint proper cycles as A-values/columns; no partial-cycle trade."""
    N = n * n
    _check(n, grid, grid)
    if not (0 <= row_a < N and 0 <= row_b < N and row_a != row_b and row_a // n == row_b // n):
        raise DataError("Trade requires distinct rows in the same band")
    mapping = {grid[row_a][c]: grid[row_b][c] for c in range(N)}
    positions = {value: c for c, value in enumerate(grid[row_a])}
    seen, cycles = set(), []
    for start in sorted(mapping):
        if start in seen:
            continue
        values, value = [], start
        while value not in seen:
            seen.add(value)
            values.append(value)
            value = mapping[value]
        if value != start:
            raise DataError("Rows do not induce a permutation cycle")
        if 2 <= len(values) < N:
            cycles.append({"values": values, "columns": [positions[v] for v in values]})
    return cycles


def trade_row_cycle(n, grid, row_a, row_b, columns):
    valid = whole_row_cycles(n, grid, row_a, row_b)
    if len(columns) != len(set(columns)) or not any(set(c["columns"]) == set(columns) for c in valid):
        raise DataError("Trade must select exactly one complete proper cycle")
    result = [list(row) for row in grid]
    for c in columns:
        result[row_a][c], result[row_b][c] = result[row_b][c], result[row_a][c]
    _check(n, result, result)
    return result


def generate_root(n, family, phase, ordinal, base_grid, seen_roots=None, log=None,
                  *, max_attempts=10000, checked_utc=None):
    if family not in FAMILIES or phase not in ("main", "pilot"):
        raise DataError("Unknown root family/phase")
    seen_roots = set() if seen_roots is None else seen_roots
    log = [] if log is None else log
    N = n * n
    root_id = f"e2-{phase}-N{N}-{family}-r{ordinal:06d}"
    for attempt in range(max_attempts):
        label = f"root|{phase}|N{N}|{family}|{root_id}|{attempt}"
        base = permute_grid(n, base_grid, label)
        grid, trade = base, None
        if family == "row_cycle":
            pairs = [(a, b) for a in range(N) for b in range(a + 1, N) if a // n == b // n]
            options = []
            for a, b in pairs:
                for cycle in whole_row_cycles(n, base, a, b):
                    options.append({"row_a": a, "row_b": b, **cycle})
            if not options:
                log.append({"kind": "root", "root_id": root_id, "seed_label": label,
                            "derived_seed": derived_seed(label), "resample_index": attempt,
                            "reason": "no_proper_cycle"})
                continue
            trade = ranked(options, label + "|cycle", key=lambda x: json_bytes(x).decode())[0]
            trade["base_content_sha256"] = content_sha256(n, base)
            grid = trade_row_cycle(n, base, trade["row_a"], trade["row_b"], trade["columns"])
        digest = content_sha256(n, grid)
        if digest in seen_roots:
            log.append({"kind": "root", "root_id": root_id, "seed_label": label,
                        "derived_seed": derived_seed(label), "resample_index": attempt,
                        "reason": "duplicate_root", "content_sha256": digest})
            continue
        seen_roots.add(digest)
        return {"root_id": root_id, "n": n, "N": N, "family": family,
                "grid": grid, "root_content_sha256": digest,
                "base_content_sha256": content_sha256(n, base_grid),
                "seed_label": label, "derived_seed": derived_seed(label),
                "resample_index": attempt, "trade": trade,
                "witness_validation": _check(n, grid, grid, checked_utc)}
    raise DataError(f"Root slot exhausted {max_attempts} attempts: {root_id}")


def generate_mask(root, percent, phase, seen, log, *, max_attempts=10000):
    if type(percent) is not int or percent not in PERCENTS:
        raise DataError("Synthetic clue percent must be 20/30/40/50/60")
    n, N = root["n"], root["N"]
    count = (percent * N * N + 50) // 100
    for attempt in range(max_attempts):
        label = f"mask|{phase}|{root['root_id']}|{percent}|{attempt}"
        keep = set(ranked(range(N * N), label)[:count])
        grid = [[root["grid"][r][c] if r * N + c in keep else 0 for c in range(N)] for r in range(N)]
        digest = content_sha256(n, grid)
        if digest in seen:
            log.append({"kind": "mask", "root_id": root["root_id"], "clue_percent_requested": percent,
                        "seed_label": label, "derived_seed": derived_seed(label),
                        "resample_index": attempt, "reason": "duplicate_puzzle", "content_sha256": digest})
            continue
        seen.add(digest)
        return {"grid": grid, "content_sha256": digest, "actual_clues": count,
                "clue_percent_requested": percent, "seed_label": label,
                "derived_seed": derived_seed(label), "resample_index": attempt}
    raise DataError(f"Mask exhausted {max_attempts} attempts: {root['root_id']}/{percent}")


def iter_public_file(path, group, *, source_url=None):
    """Streaming parser: fail on malformed lines, retain original line/rating provenance."""
    if group not in GROUPS:
        raise DataError("Unknown public group")
    digest = sha256(Path(path).read_bytes())
    with Path(path).open(encoding="ascii", newline="") as stream:
        for line_number, line in enumerate(stream, 1):
            fields = line.split()
            if len(fields) != 3 or not re.fullmatch(r"[0-9a-f]{12}", fields[0]) or not re.fullmatch(r"[0-9]{81}", fields[1]):
                raise DataError(f"Malformed public record: {group}:{line_number}")
            if not re.fullmatch(r"\d+\.\d+", fields[2]) or not math.isfinite(float(fields[2])):
                raise DataError(f"Invalid public rating: {group}:{line_number}")
            grid = [[int(x) for x in fields[1][start:start + 9]] for start in range(0, 81, 9)]
            parse_puzzle({"n": 3, "grid": grid})
            yield {"n": 3, "N": 9, "grid": grid, "content_sha256": content_sha256(3, grid),
                   "source_group": group, "source_record_id": fields[0], "source_line": line_number,
                   "source_url": source_url or SOURCE_BASE + group + ".txt",
                   "source_file_sha256": digest, "rating_original": fields[2],
                   "rating_value": float(fields[2])}


def parse_public_file(path, group, *, source_url=None):
    """Materialize a small source fixture. Real import uses iter_public_file."""
    return list(iter_public_file(path, group, source_url=source_url))


def select_public(sources, old_hashes, *, main_per_group=2500, pilot_per_group=2):
    """First ownership precedes ranking. Quota overrides are fixture-only callers."""
    owned = {digest: {"source": "old_S80"} for digest in old_hashes}
    selected = {"main": [], "pilot": []}
    logs = []
    for group in GROUPS:
        heap = []
        supply, previous_line = 0, 0
        rows = sources[group]
        if isinstance(rows, (list, tuple)):
            rows = sorted(rows, key=lambda r: r["source_line"])
        for row in rows:
            if row["source_line"] <= previous_line or row["source_group"] != group:
                raise DataError("Public sources must scan ascending original lines within their group")
            previous_line = row["source_line"]
            digest = row["content_sha256"]
            origin = {"source_group": group, "source_line": row["source_line"],
                      "source_record_id": row["source_record_id"], "source_url": row["source_url"]}
            if digest in owned:
                logs.append({"kind": "public", "reason": "duplicate_or_old", "content_sha256": digest,
                             "owner": owned[digest], "rejected": origin})
            else:
                owned[digest] = origin
                supply += 1
                entry = (-int(rank(f"public|{group}", digest), 16), -int(digest, 16), row)
                capacity = main_per_group + pilot_per_group
                if len(heap) < capacity:
                    heapq.heappush(heap, entry)
                elif entry[:2] > heap[0][:2]:
                    heapq.heapreplace(heap, entry)
        ordered = ranked([item[2] for item in heap], f"public|{group}", key=lambda r: r["content_sha256"])
        if supply < main_per_group + pilot_per_group:
            raise DataError(f"Insufficient unique supply for {group}: {supply}")
        selected["main"].extend(ordered[:main_per_group])
        selected["pilot"].extend(ordered[main_per_group:main_per_group + pilot_per_group])
    return selected, logs


def cache_sources(cache_dir):
    """Fetch pinned public source bytes only; never select or solve any instance."""
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    old_receipt = read_json(cache / "receipt.json") if (cache / "receipt.json").exists() else None
    if old_receipt and old_receipt.get("source_commit") != COMMIT:
        raise DataError("Cached receipt has a different source commit")
    known = {row["file"]: row for row in old_receipt["files"]} if old_receipt else {}
    receipts = []
    for name in [g + ".txt" for g in GROUPS] + ["LICENSE.txt", "README.md"]:
        path = cache / name
        if path.exists() and (name not in known or sha256(path.read_bytes()) != known[name]["sha256"]):
            raise DataError("Existing cache must match an established receipt; use a new empty cache")
        if not path.exists():
            request = Request(SOURCE_BASE + name, headers={"User-Agent": "Sudoku-BTL1-expanded-data"})
            with urlopen(request, timeout=120) as response:
                raw = response.read()
            # Never expose a partially downloaded file under the pinned filename.
            with path.open("xb") as stream:
                stream.write(raw)
        digest = sha256(path.read_bytes())
        if name in PINNED_KNOWN_HASHES and digest != PINNED_KNOWN_HASHES[name]:
            raise DataError(f"Pinned source/permission evidence hash differs: {name}")
        receipts.append({"file": name, "url": SOURCE_BASE + name, "sha256": digest})
    receipt = {"source_commit": COMMIT, "files": receipts}
    receipt_path = cache / "receipt.json"
    raw = json_bytes(receipt)
    if receipt_path.exists() and receipt_path.read_bytes() != raw:
        raise DataError("Cached source receipt differs; do not silently refresh pinned data")
    if not receipt_path.exists():
        receipt_path.write_bytes(raw)
    return receipt


def old_dataset_exclusions(project_root):
    project_root = Path(project_root)
    manifest = read_json(project_root / "data/manifest.json")
    freeze = (project_root / "data/freeze.json").read_bytes()
    hashes, bases = set(), {}
    for row in manifest["records"]:
        puzzle = load_puzzle(project_root / row["file"])
        hashes.add(content_sha256(puzzle.n, puzzle.grid))
        if puzzle.N in (16, 25) and puzzle.N not in bases:
            payload = read_json(project_root / row["witness_file"])
            grid = payload.get("solution", payload.get("grid"))
            _check(puzzle.n, puzzle.grid, grid)
            bases[puzzle.N] = {"grid": grid, "file": row["witness_file"],
                               "sha256": sha256((project_root / row["witness_file"]).read_bytes())}
    if len(hashes) != 80 or set(bases) != {16, 25}:
        raise DataError("Expected preserved S80 and base witnesses for N16/N25")
    return hashes, bases, sha256(freeze)


def _strata(records):
    return dict(sorted(Counter(f"N{r['N']}|{r['source_group']}|{r['family']}|{r['clue_percent_requested']}"
                               for r in records).items()))


def assign_batches(records, phase, *, batches=100):
    """Keep all five masks together. Main real quotas are verified separately."""
    if phase == "pilot":
        batches = 1
    slots = [[] for _ in range(batches)]
    for group in GROUPS:
        rows = ranked([r for r in records if r["source_group"] == group],
                      f"batch|public|{group}", key=lambda r: r["instance_id"])
        if len(rows) % batches:
            raise DataError("Public counts cannot divide evenly into batches")
        width = len(rows) // batches
        for b in range(batches):
            slots[b].extend(rows[b * width:(b + 1) * width])
    for N in (16, 25):
        for family in FAMILIES:
            rows = [r for r in records if r["N"] == N and r["family"] == family]
            roots = ranked({r["root_id"] for r in rows}, f"batch|{N}|{family}")
            if len(roots) % batches:
                raise DataError("Roots cannot divide evenly into batches")
            width = len(roots) // batches
            by_root = {root: sorted([r for r in rows if r["root_id"] == root],
                                    key=lambda r: r["clue_percent_requested"]) for root in roots}
            for root, children in by_root.items():
                if [r["clue_percent_requested"] for r in children] != list(PERCENTS):
                    raise DataError(f"Root does not have its five masks: {root}")
            for b in range(batches):
                for root in roots[b * width:(b + 1) * width]:
                    slots[b].extend(by_root[root])
    output = []
    for ordinal, rows in enumerate(slots, 1):
        batch_id = f"b{ordinal:03d}" if phase == "main" else "p001"
        for row in rows:
            row["batch_id"] = batch_id
        output.append({"batch_id": batch_id, "ordinal": ordinal,
                       "instance_ids": [r["instance_id"] for r in rows],
                       "expected_stratum_counts": _strata(rows)})
    flat = [instance for batch in output for instance in batch["instance_ids"]]
    if len(flat) != len(records) or len(set(flat)) != len(flat):
        raise DataError("Batch assignment lost or duplicated instances")
    return output


def _jsonl(rows):
    return b"".join(json_bytes(row) for row in rows)


def _write_new(directory, relative, raw):
    path = contained_path(directory, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def _record(directory, dataset_id, phase, n, grid, solution, *, public=None,
            root=None, mask=None, checked_utc=None, artificial=False, pending_public=False):
    N = n * n
    raw = canonical_puzzle_bytes(n, grid)
    digest = sha256(raw)
    instance_id = f"e2-{phase}-N{N}-{digest}"
    if pending_public and (public is None or solution is not None):
        raise DataError("Only public input staging can omit a solution")
    witness = None if pending_public else canonical_puzzle_bytes(n, solution)
    validation = None if pending_public else _check(n, grid, solution, checked_utc)
    input_file, witness_file = f"inputs/{instance_id}.json", f"witnesses/{instance_id}.json"
    _write_new(directory, input_file, raw)
    if witness is not None:
        _write_new(directory, witness_file, witness)
    label = f"public|{public['source_group']}" if public else mask["seed_label"]
    result = {"schema_version": 2, "dataset_id": dataset_id, "instance_id": instance_id,
              "batch_id": None, "phase": phase, "n": n, "N": N,
              "input_file": input_file, "input_sha256": sha256(raw), "content_sha256": digest,
              "source": "sudoku_exchange" if public else "synthetic",
              "source_group": public["source_group"] if public else None,
              "source_record_id": public["source_record_id"] if public else None,
              "source_line": public["source_line"] if public else None,
              "source_url": public["source_url"] if public else None,
              "source_file_sha256": public["source_file_sha256"] if public else None,
              "rating_original": public["rating_original"] if public else None,
              "rating_value": public["rating_value"] if public else None,
              "family": root["family"] if root else None, "root_id": root["root_id"] if root else None,
              "root_content_sha256": root["root_content_sha256"] if root else None,
              "clue_percent_requested": mask["clue_percent_requested"] if mask else None,
              "actual_clues": Puzzle(n, grid).clue_count, "master_seed": MASTER_SEED,
              "derived_seed": derived_seed(label, digest) if public else mask["derived_seed"],
              "seed_label": label, "resample_index": mask["resample_index"] if mask else 0,
              "witness_file": None if pending_public else witness_file,
              "witness_sha256": None if pending_public else sha256(witness),
              "witness_content_sha256": None if pending_public else content_sha256(n, solution),
              "witness_validation": validation,
              "sat_evidence": None if pending_public else
                              ("checked_solver_witness" if public and not artificial else "checked_generator_witness"),
              "uniqueness": "source_claimed" if public and not artificial else "unverified",
              "uniqueness_reference": SOURCE_BASE + "README.md" if public and not artificial else None}
    return result


def _save_generation_failure(directory, logs, records, slot, error):
    """Retain failed-slot provenance/attempts; never publish a ready/frozen dataset."""
    _write_new(directory, "generation-failure.json", json_bytes({
        "schema_version": 2, "state": "INCOMPLETE", "frozen": False,
        "slot": slot, "error": f"{type(error).__name__}: {error}",
        "replacement_selected": False, "completed_records": len(records)}))
    _write_new(directory, "dedup.jsonl", _jsonl(logs))
    _write_new(directory, "manifest.partial.jsonl", _jsonl(records))


def _assemble(output_dir, selected, bases, old_hashes, old_freeze_hash, *, artificial,
              main_roots, main_batches, public_witness, provenance, dedup_log, checked_utc=None,
              inputs_only=False):
    """Private quota injection is restricted to explicitly artificial construction."""
    if not artificial and (main_roots != {16: 500, 25: 100} or main_batches != 100):
        raise DataError("Real dataset quotas cannot be reduced")
    output_dir = Path(output_dir)
    ids = {phase: (f"artificial-expanded-{phase}-v2.1" if artificial else
                  ("expanded-20261019-v2" if phase == "main" else "expanded-pilot-20261019-v2"))
           for phase in ("main", "pilot")}
    directories = {phase: output_dir / identity for phase, identity in ids.items()}
    if any(path.exists() for path in directories.values()):
        raise DataError("Dataset destinations must be new; never replace a frozen dataset")
    seen = set(old_hashes)
    for phase in ("main", "pilot"):
        for row in selected[phase]:
            if row["content_sha256"] in seen:
                raise DataError("Selected public duplicate across old/main/pilot")
            seen.add(row["content_sha256"])
    seen_roots, phases = set(), {}
    for phase in ("main", "pilot"):
        directory, dataset_id = directories[phase], ids[phase]
        directory.mkdir(parents=True)
        records, roots, logs = [], [], [dict(row) for row in dedup_log]
        # Input IDs have already been selected. Witness failure aborts, not resamples.
        for public in selected[phase]:
            try:
                solution = None if inputs_only else public_witness(public)
                records.append(_record(directory, dataset_id, phase, 3, public["grid"], solution,
                                       public=public, artificial=artificial, checked_utc=checked_utc,
                                       pending_public=inputs_only))
            except Exception as exc:
                _save_generation_failure(directory, logs, records,
                                         {"phase": phase, "source_group": public["source_group"],
                                          "source_line": public["source_line"],
                                          "content_sha256": public["content_sha256"]}, exc)
                raise
        for N in (16, 25):
            n = math.isqrt(N)
            for family in FAMILIES:
                root_count = main_roots[N] if phase == "main" else 1
                for ordinal in range(1, root_count + 1):
                    try:
                        root = generate_root(n, family, phase, ordinal, bases[N]["grid"], seen_roots,
                                             logs, checked_utc=checked_utc)
                    except DataError as exc:
                        _save_generation_failure(directory, logs, records,
                                                 {"phase": phase, "N": N, "family": family,
                                                  "root_ordinal": ordinal}, exc)
                        raise
                    root_file = f"roots/{root['root_id']}.json"
                    raw = canonical_puzzle_bytes(n, root["grid"])
                    _write_new(directory, root_file, raw)
                    root_meta = {k: v for k, v in root.items() if k != "grid"}
                    root_meta.update(grid_file=root_file, grid_sha256=sha256(raw),
                                     resample_log_file="dedup.jsonl", base_grid_file=f"sources/base-N{N}.json")
                    roots.append(root_meta)
                    for percent in PERCENTS:
                        try:
                            mask = generate_mask(root, percent, phase, seen, logs)
                        except DataError as exc:
                            _save_generation_failure(directory, logs, records,
                                                     {"phase": phase, "root_id": root["root_id"],
                                                      "clue_percent_requested": percent}, exc)
                            raise
                        records.append(_record(directory, dataset_id, phase, n, mask["grid"], root["grid"],
                                               root=root, mask=mask, checked_utc=checked_utc))
        batches = assign_batches(records, phase, batches=main_batches)
        target = {"9": len(selected[phase]),
                  "16": (main_roots[16] if phase == "main" else 1) * 2 * 5,
                  "25": (main_roots[25] if phase == "main" else 1) * 2 * 5}
        if not artificial:
            required = {"9": 10000, "16": 5000, "25": 1000} if phase == "main" else {"9": 8, "16": 10, "25": 10}
            if target != required:
                raise DataError("Real public/synthetic quotas differ")
        metadata = {"schema_version": 2, "dataset_id": dataset_id, "phase": phase,
                    "artificial": artificial, "master_seed": MASTER_SEED,
                    "generator_version": GENERATOR_VERSION, "canonicalization": "sudoku-json-v2",
                    "frozen": False, "target_counts": target,
                    "actual_counts": dict(sorted(Counter(str(row["N"]) for row in records).items())),
                    "selection_rule": "first-owner dedup, rank(public|group), then frozen balanced root-local batches",
                    "source_commit": COMMIT if not artificial else None,
                    "old_dataset_freeze_sha256": old_freeze_hash,
                    "expected_batches": main_batches if phase == "main" else 1,
                    "fixture_quotas": {"main_roots_per_family": {str(k): v for k, v in main_roots.items()},
                                       "main_batches": main_batches, "instances": len(records),
                                       "batches": len(batches)} if artificial else None}
        if inputs_only:
            metadata.update(state="DRAFT_INPUTS", public_witness_pending=len(selected[phase]),
                            all_witness_check_pass=False, eligible_for_runner=False)
        _write_new(directory, "dataset.json", json_bytes(metadata))
        _write_new(directory, "manifest.jsonl", _jsonl(records))
        _write_new(directory, "roots.jsonl", _jsonl(roots))
        _write_new(directory, "dedup.jsonl", _jsonl(logs))
        _write_new(directory, "batches.json", json_bytes({"schema_version": 2, "dataset_id": dataset_id,
                                                        "batches": batches}))
        phases[phase] = {"directory": directory, "records": records, "roots": roots}
    for phase, info in phases.items():
        directory = info["directory"]
        other = phases["pilot" if phase == "main" else "main"]
        prov = {**provenance, "schema_version": 2, "artificial": artificial,
                "rng_implementation": "No PRNG draws; SHA256 rank ordering only",
                "rng_version": "sha256-rank-v2", "rng_draws": 0,
                "old_content_sha256": sorted(old_hashes),
                "other_phase_content_sha256": sorted(r["content_sha256"] for r in other["records"]),
                "other_phase_root_sha256": sorted(r["root_content_sha256"] for r in other["roots"]),
                "base_sources": {str(N): {k: v for k, v in bases[N].items() if k != "grid"} for N in (16, 25)}}
        for N in (16, 25):
            _write_new(directory, f"sources/base-N{N}.json", canonical_puzzle_bytes(math.isqrt(N), bases[N]["grid"]))
        for source in provenance.get("sources", []):
            raw = Path(source["cache_file"]).read_bytes()
            if sha256(raw) != source["sha256"]:
                raise DataError("Source cache changed during construction")
            _write_new(directory, source["dataset_file"], raw)
        # Cache filesystem locations are operational; dataset provenance uses contained paths.
        prov["sources"] = [{k: v for k, v in source.items() if k != "cache_file"}
                           for source in prov.get("sources", [])]
        _write_new(directory, "provenance.json", json_bytes(prov))
        if inputs_only:
            _seal_inputs(directory)
        else:
            freeze_dataset(directory)
    return {phase: str(info["directory"].resolve()) for phase, info in phases.items()}


def generate_datasets(project_root, output_dir, cache_dir):
    """Full generation/witness tool. Call only after coordinator releases EXP-05 QA."""
    from sudoku.sat import prepare_backend, solve_sat

    receipt = cache_sources(cache_dir)
    sources = {group: iter_public_file(Path(cache_dir) / (group + ".txt"), group) for group in GROUPS}
    old_hashes, bases, old_freeze = old_dataset_exclusions(project_root)
    selected, log = select_public(sources, old_hashes)
    prepare_backend()

    def witness(public):
        result = solve_sat(Puzzle(3, public["grid"]), "pairwise", cutoff_seconds=10.0)
        if result.status.value != "SAT" or result.validation is None or not result.validation.valid:
            raise DataError(f"Selected public witness failed ({result.status.value}); no replacement: "
                            f"{public['source_group']}:{public['source_line']}")
        return [list(row) for row in result.solution]

    provenance = {"source_commit": COMMIT, "parser_version": GENERATOR_VERSION,
                  "public_selection": {"main_per_group": 2500, "reserved_pilot_per_group": 2},
                  "group_order": list(GROUPS), "public_uniqueness": "source_claimed_not_self_proven",
                  "uniqueness_reference": SOURCE_BASE + "README.md",
                  "license_reference": "sources/LICENSE.txt", "attribution_reference": "sources/README.md",
                  "witness_solver": {"method": "sat", "encoding": "pairwise", "engine": "Glucose3",
                                     "cutoff_seconds": 10.0,
                                     "adapter_sha256": sha256(Path(__file__).with_name("sat.py").read_bytes())},
                  "sources": [{**row, "cache_file": str(Path(cache_dir) / row["file"]),
                               "dataset_file": "sources/" + row["file"]} for row in receipt["files"]]}
    return _assemble(output_dir, selected, bases, old_hashes, old_freeze, artificial=False,
                     main_roots={16: 500, 25: 100}, main_batches=100, public_witness=witness,
                     provenance=provenance, dedup_log=log)


def _read_jsonl(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    return [json.loads(line) for line in text.splitlines()]


def verify_dataset(directory, *, require_frozen=True, _inputs_only=False):
    """Data-producer self-check, not SAT07's validate_expanded_dataset API."""
    directory = Path(directory)
    meta = read_json(directory / "dataset.json")
    if meta["schema_version"] != 2 or meta["canonicalization"] != "sudoku-json-v2":
        raise DataError("Dataset version/canonicalization mismatch")
    if meta.get("state") == "DRAFT_INPUTS" and not _inputs_only:
        raise DataError("DRAFT_INPUTS is not a witnessed/frozen dataset; use verify-inputs")
    if _inputs_only and (require_frozen or meta.get("state") != "DRAFT_INPUTS" or meta["frozen"] is not False
                         or meta.get("eligible_for_runner") is not False):
        raise DataError("Input-only verification requires an explicit unfrozen DRAFT")
    records = _read_jsonl(directory / "manifest.jsonl")
    roots = _read_jsonl(directory / "roots.jsonl")
    provenance = read_json(directory / "provenance.json")
    batches = read_json(directory / "batches.json")["batches"]
    excluded = set(provenance["old_content_sha256"]) | set(provenance["other_phase_content_sha256"])
    seen, root_hashes, by_id, root_children = set(), set(), {}, {}
    pending = 0
    phase = meta["phase"]
    for root in roots:
        grid = load_puzzle(contained_path(directory, root["grid_file"]))
        _check(grid.n, grid.grid, grid.grid)
        raw = contained_path(directory, root["grid_file"]).read_bytes()
        digest = content_sha256(grid.n, grid.grid)
        if sha256(raw) != root["grid_sha256"] or digest != root["root_content_sha256"]:
            raise DataError("Root hash mismatch")
        if digest in root_hashes or digest in provenance["other_phase_root_sha256"] or root["root_id"] in by_id:
            raise DataError("Duplicate root")
        root_hashes.add(digest)
        by_id[root["root_id"]] = root
        base = load_puzzle(contained_path(directory, root["base_grid_file"]))
        transformed = permute_grid(grid.n, base.grid, root["seed_label"])
        if root["family"] == "row_cycle":
            trade = root["trade"]
            if content_sha256(grid.n, transformed) != trade["base_content_sha256"]:
                raise DataError("Trade base hash mismatch")
            cycles = whole_row_cycles(grid.n, transformed, trade["row_a"], trade["row_b"])
            if not any(c["values"] == trade["values"] and c["columns"] == trade["columns"] for c in cycles):
                raise DataError("Cycle provenance does not match a whole proper cycle")
            transformed = trade_row_cycle(grid.n, transformed, trade["row_a"], trade["row_b"], trade["columns"])
        elif root["family"] != "permutation":
            raise DataError("Unexpected root family")
        if content_sha256(grid.n, transformed) != digest or root["derived_seed"] != derived_seed(root["seed_label"]):
            raise DataError("Root transformation/seed not reproducible")
    for row in records:
        if row["schema_version"] != 2 or row["dataset_id"] != meta["dataset_id"] or row["phase"] != phase:
            raise DataError("Manifest identity/version mismatch")
        path = contained_path(directory, row["input_file"])
        puzzle = load_puzzle(path)
        digest = content_sha256(puzzle.n, puzzle.grid)
        if digest in seen or digest in excluded:
            raise DataError("Duplicate/old/cross-phase input")
        seen.add(digest)
        if row["instance_id"] != f"e2-{phase}-N{puzzle.N}-{digest}":
            raise DataError("Content-derived instance ID mismatch")
        if (sha256(path.read_bytes()) != row["input_sha256"] or digest != row["content_sha256"]
                or row["n"] != puzzle.n or row["N"] != puzzle.N or row["actual_clues"] != puzzle.clue_count):
            raise DataError("Input hash/shape/clue metadata mismatch")
        if _inputs_only and row["source"] == "sudoku_exchange":
            missing = ("witness_file", "witness_sha256", "witness_content_sha256", "witness_validation", "sat_evidence")
            if any(row.get(key) is not None for key in missing):
                raise DataError("Staged public inputs cannot claim witness/SAT validation")
            if (row["root_id"] is not None or row["family"] is not None or row["source_group"] not in GROUPS
                    or puzzle.n != 3 or row["clue_percent_requested"] is not None):
                raise DataError("Staged public metadata differs")
            label = f"public|{row['source_group']}"
            if (row["seed_label"] != label or row["derived_seed"] != derived_seed(label, digest)
                    or row["resample_index"] != 0):
                raise DataError("Staged public selection seed differs")
            pending += 1
            continue
        witness_path = contained_path(directory, row["witness_file"])
        witness = load_puzzle(witness_path)
        _check(puzzle.n, puzzle.grid, witness.grid)
        if (sha256(witness_path.read_bytes()) != row["witness_sha256"]
                or content_sha256(witness.n, witness.grid) != row["witness_content_sha256"]):
            raise DataError("Witness hash mismatch")
        if row["witness_validation"]["valid"] is not True:
            raise DataError("Missing independent witness validation")
        if row["root_id"] is not None:
            root = by_id[row["root_id"]]
            if (row["family"] != root["family"] or row["root_content_sha256"] != root["root_content_sha256"]
                    or row["witness_content_sha256"] != root["root_content_sha256"]):
                raise DataError("Mask/root/witness relationship mismatch")
            p = row["clue_percent_requested"]
            count = (p * puzzle.N * puzzle.N + 50) // 100
            label = f"mask|{phase}|{root['root_id']}|{p}|{row['resample_index']}"
            if p not in PERCENTS or row["actual_clues"] != count or row["seed_label"] != label:
                raise DataError("Mask quota/seed label mismatch")
            keep = set(ranked(range(puzzle.N * puzzle.N), label)[:count])
            expected = [[witness.grid[r][c] if r * puzzle.N + c in keep else 0
                         for c in range(puzzle.N)] for r in range(puzzle.N)]
            if digest != content_sha256(puzzle.n, expected) or row["derived_seed"] != derived_seed(label):
                raise DataError("Mask not reproducible")
            root_children.setdefault(row["root_id"], []).append(row)
        elif row["source"] != "sudoku_exchange" or row["source_group"] not in GROUPS:
            raise DataError("Public provenance mismatch")
    if set(root_children) != set(by_id):
        raise DataError("Root without masks or mask without root")
    for root_id, children in root_children.items():
        if sorted(r["clue_percent_requested"] for r in children) != list(PERCENTS) or len({r["batch_id"] for r in children}) != 1:
            raise DataError("Root masks split/missing/duplicated")
    actual = dict(sorted(Counter(str(row["N"]) for row in records).items()))
    if actual != meta["actual_counts"] or actual != meta["target_counts"]:
        raise DataError("Dataset counts do not meet targets")
    main_batches = meta["fixture_quotas"]["main_batches"] if meta["artificial"] else 100
    reranked = [dict(row) for row in records]
    expected_batches = assign_batches(reranked, phase, batches=main_batches)
    if batches != expected_batches or any(a["batch_id"] != b["batch_id"] for a, b in zip(records, reranked)):
        raise DataError("Frozen batch assignment/order differs from ranking")
    if not meta["artificial"]:
        expected = {"9": 10000, "16": 5000, "25": 1000} if phase == "main" else {"9": 8, "16": 10, "25": 10}
        if actual != expected or len(batches) != (100 if phase == "main" else 1):
            raise DataError("Real dataset target/batch count mismatch")
        for batch in batches:
            batch_ids = set(batch["instance_ids"])
            selected = [r for r in records if r["instance_id"] in batch_ids]
            public_counts = Counter(r["source_group"] for r in selected if r["N"] == 9)
            quota = 25 if phase == "main" else 2
            if public_counts != Counter({g: quota for g in GROUPS}):
                raise DataError("Public batch strata unbalanced")
            for N in (16, 25):
                quota = (5 if N == 16 else 1) if phase == "main" else 1
                counts = Counter((r["family"], r["clue_percent_requested"]) for r in selected if r["N"] == N)
                if counts != Counter({(f, p): quota for f in FAMILIES for p in PERCENTS}):
                    raise DataError("Synthetic batch strata unbalanced")
    for source in provenance.get("sources", []):
        if sha256(contained_path(directory, source["dataset_file"]).read_bytes()) != source["sha256"]:
            raise DataError("Pinned source file checksum mismatch")
    _verify_public_provenance(directory, records, provenance)
    if _inputs_only and (pending != meta.get("public_witness_pending") or pending != sum(r["N"] == 9 for r in records)
                         or meta.get("all_witness_check_pass") is not False):
        raise DataError("Staged public witness-pending count differs")
    if require_frozen:
        freeze = read_json(directory / "freeze.json")
        if not meta["frozen"] or freeze["frozen"] is not True or freeze["schema_version"] != 2:
            raise DataError("Dataset not frozen")
        files = _file_hashes(directory)
        if files != freeze["files_sha256"] or sha256((directory / "manifest.jsonl").read_bytes()) != freeze["manifest_sha256"]:
            raise DataError("Dataset freeze checksum mismatch")
        if (freeze["dataset_id"] != meta["dataset_id"] or freeze["artificial"] != meta["artificial"]
                or freeze["expected_counts"] != meta["target_counts"] or freeze["actual_counts"] != actual
                or freeze["all_witness_check_pass"] is not True
                or freeze["old_data_exclusion_hash"] != meta["old_dataset_freeze_sha256"]
                or freeze["roots_sha256"] != sha256((directory / "roots.jsonl").read_bytes())
                or freeze["batches_sha256"] != sha256((directory / "batches.json").read_bytes())):
            raise DataError("Freeze identity/counts/header mismatch")
    return {"schema_version": 2, "dataset_id": meta["dataset_id"], "artificial": meta["artificial"],
            "phase": phase, "counts": actual, "roots": len(roots), "batches": len(batches),
            "witnesses_checked": len(records) - pending, "all_witness_check_pass": pending == 0,
            "status": "PASS_INPUTS_ONLY" if _inputs_only else "PASS", "solver_calls": 0,
            **({"public_witness_pending": pending, "frozen": False, "eligible_for_runner": False} if _inputs_only else {})}


def _verify_public_provenance(directory, records, provenance):
    """Match selected original line/token/grid to its pinned source, not just a hash."""
    source_index = {s["file"]: s for s in provenance.get("sources", [])}
    for group in GROUPS:
        public = [r for r in records if r["source_group"] == group]
        if not public:
            continue
        source = source_index.get(group + ".txt")
        if source is None:
            raise DataError("Public source provenance missing")
        wanted = {row["source_line"]: row for row in public}
        if len(wanted) != len(public) or any(type(line) is not int or line < 1 for line in wanted):
            raise DataError("Invalid/duplicate original public source lines")
        with contained_path(directory, source["dataset_file"]).open(encoding="ascii") as stream:
            for number, line in enumerate(stream, 1):
                if number not in wanted:
                    continue
                row = wanted.pop(number)
                fields = line.split()
                if len(fields) != 3 or not re.fullmatch(r"[0-9]{81}", fields[1]):
                    raise DataError("Malformed selected public source line")
                grid = [[int(x) for x in fields[1][start:start + 9]] for start in range(0, 81, 9)]
                if (row["source_record_id"] != fields[0] or row["rating_original"] != fields[2]
                        or row["rating_value"] != float(fields[2]) or not math.isfinite(float(fields[2]))
                        or row["content_sha256"] != content_sha256(3, grid)
                        or row["source_url"] != source["url"] or row["source_file_sha256"] != source["sha256"]):
                    raise DataError("Selected public source identity/rating/grid differs")
                if not wanted:
                    break
        if wanted:
            raise DataError("Selected public source line is missing")


def _staged_hashes(directory):
    return {name: digest for name, digest in _file_hashes(directory).items() if name != "inputs-receipt.json"}


def _seal_inputs(directory):
    """Seal integrity of a DRAFT; this receipt deliberately is not freeze.json."""
    result = verify_inputs(directory, _require_receipt=False)
    meta = read_json(Path(directory) / "dataset.json")
    _write_new(directory, "inputs-receipt.json", json_bytes({
        "schema_version": 2, "artifact_kind": "draft-inputs-receipt", "state": "DRAFT_INPUTS",
        "dataset_id": meta["dataset_id"], "artificial": meta["artificial"], "frozen": False,
        "public_witness_pending": result["public_witness_pending"], "actual_counts": result["counts"],
        "files_sha256": _staged_hashes(directory)}))
    return verify_inputs(directory)


def verify_inputs(directory, *, _require_receipt=True):
    """Read-only stage integrity/quotas/provenance check, with no public solving."""
    directory = Path(directory)
    if (directory / "freeze.json").exists():
        raise DataError("Staged inputs must not contain a dataset freeze")
    result = verify_dataset(directory, require_frozen=False, _inputs_only=True)
    if _require_receipt:
        receipt = read_json(directory / "inputs-receipt.json")
        if (receipt.get("artifact_kind") != "draft-inputs-receipt" or receipt.get("schema_version") != 2
                or receipt.get("state") != "DRAFT_INPUTS" or receipt.get("frozen") is not False
                or receipt.get("dataset_id") != result["dataset_id"]
                or receipt.get("artificial") != result["artificial"]
                or receipt.get("actual_counts") != result["counts"]
                or receipt.get("public_witness_pending") != result["public_witness_pending"]
                or receipt["files_sha256"] != _staged_hashes(directory)):
            raise DataError("DRAFT inputs receipt hash/count/identity mismatch")
    return result


def stage_inputs(project_root, output_dir, cache_dir):
    """Fetch/select/generate only. Never import/call a solver or freeze public data."""
    if Path(output_dir).exists():
        raise DataError("Stage output must be a new directory")
    receipt = cache_sources(cache_dir)
    sources = {group: iter_public_file(Path(cache_dir) / (group + ".txt"), group) for group in GROUPS}
    old_hashes, bases, old_freeze = old_dataset_exclusions(project_root)
    selected, logs = select_public(sources, old_hashes)
    provenance = {"source_commit": COMMIT, "parser_version": GENERATOR_VERSION,
                  "state": "DRAFT_INPUTS", "witness_solver": None,
                  "public_selection": {"main_per_group": 2500, "reserved_pilot_per_group": 2},
                  "group_order": list(GROUPS), "public_uniqueness": "source_claimed_not_self_proven",
                  "uniqueness_reference": SOURCE_BASE + "README.md",
                  "license_reference": "sources/LICENSE.txt", "attribution_reference": "sources/README.md",
                  "sources": [{**row, "cache_file": str(Path(cache_dir) / row["file"]),
                               "dataset_file": "sources/" + row["file"]} for row in receipt["files"]]}
    return _assemble(output_dir, selected, bases, old_hashes, old_freeze, artificial=False,
                     main_roots={16: 500, 25: 100}, main_batches=100, public_witness=None,
                     provenance=provenance, dedup_log=logs, inputs_only=True)


def finalize_staged_inputs(dataset_dir, output_dir, public_evidence):
    """Attach externally obtained witnesses into a NEW dataset; never invoke a solver.

    Real evidence wraps production SolveResult.to_dict(), input hashes and adapter
    hash. Artificial generator witnesses are allowed only for artificial fixtures.
    No reselection, root generation or mask generation occurs in this function.
    """
    source, target = Path(dataset_dir).resolve(), Path(output_dir).resolve()
    if target.exists() or target.is_relative_to(source):
        raise DataError("Witness finalization requires a NEW destination outside the DRAFT")
    verify_inputs(source)
    evidence = read_json(public_evidence) if isinstance(public_evidence, (str, Path)) else public_evidence
    meta = read_json(source / "dataset.json")
    if (not isinstance(evidence, dict) or evidence.get("schema_version") != 2 or evidence.get("dataset_id") != meta["dataset_id"]
            or evidence.get("artificial") is not meta["artificial"]):
        raise DataError("Completion evidence namespace differs from the DRAFT")
    records = _read_jsonl(source / "manifest.jsonl")
    public = [row for row in records if row["source"] == "sudoku_exchange"]
    checked = evidence.get("records", [])
    if [r["instance_id"] for r in checked] != [r["instance_id"] for r in public]:
        raise DataError("Completion evidence must cover the exact locked public ID order")
    if not meta["artificial"] and evidence.get("adapter_code_sha256") != sha256(Path(__file__).with_name("sat.py").read_bytes()):
        raise DataError("Production witness adapter provenance missing/different")
    additions = {}
    # Validate every witness before publishing anything into the new destination.
    for row, proof in zip(public, checked):
        if proof.get("input_sha256") != row["input_sha256"]:
            raise DataError("Completion evidence is for a different input")
        if meta["artificial"] and proof.get("sat_evidence") == "checked_generator_witness":
            grid, kind = proof["solution"], "checked_generator_witness"
        else:
            result = proof.get("result", {})
            if (result.get("status") != "SAT" or result.get("method") != "sat"
                    or result.get("encoding") != "pairwise" or not result.get("validation", {}).get("valid")):
                raise DataError("Public witness result is not production SAT; no sample replacement")
            grid, kind = result["solution"], "checked_solver_witness"
        puzzle = load_puzzle(contained_path(source, row["input_file"]))
        validation = _check(puzzle.n, puzzle.grid, grid)
        raw = canonical_puzzle_bytes(puzzle.n, grid)
        name = f"witnesses/{row['instance_id']}.json"
        row.update(witness_file=name, witness_sha256=sha256(raw), witness_content_sha256=sha256(raw),
                   witness_validation=validation, sat_evidence=kind)
        additions[name] = raw
    target.mkdir(parents=True)
    for name in _staged_hashes(source):
        _write_new(target, name, contained_path(source, name).read_bytes())
    _write_new(target, "staging-origin.json", (source / "inputs-receipt.json").read_bytes())
    _write_new(target, "completion-evidence.json", json_bytes(evidence))
    for name, raw in additions.items():
        _write_new(target, name, raw)
    (target / "manifest.jsonl").write_bytes(_jsonl(records))
    meta.update(state="WITNESSES_VERIFIED", public_witness_pending=0, all_witness_check_pass=True)
    meta.pop("eligible_for_runner", None)  # Runtime admission remains SAT07/coordinator's gate.
    (target / "dataset.json").write_bytes(json_bytes(meta))
    provenance = read_json(target / "provenance.json")
    provenance.update(state="WITNESSES_VERIFIED", completion_evidence_file="completion-evidence.json",
                      staging_inputs_receipt_sha256=sha256((source / "inputs-receipt.json").read_bytes()))
    (target / "provenance.json").write_bytes(json_bytes(provenance))
    return freeze_dataset(target)


def _file_hashes(directory):
    base = Path(directory)
    result = {}
    for path in sorted(base.rglob("*")):
        if path.is_file() and path.relative_to(base).as_posix() != "freeze.json":
            relative = path.relative_to(base).as_posix()
            contained_path(base, relative)
            result[relative] = sha256(path.read_bytes())
    return result


def freeze_dataset(directory):
    directory = Path(directory)
    if (directory / "freeze.json").exists():
        raise DataError("Cannot re-freeze an existing dataset identity")
    summary = verify_dataset(directory, require_frozen=False)
    meta = read_json(directory / "dataset.json")
    meta["frozen"] = True
    (directory / "dataset.json").write_bytes(json_bytes(meta))
    freeze = {"schema_version": 2, "dataset_id": meta["dataset_id"], "artificial": meta["artificial"],
              "frozen": True, "manifest_sha256": sha256((directory / "manifest.jsonl").read_bytes()),
              "roots_sha256": sha256((directory / "roots.jsonl").read_bytes()),
              "batches_sha256": sha256((directory / "batches.json").read_bytes()),
              "files_sha256": _file_hashes(directory), "expected_counts": meta["target_counts"],
              "actual_counts": summary["counts"], "old_data_exclusion_hash": meta["old_dataset_freeze_sha256"],
              "all_witness_check_pass": True}
    _write_new(directory, "freeze.json", json_bytes(freeze))
    return verify_dataset(directory)


def smoke_artificial(output_dir, project_root):
    """Build small artificial main/pilot fixtures; never invoke a solver or network."""
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise DataError("Smoke destination must be new")
    output_dir.mkdir(parents=True)
    old_hashes, _, old_freeze = old_dataset_exclusions(project_root)
    full9 = pattern_grid(3)
    sources, witnesses, receipts = {}, {}, []
    first = None
    for group in GROUPS:
        lines = []
        if first is not None:
            # Cross-source duplicate belongs to easy, even if later groups rank it first.
            lines.append(first)
        for ordinal in range(4):
            keep = set(ranked(range(81), f"artificial|{group}|{ordinal}")[:24 + ordinal])
            grid = [[full9[r][c] if r * 9 + c in keep else 0 for c in range(9)] for r in range(9)]
            digits = "".join(str(v) for row in grid for v in row)
            token = hashlib.sha1(digits.encode("ascii")).hexdigest()[:12]
            line = f"{token} {digits}  3.4\n"
            if first is None:
                first = line
            lines.append(line)
            witnesses[content_sha256(3, grid)] = full9
        path = output_dir / "parser-sources" / (group + ".txt")
        path.parent.mkdir(exist_ok=True)
        path.write_bytes("".join(lines).encode("ascii"))
        sources[group] = parse_public_file(path, group, source_url=f"artificial://{group}.txt")
        receipts.append({"file": group + ".txt", "cache_file": str(path),
                         "dataset_file": "sources/" + group + ".txt",
                         "url": f"artificial://{group}.txt", "sha256": sha256(path.read_bytes())})
    # Explicitly exercise canonical old exclusion, not just raw serialization hashes.
    artificial_old = sources["easy"][1]["content_sha256"]
    exclusions = old_hashes | {artificial_old}
    selected, logs = select_public(sources, exclusions, main_per_group=1, pilot_per_group=2)
    bases = {N: {"grid": pattern_grid(math.isqrt(N)), "file": "artificial_pattern",
                 "sha256": content_sha256(math.isqrt(N), pattern_grid(math.isqrt(N)))} for N in (16, 25)}
    fixed_time = "2026-10-19T00:00:00+00:00"
    paths = _assemble(output_dir / "datasets", selected, bases, exclusions, old_freeze,
                      artificial=True, main_roots={16: 1, 25: 1}, main_batches=1,
                      public_witness=lambda row: witnesses[row["content_sha256"]],
                      provenance={"source_commit": None, "parser_version": GENERATOR_VERSION,
                                  "sources": receipts, "license_reference": None,
                                  "note": "ARTIFICIAL parser records; not downloaded Sudoku Exchange data"},
                      dedup_log=logs, checked_utc=fixed_time)
    checks = {phase: verify_dataset(path) for phase, path in paths.items()}
    # Independent construction invariants and negative-path checks, not full-suite QA.
    replays = []
    for N in (16, 25):
        for family in FAMILIES:
            root = generate_root(math.isqrt(N), family, "main", 1, bases[N]["grid"], checked_utc=fixed_time)
            repeat = generate_root(math.isqrt(N), family, "main", 1, bases[N]["grid"], checked_utc=fixed_time)
            if json_bytes(root) != json_bytes(repeat):
                raise DataError("Root reproducibility failed")
            initial_log = []
            retry = generate_root(math.isqrt(N), family, "main", 1, bases[N]["grid"],
                                  {root["root_content_sha256"]}, initial_log, checked_utc=fixed_time)
            if not initial_log or retry["resample_index"] < 1:
                raise DataError("Root dedup/resample not exercised")
            mask = generate_mask(root, 20, "main", set(), [])
            log = []
            retried = generate_mask(root, 20, "main", {mask["content_sha256"]}, log)
            if not log or retried["resample_index"] != 1:
                raise DataError("Mask dedup/resample not exercised")
            try:
                generate_mask(root, 20, "main", {mask["content_sha256"]}, [], max_attempts=1)
            except DataError:
                pass
            else:
                raise DataError("Exhausted mask must stop")
            if family == "row_cycle":
                trade = root["trade"]
                base = permute_grid(math.isqrt(N), bases[N]["grid"], root["seed_label"])
                for invalid in (trade["columns"][:-1], list(range(N))):
                    try:
                        trade_row_cycle(math.isqrt(N), base, trade["row_a"], trade["row_b"], invalid)
                    except DataError:
                        pass
                    else:
                        raise DataError("Partial/whole-row trade must fail")
            replays.append({"N": N, "family": family, "reproducible": True,
                            "root_resample": retry["resample_index"], "mask_resample": retried["resample_index"]})
    # Byte serialization/BOM and metadata never change the canonical content identity.
    alternate = json.loads(b'\xef\xbb\xbf' + json.dumps({"grid": full9, "extra": "dữ liệu", "n": 3}, ensure_ascii=False).encode("utf-8"))
    if content_sha256(3, alternate["grid"]) != content_sha256(3, full9):
        raise DataError("Canonical identity depends on metadata/serialization")
    for invalid in ("../escape.json", "C:/escape.json", "/escape.json", "inputs\\escape.json"):
        try:
            contained_path(output_dir, invalid)
        except DataError:
            pass
        else:
            raise DataError("Escaping path accepted")
    summary = {"schema_version": 2, "artificial": True, "status": "PASS", "datasets": paths,
               "checks": checks, "deterministic_replays": replays,
               "dedup_events": len(logs), "old_canonical_exclusion_exercised": True,
               "source_ownership_exercised": True, "partial_cycle_rejected": True,
               "full_row_swap_rejected": True, "canonical_bom_metadata": "PASS",
               "path_traversal_rejected": True, "solver_calls": 0,
               "network_calls": 0, "full_generation": False, "pilot_or_main_execution": False}
    (output_dir / "smoke.json").write_bytes(json_bytes(summary))
    return summary

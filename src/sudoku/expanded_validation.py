"""Read-only schema2 dataset, balance, witness and matrix validation."""
from collections import Counter, defaultdict
from pathlib import Path
from sudoku.expanded_common import *
from sudoku.model import load_puzzle
from sudoku.validation import check_solution


@public
def validate_expanded_dataset(dataset_dir):
    directory = Path(dataset_dir).resolve()
    meta, freeze = read(directory / "dataset.json"), read(directory / "freeze.json")
    require(meta.get("schema_version") == freeze.get("schema_version") == 2, "Dataset version must be 2")
    require(meta.get("frozen") is True and freeze.get("frozen") is True, "Dataset not frozen")
    require(meta["dataset_id"] == freeze["dataset_id"], "Dataset identity mismatch")
    phase, artificial = meta["phase"], meta.get("artificial")
    require(phase in ("main", "pilot") and type(artificial) is bool, "Invalid phase/artificial marker")
    require(meta["master_seed"] == 20261019 and meta["canonicalization"] == "sudoku-json-v2", "Seed/canonicalization mismatch")
    required = {"dataset.json", "manifest.jsonl", "roots.jsonl", "batches.json", "provenance.json", "dedup.jsonl"}
    hashes = freeze["files_sha256"]
    require(required <= hashes.keys() and "freeze.json" not in hashes, "Incomplete freeze metadata")
    for relative, expected in hashes.items():
        require(sha(contained(directory, relative)) == expected, f"Frozen file changed: {relative}")
    provenance = read(directory / "provenance.json")
    old_hashes = set()
    other_hashes = set(provenance.get("other_phase_content_sha256", []))
    other_roots = set(provenance.get("other_phase_root_sha256", []))
    checker_hash = sha(ROOT / "src/sudoku/validation.py")
    if not artificial:
        require(meta["old_dataset_freeze_sha256"] == sha(ROOT / "data/freeze.json"), "Old dataset freeze differs")
        require(meta["source_commit"] == "d8c8ebaee0c08c412cfba96af1923dfa61c83317", "Public source commit mismatch")
        require(provenance.get("source_commit") == meta["source_commit"], "Provenance commit mismatch")
        for record in read(ROOT / "data/manifest.json")["records"]:
            puzzle = load_puzzle(ROOT / record["file"])
            old_hashes.add(digest(canonical(puzzle.n, puzzle.grid)))
    records, seen = {}, set()
    root_records = lines(directory / "roots.jsonl")
    roots = {r["root_id"]: r for r in root_records}
    require(len(roots) == len(root_records), "Duplicate root ID")
    groups = defaultdict(list)
    fields = "schema_version dataset_id instance_id batch_id phase n N input_file input_sha256 content_sha256 source source_group source_record_id source_line source_url source_file_sha256 rating_original rating_value family root_id root_content_sha256 clue_percent_requested actual_clues master_seed derived_seed seed_label resample_index witness_file witness_sha256 witness_content_sha256 witness_validation sat_evidence uniqueness uniqueness_reference".split()
    for record in lines(directory / "manifest.jsonl"):
        require(set(fields) <= record.keys(), "Manifest fields missing")
        r = record
        require(r["schema_version"] == 2 and r["dataset_id"] == meta["dataset_id"] and r["phase"] == phase, "Record namespace mismatch")
        require(type(r["n"]) is int and type(r["N"]) is int and r["N"] == r["n"]**2, "Invalid n/N")
        require(r["N"] in (9, 16, 25) or artificial, "Unexpected real board size")
        require(r["master_seed"] == 20261019 and isinstance(r["derived_seed"], str) and r["derived_seed"].isdigit(), "Invalid seed")
        require(type(r["resample_index"]) is int and r["resample_index"] >= 0, "Invalid resampling index")
        for path_key, hash_key in (("input_file", "input_sha256"), ("witness_file", "witness_sha256")):
            require(r[path_key] in hashes and hashes[r[path_key]] == r[hash_key], "Input/witness not covered by freeze")
        puzzle = load_puzzle(contained(directory, r["input_file"]))
        witness = load_puzzle(contained(directory, r["witness_file"]))
        content = digest(canonical(puzzle.n, puzzle.grid))
        require((puzzle.n, puzzle.N, puzzle.clue_count) == (r["n"], r["N"], r["actual_clues"]), "Input shape/clue metadata mismatch")
        require(r["content_sha256"] == content and content not in seen and content not in old_hashes and content not in other_hashes, "Duplicate/content hash mismatch")
        require(r["instance_id"] == f"e2-{phase}-N{puzzle.N}-{content}", "Instance ID not content-addressed")
        require(witness.n == puzzle.n and check_solution(puzzle, witness.grid).valid, "Witness checker rejected puzzle")
        require(r["witness_content_sha256"] == digest(canonical(witness.n, witness.grid)), "Witness canonical hash mismatch")
        require(r["witness_validation"].get("valid") is True and r["witness_validation"].get("checker_code_sha256") == checker_hash, "Witness checker provenance mismatch")
        require(r["rating_value"] is None or finite(r["rating_value"]), "Invalid rating value")
        if r["source"] == "synthetic":
            require(r["family"] in ("permutation", "row_cycle") and r["root_id"] in roots, "Unknown synthetic family/root")
            require(r["clue_percent_requested"] in (20,30,40,50,60) and r["uniqueness"] == "unverified", "Synthetic density/uniqueness mismatch")
            require(r["actual_clues"] == (r["clue_percent_requested"] * r["N"]**2 + 50)//100, "Clue rounding mismatch")
            require(r["root_content_sha256"] == r["witness_content_sha256"], "Mask witness differs from its root")
            groups[r["root_id"]].append(r)
        else:
            require(r["source"] == "sudoku_exchange" and r["source_group"] in ("easy","medium","hard","diabolical"), "Unknown public group")
            require(r["family"] is None and r["root_id"] is None and r["clue_percent_requested"] is None, "Public synthetic metadata")
            require(r["uniqueness"] in ("unverified", "source_claimed"), "Unsupported uniqueness claim")
            require(r["uniqueness"] != "source_claimed" or bool(r["uniqueness_reference"]), "Uncited uniqueness claim")
        seen.add(content)
        require(r["instance_id"] not in records, "Duplicate instance ID")
        records[r["instance_id"]] = r
    root_hashes = set()
    for rid, root in roots.items():
        require(rid in groups, "Unused root")
        root_path = root.get("grid_file")
        require(root_path in hashes, "Root grid missing from freeze")
        solution = load_puzzle(contained(directory, root_path))
        content = digest(canonical(solution.n, solution.grid))
        require(check_solution(solution, solution.grid).valid and content not in root_hashes, "Invalid/duplicate root")
        require(content not in other_roots,"Root overlaps pilot/main")
        if root.get("root_content_sha256") is not None:
            require(root["root_content_sha256"]==content and root.get("grid_sha256")==hashes[root_path],"Root file/content hash mismatch")
        if root["family"]=="row_cycle":
            trade=root["trade"]; a,b=trade["row_a"],trade["row_b"]; columns=trade["columns"]
            require(type(a) is int and type(b) is int and 0<=a<solution.N and 0<=b<solution.N and a!=b and a//solution.n==b//solution.n,"Row trade band mismatch")
            require(len(columns)==len(set(columns)) and 2<=len(columns)<solution.N and all(type(c) is int and 0<=c<solution.N for c in columns),"Invalid proper trade columns")
            base=[list(row) for row in solution.grid]
            for column in columns: base[a][column],base[b][column]=base[b][column],base[a][column]
            require(digest(canonical(solution.n,base))==trade["base_content_sha256"],"Reversed trade base hash mismatch")
            from sudoku.model import Puzzle
            require(check_solution(Puzzle(solution.n,base),base).valid,"Reversed trade base invalid")
            mapping=dict(zip(base[a],base[b])); first=base[a][columns[0]]; cycle=[]; value=first
            while value not in cycle:
                cycle.append(value); value=mapping[value]
            require(value==first and set(cycle)=={base[a][c] for c in columns}==set(trade["values"]),"Not a whole permutation cycle")
        require(all(r["root_content_sha256"] == content and r["family"] == root["family"] and r["N"] == root["N"] for r in groups[rid]), "Root relationship mismatch")
        require(len({r["batch_id"] for r in groups[rid]}) == 1, "Root split across blocks")
        if not artificial:
            require(sorted(r["clue_percent_requested"] for r in groups[rid]) == [20,30,40,50,60], "Missing five root masks")
        root_hashes.add(content)
    value = read(directory / "batches.json")
    batches = value if isinstance(value, list) else value["batches"]
    require(bool(records) and bool(batches), "Dataset/batches must not be empty")
    assigned = []
    for ordinal, batch in enumerate(batches, 1):
        require(batch["ordinal"] == ordinal, "Batch ordinal mismatch")
        require(batch["batch_id"] == (f"b{ordinal:03d}" if phase == "main" else "p001"), "Invalid batch ID/order")
        ids = batch["instance_ids"]
        require(all(i in records and records[i]["batch_id"] == batch["batch_id"] for i in ids), "Batch membership mismatch")
        assigned.extend(ids)
        if not artificial:
            selected = [records[i] for i in ids]
            expected9 = 25 if phase == "main" else 2
            require(Counter(r["source_group"] for r in selected if r["N"] == 9) == {g:expected9 for g in ("easy","medium","hard","diabolical")}, "Public batch quota mismatch")
            for size, each in ((16, 5 if phase == "main" else 1), (25, 1)):
                require(Counter((r["family"],r["clue_percent_requested"]) for r in selected if r["N"] == size) == {(f,p):each for f in ("permutation","row_cycle") for p in (20,30,40,50,60)}, "Synthetic batch quota mismatch")
    require(len(assigned) == len(set(assigned)) == len(records) and set(assigned) == set(records), "Duplicate/missing batch IDs")
    # Recompute the predeclared ranked assignment, not merely its totals.
    expected=[[] for _ in batches]
    for group in ("easy","medium","hard","diabolical"):
        ids=sorted((r["instance_id"] for r in records.values() if r["source_group"]==group),key=lambda i:(rank(f"batch|public|{group}",i),i))
        require(len(ids)%len(batches)==0,"Public batch division mismatch")
        width=len(ids)//len(batches)
        for number in range(len(batches)): expected[number].extend(ids[number*width:(number+1)*width])
    for size in sorted({r["N"] for r in records.values() if r["source"]=="synthetic"}):
        for family in ("permutation","row_cycle"):
            ids=sorted((rid for rid,children in groups.items() if children[0]["N"]==size and children[0]["family"]==family),key=lambda i:(rank(f"batch|{size}|{family}",i),i))
            require(len(ids)%len(batches)==0,"Root batch division mismatch")
            width=len(ids)//len(batches)
            for number in range(len(batches)):
                for rid in ids[number*width:(number+1)*width]: expected[number].extend(r["instance_id"] for r in sorted(groups[rid],key=lambda r:r["clue_percent_requested"]))
    require(expected==[b["instance_ids"] for b in batches],"Batch order differs from frozen rank rule")
    if artificial:
        quotas = meta["fixture_quotas"]
        require(quotas["instances"] == len(records) and quotas["batches"] == len(batches), "Artificial explicit quotas mismatch")
    else:
        require(len(batches) == (100 if phase == "main" else 1), "Wrong real batch count")
        require(Counter(r["N"] for r in records.values()) == ({9:10000,16:5000,25:1000} if phase == "main" else {9:8,16:10,25:10}), "Real dataset total mismatch")
        require(freeze.get("all_witness_check_pass") is True,"Missing dataset witness gate")
        require(bool(provenance.get("license_reference")) and bool(provenance.get("other_phase_content_sha256")),"Real source license/cross-phase evidence missing")
        for source in provenance["sources"]:
            require(source["dataset_file"] in hashes and source["sha256"]==hashes[source["dataset_file"]],"Source not frozen")
    return dict(schema_version=2, dataset_id=meta["dataset_id"], phase=phase, artificial=artificial,
                dataset_dir=str(directory), freeze_sha256=sha(directory / "freeze.json"), records=records,
                batches=batches, counts=dict(instances=len(records),batches=len(batches)), metadata=meta, roots=roots)


def validate_config(value, phase):
    expected = dict(schema_version=2,phase=phase,cutoff_seconds=10.0,repetitions=3 if phase=="main" else 1,
                    schedule_seed=20261019,startup_seconds=60.0,postprocessing_seconds=30.0)
    require(all(value.get(k) == v and not isinstance(value.get(k),bool) for k,v in expected.items()), "Config does not match accepted protocol")
    require(type(value.get("disk_reserve_bytes")) is int and value["disk_reserve_bytes"] >= 1073741824, "Disk reserve must be at least 1GiB")


def validate_matrix(matrix, artificial=False):
    require(matrix.get("schema_version") == 2, "Matrix schema must be 2")
    rows = matrix["rows"]
    keys = [(r["N"],r["configuration"]) for r in rows]
    require(len(keys) == len(set(keys)), "Duplicate matrix cells")
    for row in rows:
        config = row["method"] + (":"+row["encoding"] if row.get("encoding") else "")
        require(config == row["configuration"] and config in CONFIGURATIONS and type(row["eligible"]) is bool, "Invalid matrix row")
    if not artificial:
        require(set(keys) == {(n,c) for n in (9,16,25) for c in CONFIGURATIONS}, "Matrix must have all24 cells")
        require(all(r["eligible"] == (r["N"] == 9 or r["method"] in ("sat","cpsat","highs")) for r in rows), "Eligibility differs from accepted preflight")
        for ref in matrix["evidence"]:
            require(sha(contained(ROOT,ref["path"])) == ref["sha256"], "Preflight evidence changed")
    return rows

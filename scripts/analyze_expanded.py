"""EXP-08A: read-only schema-2 export analysis; never starts a solver.

See diagnostics/expansion/analysis/API.md for the explicit fixture envelope.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import sqlite3
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sudoku.model import parse_puzzle
from sudoku.validation import check_solution

FIELDS = "schema_version,experiment_id,dataset_id,phase,batch_id,job_id,attempt_id,attempt_no,instance_id,method,encoding,repetition,block_side,board_side,source,source_group,rating_original,rating_value,family,root_id,clue_percent_requested,actual_clues,input_sha256,cutoff_seconds,status,raw_status,build_seconds,solve_seconds,total_seconds,attempt_wall_seconds,checkpoint_seconds,primary_variables,auxiliary_variables,total_variables,clauses,validation,validation_message,solution_ref,solution_sha256,guard_phase,error".split(",")
STATUS = {"SAT", "TIMEOUT", "UNSAT", "ERROR", "UNAVAILABLE", "LICENSE_LIMIT", "INVALID_INPUT"}
METRICS = ("build_seconds", "solve_seconds", "total_seconds")
CONFIGS = {"sat:pairwise", "sat:seqcounter", "sat:bitwise", "cpsat", "highs", "gurobi", "cplex_mip", "cpoptimizer"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def js(path):
    def reject(value):
        raise ValueError(f"Nonfinite JSON token: {value}")
    return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=reject)


def js_config(text):
    def reject(value):
        raise ValueError(f"Nonfinite snapshot JSON token: {value}")
    return json.loads(text,parse_constant=reject)


def child(root, relative):
    require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), "Expected relative artifact path")
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), "Path escapes export/dataset root")
    return path


def csv_read(path, fields=None):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames is not None and len(reader.fieldnames) == len(set(reader.fieldnames)), "CSV missing/duplicate header")
        if fields:
            require(reader.fieldnames == fields, "results.csv schema-2 header mismatch")
        rows = list(reader)
    require(all(None not in r and None not in r.values() for r in rows), "Malformed CSV row")
    return rows


def numeric(value, integer=False):
    if value in (None, ""):
        return None
    result = int(value) if integer else float(value)
    require(math.isfinite(result) and result >= 0, "Invalid nonnegative finite measurement")
    return result


def quantile_type7(values, p):
    require(0 <= p <= 1, "Quantile probability outside [0,1]")
    values = sorted(values)
    if not values:
        return None
    h = (len(values) - 1) * p
    lo, hi = math.floor(h), math.ceil(h)
    return values[lo] + (h - lo) * (values[hi] - values[lo])


def config(row):
    return row["method"] + (":" + row["encoding"] if row["encoding"] else "")


def stratum(row):
    return (row["board_side"], row["source"], row["source_group"], row["rating_original"],
            row["clue_percent_requested"], row["family"])


STRATA = ("board_side", "source", "source_group", "rating_original", "clue_percent_requested", "family")


def table(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        fields=list(rows[0]) if rows else OUTPUT_COLUMNS.get(path.name)
        if fields:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                             for k, v in r.items()} for r in rows)


OUTPUT_COLUMNS={
    "instances.csv":["instance_id","configuration","batch_id",*STRATA,"root_id","observed_primary_repetitions","missing_repetitions","statuses","mixed_status","runtime_eligible","par2_eligible",*("median_"+k for k in METRICS),"par2_seconds"],
    "strata.csv":["configuration",*STRATA,"observed_instances","planned_instances","observed_instances_with_results","missing_primary_repetitions","runtime_instances","missing_or_ineligible_instances","mixed_instances","par2_instances","par2_primary_attempts","mean_instance_par2_seconds","root_clusters",*(label+"_"+metric for metric in METRICS for label in ("median","p90","p95"))],
    "matched-pairs.csv":["configuration_a","configuration_b",*STRATA,"matched_instances","instance_ids","median_a_seconds","median_b_seconds","median_paired_a_over_b","cluster_ids"],
    "blocks.csv":["batch_id","expected_jobs","observed_primary_jobs","execution_complete","qa_complete","reason"],
    "coverage.csv":["configuration","selected_matrix_jobs","observed_primary_jobs","missing_primary_jobs","selected_instances","any_sat_instances","all_three_sat_instances","status_counts"],
    "primary-par2.csv":["job_id","attempt_id","instance_id","configuration","repetition","batch_id","status","par2_seconds"],
    "clusters.csv":["board_side","family","cluster_id","batch_id","instance_ids"],
}


def _validate(export):
    from sudoku.expanded_common import ExpandedError, dumps, rank
    from sudoku.expanded_validation import validate_expanded_dataset, validate_config, validate_matrix
    meta = js(export / "export.json")
    require(type(meta.get("schema_version")) is int and meta["schema_version"] == 2, "Export requires schema 2")
    require(meta.get("mode") in ("partial", "complete-blocks") and "selection_mode" not in meta, "Unknown/noncanonical export mode")
    require(meta.get("phase") in ("main", "pilot") and type(meta.get("artificial")) is bool, "Invalid phase/artificial")
    manifest=meta["manifest"]
    require(manifest["schema_version"] == 2 and all(meta[k] == manifest[k] for k in ("experiment_id","dataset_id","phase","artificial")), "Nested manifest/export identity mismatch")
    require(meta["mode"] != "complete-blocks" or meta["phase"] == "main", "Pilot cannot claim main complete blocks")
    require(type(meta["report_ready"]) is bool, "Invalid report-ready marker")
    expected_ready=meta["mode"]=="complete-blocks" and not meta["artificial"] and bool(meta["selected_blocks"])
    require(meta["report_ready"] == expected_ready, "Fake final/report-ready claim")
    hashes=js(export/"hashes.json")
    require(hashes.get("schema_version")==2 and isinstance(hashes.get("files_sha256"),dict), "Hash schema mismatch")
    inventory=hashes["files_sha256"]
    required={"export.json","snapshot.sqlite3","results.csv","attempts.csv","jobs.csv","matrix.json","manifest.jsonl","batches.json"}
    require(required<=inventory.keys() and "hashes.json" not in inventory,"Incomplete/recursive hash inventory")
    for name,expected in inventory.items():
        require(digest(child(export,name))==expected,f"Export hash mismatch: {name}")
    require({p.relative_to(export).as_posix() for p in export.rglob("*") if p.is_file() and p.name!="hashes.json"}==inventory.keys(),"Uninventoried export artifacts")
    require(hashlib.sha256(dumps(manifest["config"]).encode()).hexdigest()==manifest["config_sha256"],"Scientific config hash mismatch")
    require(hashlib.sha256(dumps(manifest["matrix"]).encode()).hexdigest()==manifest["matrix_sha256"],"Matrix fingerprint mismatch")
    scientific={k:v for k,v in manifest.items() if k not in ("created_utc","scientific_sha256")}
    require(hashlib.sha256(dumps(scientific).encode()).hexdigest()==manifest["scientific_sha256"],"Scientific manifest fingerprint mismatch")
    require(js(export/"matrix.json")==manifest["matrix"],"Export/nested matrix mismatch")
    try:
        validate_config(manifest["config"],meta["phase"])
        validate_matrix(manifest["matrix"],meta["artificial"])
        dataset=validate_expanded_dataset(manifest["dataset_dir"])
    except ExpandedError as exc:
        raise ValueError(f"Canonical dataset/config/matrix rejected: {exc}") from exc
    require(dataset["freeze_sha256"]==manifest["dataset_freeze_sha256"] and all(dataset[k]==meta[k] for k in ("dataset_id","phase","artificial")),"Frozen dataset identity/hash mismatch")
    records=[js_config(line) for line in (export/"manifest.jsonl").read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    index={r["instance_id"]:r for r in records}
    require(len(records)==len(index) and index==dataset["records"],"Export/frozen manifest mismatch")
    batches=js(export/"batches.json")
    require(isinstance(batches,list) and batches==dataset["batches"],"Canonical batches list mismatch")
    block_index={b["batch_id"]:b for b in batches}
    require(not any(name.startswith("snapshot.sqlite3-") for name in inventory),"Export snapshot must be standalone, without SQLite sidecars")
    connection=sqlite3.connect((export/"snapshot.sqlite3").as_uri()+"?mode=ro&immutable=1",uri=True)
    connection.row_factory=sqlite3.Row
    try:
        require(connection.execute("PRAGMA user_version").fetchone()[0]==2,"Snapshot requires schema 2")
        require(connection.execute("PRAGMA integrity_check").fetchone()[0]=="ok" and not list(connection.execute("PRAGMA foreign_key_check")),"SQLite integrity/FK failure")
        columns={
            "experiment":"experiment_id manifest_json state halt_reason",
            "batches":"batch_id ordinal expected_instances expected_jobs qa_state qa_reason",
            "instances":"instance_id content_sha256 batch_id block_side board_side manifest_record_json",
            "jobs":"job_id instance_id configuration method encoding repetition ordinal state",
            "sessions":"session_id host pid creation_time started_utc ended_utc stop_starting_at heartbeat_utc reason",
            "attempts":"attempt_id job_id attempt_no session_id state started_utc ended_utc attempt_wall_seconds interruption_reason",
            "results":"attempt_id status result_json solution_attempt_id",
            "solutions":"attempt_id payload sha256 checker_json",
            "primary_attempt":"job_id attempt_id",
            "events":"event_id utc session_id job_id attempt_id type details_json",
        }
        for name,fields in columns.items():
            require([c["name"] for c in connection.execute(f'PRAGMA table_info("{name}")')]==fields.split(),f"Unknown/noncanonical snapshot columns: {name}")
        db={name:[dict(r) for r in connection.execute(f'SELECT * FROM "{name}"')]
            for name in ("experiment","batches","instances","jobs","sessions","attempts","results","solutions","primary_attempt","events")}
    finally:
        connection.close()
    require(len(db["experiment"])==1 and db["experiment"][0]["experiment_id"]==meta["experiment_id"] and js_config(db["experiment"][0]["manifest_json"])==manifest,"SQLite immutable manifest/fingerprint mismatch")
    require(manifest["fingerprint"].get("threads")==1,"Recorded thread policy mismatch")
    expected_jobs=[]
    for batch in batches:
        group=[]
        for iid in batch["instance_ids"]:
            for cell in manifest["matrix"]["rows"]:
                if cell["N"]!=index[iid]["N"] or not cell["eligible"]:continue
                for rep in range(1,manifest["config"]["repetitions"]+1):
                    encoding=cell.get("encoding") or ""
                    identity=[meta["experiment_id"],iid,cell["method"],encoding,rep]
                    jid="j2-"+hashlib.sha256(dumps(identity).encode()).hexdigest()
                    group.append(dict(job_id=jid,instance_id=iid,configuration=cell["configuration"],method=cell["method"],encoding=encoding,repetition=rep))
        group.sort(key=lambda j:(rank(f"schedule|{meta['phase']}|{batch['batch_id']}",j["job_id"]),j["job_id"]))
        expected_jobs.extend(group)
    for ordinal,job in enumerate(expected_jobs,1):job["ordinal"]=ordinal
    require(bool(expected_jobs),"Empty frozen schedule")
    jobs_ordered=sorted(db["jobs"],key=lambda j:j["ordinal"])
    require([{k:j[k] for k in expected_jobs[0]} for j in jobs_ordered]==expected_jobs,"Frozen canonical schedule/matrix/ordinal mismatch")
    scheduled=[dict(j,batch_id=index[j["instance_id"]]["batch_id"]) for j in expected_jobs]
    require(hashlib.sha256((dumps(scheduled)+"\n").encode()).hexdigest()==manifest["schedule_sha256"],"Frozen schedule hash mismatch")
    db_jobs={j["job_id"]:j for j in jobs_ordered}
    db_instances={r["instance_id"]:r for r in db["instances"]}
    require(set(db_instances)==set(index) and len(db_instances)==len(db["instances"]),"SQLite instance universe mismatch")
    for iid,r in index.items():
        d=db_instances[iid]
        require(js_config(d["manifest_record_json"])==r and (d["block_side"],d["board_side"],d["batch_id"],d["content_sha256"])==(r["n"],r["N"],r["batch_id"],r["content_sha256"]),"SQLite instance/hash/dimensions mismatch")
    db_blocks={b["batch_id"]:b for b in db["batches"]}
    require(db_blocks.keys()==block_index.keys(),"SQLite batch universe mismatch")
    attempts={a["attempt_id"]:a for a in db["attempts"]}
    stored_results={r["attempt_id"]:r for r in db["results"]}
    primaries={p["job_id"]:p["attempt_id"] for p in db["primary_attempt"]}
    solutions={s["attempt_id"]:s for s in db["solutions"]}
    require(len(attempts)==len(db["attempts"]) and len(stored_results)==len(db["results"]) and len(primaries)==len(db["primary_attempt"]) and len(solutions)==len(db["solutions"]),"Duplicate SQLite identities")
    require(stored_results.keys()<=attempts.keys() and set(primaries.values())==stored_results.keys() and len(primaries)==len(set(primaries.values())),"Dangling/nonprimary SQLite result")
    require(solutions.keys()=={aid for aid,r in stored_results.items() if r["status"]=="SAT"},"Result/solution atomicity failure")
    require(all((a["state"]=="FINISHED")== (aid in stored_results) and a["state"] in ("FINISHED","INTERRUPTED","RUNNING") and a["job_id"] in db_jobs for aid,a in attempts.items()),"Attempt/result atomicity failure")
    require(all((j["state"]=="TERMINAL")== (jid in primaries) for jid,j in db_jobs.items()),"Job/primary atomicity failure")
    require(all(primaries.get(attempts[aid]["job_id"])==aid for aid in stored_results),"Primary attempt/job mismatch")
    sessions={s["session_id"] for s in db["sessions"]}
    require(all(a["session_id"] in sessions for a in attempts.values()),"Missing attempt session")
    checkpoints={}
    for event in sorted(db["events"],key=lambda e:e["event_id"]):
        if event["type"]=="CHECKPOINT" and event["attempt_id"] not in checkpoints:
            checkpoints[event["attempt_id"]]=js_config(event["details_json"])["checkpoint_seconds"]
    require(meta["last_event_id"]==max((e["event_id"] for e in db["events"]),default=0),"Snapshot last event mismatch")
    first_terminal={}
    for a in attempts.values():
        if a["state"]=="FINISHED":first_terminal[a["job_id"]]=min(first_terminal.get(a["job_id"],a["attempt_no"]),a["attempt_no"])
    result_objects={}
    puzzles={}
    for aid,stored in stored_results.items():
        result=js_config(stored["result_json"]);a=attempts[aid];job=db_jobs[a["job_id"]];record=index[job["instance_id"]]
        require(a["attempt_no"]==first_terminal[a["job_id"]],"Primary is not first terminal attempt")
        require(result["status"]==stored["status"] and result["status"] in STATUS and result.get("method")==job["method"] and (result.get("encoding") or "")==job["encoding"],"Stored result status/configuration mismatch")
        require(result["status"]!="UNSAT","UNSAT conflicts with witnessed-SAT dataset")
        for key in METRICS:
            value=result.get(key)
            require(value is None or type(value) in (int,float) and math.isfinite(value) and value>=0,"Invalid stored timing")
        b,s,t=(result.get(k) for k in METRICS)
        if all(v is not None for v in (b,s,t)):require(math.isclose(b+s,t,rel_tol=1e-7,abs_tol=1e-7),"Timing sum mismatch")
        if result["status"]=="TIMEOUT":require(result.get("guard_phase") in ("measurement","complete"),"TIMEOUT outside measurement")
        if result["status"]=="SAT":
            require(all(v is not None for v in (b,s,t)) and t<=10 and result.get("guard_phase")=="complete" and (result.get("validation") or {}).get("valid") is True,"Invalid successful SAT timing/validation")
            solution=solutions[aid];payload=solution["payload"]
            require(isinstance(payload,bytes) and hashlib.sha256(payload).hexdigest()==solution["sha256"] and stored["solution_attempt_id"]==aid,"SQLite canonical solution hash/reference mismatch")
            grid=js_config(payload)
            canonical=(dumps(dict(n=grid["n"],grid=grid["grid"]))+"\n").encode()
            require(payload==canonical and grid["n"]==record["n"] and js_config(solution["checker_json"]).get("valid") is True,"Canonical grid/checker evidence mismatch")
            iid=job["instance_id"]
            if iid not in puzzles:puzzles[iid]=parse_puzzle(js(child(Path(dataset["dataset_dir"]),record["input_file"])))
            require(check_solution(puzzles[iid],grid["grid"]).valid,"Independent checker rejected solution")
            stats=result.get("stats")
            if job["method"]=="sat":
                require(isinstance(stats,dict) and all(type(stats.get(k)) is int and stats[k]>=0 for k in ("primary_variables","auxiliary_variables","total_variables","clauses")),"Missing/invalid CNF counts")
                n=record["N"]
                require(stats["primary_variables"]==n**3 and stats["total_variables"]==stats["primary_variables"]+stats["auxiliary_variables"] and stats["clauses"]>0,"CNF size mismatch")
                if job["encoding"]=="pairwise":require(stats["auxiliary_variables"]==0 and stats["clauses"]==4*n*n*(1+n*(n-1)//2)+record["actual_clues"],"Pairwise CNF mismatch")
            else:require(stats is None,"Baseline SAT counts forbidden")
        else:require(stored["solution_attempt_id"] is None,"NonSAT solution reference")
        result_objects[aid]=result
    quality={};states=[]
    for batch in batches:
        bid=batch["batch_id"];block_jobs=[j for j in jobs_ordered if index[j["instance_id"]]["batch_id"]==bid]
        count=len(block_jobs);d=db_blocks[bid]
        require(count>0 and (d["ordinal"],d["expected_instances"],d["expected_jobs"])==(batch["ordinal"],len(batch["instance_ids"]),count),"SQLite batch counts/order mismatch")
        terminal=[j for j in block_jobs if j["job_id"] in primaries]
        complete=len(terminal)==count
        reason=None if complete else "incomplete jobs"
        if complete and any(result_objects[primaries[j["job_id"]]]["status"] not in ("SAT","TIMEOUT") for j in terminal):reason="fatal/noneligible terminal status"
        if any(a["state"]=="RUNNING" and index[db_jobs[a["job_id"]]["instance_id"]]["batch_id"]==bid for a in attempts.values()):reason="unresolved running attempt"
        quality[bid]=dict(execution_complete=complete,qa_complete=reason is None,reason=reason)
    valid={bid for bid,q in quality.items() if q["qa_complete"]}
    expected_blocks=[b["batch_id"] for b in batches if meta["mode"]=="partial" or b["batch_id"] in valid]
    require(meta["selected_blocks"]==expected_blocks and meta["qa_complete_blocks"]==sorted(valid) and meta["excluded_blocks"]=={bid:q["reason"] for bid,q in quality.items() if not q["qa_complete"]},"Declared block selection/quality differs from snapshot")
    selected=set(expected_blocks)
    chosen_jobs={j["job_id"]:j for j in jobs_ordered if index[j["instance_id"]]["batch_id"] in selected}
    require(meta["planned_blocks"]==len(batches) and meta["planned_jobs"]==len(db_jobs),"Planned denominators mismatch")
    require(meta["selected_jobs"]==list(chosen_jobs),"Declared selected job order mismatch")
    job_csv=csv_read(export/"jobs.csv")
    expected_job_csv=[dict(j,batch_id=index[j["instance_id"]]["batch_id"]) for j in chosen_jobs.values()]
    def text(value):return "" if value is None else str(value)
    def equal_csv(actual,expected,fields):
        require(len(actual)==len(expected),"CSV/snapshot count mismatch")
        require(all(set(r)==set(fields) for r in actual),"Unknown CSV fields")
        require(all(all(r[k]==text(e.get(k)) for k in fields) for r,e in zip(actual,expected)),"CSV/snapshot identity/order/value mismatch")
    equal_csv(job_csv,expected_job_csv,"job_id instance_id configuration method encoding repetition ordinal state batch_id".split())
    selected_attempts={aid:a for aid,a in attempts.items() if a["job_id"] in chosen_jobs}
    ordered_attempts=sorted(selected_attempts.values(),key=lambda a:(db_jobs[a["job_id"]]["ordinal"],a["attempt_no"]))
    expected_attempts=[]
    for a in ordered_attempts:
        j=chosen_jobs[a["job_id"]];aid=a["attempt_id"];status=stored_results[aid]["status"] if aid in stored_results else None
        expected_attempts.append(dict(a,**{k:j[k] for k in ("instance_id","method","encoding","repetition")},batch_id=index[j["instance_id"]]["batch_id"],status=status,is_primary=int(primaries.get(a["job_id"])==aid),solution_ref=f"solutions/{aid}.json" if status=="SAT" else None))
    equal_csv(csv_read(export/"attempts.csv"),expected_attempts,"attempt_id job_id instance_id method encoding repetition batch_id attempt_no session_id state started_utc ended_utc attempt_wall_seconds interruption_reason is_primary status solution_ref".split())
    require(meta["attempt_ids"]==[a["attempt_id"] for a in ordered_attempts],"Declared attempt set/order mismatch")
    rows=csv_read(export/"results.csv",FIELDS)
    primary_jobs=[j for j in chosen_jobs.values() if j["job_id"] in primaries]
    require([r["job_id"] for r in rows]==[j["job_id"] for j in primary_jobs]==meta["observed_primary_jobs"],"Primary rows missing/duplicate/order mismatch")
    checked=[]
    for raw,job in zip(rows,primary_jobs):
        aid=primaries[job["job_id"]];a=attempts[aid];r=index[job["instance_id"]];result=result_objects[aid]
        expected=dict.fromkeys(FIELDS)
        expected.update(schema_version=2,experiment_id=meta["experiment_id"],dataset_id=meta["dataset_id"],phase=meta["phase"],cutoff_seconds=manifest["config"]["cutoff_seconds"],batch_id=r["batch_id"],job_id=job["job_id"],attempt_id=aid,attempt_no=a["attempt_no"],instance_id=job["instance_id"],method=job["method"],encoding=job["encoding"],repetition=job["repetition"],attempt_wall_seconds=a["attempt_wall_seconds"],checkpoint_seconds=checkpoints.get(aid),block_side=r["n"],board_side=r["N"])
        expected.update({k:r[k] for k in ("source","source_group","rating_original","rating_value","family","root_id","clue_percent_requested","actual_clues","input_sha256")})
        expected.update({k:result.get(k) for k in ("status","raw_status",*METRICS,"guard_phase","error")})
        stats=result.get("stats") or {}
        expected.update({k:stats.get(k) for k in ("primary_variables","auxiliary_variables","total_variables","clauses")})
        validation=result.get("validation")
        if validation is not None:expected.update(validation="pass" if validation["valid"] else "fail",validation_message=validation.get("message"))
        if result["status"]=="SAT":
            ref=f"solutions/{aid}.json";expected.update(solution_ref=ref,solution_sha256=solutions[aid]["sha256"])
            require(ref in inventory and child(export,ref).read_bytes()==solutions[aid]["payload"],"Dangling/mismatched exported solution bytes")
        equal_csv([raw],[expected],FIELDS)
        row=dict(raw)
        for key in (*METRICS,"attempt_wall_seconds","checkpoint_seconds","primary_variables","auxiliary_variables","total_variables","clauses","rating_value","cutoff_seconds"):
            row[key]=numeric(row[key],integer=key in ("primary_variables","auxiliary_variables","total_variables","clauses"))
        row.update(configuration=config(row),repetition=int(row["repetition"]),board_side=int(row["board_side"]),par2_seconds=row["total_seconds"] if row["status"]=="SAT" else 20. if row["status"]=="TIMEOUT" else None)
        checked.append(row)
    require({f"solutions/{r['attempt_id']}.json" for r in rows if r["status"]=="SAT"}=={k for k in inventory if k.startswith("solutions/")},"Extra/dangling solution artifact")
    for batch in batches:
        bid=batch["batch_id"];q=quality[bid]
        states.append(dict(batch_id=bid,expected_jobs=db_blocks[bid]["expected_jobs"],observed_primary_jobs=sum(r["batch_id"]==bid for r in checked),execution_complete=q["execution_complete"] and bid in selected,qa_complete=q["qa_complete"] and bid in selected,reason="eligible" if bid in selected and q["qa_complete"] else q["reason"] or "unselected"))
    internal=dict(meta,selection_mode="complete_blocks" if meta["mode"]=="complete-blocks" else "all",config=manifest["config"],snapshot_state=db["experiment"][0]["state"],halt_reason=db["experiment"][0]["halt_reason"],target_counts=dict(puzzles=16000 if meta["phase"]=="main" else 28,jobs=330000 if meta["phase"]=="main" else 164))
    return internal,checked,states,index,selected_attempts,inventory,chosen_jobs


def analyze_expanded(export_dir, output_dir):
    export, output = Path(export_dir).resolve(), Path(output_dir).resolve()
    require(export != output and not output.is_relative_to(export), "Output must be separate from immutable export")
    require(not output.exists(), "Output directory already exists")
    meta, rows, blocks, index, attempts, inventory, planned_jobs = _validate(export)
    if meta["artificial"]:
        allowed = ROOT / "diagnostics/expansion"
        import tempfile
        require(output.is_relative_to(allowed) or output.is_relative_to(Path(tempfile.gettempdir()).resolve()), "Artificial output restricted to diagnostics/expansion or test temp")
    qa = {b["batch_id"] for b in blocks if b["qa_complete"]}
    included = [r for r in rows if r["batch_id"] in qa and meta["phase"] == "main"]
    by_instance = defaultdict(list)
    for job in planned_jobs.values():
        by_instance[(job["instance_id"],job["configuration"])]
    for row in rows:
        by_instance[(row["instance_id"], row["configuration"])].append(row)
    instances, eligible = [], {}
    all_configs = sorted({j["configuration"] for j in planned_jobs.values()})
    for (iid, configuration), group in sorted(by_instance.items()):
        rec=index[iid]
        r = group[0] if group else dict(board_side=rec["N"], **{k:"" if rec[k] is None else str(rec[k]) for k in STRATA if k!="board_side"},batch_id=rec["batch_id"],root_id=rec["root_id"])
        complete = {g["repetition"] for g in group} == {1, 2, 3} and len(group) == 3
        in_main = r["batch_id"] in qa and meta["phase"] == "main"
        sat = in_main and complete and all(g["status"] == "SAT" for g in group)
        penalties = [g["par2_seconds"] for g in group]
        item = dict(instance_id=iid, configuration=configuration, batch_id=r["batch_id"],
                    **{k: r[k] for k in STRATA}, root_id=r["root_id"] or None,
                    observed_primary_repetitions=len(group), missing_repetitions=[i for i in range(1,(3 if meta["phase"]=="main" else 1)+1) if i not in {g["repetition"] for g in group}],
                    statuses=[g["status"] for g in sorted(group, key=lambda g: g["repetition"])],
                    mixed_status=len({g["status"] for g in group}) > 1,
                    runtime_eligible=sat, par2_eligible=in_main and complete and all(v is not None for v in penalties))
        item.update({"median_" + key: statistics.median(g[key] for g in group) if sat else None for key in METRICS})
        item["par2_seconds"] = statistics.mean(penalties) if item["par2_eligible"] else None
        instances.append(item)
        if sat:
            eligible[iid, configuration] = item
    strata = defaultdict(list)
    for item in instances:
        strata[(item["configuration"], *(item[k] for k in STRATA))].append(item)
    summary = []
    for key, group in sorted(strata.items(), key=lambda p: str(p[0])):
        valid = [i for i in group if i["runtime_eligible"]]
        pvalid = [i for i in group if i["par2_eligible"]]
        item = dict(configuration=key[0], **dict(zip(STRATA, key[1:])), observed_instances=sum(i["observed_primary_repetitions"]>0 for i in group),
                    planned_instances=len(group),observed_instances_with_results=sum(i["observed_primary_repetitions"]>0 for i in group),
                    missing_primary_repetitions=sum(len(i["missing_repetitions"]) for i in group),
                    runtime_instances=len(valid), missing_or_ineligible_instances=len(group)-len(valid),
                    mixed_instances=sum(i["mixed_status"] for i in group),
                    par2_instances=len(pvalid), par2_primary_attempts=3*len(pvalid),
                    mean_instance_par2_seconds=statistics.mean(i["par2_seconds"] for i in pvalid) if pvalid else None,
                    root_clusters=len({i["root_id"] for i in group if i["root_id"]}))
        for metric in METRICS:
            values = [i["median_" + metric] for i in valid]
            for label, p in (("median", .5), ("p90", .9), ("p95", .95)):
                item[label + "_" + metric] = quantile_type7(values, p)
        summary.append(item)
    paired = []
    for a, b in itertools.combinations(all_configs, 2):
        paired_groups = defaultdict(list)
        for iid in index:
            if (iid, a) in eligible and (iid, b) in eligible:
                paired_groups[tuple(eligible[iid, a][k] for k in STRATA)].append(iid)
        for key, ids in sorted(paired_groups.items(), key=lambda p: str(p[0])):
            av = [eligible[i, a]["median_total_seconds"] for i in ids]
            bv = [eligible[i, b]["median_total_seconds"] for i in ids]
            paired.append(dict(configuration_a=a, configuration_b=b, **dict(zip(STRATA, key)),
                               matched_instances=len(ids), instance_ids=ids,
                               median_a_seconds=quantile_type7(av,.5), median_b_seconds=quantile_type7(bv,.5),
                               median_paired_a_over_b=quantile_type7([x/y for x,y in zip(av,bv)],.5) if all(y>0 for y in bv) else None,
                               cluster_ids=sorted({eligible[i,a]["root_id"] or i for i in ids})))
    planned = sum(b["expected_jobs"] for b in blocks)
    coverage = dict(target_counts=meta["target_counts"], matrix_planned_jobs=planned,
                    selected_matrix_jobs=len(planned_jobs),
                    selected_blocks=meta["selected_blocks"], selected_complete_blocks=sorted(qa),
                    selected_complete_jobs=sum(b["expected_jobs"] for b in blocks if b["qa_complete"]),
                    observed_primary_jobs=len(rows), solved_primary_jobs=sum(r["status"] == "SAT" for r in rows),
                    any_sat_instance_configurations=sum(any(s == "SAT" for s in i["statuses"]) for i in instances),
                    all_three_sat_instance_configurations=len(eligible),
                    observed_unique_instances=len({r["instance_id"] for r in rows}),
                    complete_block_unique_instances=len({r["instance_id"] for r in included}),
                    status_counts={s:sum(r["status"] == s for r in rows) for s in sorted(STATUS)},
                    historical_interrupted_attempts=sum(a["state"] == "INTERRUPTED" for a in attempts.values()),
                    primary_par2_eligible_attempts=sum(r["par2_seconds"] is not None for r in included),
                    primary_par2_sum_seconds=sum(r["par2_seconds"] for r in included if r["par2_seconds"] is not None))
    configuration_coverage=[]
    for configuration in all_configs:
        selected_jobs=[j for j in planned_jobs.values() if j["configuration"]==configuration]
        observed=[r for r in rows if r["configuration"]==configuration]
        configuration_coverage.append(dict(configuration=configuration,selected_matrix_jobs=len(selected_jobs),
            observed_primary_jobs=len(observed),missing_primary_jobs=len(selected_jobs)-len(observed),
            selected_instances=len({j["instance_id"] for j in selected_jobs}),
            any_sat_instances=len({r["instance_id"] for r in observed if r["status"]=="SAT"}),
            all_three_sat_instances=sum(i["configuration"]==configuration and i["runtime_eligible"] for i in instances),
            status_counts=dict(Counter(r["status"] for r in observed))))
    coverage["by_configuration"]=configuration_coverage
    report_ready = meta["phase"] == "main" and not meta["artificial"] and meta["selection_mode"] == "complete_blocks" and bool(qa)
    label = "ARTIFICIAL_DIAGNOSTIC" if meta["artificial"] else "PILOT_ONE_REPETITION" if meta["phase"] == "pilot" else "COMPLETE_BLOCKS" if report_ready else "PARTIAL_NOT_REPORT_READY"
    summary_dict = dict(analysis_api_version=2, schema_version=2, experiment_id=meta["experiment_id"], dataset_id=meta["dataset_id"],
                        phase=meta["phase"], artificial=meta["artificial"], report_ready=report_ready, label=label,
                        scientific_sha256=meta["manifest"]["scientific_sha256"],config=meta["config"],snapshot_state=meta["snapshot_state"],halt_reason=meta["halt_reason"],
                        coverage=coverage, uncertainty={"estimated":False,"reason":"No confidence intervals estimated; repetitions are not independent puzzles", "synthetic_unit":"root_id with all five masks jointly within N/family", "public_unit":"instance_id"},
                        statistics={"quantile":"type7 over per-instance three-SAT medians", "par2":"SAT observed total; TIMEOUT 20; other statuses and interrupted attempts excluded", "paired":"same IDs/strata/QA blocks; median instance A/B ratios"},
                        input_hashes=inventory, hashes_json_sha256=digest(export/"hashes.json"))
    output.mkdir(parents=True, exist_ok=False)
    table(output/"instances.csv", instances)
    table(output/"strata.csv", summary)
    table(output/"matched-pairs.csv", paired)
    table(output/"blocks.csv", blocks)
    table(output/"coverage.csv", configuration_coverage)
    table(output/"primary-par2.csv", [{k:r[k] for k in ("job_id","attempt_id","instance_id","configuration","repetition","batch_id","status","par2_seconds")} for r in rows])
    clusters = defaultdict(list)
    for iid,r in index.items():
        clusters[(r["N"],r["family"],r["root_id"] or iid,r["batch_id"])].append(iid)
    table(output/"clusters.csv", [dict(board_side=k[0],family=k[1],cluster_id=k[2],batch_id=k[3],instance_ids=ids)
                                  for k,ids in sorted(clusters.items(),key=lambda p:str(p[0]))])
    (output/"summary.json").write_text(json.dumps(summary_dict,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    # Producer receipt is the final publication step, never a root-acceptance claim.
    receipt_files=("summary.json",*OUTPUT_COLUMNS)
    receipt=dict(schema_version=2,files_sha256={name:digest(output/name) for name in receipt_files},
                 upstream_export_hashes_json_sha256=summary_dict["hashes_json_sha256"])
    require(len(receipt["files_sha256"])==8 and all(digest(output/name)==value for name,value in receipt["files_sha256"].items()),"Incomplete analysis output receipt")
    temporary=output/"analysis-hashes.json.tmp"
    temporary.write_text(json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    temporary.replace(output/"analysis-hashes.json")
    return summary_dict


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    try:
        result=analyze_expanded(args.export,args.output)
    except (ValueError,KeyError,OSError,sqlite3.Error) as exc:
        parser.exit(2,f"Analysis rejected export: {exc}\n")
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))

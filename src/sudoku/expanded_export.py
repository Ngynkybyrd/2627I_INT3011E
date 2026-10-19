"""Consistent schema2 SQLite backup -> CSV/solution export, no solver calls."""
import csv
import json
from pathlib import Path
import sqlite3
import uuid
from sudoku.expanded_common import *
from sudoku import expanded_storage as storage


def csv_write(path, fields, rows):
    with path.open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def export_snapshot(experiment_dir, output_dir, *, complete_blocks=False):
    from sudoku.expanded_runner import _load
    directory=Path(experiment_dir).resolve(); output=Path(output_dir).resolve()
    require(not output.exists(),"Export destination already exists")
    require(not output.is_relative_to(directory),"Export must be separate from live experiment")
    staging=output.with_name(output.name+".incomplete-"+uuid.uuid4().hex)
    staging.mkdir(parents=True,exist_ok=False)
    live=storage.connect(directory,readonly=True)
    snapshot=sqlite3.connect(staging/"snapshot.sqlite3")
    try: live.backup(snapshot)
    finally: live.close(); snapshot.close()
    db=sqlite3.connect(staging/"snapshot.sqlite3",isolation_level=None)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        manifest,index=_load(directory,db,verify_fingerprint=False,verify_results=False)
        require(not (manifest["artificial"] and output.is_relative_to(ROOT/"results")),"Artificial export cannot use results/")
        if complete_blocks:
            require(manifest["phase"]=="main","Complete-block report export requires main phase")
        observed=[]; valid_blocks=set(); reasons={}
        checked_solutions={}
        checkpoints={}
        for row in db.execute("SELECT attempt_id,details_json FROM events WHERE type='CHECKPOINT' ORDER BY event_id"):
            checkpoints.setdefault(row["attempt_id"],json.loads(row["details_json"])["checkpoint_seconds"])
        for r in storage.checked_primary_results(db,index):
            if r["status"]=="SAT":
                checked_solutions[r["attempt_id"]]=r["payload"]
            observed.append(r)
        for bid,quality in storage.assess_blocks(db).items():
            if quality["qa_complete"]: valid_blocks.add(bid)
            else: reasons[bid]=quality["reason"]
        selected_blocks=[b["batch_id"] for b in index["batches"] if not complete_blocks or b["batch_id"] in valid_blocks]
        selected_set=set(selected_blocks)
        observations=[r for r in observed if r["batch_id"] in selected_set]
        exported=[]
        (staging/"solutions").mkdir()
        for r in observations:
            record=index["records"][r["instance_id"]]; result=r["result"]
            out=dict.fromkeys(CSV_FIELDS)
            out.update(schema_version=2,experiment_id=manifest["experiment_id"],dataset_id=manifest["dataset_id"],phase=manifest["phase"],cutoff_seconds=manifest["config"]["cutoff_seconds"])
            out.update({k:r[k] for k in ("batch_id","job_id","attempt_id","attempt_no","instance_id","method","encoding","repetition","attempt_wall_seconds")})
            out.update(block_side=record["n"],board_side=record["N"])
            for k in ("source","source_group","rating_original","rating_value","family","root_id","clue_percent_requested","actual_clues","input_sha256"): out[k]=record[k]
            for k in ("status","raw_status","build_seconds","solve_seconds","total_seconds","guard_phase","error"): out[k]=result.get(k)
            stats=result.get("stats") or {}
            for k in ("primary_variables","auxiliary_variables","total_variables","clauses"): out[k]=stats.get(k)
            validation=result.get("validation")
            if validation is not None:
                out.update(validation="pass" if validation["valid"] else "fail",validation_message=validation.get("message"))
            out["checkpoint_seconds"]=checkpoints.get(r["attempt_id"])
            if r["status"]=="SAT":
                ref=f"solutions/{r['attempt_id']}.json"
                (staging/ref).write_bytes(checked_solutions[r["attempt_id"]])
                out.update(solution_ref=ref,solution_sha256=r["solution_hash"])
            exported.append(out)
        csv_write(staging/"results.csv",CSV_FIELDS,exported)
        attempts=[]
        for row in db.execute("""SELECT a.*,j.instance_id,j.method,j.encoding,j.repetition,i.batch_id,r.status,
            CASE WHEN p.attempt_id IS NULL THEN 0 ELSE 1 END AS is_primary
            FROM attempts a JOIN jobs j USING(job_id) JOIN instances i USING(instance_id)
            LEFT JOIN results r USING(attempt_id) LEFT JOIN primary_attempt p ON p.attempt_id=a.attempt_id
            ORDER BY j.ordinal,a.attempt_no"""):
            if row["batch_id"] in selected_set:
                value=dict(row)
                value["solution_ref"]=f"solutions/{row['attempt_id']}.json" if row["status"]=="SAT" else None
                attempts.append(value)
        afields="attempt_id job_id instance_id method encoding repetition batch_id attempt_no session_id state started_utc ended_utc attempt_wall_seconds interruption_reason is_primary status solution_ref".split()
        csv_write(staging/"attempts.csv",afields,attempts)
        jobs=[dict(row) for row in db.execute("SELECT j.*,i.batch_id FROM jobs j JOIN instances i USING(instance_id) ORDER BY j.ordinal") if row["batch_id"] in selected_set]
        csv_write(staging/"jobs.csv","job_id instance_id configuration method encoding repetition ordinal state batch_id".split(),jobs)
        write(staging/"matrix.json",manifest["matrix"])
        write(staging/"batches.json",index["batches"])
        with (staging/"manifest.jsonl").open("w",encoding="utf-8") as stream:
            for record in index["records"].values(): stream.write(dumps(record)+"\n")
        audit=dict(schema_version=2,experiment_id=manifest["experiment_id"],dataset_id=manifest["dataset_id"],phase=manifest["phase"],artificial=manifest["artificial"],
          mode="complete-blocks" if complete_blocks else "partial",report_ready=complete_blocks and not manifest["artificial"] and bool(selected_blocks),
          selected_blocks=selected_blocks,selected_jobs=[j["job_id"] for j in jobs],observed_primary_jobs=[r["job_id"] for r in observations],
          attempt_ids=[a["attempt_id"] for a in attempts],qa_complete_blocks=sorted(valid_blocks),excluded_blocks=reasons,
          planned_blocks=len(index["batches"]),planned_jobs=db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
          last_event_id=db.execute("SELECT COALESCE(MAX(event_id),0) FROM events").fetchone()[0],
          manifest=manifest,notice="ARTIFICIAL" if manifest["artificial"] else "PILOT" if manifest["phase"]=="pilot" else "MAIN COMPLETE BLOCKS ONLY" if complete_blocks else "PARTIAL NOT REPORT READY")
        write(staging/"export.json",audit)
    finally: db.close()
    hashes={str(p.relative_to(staging)).replace("\\","/"):sha(p) for p in sorted(staging.rglob("*")) if p.is_file()}
    write(staging/"hashes.json",dict(schema_version=2,files_sha256=hashes))
    receipt=sha(staging/"hashes.json")
    require(not output.exists(),"Export destination appeared during export")
    staging.rename(output)
    return dict(output_dir=str(output),selected_blocks=selected_blocks,selected_jobs=len(jobs),hashes_sha256=receipt,exit_code=0)

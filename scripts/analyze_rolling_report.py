"""Read a SAT07 verified rolling snapshot; single-repeat subset, never live DB."""
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

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from sudoku.model import parse_puzzle
from sudoku.validation import check_solution

CORE="schema_version experiment_id dataset_id phase batch_id job_id attempt_id attempt_no instance_id method encoding repetition block_side board_side source source_group rating_original rating_value family root_id clue_percent_requested actual_clues input_sha256 cutoff_seconds status raw_status build_seconds solve_seconds total_seconds attempt_wall_seconds checkpoint_seconds primary_variables auxiliary_variables total_variables clauses validation validation_message solution_ref solution_sha256 guard_phase error".split()
EXTRA="session_id profile workers timing_policy".split()
STRATA=("board_side","source","source_group","clue_percent_requested","family")


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    def invalid(value):raise ValueError("Nonfinite JSON: "+value)
    return json.loads(path.read_text(encoding="utf-8-sig"),parse_constant=invalid)


def contained(root,relative):
    require(isinstance(relative,str) and relative and not Path(relative).is_absolute(),"Expected relative artifact path")
    result=(root/relative).resolve()
    require(result.is_relative_to(root.resolve()),"Path escapes snapshot/dataset")
    return result


def read_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as stream:
        reader=csv.DictReader(stream)
        require(reader.fieldnames==CORE+EXTRA,"Rolling CSV wire mismatch")
        rows=list(reader)
    require(all(None not in r and None not in r.values() for r in rows),"Malformed rolling CSV")
    return rows


def config(row):return row["method"]+(":"+row["encoding"] if row["encoding"] else "")


def number(value):
    if value in (None,""):return None
    result=float(value)
    require(math.isfinite(result) and result>=0,"Invalid finite timing")
    return result


def same_number(raw,value):
    return number(raw)==value


def read_verified_snapshot(directory):
    directory=Path(directory).resolve()
    require((directory/"snapshot.json").exists(),"Verified snapshot required; live directories are not inputs")
    snapshot=load(directory/"snapshot.json")
    require(snapshot.get("schema_version")==1 and snapshot.get("kind")=="VERIFIED_ROLLING_SNAPSHOT" and snapshot.get("qa_passed") is True,"Unverified rolling snapshot")
    require(snapshot.get("full_experiment_complete") is False and snapshot.get("selected_repetitions")==[1] and snapshot.get("effective_repetitions")==1 and snapshot.get("original_repetitions")==3,"Not the accepted single-repeat subset")
    require(snapshot["target_jobs"]==110000 and snapshot["target_instances"]==16000,"Rolling target metadata mismatch")
    hashes=snapshot["files_sha256"]
    names={"results.csv","instances.jsonl","snapshot.sqlite3","source-manifest.json","source-index.json","profiles.json"}
    require(names<=hashes.keys() and "snapshot.json" not in hashes,"Incomplete/recursive snapshot hashes")
    require(not any(name.startswith("snapshot.sqlite3-") for name in hashes),"Snapshot must be standalone")
    for name,expected in hashes.items():require(sha(contained(directory,name))==expected,"Snapshot hash mismatch: "+name)
    manifest=load(directory/"source-manifest.json");index=load(directory/"source-index.json")
    artificial=manifest.get("artificial") is True
    require(manifest["schema_version"]==2 and manifest["experiment_id"]==snapshot["source_experiment_id"] and manifest["scientific_sha256"]==snapshot["source_scientific_sha256"],"Source manifest identity mismatch")
    require(manifest["phase"]=="main" and manifest["config"]["repetitions"]==3 and manifest["config"]["cutoff_seconds"]==10,"Original scientific protocol changed")
    require(index["dataset_id"]==manifest["dataset_id"] and index["freeze_sha256"]==manifest["dataset_freeze_sha256"],"Source index/freeze mismatch")
    records=index["records"];batches=index["batches"]
    selected=[b["batch_id"] for b in batches[:3]]
    require(len(selected)==3 and snapshot["selected_batch_ids"]==selected,"Selector must be first three frozen batches")
    selected_ids=[iid for b in batches[:3] for iid in b["instance_ids"]]
    chosen=[json.loads(line) for line in (directory/"instances.jsonl").read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    require(len(selected_ids)==len(set(selected_ids))==len(chosen) and {r["instance_id"]:r for r in chosen}=={i:records[i] for i in selected_ids},"Selected instance snapshot mismatch")
    eligible=defaultdict(list)
    for cell in manifest["matrix"]["rows"]:
        if cell["eligible"]:eligible[cell["N"]].append(cell)
    expected={(iid,c["method"],c.get("encoding") or "",1) for iid in selected_ids for c in eligible[records[iid]["N"]]}
    require(len(expected)==sum(len(eligible[records[i]["N"]]) for i in selected_ids),"Duplicate matrix identities")
    if not artificial:
        require(len(records)==16000 and sum(len(eligible[r["N"]]) for r in records.values())==110000,"Full rep1 matrix target mismatch")
    rows=read_csv(directory/"results.csv")
    require(len(rows)==len(expected)==snapshot["expected_jobs"]==snapshot["observed_jobs"] and len(chosen)==snapshot["selected_instances"],"Subset missing jobs/instances")
    require({(r["instance_id"],r["method"],r["encoding"],int(r["repetition"])) for r in rows}==expected,"Missing/duplicate/non-rep1 job")
    require(len({r["job_id"] for r in rows})==len(rows)==len({r["attempt_id"] for r in rows}),"Duplicate primary job/attempt")
    profile_file=load(directory/"profiles.json")
    profiles=profile_file.get("sessions",profile_file)
    require(isinstance(profiles,dict),"profiles.json must map session IDs")
    db=sqlite3.connect((directory/"snapshot.sqlite3").as_uri()+"?mode=ro&immutable=1",uri=True);db.row_factory=sqlite3.Row
    try:
        require(db.execute("PRAGMA user_version").fetchone()[0]==2 and db.execute("PRAGMA integrity_check").fetchone()[0]=="ok" and not db.execute("PRAGMA foreign_key_check").fetchall(),"Snapshot SQLite integrity failure")
        saved=db.execute("SELECT manifest_json FROM experiment WHERE experiment_id=?",(manifest["experiment_id"],)).fetchall()
        require(len(saved)==1 and json.loads(saved[0][0])==manifest,"Snapshot scientific manifest mismatch")
        sql="""SELECT j.*,a.attempt_id,a.attempt_no,a.session_id,r.status,r.result_json,s.payload,s.sha256
        FROM primary_attempt p JOIN jobs j USING(job_id) JOIN attempts a ON a.attempt_id=p.attempt_id
        JOIN results r ON r.attempt_id=p.attempt_id LEFT JOIN solutions s ON s.attempt_id=r.attempt_id
        JOIN instances i USING(instance_id) WHERE j.repetition=1 AND i.batch_id IN (?,?,?) ORDER BY j.ordinal"""
        committed={r["job_id"]:dict(r) for r in db.execute(sql,selected)}
        require(set(committed)=={r["job_id"] for r in rows},"CSV/primary snapshot set mismatch")
        require([r["job_id"] for r in rows]==list(committed),"CSV/schedule order mismatch")
        parsed=[];puzzles={}
        for raw in rows:
            row=dict(raw);stored=committed[row["job_id"]];record=records[row["instance_id"]]
            require(row["schema_version"]=="2" and row["experiment_id"]==manifest["experiment_id"] and row["dataset_id"]==manifest["dataset_id"] and row["phase"]=="main","Row scientific identity mismatch")
            require(row["status"] in ("SAT","TIMEOUT") and row["status"]==stored["status"],"Only checked SAT/TIMEOUT primary observations may be used")
            require(all(row[k]==str(stored[k]) for k in ("attempt_id","attempt_no","instance_id","method","encoding","repetition","session_id")),"Row primary/session identity mismatch")
            require(row["batch_id"]==record["batch_id"] and row["batch_id"] in selected and int(row["board_side"])==record["N"] and int(row["block_side"])==record["n"],"Row batch/dimension mismatch")
            for key in ("source","source_group","rating_original","family","root_id","clue_percent_requested","actual_clues","input_sha256"):
                require(row[key]==("" if record[key] is None else str(record[key])),"Row stratum/hash mismatch: "+key)
            require(row["session_id"] in profiles,"Missing session profile evidence")
            profile=profiles[row["session_id"]]
            require(row["profile"]==profile["profile"] and int(row["workers"])==profile["workers"] and profile["workers"] in (1,4),"Session profile/workers mismatch")
            require(isinstance(row["timing_policy"],str) and bool(row["timing_policy"]),"Timing policy required")
            if "timing_policy" in profile:require(row["timing_policy"]==profile["timing_policy"],"Session timing policy mismatch")
            result=json.loads(stored["result_json"])
            for key in ("build_seconds","solve_seconds","total_seconds"):
                row[key]=number(row[key]);require(row[key]==result.get(key),"CSV/SQLite timing mismatch")
            b,s,t=(row[k] for k in ("build_seconds","solve_seconds","total_seconds"))
            if all(v is not None for v in (b,s,t)):require(math.isclose(b+s,t,rel_tol=1e-7,abs_tol=1e-7),"Timing sum mismatch")
            require(number(row["cutoff_seconds"])==10 and row["guard_phase"]==result.get("guard_phase"),"Cutoff/guard mismatch")
            require(row["guard_phase"]!="cleanup","Cleanup failure cannot enter report")
            if row["status"]=="SAT":
                require(t is not None and b is not None and s is not None and t<=10 and row["guard_phase"]=="complete" and row["validation"]=="pass" and (result.get("validation") or {}).get("valid") is True,"Unchecked/late SAT")
                require(isinstance(stored["payload"],bytes) and hashlib.sha256(stored["payload"]).hexdigest()==stored["sha256"]==row["solution_sha256"],"Stored solution hash mismatch")
                grid=json.loads(stored["payload"])
                iid=row["instance_id"]
                if iid not in puzzles:
                    input_path=contained(Path(index["dataset_dir"]),record["input_file"])
                    require(sha(input_path)==record["input_sha256"],"Original puzzle bytes changed")
                    puzzles[iid]=parse_puzzle(load(input_path))
                require(grid["n"]==record["n"] and check_solution(puzzles[iid],grid["grid"]).valid,"Independent solution checker failed")
            else:
                require(stored["payload"] is None and not row["solution_sha256"] and row["guard_phase"] in ("measurement","complete"),"Invalid TIMEOUT solution/phase")
            row.update(configuration=config(row),workers=int(row["workers"]),board_side=int(row["board_side"]),par2_seconds=t if row["status"]=="SAT" else 20.,resource_contention="resource-contended" if int(row["workers"])==4 else "sequential")
            parsed.append(row)
    finally:db.close()
    return snapshot,parsed,artificial,profiles


def tex(value):
    mapping={"\\":r"\textbackslash{}","_":r"\_","&":r"\&","%":r"\%","#":r"\#","$":r"\$","{":r"\{","}":r"\}","~":r"\textasciitilde{}","^":r"\textasciicircum{}"}
    return "".join(mapping.get(c,c if c not in "\r\n\t" else " ") for c in str(value))


def write_csv(path,rows,fields):
    with path.open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()} for row in rows)


def native_table(path,rows,columns):
    lines=[r"\begin{tabular}{"+"l"*len(columns)+"}",r"\hline"," & ".join(tex(k) for k in columns)+r" \\",r"\hline"]
    for row in rows:lines.append(" & ".join("--" if row[k] is None else f"{row[k]:.6f}" if isinstance(row[k],float) else tex(row[k]) for k in columns)+r" \\")
    lines.extend([r"\hline",r"\end{tabular}"]);path.write_text("\n".join(lines)+"\n",encoding="utf-8")


def analyze_rolling(snapshot_dir,output_dir):
    source,output=Path(snapshot_dir).resolve(),Path(output_dir).resolve()
    require(not output.exists() and output!=source and not output.is_relative_to(source),"Output must be NEW and outside snapshot")
    snapshot,rows,artificial,profiles=read_verified_snapshot(source)
    require(not artificial or output.is_relative_to(ROOT/"diagnostics/expansion/rolling-analysis") or "pytest" in str(output),"Artificial output must stay diagnostic")
    require(artificial or output==ROOT/"results/rolling-analysis/rolling-20261019-first3","Real output ownership path mismatch")
    group=defaultdict(list);profile_groups=defaultdict(list)
    for r in rows:
        key=(r["profile"],r["session_id"],r["workers"],r["timing_policy"],r["configuration"],*(r[k] for k in STRATA))
        group[key].append(r);profile_groups[key[:4]].append(r)
    summaries=[]
    for key,g in sorted(group.items(),key=lambda item:str(item[0])):
        sat=[r for r in g if r["status"]=="SAT"]
        summaries.append(dict(profile=key[0],session_id=key[1],workers=key[2],timing_policy=key[3],configuration=key[4],**dict(zip(STRATA,key[5:])),observed_jobs=len(g),sat_jobs=len(sat),timeout_jobs=len(g)-len(sat),single_run_instances=len(g),median_single_run_total_seconds=statistics.median(r["total_seconds"] for r in sat) if sat else None,mean_par2_seconds=statistics.mean(r["par2_seconds"] for r in g),par2_primary_denominator=len(g)))
    paired=[]
    for profile_key,g in sorted(profile_groups.items(),key=lambda item:str(item[0])):
        configs=sorted({r["configuration"] for r in g})
        values={(r["instance_id"],r["configuration"]):r for r in g if r["status"]=="SAT"}
        for a,b in itertools.combinations(configs,2):
            sets=defaultdict(list)
            for iid in {r["instance_id"] for r in g}:
                if (iid,a) in values and (iid,b) in values:sets[tuple(values[iid,a][k] for k in STRATA)].append(iid)
            for stratum,ids in sorted(sets.items(),key=lambda item:str(item[0])):
                ids.sort();ratios=[values[i,a]["total_seconds"]/values[i,b]["total_seconds"] for i in ids if values[i,b]["total_seconds"]>0]
                paired.append(dict(profile=profile_key[0],session_id=profile_key[1],workers=profile_key[2],timing_policy=profile_key[3],configuration_a=a,configuration_b=b,**dict(zip(STRATA,stratum)),matched_instances=len(ids),instance_ids=ids,median_single_run_a_over_b=statistics.median(ratios) if len(ratios)==len(ids) else None))
    coverage=[]
    for key,g in sorted(profile_groups.items(),key=lambda item:str(item[0])):
        counts=Counter(r["status"] for r in g)
        coverage.append(dict(profile=key[0],session_id=key[1],workers=key[2],timing_policy=key[3],resource_contention="resource-contended" if key[2]==4 else "sequential",observed_jobs=len(g),observed_instances=len({r["instance_id"] for r in g}),sat_jobs=counts["SAT"],timeout_jobs=counts["TIMEOUT"],mean_par2_seconds=statistics.mean(r["par2_seconds"] for r in g)))
    summary=dict(schema_version=1,kind="VERIFIED_SUBSET",artificial=artificial,full_experiment_complete=False,effective_repetitions=1,original_repetitions=3,target_jobs=snapshot["target_jobs"],target_instances=snapshot["target_instances"],source_experiment_id=snapshot["source_experiment_id"],selected_batch_ids=snapshot["selected_batch_ids"],selected_instances=snapshot["selected_instances"],expected_jobs=snapshot["expected_jobs"],observed_jobs=len(rows),status_counts=dict(Counter(r["status"] for r in rows)),profiles=coverage,statistics="Median across single-run SAT instances within profile/session/stratum; no median of three repetitions; PAR2 SAT total/TIMEOUT20; paired IDs within same profile/session only",limitations=["first three fixed batches only; target not achieved claim","4 workers with solver threads 1 are resource-contended","no cross-profile speedup or stability claim","no confidence intervals; masks remain linked by root_id"],snapshot_sha256=sha(source/"snapshot.json"),upstream_files_sha256=snapshot["files_sha256"])
    output.mkdir(parents=True)
    write_csv(output/"coverage.csv",coverage,list(coverage[0]))
    write_csv(output/"strata.csv",summaries,list(summaries[0]))
    paired_fields=["profile","session_id","workers","timing_policy","configuration_a","configuration_b",*STRATA,"matched_instances","instance_ids","median_single_run_a_over_b"]
    write_csv(output/"matched-pairs.csv",paired,paired_fields)
    instance_fields=["instance_id","configuration","batch_id","session_id","profile","workers","timing_policy",*STRATA,"root_id","status","build_seconds","solve_seconds","total_seconds","par2_seconds"]
    write_csv(output/"instances.csv",[{k:r[k] for k in instance_fields} for r in rows],instance_fields)
    native_table(output/"coverage.tex",coverage,["profile","workers","observed_jobs","sat_jobs","timeout_jobs","mean_par2_seconds"])
    native_table(output/"runtime.tex",summaries,["profile","session_id","configuration","board_side","source_group","clue_percent_requested","family","sat_jobs","timeout_jobs","median_single_run_total_seconds","mean_par2_seconds"])
    native_table(output/"paired.tex",paired,["profile","session_id","configuration_a","configuration_b","matched_instances","median_single_run_a_over_b"])
    figure=[r"\begin{tikzpicture}[x=0.07cm,y=0.75cm]",r"\node[anchor=west] at (0,1) {Single-repeat verified subset: observed status counts};"]
    maximum=max(c["observed_jobs"] for c in coverage)
    for y,c in enumerate(coverage):
        sat=100*c["sat_jobs"]/maximum;total=100*c["observed_jobs"]/maximum
        figure.extend([f"\\fill[blue!45] (0,{-y}) rectangle ({sat:.6f},{-y+.35});",f"\\fill[orange!60] ({sat:.6f},{-y}) rectangle ({total:.6f},{-y+.35});",f"\\node[anchor=west,font=\\scriptsize] at (0,{-y-.25}) {{{tex(c['profile'])}; {c['workers']} workers; SAT={c['sat_jobs']}, TIMEOUT={c['timeout_jobs']}; {tex(c['session_id'])}}};"])
    figure.extend([r"\end{tikzpicture}","% Blue=SAT, orange=TIMEOUT. Descriptive coverage, not speedup. Profile/session separate."])
    (output/"coverage-tikz.tex").write_text("\n".join(figure)+"\n",encoding="utf-8")
    (output/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    receipt=dict(schema_version=1,kind="ROLLING_ANALYSIS_RECEIPT",upstream_snapshot_sha256=summary["snapshot_sha256"],files_sha256={p.name:sha(p) for p in sorted(output.iterdir()) if p.is_file()})
    (output/"analysis-hashes.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--snapshot",required=True,type=Path);parser.add_argument("--output",required=True,type=Path);args=parser.parse_args()
    try:
        result=analyze_rolling(args.snapshot,args.output)
    except (ValueError,KeyError,OSError,sqlite3.Error) as exc:parser.exit(2,f"Rolling analysis rejected: {exc}\n")
    print(json.dumps(dict(kind=result["kind"],observed_jobs=result["observed_jobs"],effective_repetitions=1,output=str(args.output))))

"""Final report metric kernel only. Real-export reader awaits SAT07 CONTRACT/PASS."""
from collections import Counter, defaultdict
import math
import statistics
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from sudoku.model import parse_puzzle
from sudoku.validation import check_solution

STATE="WAITING_FOR_EXPORT"
CONTRACT_PATH=ROOT/"diagnostics/expansion/final-export/CONTRACT.json"
STRATA=("profile","session_id","workers","N","source","source_group","family","clue_percent")


def _require(value,message):
    if not value:raise ValueError(message)


def _json(path):
    def reject(value):raise ValueError("Nonfinite JSON: "+value)
    return json.loads(path.read_text(encoding="utf-8-sig"),parse_constant=reject)


def _sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value):return (json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()


def _contained(root,name):
    _require(isinstance(name,str) and name and not Path(name).is_absolute(),"Relative snapshot path required")
    path=(root/name).resolve();_require(path.is_relative_to(root),"Snapshot path escape")
    return path


def _read_final_snapshot(directory,contract):
    """Strict snapshot-only reader; contract argument is internal for focused fixtures."""
    directory=Path(directory).resolve();receipt=_json(directory/"snapshot.json")
    _require(contract["kind"]=="FINAL_EXPANDED_REP1_CONTRACT" and contract["schema_version"]==1,"Unknown final contract")
    _require(_json(directory/"CONTRACT.json")==contract,"Pinned contract mismatch")
    _require(receipt["schema_version"]==1 and receipt["kind"]==contract["receipt_kind"] and receipt["status"]=="PASS","Snapshot QA PASS required")
    for key in ("quality","error_free","selected_scope_observed_complete","original_three_repetition_experiment_complete"):
        _require(receipt[key]==contract[key],"Declared quality/error scope mismatch: "+key)
    _require(receipt["selected_repetitions"]==[1] and receipt["effective_repetitions"]==1 and receipt["original_repetitions"]==3,"Only rep1 from original3 accepted")
    expected=contract["selection"]
    _require(receipt["expected_jobs"]==receipt["observed_jobs"]==expected["expected_jobs"] and receipt["selected_instances"]==expected["expected_instances"],"Scope counts mismatch")
    _require(receipt["primary_counts"]==expected["expected_statuses"],"Primary status count mismatch")
    hashes=receipt["files_sha256"]
    required={"snapshot.sqlite3","inputs.sqlite3","results.csv","instances.jsonl","profiles.json","source-manifest.json","source-index.json","source-freeze.json","CONTRACT.json"}
    _require(required<=hashes.keys() and "snapshot.json" not in hashes,"Missing snapshot receipt files")
    _require(not any(n.endswith(("-wal","-shm")) for n in hashes),"Snapshot SQLite must be standalone")
    for name,h in hashes.items():_require(_sha(_contained(directory,name))==h,"Snapshot hash mismatch: "+name)
    _require({p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file() and p.name!="snapshot.json"}==hashes.keys(),"Uninventoried snapshot file")
    manifest=_json(directory/"source-manifest.json");index=_json(directory/"source-index.json")
    _require(manifest["experiment_id"]==receipt["source_experiment_id"] and manifest["scientific_sha256"]==receipt["source_scientific_sha256"] and manifest["config"]["repetitions"]==3,"Source scientific identity mismatch")
    _require(_sha(directory/"source-freeze.json")==manifest["dataset_freeze_sha256"]==index["freeze_sha256"],"Dataset freeze mismatch")
    records=[json.loads(line) for line in (directory/"instances.jsonl").read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    record_index={r["instance_id"]:r for r in records}
    _require(len(records)==len(record_index)==expected["expected_instances"] and record_index==index["records"],"Full manifest instance identity mismatch")
    profiles=_json(directory/"profiles.json")
    for sid,p in profiles.items():
        name=p["source_session_manifest"]
        _require(name in hashes and hashes[name]==p["source_session_manifest_sha256"],"Session provenance hash mismatch")
    with (directory/"results.csv").open(encoding="utf-8-sig",newline="") as stream:
        reader=csv.DictReader(stream);fields=reader.fieldnames
        core="schema_version experiment_id dataset_id phase batch_id job_id attempt_id attempt_no instance_id method encoding repetition block_side board_side source source_group rating_original rating_value family root_id clue_percent_requested actual_clues input_sha256 cutoff_seconds status raw_status build_seconds solve_seconds total_seconds attempt_wall_seconds checkpoint_seconds primary_variables auxiliary_variables total_variables clauses validation validation_message solution_ref solution_sha256 guard_phase error session_id profile workers timing_policy".split()
        _require(fields==core,"Final CSV columns mismatch");rows=list(reader)
    _require(all(None not in r and None not in r.values() for r in rows),"Malformed CSV")
    _require(len(rows)==len({r["job_id"] for r in rows})==len({r["attempt_id"] for r in rows})==expected["expected_jobs"],"Missing/duplicate primary identity")
    _require(dict(Counter(r["status"] for r in rows))==expected["expected_statuses"],"CSV statuses mismatch")
    raw=sqlite3.connect((directory/"snapshot.sqlite3").as_uri()+"?mode=ro&immutable=1",uri=True);raw.row_factory=sqlite3.Row
    inputs=sqlite3.connect((directory/"inputs.sqlite3").as_uri()+"?mode=ro&immutable=1",uri=True);inputs.row_factory=sqlite3.Row
    try:
        for db in (raw,inputs):_require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok" and not db.execute("PRAGMA foreign_key_check").fetchall(),"SQLite integrity failure")
        _require(raw.execute("PRAGMA user_version").fetchone()[0]==2,"Raw snapshot version mismatch")
        _require(json.loads(raw.execute("SELECT manifest_json FROM experiment").fetchone()[0])==manifest,"Snapshot scientific manifest mismatch")
        committed={r["job_id"]:dict(r) for r in raw.execute("""SELECT j.*,a.attempt_id,a.attempt_no,a.session_id,r.status,r.result_json,s.payload,s.sha256,s.checker_json FROM primary_attempt p JOIN jobs j USING(job_id) JOIN attempts a ON a.attempt_id=p.attempt_id JOIN results r ON r.attempt_id=p.attempt_id LEFT JOIN solutions s ON s.attempt_id=p.attempt_id WHERE j.repetition=1 ORDER BY j.ordinal""")}
        _require([r["job_id"] for r in rows]==list(committed),"CSV primary selector/order mismatch")
        historical={str(rep):raw.execute("SELECT COUNT(*) FROM primary_attempt p JOIN jobs j USING(job_id) WHERE repetition=?",(rep,)).fetchone()[0] for rep in (2,3)}
        _require(historical==expected["excluded_historical_repetitions"],"Historical repetition exclusion mismatch")
        puzzles={}
        _require(inputs.execute("SELECT COUNT(*) FROM inputs").fetchone()[0]==len(record_index),"Frozen input count mismatch")
        for iid,record in record_index.items():
            source=inputs.execute("SELECT * FROM inputs WHERE instance_id=?",(iid,)).fetchone();_require(source is not None,"Missing frozen input")
            decoded={}
            for prefix in ("input","witness"):
                blob=source[prefix+"_payload"];value=json.loads(blob)
                _require(hashlib.sha256(blob).hexdigest()==source[prefix+"_sha256"]==record[prefix+"_sha256"],"Input/witness bytes mismatch")
                _require(hashlib.sha256(_canonical(value)).hexdigest()==source[prefix+"_canonical_sha256"]==record["content_sha256" if prefix=="input" else "witness_content_sha256"],"Canonical input/witness hash mismatch")
                decoded[prefix]=value
            puzzle=parse_puzzle(decoded["input"])
            _require((puzzle.n,puzzle.N)==(source["block_side"],source["board_side"])==(record["n"],record["N"]) and puzzle.clue_count==record["actual_clues"],"Frozen dimensions/clues mismatch")
            _require(check_solution(puzzle,decoded["witness"]["grid"]).valid,"Acquisition witness checker failed");puzzles[iid]=puzzle
        normalized=[]
        for row in rows:
            stored=committed[row["job_id"]];result=json.loads(stored["result_json"]);record=record_index[row["instance_id"]]
            _require(row["repetition"]=="1" and all(row[k]==str(stored[k]) for k in ("instance_id","attempt_id","attempt_no","method","encoding","session_id")),"Primary job/attempt/session mismatch")
            _require(row["status"]==stored["status"]==result["status"],"Stored status mismatch")
            _require(row["guard_phase"]==(result.get("guard_phase") or "") and row["error"]==(result.get("error") or ""),"CSV/stored guard/error mismatch")
            p=profiles[row["session_id"]]
            _require(row["profile"]==p["profile"] and int(row["workers"])==p["workers"] and row["timing_policy"]==p["timing_policy"],"Profile/session worker mismatch")
            for key in ("build_seconds","solve_seconds","total_seconds"):
                value=None if row[key]=="" else float(row[key]);_require(value==result.get(key) and (value is None or math.isfinite(value) and value>=0),"Stored timing mismatch")
            if row["status"]=="SAT":
                _require(row["solution_ref"]==f"sqlite:snapshot.sqlite3#solutions/{row['attempt_id']}" and hashlib.sha256(stored["payload"]).hexdigest()==row["solution_sha256"]==stored["sha256"],"Canonical SQLite solution identity/hash mismatch")
                solution=json.loads(stored["payload"])
                _require(stored["payload"]==_canonical(solution) and solution["n"]==record["n"] and check_solution(puzzles[row["instance_id"]],solution["grid"]).valid and json.loads(stored["checker_json"])["valid"] is True,"SAT checker/canonical payload failed")
                _require(row["validation"]=="pass" and row["guard_phase"]=="complete" and result.get("validation",{}).get("valid") is True,"SAT validation evidence mismatch")
            else:
                _require(not row["solution_ref"] and not row["solution_sha256"] and stored["payload"] is None,"NonSAT dangling solution")
                if row["status"]=="ERROR":
                    declared=receipt["declared_error"]
                    _require(all(row[k]==declared[k] for k in ("job_id","attempt_id","batch_id")),"Undeclared infrastructure ERROR exact identity")
                    pinned=declared["result_json"];pinned=json.loads(pinned) if isinstance(pinned,str) else pinned
                    _require(pinned==result and row["error"]==pinned["error"],"Declared ERROR raw result mismatch")
                    _require(row["guard_phase"]=="guard" and "winerror6" in "".join(row["error"].lower().split()) and result.get("validation") is None and row["validation"]=="" and all(row[k]=="" for k in ("build_seconds","solve_seconds","total_seconds")),"Declared premeasurement guard WinError6 changed")
            normalized.append(dict(instance_id=row["instance_id"],configuration=row["method"]+(":"+row["encoding"] if row["encoding"] else ""),status=row["status"],total_seconds=None if row["total_seconds"]=="" else float(row["total_seconds"]),profile=row["profile"],session_id=row["session_id"],workers=int(row["workers"]),N=record["N"],source=record["source"],source_group=record["source_group"],family=record["family"],clue_percent=record["clue_percent_requested"],root_id=record["root_id"],actual_clues=record["actual_clues"],uniqueness=record["uniqueness"],job_id=row["job_id"],attempt_id=row["attempt_id"],batch_id=row["batch_id"],guard_phase=row["guard_phase"],error=row["error"],build_seconds=None if row["build_seconds"]=="" else float(row["build_seconds"]),solve_seconds=None if row["solve_seconds"]=="" else float(row["solve_seconds"]),**{k:None if row[k]=="" else int(row[k]) for k in ("primary_variables","auxiliary_variables","total_variables","clauses")}))
    finally:raw.close();inputs.close()
    summarize_observations(normalized)
    return dict(state="READER_VALIDATED_WITH_DECLARED_ERROR",receipt=receipt,observations=normalized,contract_sha256=_sha(directory/"CONTRACT.json"),snapshot_sha256=_sha(directory/"snapshot.json"))


def read_final_snapshot(directory):
    return _read_final_snapshot(directory,_json(CONTRACT_PATH))


def quantile_type7(values,p):
    values=sorted(values)
    if not values:return None
    h=(len(values)-1)*p;a,b=math.floor(h),math.ceil(h)
    return values[a]+(h-a)*(values[b]-values[a])


def summarize_observations(rows):
    """Internal normalized 1-rep fixture records, NOT an assumed producer wire."""
    groups=defaultdict(list);cells=set()
    for row in rows:
        if row["status"] not in ("SAT","TIMEOUT","ERROR"):raise ValueError("Unsupported primary status")
        identity=(row["instance_id"],row["configuration"])
        if identity in cells:raise ValueError("Duplicate primary instance/configuration")
        cells.add(identity)
        value=row["total_seconds"]
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or value<0):raise ValueError("Invalid timing")
        if row["status"]=="SAT" and (value is None or value>10):raise ValueError("SAT requires observed in-cutoff total")
        groups[tuple(row[k] for k in STRATA)+(row["configuration"],)].append(row)
    summary=[]
    for key,group in sorted(groups.items(),key=lambda item:str(item[0])):
        statuses=Counter(r["status"] for r in group);sat=[r["total_seconds"] for r in group if r["status"]=="SAT"]
        summary.append(dict(zip(STRATA+("configuration",),key),observed_primary=len(group),SAT=statuses["SAT"],TIMEOUT=statuses["TIMEOUT"],ERROR=statuses["ERROR"],censored_count=statuses["TIMEOUT"],sat_runtime_instances=len(sat),median_single_run_seconds=quantile_type7(sat,.5),p90_single_run_seconds=quantile_type7(sat,.9),p95_single_run_seconds=quantile_type7(sat,.95),performance_interpretation_allowed=key[2] not in (24,40)))
    return dict(observed_primary=len(rows),status_counts=dict(Counter(r["status"] for r in rows)),effective_repetitions=1,median_of_repetitions_computed=False,strata=summary)


def matched_single_run_pairs(rows):
    summarize_observations(rows)
    groups=defaultdict(dict)
    for row in rows:
        if row["status"]=="SAT" and row["workers"] not in (24,40):groups[tuple(row[k] for k in STRATA)][row["instance_id"],row["configuration"]]=row["total_seconds"]
    import itertools
    result=[]
    for key,observations in sorted(groups.items(),key=lambda item:str(item[0])):
        configs=sorted({c for _,c in observations})
        for a,b in itertools.combinations(configs,2):
            ids=sorted({i for i,c in observations if c==a}&{i for i,c in observations if c==b})
            if not ids:continue
            ratios=[observations[i,a]/observations[i,b] for i in ids if observations[i,b]>0]
            item=dict(zip(STRATA,key),configuration_a=a,configuration_b=b,matched_instances=len(ids),instance_ids=ids,median_single_run_ratio=statistics.median(ratios) if len(ratios)==len(ids) else None)
            for name,c in (("a",a),("b",b)):
                values=[observations[i,c] for i in ids]
                for label,p in (("median",.5),("p90",.9),("p95",.95)):item[label+"_"+name+"_single_run_seconds"]=quantile_type7(values,p)
            result.append(item)
    return result


def write_compact_tables(output,status_rows,cnf_rows,profile_rows,main_pairs):
    """Short headers/labels for cas-sc; exact identities remain in CSV artifacts."""
    labels={"sat:pairwise":"PW","sat:seqcounter":"SC","sat:bitwise":"BW","cpsat":"CP-SAT","highs":"HiGHS","gurobi":"Gurobi","cplex_mip":"CPLEX","cpoptimizer":"CPO"}
    def emit(name,rows):
        cols=list(rows[0]);lines=[r"\begin{tabular}{"+"l"*len(cols)+"}",r"\hline"," & ".join(cols)+r" \\",r"\hline"]
        for row in rows:
            values=["--" if v is None or v=="" else f"{v:.6f}" if isinstance(v,float) else str(v) for v in row.values()]
            lines.append(" & ".join(values)+r" \\")
        (Path(output)/name).write_text("\n".join(lines+[r"\hline",r"\end{tabular}"])+"\n",encoding="utf-8")
    emit("coverage-main.tex",[dict(N=r["N"],Method=labels[r["configuration"]],Jobs=r["observed_primary"],SAT=r["SAT"],TO=r["TIMEOUT"],Err=r["ERROR"]) for r in status_rows])
    emit("encoding-counts-main.tex",[dict(N=r["N"],Encoding=labels[r["configuration"]],Primary=r["measured_primary"],Aux=r["auxiliary_min"],Clauses=r["clauses_without_clues"]) for r in cnf_rows])
    emit("profile-timeline-main.tex",[dict(Session=r["session_id"][:8],W=r["workers"],Jobs=r["observed_primary"],SAT=r["SAT"],TO=r["TIMEOUT"],Err=r["ERROR"]) for r in profile_rows])
    emit("runtime-common-compact.tex",[dict(Pair=labels[r["configuration_a"]]+"/"+labels[r["configuration_b"]],n=r["matched_instances"],**{"A med":float(r["median_a_single_run_seconds"]),"A p95":float(r["p95_a_single_run_seconds"]),"B med":float(r["median_b_single_run_seconds"]),"B p95":float(r["p95_b_single_run_seconds"]),"Ratio":float(r["median_single_run_ratio"])}) for r in main_pairs])


def analyze_final_report(snapshot_dir,output_dir):
    directory=Path(snapshot_dir).resolve();output=Path(output_dir).resolve()
    if directory!=ROOT/"results/final-snapshots/final-20261020-rep1":raise RuntimeError("WAITING_FOR_EXPORT: root-approved final snapshot path required")
    _require(output==ROOT/"results/final-analysis/final-20261020-rep1" and not output.exists(),"NEW owned final output required")
    snapshot_pin="70eaaf0acb6c74ba02f4ca65d8ca3db5d42d83cdbafe6620865d42d5b8af4781"
    provenance_pin="7c11accf78f831d33542b621b06d80d00420cae5fc9a7ec89e291322d9871efc"
    _require(_sha(directory/"snapshot.json")==snapshot_pin,"Root snapshot pin mismatch")
    prov_dir=ROOT/"diagnostics/expansion/final-provenance";prov=_json(prov_dir/"receipt.json")
    _require(_sha(prov_dir/"receipt.json")==provenance_pin and prov["status"]=="PASS","Provenance receipt pin/PASS mismatch")
    for name,h in prov["hashes_sha256"].items():_require(_sha(_contained(prov_dir,name))==h,"Provenance file hash mismatch")
    validated=read_final_snapshot(directory);rows=validated["observations"];receipt=validated["receipt"]
    aggregate=summarize_observations(rows);paired=matched_single_run_pairs(rows)
    records=_json(directory/"source-index.json")["records"];composition=Counter((r["N"],r["source"],r["source_group"],r["family"],r["clue_percent_requested"],r["actual_clues"],r["uniqueness"]) for r in records.values())
    provenance=_json(prov_dir/"counts.json")
    _require(Counter(str(r["N"]) for r in records.values())==provenance["by_N"],"SAT05 composition mismatch")
    # Independent pair audit indexed once; never O(rows * pairs).
    lookup=defaultdict(dict)
    for r in rows:
        if r["status"]=="SAT":lookup[tuple(r[k] for k in STRATA)][r["instance_id"],r["configuration"]]=r["total_seconds"]
    for pair in paired:
        values=lookup[tuple(pair[k] for k in STRATA)];a,b=pair["configuration_a"],pair["configuration_b"]
        common={i for i,c in values if c==a}&{i for i,c in values if c==b}
        _require(common==set(pair["instance_ids"]) and len(common)==pair["matched_instances"],"Independent paired sample audit failed")
        for label,c in (("a",a),("b",b)):
            _require(math.isclose(statistics.median(values[i,c] for i in common),pair["median_"+label+"_single_run_seconds"],abs_tol=1e-12),"Independent matched median audit failed")
    status_nc=defaultdict(Counter);session_groups=defaultdict(list);cnf_groups=defaultdict(list)
    for r in rows:
        status_nc[r["N"],r["configuration"]][r["status"]]+=1
        session_groups[r["session_id"]].append(r)
        if r["configuration"].startswith("sat:") and r["clauses"] is not None:cnf_groups[r["N"],r["configuration"]].append(r)
    status_rows=[dict(N=n,configuration=c,observed_primary=sum(v.values()),SAT=v["SAT"],TIMEOUT=v["TIMEOUT"],ERROR=v["ERROR"],timeout_fraction=v["TIMEOUT"]/sum(v.values())) for (n,c),v in sorted(status_nc.items())]
    _require(sum(r["observed_primary"] for r in status_rows)==110000 and sum(r["ERROR"] for r in status_rows)==1 and sum(r["TIMEOUT"] for r in status_rows)==335,"Independent denominator audit failed")
    composition_rows=[dict(N=k[0],source=k[1],source_group=k[2],family=k[3],clue_percent=k[4],actual_clues=k[5],uniqueness=k[6],instances=n) for k,n in sorted(composition.items(),key=lambda p:str(p[0]))]
    cnf_rows=[]
    for (n,c),g in sorted(cnf_groups.items()):
        bases={r["clauses"]-r["actual_clues"] for r in g}
        _require(len(bases)==1 and {r["primary_variables"] for r in g}=={n**3},"CNF repetition/instance count inconsistency")
        pairwise=4*n*n*(1+n*(n-1)//2) if c=="sat:pairwise" else None
        if pairwise is not None:_require(bases=={pairwise},"Pairwise theoretical/observed count mismatch")
        cnf_rows.append(dict(N=n,configuration=c,observations_with_counts=len(g),theoretical_primary=n**3,measured_primary=n**3,auxiliary_min=min(r["auxiliary_variables"] for r in g),auxiliary_max=max(r["auxiliary_variables"] for r in g),clauses_without_clues=next(iter(bases)),pairwise_theoretical_without_clues=pairwise))
    profiles=_json(directory/"profiles.json")
    db=sqlite3.connect((directory/"snapshot.sqlite3").as_uri()+"?mode=ro&immutable=1",uri=True);db.row_factory=sqlite3.Row
    try:sessions={r["session_id"]:dict(r) for r in db.execute("SELECT * FROM sessions")}
    finally:db.close()
    profile_rows=[]
    for sid,g in session_groups.items():
        p=profiles[sid];s=sessions[sid];counts=Counter(r["status"] for r in g)
        profile_rows.append(dict(session_id=sid,profile=p["profile"],workers=p["workers"],timing_policy=p["timing_policy"],started_utc=s["started_utc"],ended_utc=s["ended_utc"],observed_primary=len(g),SAT=counts["SAT"],TIMEOUT=counts["TIMEOUT"],ERROR=counts["ERROR"],performance_interpretation_allowed=p["workers"] not in (24,40)))
    profile_rows.sort(key=lambda r:r["started_utc"])
    # Output helpers are local; no legacy/pinned analyzer import.
    def table(name,values,fields=None):
        fields=fields or (list(values[0]) if values else [])
        with (output/name).open("w",encoding="utf-8",newline="") as f:
            if not fields:return
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()} for r in values)
    def escape(v):
        mapping={"\\":r"\textbackslash{}","_":r"\_","%":r"\%","&":r"\&","#":r"\#","$":r"\$","{":r"\{","}":r"\}"}
        return "".join(mapping.get(c,c) for c in str(v))
    def latex(name,values,columns):
        text=[r"\begin{tabular}{"+"l"*len(columns)+"}",r"\hline"," & ".join(escape(k) for k in columns)+r" \\",r"\hline"]
        for r in values:text.append(" & ".join("--" if r[k] is None else f"{r[k]:.6f}" if isinstance(r[k],float) else escape(r[k]) for k in columns)+r" \\")
        (output/name).write_text("\n".join(text+[r"\hline",r"\end{tabular}"])+"\n",encoding="utf-8")
    output.mkdir(parents=True)
    table("coverage.csv",aggregate["strata"]);table("status-N-config.csv",status_rows);table("timeouts.csv",[r for r in status_rows if r["TIMEOUT"] or r["ERROR"]])
    table("dataset-composition.csv",composition_rows);table("encoding-counts.csv",cnf_rows);table("profile-timeline.csv",profile_rows)
    table("runtime-common.csv",paired);table("instances.csv",rows)
    table("runtime-common-report.csv",[dict(sample_row=i,**{k:v for k,v in p.items() if k!="instance_ids"}) for i,p in enumerate(paired,2)])
    errors=[r for r in rows if r["status"]=="ERROR"];table("declared-error.csv",errors)
    latex("coverage.tex",status_rows,["N","configuration","observed_primary","SAT","TIMEOUT","ERROR"])
    latex("dataset-composition.tex",composition_rows,["N","source_group","family","clue_percent","actual_clues","instances"])
    latex("encoding-counts.tex",cnf_rows,["N","configuration","theoretical_primary","auxiliary_min","auxiliary_max","clauses_without_clues"])
    latex("profile-timeline.tex",profile_rows,["session_id","workers","observed_primary","SAT","TIMEOUT","ERROR","performance_interpretation_allowed"])
    dominant=max(profile_rows,key=lambda r:r["observed_primary"])
    main_pairs=[p for p in paired if p["session_id"]==dominant["session_id"] and p["N"]==25 and p["family"]=="permutation" and p["clue_percent"]==40]
    latex("runtime-common-main.tex",main_pairs,["configuration_a","configuration_b","matched_instances","median_a_single_run_seconds","p95_a_single_run_seconds","median_b_single_run_seconds","p95_b_single_run_seconds","median_single_run_ratio"])
    table("runtime-common-main.csv",main_pairs)
    write_compact_tables(output,status_rows,cnf_rows,profile_rows,main_pairs)
    size_counts={n:Counter(r["status"] for r in rows if r["N"]==n) for n in (9,16,25)}
    (output/"timeout-by-N.dat").write_text("N timeout_percent error_count\n"+"".join(f"{n} {100*c['TIMEOUT']/sum(c.values()):.8f} {c['ERROR']}\n" for n,c in size_counts.items()),encoding="utf-8")
    (output/"timeout-by-N.tex").write_text(r"\begin{tikzpicture}\begin{axis}[ybar,xlabel={Board side $N$},ylabel={TIMEOUT (\% of primary jobs)},xtick=data]"+"\n"+r"\addplot table[x=N,y=timeout_percent] {timeout-by-N.dat};"+"\n"+r"\end{axis}\end{tikzpicture}"+"\n% Descriptive counts only; different source/method matrices by N, not a size-only complexity claim.\n",encoding="utf-8")
    (output/"paired-ratios.dat").write_text("index ratio matched\n"+"".join(f"{i} {p['median_single_run_ratio']:.9f} {p['matched_instances']}\n" for i,p in enumerate(main_pairs,1) if p["median_single_run_ratio"] is not None),encoding="utf-8")
    (output/"paired-ratios.tex").write_text(r"\begin{tikzpicture}\begin{axis}[ybar,xlabel={Pair index (see runtime-common-main.csv)},ylabel={Median single-run ratio A/B}]"+"\n"+r"\addplot table[x=index,y=ratio] {paired-ratios.dat};"+"\n"+r"\end{axis}\end{tikzpicture}"+"\n% Same session/worker and exact paired SAT IDs per bar; different pairs may have different n. No cross-profile speedup.\n",encoding="utf-8")
    findings="""# Full rep1 analysis — declared infrastructure error retained

110000 primary observations on 16000 puzzles were attempted: 109664 SAT,
335 TIMEOUT (censored), 1 ERROR. This is NOT full 330000/3rep completion.
No diagnostic retry replaces or augments primary observations. Runtime tables
condition on SAT and disclose sample sizes; no runtime is imputed for None.
Each profile/session/worker has its own stratum. Trials with 24/40 workers
are present in coverage/timeline but excluded from paired performance claims.
No confidence interval, repeatability or isolated speedup is estimated.

coverage.csv retains every observation including ERROR; status-N-config.csv is
counts only across sessions, not a timing leaderboard. runtime-common.csv has
exact common SAT IDs, same N/source/group/family/clues/session/worker and n;
median/p90/p95 describe single-run matched samples, never three repetitions.
The compact main runtime panel uses the largest session BY COVERAGE, fixed
N25/permutation/40% clues, with no selection by speed. Full detailed pairs stay
in artifacts; do not dump all rows into the report. Keep original906/3rep
and historical rolling480 outputs separate from this full rep1 experiment.

Dataset composition and source claims are pinned to SAT05 PASS. Synthetic
masks share 1200 roots and seed grids; do not treat 16000 inputs as independent
roots. Source labels are not a proof of hardness; no uniformity/uniqueness or
non-isomorphism claim. Acquisition witness time is not benchmark runtime.
The ERROR case is premeasurement guard WinError6, null timings, acknowledged
separately; it is not UNSAT, TIMEOUT or cleanup failure. See declared-error.csv
and original snapshot declared_error/evidence for the immutable identity.
All claims are local revision results; do not claim new files are public.
"""
    (output/"FINDINGS.md").write_text(findings,encoding="utf-8")
    final=dict(status="READY_FOR_REPORT_WITH_DECLARED_ERROR",schema_version=1,error_free=False,quality=receipt["quality"],selected_scope_observed_complete=True,original_three_repetition_experiment_complete=False,effective_repetitions=1,observed_primary=110000,instances=16000,status_counts=aggregate["status_counts"],by_size={str(k):dict(v) for k,v in size_counts.items()},excluded_historical_repetitions=receipt["excluded_primary_counts"],declared_error=receipt["declared_error"],provenance_receipt_sha256=provenance_pin,snapshot_sha256=snapshot_pin,contract_sha256=validated["contract_sha256"],profiles=profile_rows,matched_strata=len(paired),independent_pair_sample_audit_passed=True,dominant_session_selected_by="coverage not speed",main_pair_panel_session=dominant["session_id"],no_CI=True,solver_calls=0)
    (output/"summary.json").write_text(json.dumps(final,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    _require(_sha(directory/"snapshot.json")==snapshot_pin,"Upstream snapshot changed")
    inventory={p.name:_sha(p) for p in sorted(output.iterdir()) if p.is_file()}
    analysis_receipt=dict(schema_version=1,kind="FINAL_REP1_ANALYSIS_RECEIPT",status=final["status"],error_free=False,snapshot_sha256=snapshot_pin,contract_sha256=validated["contract_sha256"],provenance_receipt_sha256=provenance_pin,files_sha256=inventory)
    (output/"analysis-hashes.json").write_text(json.dumps(analysis_receipt,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return final


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument("--snapshot",required=True,type=Path);parser.add_argument("--output",required=True,type=Path);args=parser.parse_args()
    result=analyze_final_report(args.snapshot,args.output)
    print(json.dumps({k:result[k] for k in ("status","error_free","observed_primary","instances","status_counts","matched_strata")}))

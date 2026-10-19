"""Conditional root-delegated local gate auditor. Never launches a worker.

Authority is a root-owned, hash-bound full-regression code release at the fixed
wave3 path. This module cannot create that release or authorize orphan cleanup.
"""
from collections import defaultdict
import importlib.metadata
import os
import platform
import statistics
import sys
import uuid
import xml.etree.ElementTree as ET

from sudoku.expanded_common import *
from sudoku import expanded_storage as storage
from sudoku.expanded_runner import _load, _gates

POLICY="conditional-local-root-wave3-v1"
RELEASE_PATH=ROOT/"diagnostics/expansion/root-wave3/code-release.json"


def release_source_paths():
    paths=set((ROOT/"src/sudoku").glob("expanded*.py"))
    paths.update(ROOT/p for p in ("scripts/run_expanded.py","scripts/analyze_expanded.py",
        "scripts/prepare_expanded_data.py","scripts/complete_expanded_witnesses.py","scripts/authorize_expanded_local.py",
        "report/prepare_expanded_report.py","scripts/local_expanded_pipeline.ps1","scripts/start_full_expanded_run.ps1",
        "docs/expanded-local-run.md","docs/expanded-terminal-policy.md","docs/expanded-contract.md",
        "docs/expanded-acceptance.md","requirements.txt","pyproject.toml","configs/expanded/main.json",
        "configs/expanded/pilot.json","configs/expanded/matrix.json"))
    # requirements/pyproject and imported v1 sources are additionally verified
    # through the protected execution freeze, as in root verify_release.py.
    paths.discard(ROOT/"requirements.txt"); paths.discard(ROOT/"pyproject.toml")
    return sorted(str(p.relative_to(ROOT)).replace("\\","/") for p in paths)


def _regression(release):
    evidence=release.get("regression")
    if evidence is None:
        # Current root verify_release.py uses this flat, fixed-path receipt.
        require(release.get("failed_tests")==0 and release.get("skipped_tests")==0,"Root regression is not clean")
        evidence=dict(path="diagnostics/expansion/root-wave3/regression-final.xml",sha256=release["regression_xml_sha256"],scope="full",tests=release["passed_tests"])
    require(evidence.get("scope")=="full","Code release needs full regression evidence")
    xml=contained(ROOT,evidence["path"])
    require(sha(xml)==evidence["sha256"],"Regression XML hash mismatch")
    try: tree=ET.parse(xml)
    except ET.ParseError as exc: raise ExpandedError("Invalid regression XML") from exc
    cases=list(tree.iter("testcase"))
    counts=dict(tests=len(cases),failures=len(list(tree.iter("failure"))),
        errors=len(list(tree.iter("error"))),skipped=len(list(tree.iter("skipped"))))
    require(counts["tests"]>0 and all(counts[k]==0 for k in ("failures","errors","skipped")),"Regression has missing/failed/error/skipped cases")
    require(type(evidence.get("tests")) is int and evidence["tests"]==counts["tests"],"Regression case count mismatch")
    # Collection/setup errors and aggregate failures must not be hidden outside
    # testcase children. Validate every suite's declared counters as well.
    for suite in tree.iter():
        if suite.tag in ("testsuite","testsuites"):
            for key in ("failures","errors","skipped"):
                require(int(suite.get(key,"0"))==0,"Regression suite is not clean")
    for key in ("failures","errors","skipped"):
        require(evidence.get(key,0)==0,"Code release declares failed/skipped regression")
    return dict(path=evidence["path"],sha256=evidence["sha256"],scope="full",**counts)


def _release(path):
    path=Path(path).resolve()
    require(path==RELEASE_PATH.resolve(),"Only the root wave3 code-release path is accepted")
    release=read(path)
    require(release.get("schema_version",2)==2 and release.get("status")=="PASS" and release.get("approved_explicit_terminal_execution") is True,"Root has not released explicit terminal execution")
    sources=release["source_sha256"]
    require(isinstance(sources,dict) and set(release_source_paths())<=set(sources),"Code release source/test coverage incomplete")
    for relative,expected in sources.items():
        require(sha(contained(ROOT,relative))==expected,f"Released source changed: {relative}")
    regression=_regression(release)
    protected={}
    for name,count_key in (("results/raw/main-20261016-01/execution-freeze.json","protected_execution_files"),("data/freeze.json","protected_data_files")):
        freeze=read(ROOT/name)
        require(len(freeze["files_sha256"])==release[count_key],"Protected freeze count mismatch")
        for relative,expected in freeze["files_sha256"].items():
            require(sha(contained(ROOT,relative))==expected,"Protected v1 file changed: "+relative)
        protected[name]=sha(ROOT/name)
    require(release.get("existing_two_pdfs_unchanged") is True,"Root PDF preservation check missing")
    for name,expected in (("sudoku-vi.pdf","e0e3a294639371c5dc07398afd02cbac1afcc6a527cea02bc4ec1464ddd0fd64"),("sudoku-en.pdf","bae7455b3584612371c7c51ce533369a40b98795841f974d7be4c63cfe823075")):
        require(sha(ROOT/"report/output/pdf"/name)==expected,"Protected original PDF changed")
    return dict(path=str(path.relative_to(ROOT)).replace("\\","/"),sha256=sha(path),regression=regression,source_sha256=sources,protected_freeze_sha256=protected)


def _preflight(manifest):
    from sudoku.runner import machine_info,package_versions
    env=read(ROOT/"diagnostics/expansion/env/environment.json")
    inventory=read(ROOT/"diagnostics/expansion/solvers/inventory.json")
    hardware=read(ROOT/"diagnostics/expansion/env/inventory.json")
    machine=machine_info()
    require(env["python"]==sys.version and env["platform"]==platform.platform() and env["architecture"]==platform.machine(),"Preflight Python/OS/architecture mismatch")
    require((hardware["cpu"],hardware["logical_cpus"],hardware["ram_total_bytes"])==(machine["processor"],machine["logical_cpus"],machine["ram_bytes"]),"Preflight machine identity mismatch")
    require(Path(inventory["executable"]).resolve()==Path(sys.executable).resolve() and inventory["packages"]==package_versions(),"Preflight interpreter/solver package mismatch")
    for package in env["packages"]:
        require(importlib.metadata.version(package["name"])==package["version"],"Preflight dependency version mismatch: "+package["name"])
    for row in env["interpreter_files"]:
        require(sha(row["path"])==row["sha256"],"Preflight interpreter binary changed")
    native=read(ROOT/"diagnostics/expansion/env/native-runtime.json")
    # Use the environment inventory's UTF-8 canonical JSON aggregate definition.
    aggregate=digest(json.dumps(native,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode())
    require(aggregate==env["native_files_sha256"],"Native inventory aggregate mismatch")
    for row in native:
        require(sha(contained(sys.prefix,row["path"]))==row["sha256"],"Preflight native runtime changed: "+row["path"])
    require(sha(inventory["cpoptimizer_executable"])==inventory["cpoptimizer_sha256"],"Preflight CP Optimizer changed")
    # _load has already checked the matrix's complete evidence list and current
    # machine/package/native fingerprint against this experiment's frozen one.
    return dict(matrix_sha256=manifest["matrix_sha256"],evidence=manifest["matrix"]["evidence"],
        native_files_checked=len(native),fingerprint=manifest["fingerprint"])


def _pilot_audit(directory, main_manifest, main_index, release):
    directory=Path(directory).resolve()
    with storage.WriterLock(directory):
        db=storage.connect(directory,readonly=True)
        try:
            db.execute("BEGIN")
            pilot,index=_load(directory,db)
            require(pilot["phase"]=="pilot" and not pilot["artificial"],"Main requires a real pilot; artificial/replay rejected")
            require(pilot["matrix"]==main_manifest["matrix"] and pilot["fingerprint"]==main_manifest["fingerprint"],"Pilot/main code, native environment or matrix differs")
            require(db.execute("SELECT state FROM experiment").fetchone()[0]=="COMPLETED","Real pilot is not COMPLETED")
            require(not db.execute("SELECT 1 FROM jobs WHERE state!='TERMINAL' LIMIT 1").fetchone(),"Pilot has unfinished jobs")
            require(not db.execute("SELECT 1 FROM events WHERE type='REJECTED_OBSERVATION' LIMIT 1").fetchone(),"Pilot has rejected observations")
            refs=_gates(pilot)
            for key in ("dataset","qa","preflight"):
                receipt=read(contained(ROOT,refs["gates"][key]["path"]))
                require(receipt.get("policy")==POLICY and receipt.get("code_release",{}).get("sha256")==release["sha256"],"Pilot was not authorized under this code release")
            used_sessions={r[0] for r in db.execute("SELECT DISTINCT session_id FROM attempts")}
            for sid in used_sessions:
                session=db.execute("SELECT * FROM sessions WHERE session_id=?",(sid,)).fetchone()
                require(session["ended_utc"] is not None,"Pilot session has not ended")
                saved=read(directory/"session-manifests"/(sid+".json"))
                require(saved.get("scientific_manifest")==pilot and saved.get("session_id")==sid,"Pilot session manifest mismatch")
                for key in ("dataset","qa","preflight"):
                    require(saved.get("gate_refs",{}).get("gates",{}).get(key)==refs["gates"][key],"Pilot session gate evidence differs")
                events=db.execute("SELECT details_json FROM events WHERE session_id=? AND type='GATES_VERIFIED'",(sid,)).fetchall()
                require(len(events)==1 and json.loads(events[0][0])==saved.get("gate_refs"),"Pilot session lacks matching gate verification audit")
            require(used_sessions,"Pilot has no executed sessions")
            main_contents={r["content_sha256"] for r in main_index["records"].values()}
            require(not main_contents.intersection(r["content_sha256"] for r in index["records"].values()),"Pilot/main content overlaps")
            require(not {r.get("root_content_sha256") for r in main_index["roots"].values()}.intersection(r.get("root_content_sha256") for r in index["roots"].values()),"Pilot/main roots overlap")
            walls=defaultdict(list); counts=defaultdict(int); observed=0
            # _load has already independently checked every stored SAT grid,
            # canonical hash, original clues, CNF identity and finite timings.
            for row in db.execute("""SELECT r.status,r.result_json,a.attempt_wall_seconds,j.configuration,i.board_side
                FROM primary_attempt p JOIN results r USING(attempt_id) JOIN attempts a USING(attempt_id)
                JOIN jobs j USING(job_id) JOIN instances i USING(instance_id)"""):
                result=json.loads(row["result_json"])
                require(row["status"] in ("SAT","TIMEOUT") and result.get("guard_phase") in ("complete","measurement"),"Pilot contains fatal status or cleanup/protocol failure")
                raw=str(result.get("raw_status","")).upper()
                require(not any(token in raw for token in ("ARTIFICIAL","FIXTURE","REPLAY")),"Pilot replay/artificial observation rejected")
                require(finite(row["attempt_wall_seconds"]),"Pilot wall duration missing/nonfinite")
                walls[row["board_side"],row["configuration"]].append(row["attempt_wall_seconds"])
                counts[row["status"]]+=1; observed+=1
            expected=db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            require(expected==manifest_pilot_job_count(main_manifest["matrix"])==observed,"Pilot has wrong terminal job count")
            require(all(b["qa_complete"] for b in storage.assess_blocks(db).values()),"Pilot block QA failed")
            return dict(pilot_experiment_id=pilot["experiment_id"],pilot_scientific_sha256=pilot["scientific_sha256"],
                pilot_dataset_freeze_sha256=index["freeze_sha256"],primary_counts=dict(counts),jobs=observed,disjoint=True,
                gate_refs=refs,wall_estimates=[dict(N=n,configuration=c,median_attempt_wall_seconds=statistics.median(values)) for (n,c),values in sorted(walls.items())])
        finally: db.close()


def manifest_pilot_job_count(matrix):
    return sum(({9:8,16:10,25:10}[r["N"]]) for r in matrix["rows"] if r["eligible"])


def _durable_json(path,body):
    with path.open("x",encoding="utf-8",newline="\n") as stream:
        stream.write(dumps(body)+"\n"); stream.flush(); os.fsync(stream.fileno())


@public
def authorize_expanded_local(experiment_dir,code_release,*,pilot_experiment=None):
    directory=Path(experiment_dir).resolve()
    require(os.name=="nt","Local authorization requires the Windows runner host")
    manifest=read(directory/"experiment.json")
    require(manifest.get("artificial") is False,"Artificial experiment cannot be locally authorized")
    require(manifest["phase"] in ("main","pilot"),"Invalid experiment phase")
    require((manifest["phase"]=="main")==bool(pilot_experiment),"Main requires --pilot-experiment; pilot must omit it")
    release=_release(code_release)  # No directory/gate/receipt mutation before this.
    gate_file=contained(ROOT,manifest["gate_refs_path"])
    require(not gate_file.exists(),"Gate file already exists; never overwrite root gates")
    with storage.WriterLock(directory):
        db=storage.connect(directory,readonly=True)
        try:
            db.execute("BEGIN")
            manifest,index=_load(directory,db)
            require(db.execute("SELECT state FROM experiment").fetchone()[0]=="PREPARED" and db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==0,"Only a fresh PREPARED experiment can be authorized")
            preflight=_preflight(manifest)
            pilot=None if manifest["phase"]=="pilot" else _pilot_audit(pilot_experiment,manifest,index,release)
            common=dict(schema_version=2,policy=POLICY,delegated_by="root",code_release=release,
                experiment_id=manifest["experiment_id"],scientific_sha256=manifest["scientific_sha256"],created_utc=stamp())
            receipts=dict(dataset=dict(common,dataset_id=index["dataset_id"],dataset_dir=index["dataset_dir"],
                freeze_path=str(Path(index["dataset_dir"])/"freeze.json"),freeze_sha256=index["freeze_sha256"],counts=index["counts"],all_witness_check_pass=True),
                qa=dict(common,regression=release["regression"],dataset_validation="full independent schema/hash/witness/batch check"),
                preflight=dict(common,**preflight))
            if pilot is not None:
                receipts["pilot"]=dict(common,**pilot)
                receipts["execution_freeze"]=dict(common,scientific_manifest=manifest,pilot_scientific_sha256=pilot["pilot_scientific_sha256"])
            base=ROOT/"diagnostics/expansion/local-gates"; base.mkdir(parents=True,exist_ok=True)
            final=base/(manifest["experiment_id"]+"-"+uuid.uuid4().hex)
            staging=final.with_name(final.name+".incomplete"); staging.mkdir()
            refs={}
            for key,body in receipts.items():
                _durable_json(staging/(key+".json"),body)
                refs[key]=dict(path=str((final/(key+".json")).relative_to(ROOT)).replace("\\","/"),sha256=sha(staging/(key+".json")),
                    accepted_by="root",accepted=True,policy=POLICY,code_release_sha256=release["sha256"])
            # Reverify authority immediately before publishing anything accepted.
            require(_release(code_release)==release,"Code release changed during audit")
            staging.rename(final)
            gate_file.parent.mkdir(parents=True,exist_ok=True)
            temp=gate_file.with_name(gate_file.name+".incomplete-"+uuid.uuid4().hex)
            _durable_json(temp,dict(common,gates=refs)); temp.rename(gate_file)
            verified=_gates(manifest)
            return dict(experiment_id=manifest["experiment_id"],phase=manifest["phase"],gate_path=verified["path"],gate_sha256=verified["sha256"],
                receipt_dir=str(final),policy=POLICY,solver_calls=0,exit_code=0)
        finally: db.close()

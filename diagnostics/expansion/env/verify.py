"""Validate EXP-01 evidence without solving or modifying the environment."""
import hashlib
import importlib.metadata as md
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",", ":"),ensure_ascii=False).encode()).hexdigest()


def main():
    load=lambda name:json.loads((HERE/name).read_text(encoding="utf-8"))
    env=load("environment.json"); native=load("native-runtime.json")
    files=load("installed-files.json"); inventory=load("inventory.json"); budget=load("capacity-budget.json")
    fingerprint=(HERE/"environment.sha256").read_text().strip()
    assert canonical(env)==fingerprint==inventory["environment_sha256"]
    assert canonical(native)==env["native_files_sha256"]
    assert len({p["path"] for p in files})==len(files)==inventory["installed_files_hashed"]
    assert not any(p["missing_record_files"] for p in env["packages"])
    assert all(md.version(p["name"])==p["version"] for p in env["packages"])
    for runtime in ("Scripts/cpoptimizer.exe", "Lib/site-packages/gurobipy/gurobi130.dll", "Lib/site-packages/cplex/_internal/cplex2220.dll"):
        item=next(p for p in native if p["path"]==runtime)
        assert hashlib.sha256((Path(sys.prefix)/runtime).read_bytes()).hexdigest()==item["sha256"]
    requirements=HERE.parents[2]/"requirements.txt"
    pins=[line.strip().split("==") for line in requirements.read_text(encoding="utf-8-sig").splitlines() if line.strip() and not line.startswith("#")]
    assert all(len(pin)==2 and md.version(pin[0])==pin[1] for pin in pins)
    assert budget["jobs_total"]==sum(budget["jobs_by_N"].values())==330000
    assert budget["blocks"]*budget["jobs_per_block"]==330000
    for scenario in budget["scenarios"].values():
        assert scenario["db_metadata_bytes"]+scenario["db_witness_bytes"]==scenario["sqlite_main_bytes"]
        parts=("sqlite_main_bytes","logs_bytes","csv_export_bytes","dataset_input_and_witness_bytes","wal_reservation_bytes","one_backup_and_export_regeneration_bytes")
        assert sum(scenario[k] for k in parts)==scenario["subtotal_bytes"]
        assert int(scenario["subtotal_bytes"]*1.25)==scenario["with_25_percent_headroom_bytes"]
    result={"status":"PASS","environment_sha256":fingerprint,"package_count":len(env["packages"]),
            "pinned_requirements_verified":len(pins),"runtime_binary_hashes_rechecked":3,
            "missing_installed_record_files":0,"capacity_arithmetic":"PASS",
            "scope":"EXP-01 artifact consistency only; no solver/pilot/fullsuite"}
    (HERE/"verification.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()

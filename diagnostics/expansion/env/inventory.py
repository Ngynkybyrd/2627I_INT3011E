"""Read-only environment fingerprint and explicit storage planning; no solver imports."""
import ctypes
from datetime import datetime, timezone
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import winreg

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def version_resource(path):
    version = ctypes.windll.version
    size = version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return None
    buf = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(path), 0, size, buf):
        return None
    pointer = ctypes.c_void_p()
    length = ctypes.c_uint()
    if not version.VerQueryValueW(buf, "\\", ctypes.byref(pointer), ctypes.byref(length)):
        return None
    values = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32))
    return ".".join(map(str, (values[2] >> 16, values[2] & 65535,
                              values[3] >> 16, values[3] & 65535)))


def estimate():
    jobs = {9: 10000 * 8 * 3, 16: 5000 * 5 * 3, 25: 1000 * 5 * 3}
    scenarios = {}
    for name, row, log, csv, attempts in (
        ("compact", 4096, 2048, 2048, 1.0),
        ("planning", 8192, 16384, 4096, 1.1),
        ("stress", 16384, 65536, 8192, 2.0),
    ):
        metadata_bytes = sum(jobs.values()) * row * attempts
        # Text JSON worst case within 1..25: <=4 bytes per value including separator,
        # plus 512 bytes envelope; aligned to a 4KiB planning allocation.
        witness = sum(count * (((n*n*4 + 512 + 4095)//4096)*4096)
                      for n, count in jobs.items()) * attempts
        db = int(metadata_bytes + witness)
        logs = int(sum(jobs.values()) * log * attempts)
        export = sum(jobs.values()) * csv  # one current CSV export, without witness
        dataset = sum(count//(8*3 if n == 9 else 5*3) * (n*n*8 + 4096)
                      for n, count in jobs.items())
        # WAL growth must be bounded by runner; this is a reservation, not a guarantee.
        wal = max(1024**3, db//4)
        backup = db + export  # one snapshot plus another CSV generation
        subtotal = db + logs + export + dataset + wal + backup
        scenarios[name] = {"attempt_multiplier": attempts,
            "assumed_metadata_and_indexes_bytes_per_attempt": row,
            "assumed_log_bytes_per_attempt": log, "assumed_csv_bytes_per_job": csv,
            "db_metadata_bytes": int(metadata_bytes), "db_witness_bytes": int(witness),
            "sqlite_main_bytes": db, "logs_bytes": logs, "csv_export_bytes": export,
            "dataset_input_and_witness_bytes": dataset, "wal_reservation_bytes": wal,
            "one_backup_and_export_regeneration_bytes": backup,
            "subtotal_bytes": subtotal, "with_25_percent_headroom_bytes": int(subtotal*1.25)}
    return {"kind": "assumption-based capacity budget, not measured schema or performance",
            "jobs_by_N": jobs, "jobs_total": sum(jobs.values()),
            "blocks": 100, "jobs_per_block": 3300, "scenarios": scenarios}


def main():
    assert ROOT == Path.cwd().resolve(), (ROOT, Path.cwd())
    assert Path(sys.prefix).resolve() == ROOT / ".venv", "Use project's existing venv"
    files = {}
    packages = []
    for dist in sorted(md.distributions(), key=lambda d: d.metadata["Name"].lower()):
        records = []
        missing = []
        for entry in dist.files or []:
            if str(entry).endswith((".pyc", ".pyo")):
                continue
            path = Path(dist.locate_file(entry)).resolve()
            # Editable application code is frozen separately by EXP-07, not environment.
            if not path.is_relative_to(Path(sys.prefix).resolve()):
                continue
            rel = path.relative_to(Path(sys.prefix).resolve()).as_posix()
            if not path.is_file():
                missing.append(rel)
                continue
            if rel not in files:
                files[rel] = {"path": rel, "bytes": path.stat().st_size, "sha256": sha(path)}
            records.append(files[rel])
        packages.append({"name": dist.metadata["Name"], "version": dist.version,
                         "files_hashed": len(records), "missing_record_files": missing,
                         "installed_files_sha256": canonical(sorted(records, key=lambda r:r["path"]))})

    interpreter_paths = [Path(sys.executable), Path(sys.base_prefix)/"python.exe",
                         Path(sys.base_prefix)/"python313.dll", ROOT/".venv"/"pyvenv.cfg"]
    interpreter = [{"path":str(p), "bytes":p.stat().st_size, "sha256":sha(p),
                    "file_version":version_resource(p)} for p in interpreter_paths if p.is_file()]
    native = []
    for rel, item in sorted(files.items()):
        if Path(rel).suffix.lower() in (".dll", ".pyd", ".exe"):
            native.append({**item, "file_version":version_resource(Path(sys.prefix)/rel)})
    cp = Path(sys.prefix)/"Scripts"/"cpoptimizer.exe"
    assert cp.is_file(), "CP runtime executable absent"
    assert any(p["path"] == cp.relative_to(sys.prefix).as_posix() for p in native)

    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
        cpu = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    class Memory(ctypes.Structure):
        _fields_ = [("length",ctypes.c_ulong),("load",ctypes.c_ulong)] + [
            (name,ctypes.c_ulonglong) for name in ("total", "available", "page", "available_page", "virtual", "available_virtual", "extended")]
    mem=Memory(); mem.length=ctypes.sizeof(mem)
    assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
    disks = []
    for path in (ROOT, Path(sys.base_prefix)):
        usage=shutil.disk_usage(path)
        disks.append({"path":str(path),"drive":path.anchor,"total_bytes":usage.total,
                      "used_bytes":usage.used,"free_bytes":usage.free})
    stable = {"fingerprint_schema":"sat-expanded-env-v1", "python":sys.version,
              "platform":platform.platform(), "architecture":platform.machine(),
              "interpreter_files":interpreter,"packages":packages,
              "native_files_sha256":canonical(native)}
    (OUT/"installed-files.json").write_text(json.dumps(sorted(files.values(),key=lambda x:x["path"]),indent=2),encoding="utf-8")
    (OUT/"native-runtime.json").write_text(json.dumps(native,indent=2),encoding="utf-8")
    (OUT/"environment.json").write_text(json.dumps(stable,indent=2),encoding="utf-8")
    fingerprint=canonical(stable)
    (OUT/"environment.sha256").write_text(fingerprint+"\n",encoding="ascii")
    budget=estimate()
    (OUT/"capacity-budget.json").write_text(json.dumps(budget,indent=2),encoding="utf-8")
    snapshot={"timestamp_utc":datetime.now(timezone.utc).isoformat(),"cpu":cpu,
              "logical_cpus":os.cpu_count(),"ram_total_bytes":mem.total,
              "ram_available_bytes":mem.available,"disks":disks,
              "environment_sha256":fingerprint,"package_count":len(packages),
              "installed_files_hashed":len(files),"native_files_hashed":len(native),
              "project_disk_planning_budget_fits":disks[0]["free_bytes"] > budget["scenarios"]["planning"]["with_25_percent_headroom_bytes"]}
    (OUT/"inventory.json").write_text(json.dumps(snapshot,indent=2),encoding="utf-8")
    print(json.dumps(snapshot,indent=2))
    print(json.dumps({k:round(v["with_25_percent_headroom_bytes"]/1024**3,3) for k,v in budget["scenarios"].items()}))


if __name__ == "__main__":
    main()

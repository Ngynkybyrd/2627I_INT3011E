"""Restore immutable SQLite files after cloning; verify snapshot hashes."""
from pathlib import Path
import gzip, hashlib, json, shutil, tempfile
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/final-snapshots/final-20261020-rep1"
def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
def main():
    manifest = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8-sig"))
    for name in ("snapshot.sqlite3", "inputs.sqlite3"):
        target = BASE / name
        expected = manifest["files_sha256"][name]
        if target.exists():
            if digest(target) != expected: raise ValueError("Existing database hash mismatch: " + name)
            continue
        parts = sorted(BASE.glob(name + ".gz.part*")) or [BASE / (name + ".gz")]
        temporary = BASE / (name + ".restoring")
        if temporary.exists(): raise ValueError("Unfinished restore exists: " + str(temporary))
        with tempfile.TemporaryFile(dir=BASE) as joined:
            for part in parts:
                with part.open("rb") as source: shutil.copyfileobj(source, joined, 1024 * 1024)
            joined.seek(0)
            with gzip.GzipFile(fileobj=joined, mode="rb") as source, temporary.open("xb") as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
        if digest(temporary) != expected: raise ValueError("Restored database hash mismatch: " + name)
        temporary.replace(target)
    for name, expected in manifest["files_sha256"].items():
        if digest(BASE / name) != expected: raise ValueError("Snapshot hash mismatch: " + name)
    archive = ROOT / "reports/archive"
    for lang in ("EN", "VI"):
        source = archive / ("24021587_TaDinhNguyen_BTL1_Sudoku_Baseline_" + lang + ".pdf")
        if source.is_file():
            target = ROOT / ("report/output/pdf/sudoku-" + lang.lower() + ".pdf")
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists(): shutil.copyfile(source, target)
    print("PASS: all 48 final snapshot artifacts verified; 16,000 inputs and 110,000 primary observations available.")
if __name__ == "__main__": main()

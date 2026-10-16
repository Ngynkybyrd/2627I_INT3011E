"""Read-only frozen-code/dependency provenance check; never imports a solver."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "report"
RUN = ROOT / "results/raw/main-20261016-01"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

freeze = json.loads((RUN / "execution-freeze.json").read_text(encoding="utf-8"))
run = json.loads((RUN / "run.json").read_text(encoding="utf-8"))
checks = []
for relative, expected in freeze["files_sha256"].items():
    actual = sha(ROOT / relative)
    assert actual == expected, relative
    checks.append({"path": relative, "sha256": actual})
assert sha(RUN / "run.json") == freeze["run_sha256"]
site = ROOT / ".venv/Lib/site-packages"
installed = {d.metadata["Name"].lower().replace("_", "-"): d
             for d in metadata.distributions(path=[str(site)])}
for line in (ROOT / "requirements.txt").read_text().splitlines():
    if not line.strip() or line.startswith("#"):
        continue
    name, version = line.split("==")
    assert installed[name.lower().replace("_", "-")].version == version, name
for name, version in run["packages"].items():
    assert installed[name].version == version, name
artifacts = [
    "python_sat-1.9.dev16.dist-info/METADATA",
    "python_sat-1.9.dev16.dist-info/RECORD",
    "python_sat-1.9.dev16.dist-info/licenses/LICENSE.txt",
    "pysat/card.py", "pysat/solvers.py",
    "pycard.cp313-win_amd64.pyd", "pysolvers.cp313-win_amd64.pyd",
    "cplex/__init__.py",
]
for original, copied in [
    ("python_sat-1.9.dev16.dist-info/METADATA", "PySAT-installed-METADATA.txt"),
    ("python_sat-1.9.dev16.dist-info/licenses/LICENSE.txt", "PySAT-installed-LICENSE.txt"),
]:
    assert sha(site / original) == sha(REPORT / "reading/evidence" / copied), copied
record = {
    "status": "PASS", "run_id": run["run_id"],
    "freeze_sha256": sha(RUN / "execution-freeze.json"),
    "run_sha256": sha(RUN / "run.json"),
    "frozen_files_verified": checks,
    "requirements_match_installed_metadata": True,
    "installed_pysat_notice_metadata_copies_identical": True,
    "recorded_packages": run["packages"],
    "installed_artifacts": [{"path": x, "sha256": sha(site / x)} for x in artifacts],
    "upstream_snapshot_matches_installed_binary": "not established; not asserted",
    "project_repository_url": "https://github.com/Ngynkybyrd/2627I_INT3011E",
    "repository_role": "published source/data/results; coordinator verified all 1384 GitHub tree blobs against initial local HEAD",
    "initial_publication_commit": "f45d37894cfb19fe3bb890e8f0e06f13b472c2a2",
    "online_project_contents_confirmed": True,
}
out = REPORT / "logs/frozen-reference-verification.json"
out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"PASS: {len(checks)} frozen files, requirements and run package metadata; no solver calls")

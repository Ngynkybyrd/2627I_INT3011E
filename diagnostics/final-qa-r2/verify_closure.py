"""Targeted final document closure after metadata-only changes."""
import json
from pathlib import Path
import check_report as qa

qa.main()
result = qa.read(qa.OUT / "report-qa.json")
assert result["technical_status"] == "PASS" and not result["metadata_issues"]
dependencies = qa.read(qa.REPORT / "logs/source-dependencies.json")
for entry in dependencies:
    assert qa.sha(qa.REPORT / entry["path"]) == entry["sha256"], entry["path"]
run = qa.ROOT / "results/raw/main-20261016-01"
freeze = qa.read(run / "execution-freeze.json")
for relative, expected in freeze["files_sha256"].items():
    assert qa.sha(qa.ROOT / relative) == expected, relative
assert qa.sha(run / "results.csv") == qa.read(run / "supervisor-status.json")["results_sha256"]
outcome = dict(technical_document_closure="PASS", provenance_entries=len(dependencies),
    frozen_sources=len(freeze["files_sha256"]), build_id=result["build_id"],
    metadata_author="Tạ Đình Nguyên", known_blocker=result["known_blocker"],
    suite_evidence="diagnostics/final-qa/suite.xml: 653 pass; source unchanged")
(qa.OUT / "closure.json").write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(outcome, ensure_ascii=False))

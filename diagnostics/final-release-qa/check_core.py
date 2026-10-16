"""Final release core/data/results QA; does not read or modify report artifacts."""
import importlib.metadata as md
import json
from collections import Counter
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUN = ROOT / "results/raw/main-20261016-01"
SUMMARY = ROOT / "results/summary/main-20261016-01"
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_results import validate_run
from sudoku.runner import read_json, sha256


def snapshot():
    files = {ROOT / p for p in read_json(RUN / "execution-freeze.json")["files_sha256"]}
    files.update(ROOT / p for p in read_json(ROOT / "data/freeze.json")["files_sha256"])
    for directory in (RUN, SUMMARY):
        files.update(p for p in directory.rglob("*") if p.is_file())
    files.update((ROOT / "tests").glob("*.py"))
    return {str(p.relative_to(ROOT)): sha256(p) for p in sorted(files)}


def check():
    freeze, state = read_json(RUN / "execution-freeze.json"), read_json(RUN / "supervisor-status.json")
    assert state["state"] == "COMPLETED" and state["exit_code"] == 0
    assert len(freeze["files_sha256"]) == 32
    for name, expected in freeze["files_sha256"].items():
        assert sha256(ROOT / name) == expected, name
    data = read_json(ROOT / "data/freeze.json")
    assert data["frozen"] and len(data["files_sha256"]) == 169
    for name, expected in data["files_sha256"].items():
        assert sha256(ROOT / name) == expected, name
    for name, key in (("run.json", "run_sha256"), ("schedule.json", "schedule_sha256")):
        assert sha256(RUN / name) == freeze[key] == state[key]
    assert sha256(RUN / "execution-freeze.json") == state["freeze_sha256"]
    assert sha256(RUN / "results.csv") == state["results_sha256"]
    assert sha256(ROOT / freeze["suite_xml"]) == freeze["suite_sha256"]
    run = read_json(RUN / "run.json")
    assert sys.version.split()[0] == run["machine"]["python"]
    for name, version in run["packages"].items():
        assert md.version(name) == version
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            name, version = line.split("==")
            assert md.version(name) == version
    rows, audit, scopes = validate_run(RUN, partial=False, diagnostic=False)
    assert len(rows) == audit["planned_jobs"] == audit["selected_jobs"] == state["completed_jobs"] == 906
    assert not audit["missing_executed_ids"]
    assert Counter(r["status"] for r in rows) == {"SAT": 903, "TIMEOUT": 3}
    assert Counter(r["scope"] for r in rows) == {"S80": 720, "B16": 96, "C10": 90}
    assert len(audit["solutions"]) == 903
    final_audit = read_json(SUMMARY / "audit.json")
    assert final_audit["analyzer_sha256"] == sha256(ROOT / "scripts/analyze_results.py")
    assert len(final_audit["runs"]) == 1
    previous = final_audit["runs"][0]
    assert previous["run_id"] == RUN.name
    assert previous["inputs"] == audit["inputs"]
    assert previous["solutions"] == audit["solutions"]
    assert previous["code_sha256"] == audit["code_sha256"]
    checks = read_json(SUMMARY / "final-checks.json")
    verification = read_json(SUMMARY / "verification.json")
    assert checks["raw_sha256_after"] == verification["raw_sha256_after"] == sha256(RUN / "results.csv")
    assert checks["findings_sha256"] == sha256(SUMMARY / "findings.md")
    assert verification["accepted"] and verification["rows"] == 906
    assert verification["solution_hashes_equal_root_acceptance"] == 903
    return {"status": "PASS", "run_id": RUN.name, "frozen_source_files": 32, "frozen_data_files": 169,
            "raw_rows": 906, "checker_revalidated": 903, "statuses": {"SAT": 903, "TIMEOUT": 3},
            "raw_sha256": sha256(RUN / "results.csv"),
            "execution_freeze_sha256": sha256(RUN / "execution-freeze.json"),
            "data_freeze_sha256": sha256(ROOT / "data/freeze.json"),
            "run_sha256": sha256(RUN / "run.json"),
            "summary_sha256": sha256(SUMMARY / "summary.csv"),
            "findings_sha256": sha256(SUMMARY / "findings.md"),
            "python": sys.version.split()[0], "versions_match": run["packages"],
            "benchmark_rerun": False, "report_qa": "outside scope; owner building"}


if __name__ == "__main__":
    phase = sys.argv[1]
    if phase == "before":
        (OUT / "before-sha256.json").write_text(json.dumps(snapshot(), indent=2), encoding="utf-8")
    result = check()
    if phase == "after":
        before, after = read_json(OUT / "before-sha256.json"), snapshot()
        assert before == after, [p for p in before.keys() | after.keys() if before.get(p) != after.get(p)]
        result["artifacts_unchanged"] = len(after)
        suite = ET.parse(OUT / "suite.xml")
        assert not any(suite.findall(".//" + kind) for kind in ("failure", "error", "skipped"))
        result["suite_passed"] = len(suite.findall(".//testcase"))
        result["suite_sha256"] = sha256(OUT / "suite.xml")
        result["suite_names"] = [case.attrib["name"] for case in suite.findall(".//testcase")]
        required = {
            "SAT_UNSAT_oracle_agreement": "test_production_adapters_agree_with_independent_oracle",
            "invalid_before_adapter": "test_invalid_input_stops_before_every_adapter",
            "auxiliary_existential_truth_table": "test_amo_exo_truth_tables_with_existential_auxiliaries",
            "mapping_all_sizes": "test_mapping_and_all_groups_including_block_boundaries",
            "SAT_remaining_budget": "test_build_load_solve_timing_and_remaining_budget",
            "baseline_remaining_budget": "test_remaining_budget_after_setup",
            "SAT_validation_excluded": "test_validation_time_is_excluded_and_timer_stopped_first",
            "baseline_validation_excluded": "test_measurement_hook_precedes_slow_validation_and_cleanup",
            "Windows_hard_guard": "test_guard_modes",
            "separate_startup_postprocess_watchdogs": "test_separate_watchdogs",
            "process_tree_cleanup": "test_descendant_terminated",
            "deadline_race": "test_end_deadline_race_recheck",
            "missing_END_cannot_accept_final": "test_no_end_at_deadline_never_uses_final_result",
        }
        result["required_regression_groups"] = {
            label: [name for name in result["suite_names"] if name.split("[", 1)[0] == prefix]
            for label, prefix in required.items()}
        assert all(result["required_regression_groups"].values())
    (OUT / f"core-{phase}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in ("suite_names", "required_regression_groups")}))

"""Freeze a new main plan after accepted RUN010 and a fresh complete test suite."""
from pathlib import Path
import csv
import sys
from collections import Counter
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from sudoku.runner import RunnerConfig, prepare_run, read_json, sha256, write_json


def main():
    suite = ROOT / "diagnostics/runner/full-suite-main-01.xml"
    tree = ET.parse(suite)
    cases = tree.findall(".//testcase")
    assert cases and not tree.findall(".//failure") and not tree.findall(".//error") and not tree.findall(".//skipped")
    analysis = ROOT / "diagnostics/runner/pilot-analysis-01"
    audit = read_json(analysis / "audit.json")
    assert audit["mode"] == "pilot" and audit["runs"][0]["observed_rows"] == 55
    assert not audit["runs"][0]["missing_executed_ids"]
    for filename, columns in (("instances.csv", ["median_build_seconds", "median_solve_seconds", "median_total_seconds"]),
                              ("matched-pairs.csv", ["median_a_seconds", "median_b_seconds", "median_paired_a_over_b"])):
        with (analysis / filename).open(encoding="utf-8", newline="") as stream:
            assert all(all(row[column] == "" for column in columns) for row in csv.DictReader(stream))
    pilot = ROOT / "diagnostics/runner/pilot-20261016-01"
    old = read_json(pilot / "pilot-audit.json")
    assert sha256(pilot / "results.csv") == old["results_sha256"]
    output = ROOT / "results/raw/main-20261016-01"
    config = RunnerConfig(**read_json(ROOT / "configs/benchmark.json"))
    assert config.cutoff_seconds == 10 and config.repetitions == 3 and config.schedule_seed == 20261016
    jobs = prepare_run(output, config)
    assert len(jobs) == 906 and Counter(j["scope"] for j in jobs) == {"S80":720,"B16":96,"C10":90}
    paths = list((ROOT / "src/sudoku").rglob("*.py"))
    paths += list((ROOT / "scripts").glob("*.py"))
    paths += list((ROOT / "docs").glob("*-api.md"))
    paths += [ROOT / relative for relative in (
        "configs/benchmark.json", "requirements.txt", "pyproject.toml", "data/freeze.json",
        "docs/results-schema.md", "docs/contracts.md", "docs/adapter-contract.md",
        "diagnostics/runner/main_supervisor.py", "diagnostics/runner/prepare_main.py")]
    write_json(output / "execution-freeze.json", dict(
        files_sha256={str(p.relative_to(ROOT)): sha256(p) for p in sorted(set(paths))},
        suite_xml=str(suite.relative_to(ROOT)), suite_sha256=sha256(suite), passed_tests=len(cases),
        run_sha256=sha256(output / "run.json"), schedule_sha256=sha256(output / "schedule.json"),
        pilot_audit_sha256=sha256(analysis / "audit.json"),
        workload_gate="SAT09 build complete/idle; SAT10 README/help only per coordinator; no heavy work authorized",
        protocol="906 fresh jobs; 720 S80 + 96 B16 + 90 C10; 3 reps; 10 seconds; no pilot reuse"))
    print(f"Prepared and frozen {len(jobs)} jobs; {len(cases)} tests passed; {output}")


if __name__ == "__main__":
    main()

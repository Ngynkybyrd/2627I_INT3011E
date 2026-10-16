"""Artificial analysis-only observations. No solver calls or research rows."""
import csv
import importlib.util
import json
from pathlib import Path
import uuid

import pytest

from sudoku.model import load_puzzle
from sudoku.runner import ROOT, CSV_FIELDS, RunnerConfig, prepare_run, read_json, write_json, write_result

spec = importlib.util.spec_from_file_location("analysis_script", ROOT / "scripts/analyze_results.py")
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def make_fixture(path, repetitions=3):
    """Build diagnostic artifacts using real frozen inputs and invented timings."""
    jobs = prepare_run(path, RunnerConfig(repetitions=repetitions))
    metadata = read_json(path / "run.json")
    metadata["diagnostic_artificial"] = True
    metadata["note"] = "ARTIFICIAL analysis fixture; not solver/benchmark evidence"
    write_json(path / "run.json", metadata)
    scopes, index = analysis.verify_dataset(ROOT)
    instance = next(i for i in scopes["B16"] if index[i]["source"] == "synthetic" and index[i]["N"] == 4)
    selected = [j for j in jobs if j["instance_id"] == instance
                and j["method"] in ("sat", "cpsat") and j["encoding"] in (None, "pairwise")]
    write_json(path / "executed-job-ids.json", [j["job_id"] for j in selected])
    puzzle = load_puzzle(ROOT / index[instance]["file"])
    witness = read_json(ROOT / index[instance]["witness_file"])["solution"]
    for job in selected:
        build = .01 * job["repetition"]
        solve = .02 * job["repetition"] * (2 if job["method"] == "cpsat" else 1)
        stats = dict(primary_variables=64, auxiliary_variables=0, total_variables=64,
                     clauses=4 * 16 * 7 + puzzle.clue_count) if job["method"] == "sat" else None
        write_result(path, job, dict(status="SAT", raw_status="ARTIFICIAL_FIXTURE", build_seconds=build,
                                     solve_seconds=solve, total_seconds=build + solve,
                                     stats=stats, validation=dict(valid=True), solution=witness,
                                     guard_phase="complete"))
    return selected


@pytest.fixture
def run(tmp_path):
    path = tmp_path / "artificial-analysis-run"
    make_fixture(path)
    return path


def csv_rows(run):
    with (run / "results.csv").open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def replace_rows(run, rows):
    with (run / "results.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def validate(run):
    return analysis.validate_run(run, partial=True, diagnostic=True)


def test_checked_median_matched_and_case_sensitive_metadata(run):
    rows, audit, scopes = validate(run)
    instances, summary, pairs = analysis.summarize(rows, scopes)
    assert len(rows) == len(audit["solutions"]) == 6
    assert all(r["n"] == 2 and r["N"] == 4 for r in rows)
    sat = next(i for i in instances if i["configuration"] == "sat:pairwise")
    assert sat["median_total_seconds"] == pytest.approx(.06)
    assert len(pairs) == 1 and pairs[0]["scope"] == "B16" and pairs[0]["matched_count"] == 1
    assert pairs[0]["median_paired_a_over_b"] == pytest.approx(.1 / .06)  # cpsat / sat
    assert all(s["solved_runs"] == 3 for s in summary)


def test_one_rep_pilot_has_no_median_or_speed(tmp_path):
    path = tmp_path / "one-rep"
    make_fixture(path, 1)
    rows, audit, scopes = validate(path)
    instances, summary, pairs = analysis.summarize(rows, scopes)
    assert audit["planned_jobs"] == 302
    assert all(i["median_total_seconds"] is None for i in instances)
    assert all(s["solved_instances_three"] == 0 for s in summary)
    assert all(p["matched_count"] == 0 and p["median_a_seconds"] is None for p in pairs)


@pytest.mark.parametrize("status,penalty", [("TIMEOUT", 20), ("ERROR", None), ("LICENSE_LIMIT", None),
                                           ("UNAVAILABLE", None), ("INVALID_INPUT", None)])
def test_penalties_only_timeout(run, status, penalty):
    rows = csv_rows(run)
    rows[0].update(status=status, validation="", solution_artifact="", build_seconds="", solve_seconds="", total_seconds="")
    replace_rows(run, rows)
    checked, _, scopes = validate(run)
    assert checked[0]["par2_seconds"] == penalty
    instances, summary, pairs = analysis.summarize(checked, scopes)
    assert sum(i["three_sat_repetitions"] for i in instances) == 1
    assert pairs[0]["matched_count"] == 0
    assert sum(s[status + "_runs"] for s in summary) == 1


@pytest.mark.parametrize("field,value", [("scope", "C10"), ("repetition", "9"), ("encoding", "bitwise"),
                                        ("run_id", "wrong"), ("status", "OPTIMAL"), ("guard_phase", "invalid"),
                                        ("build_seconds", "nan"), ("solve_seconds", "-1"),
                                        ("total_seconds", "0.99"), ("validation", "fail"),
                                        ("solution_artifact", "../outside.json"), ("cutoff_seconds", "20")])
def test_reject_bad_csv(run, field, value):
    rows = csv_rows(run)
    rows[0][field] = value
    replace_rows(run, rows)
    with pytest.raises((ValueError, FileNotFoundError)):
        validate(run)


def test_duplicate_missing_and_order(run):
    rows = csv_rows(run)
    replace_rows(run, rows + [rows[0]])
    with pytest.raises(ValueError, match="Duplicate"):
        validate(run)
    replace_rows(run, rows[::-1])
    with pytest.raises(ValueError, match="order"):
        validate(run)
    replace_rows(run, rows[:-1])
    _, audit, _ = validate(run)
    assert len(audit["missing_executed_ids"]) == 1


@pytest.mark.parametrize("artifact,key", [("schedule.json", "schedule"), ("executed-job-ids.json", "executed")])
def test_bad_plan(run, artifact, key):
    value = read_json(run / artifact)
    value.append(value[0])
    write_json(run / artifact, value)
    with pytest.raises(ValueError):
        validate(run)


def test_freeze_and_artifact_checker(run):
    metadata = read_json(run / "run.json")
    original = metadata["dataset_freeze_sha256"]
    metadata["dataset_freeze_sha256"] = "0" * 64
    write_json(run / "run.json", metadata)
    with pytest.raises(ValueError, match="freeze hash"):
        validate(run)
    metadata["dataset_freeze_sha256"] = original
    write_json(run / "run.json", metadata)
    row = csv_rows(run)[0]
    artifact = run / row["solution_artifact"]
    value = read_json(artifact)
    value["solution"][0][0] = 0
    write_json(artifact, value)
    with pytest.raises(ValueError, match="checker rejected"):
        validate(run)


def test_unsat_research_disagreement_and_artificial_isolation(run):
    with pytest.raises(ValueError, match="Artificial"):
        analysis.validate_run(run, partial=True)
    metadata = read_json(run / "run.json")
    metadata.pop("diagnostic_artificial")
    write_json(run / "run.json", metadata)
    rows = csv_rows(run)
    rows[0].update(status="UNSAT", validation="", solution_artifact="")
    replace_rows(run, rows)
    with pytest.raises(ValueError, match="UNSAT disagrees"):
        analysis.validate_run(run, partial=True)
    with pytest.raises(ValueError, match="UNSAT disagrees"):
        validate(run)  # Diagnostic mode alone cannot waive real-data SAT evidence.


@pytest.mark.parametrize("phase", ["startup", "postprocessing", "cleanup", "guard"])
def test_timeout_phase_consistency(run, phase):
    rows = csv_rows(run)
    rows[0].update(status="TIMEOUT", guard_phase=phase, validation="", solution_artifact="",
                   build_seconds="", solve_seconds="", total_seconds="")
    replace_rows(run, rows)
    with pytest.raises(ValueError, match="TIMEOUT outside"):
        validate(run)


def test_sat_beyond_cutoff_and_bad_counts(run):
    rows = csv_rows(run)
    rows[0].update(build_seconds="5", solve_seconds="6", total_seconds="11")
    replace_rows(run, rows)
    with pytest.raises(ValueError, match="beyond cutoff"):
        validate(run)
    rows = csv_rows(run)
    sat = next(row for row in rows if row["method"] == "sat")
    rows[0].update(build_seconds=".01", solve_seconds=".02", total_seconds=".03")
    sat["primary_variables"] = "729"
    replace_rows(run, rows)
    with pytest.raises(ValueError, match="CNF"):
        validate(run)


def test_matching_scopes_and_strata(run):
    checked, _, _ = validate(run)
    base = next(row for row in checked if row["method"] == "sat")
    artificial = []
    scopes = {"S80": ["x", "y", "z"], "B16": ["x", "y"], "C10": ["x"]}
    for configuration, ids in (("sat:pairwise", scopes["S80"]), ("sat:bitwise", scopes["S80"]),
                               ("cpsat", scopes["B16"]), ("gurobi", scopes["C10"])):
        for instance_id in ids:
            for repetition in (1, 2, 3):
                artificial.append(dict(base, instance_id=instance_id, configuration=configuration,
                                       method=configuration.split(":")[0], repetition=repetition,
                                       source="public" if instance_id == "y" else "synthetic"))
    _, _, pairs = analysis.summarize(artificial, scopes)
    satpair = [p for p in pairs if p["scope"] == "S80"]
    assert sum(p["matched_count"] for p in satpair) == 3
    cp_pairs = [p for p in pairs if p["configuration_a"] == "cpsat" and p["configuration_b"] == "sat:pairwise"]
    assert sum(p["matched_count"] for p in cp_pairs) == 2
    assert {p["source"] for p in cp_pairs} == {"public", "synthetic"}
    assert all(p["instance_ids"] == "x" for p in pairs if p["scope"] == "C10")


def test_duplicate_across_runs_and_unsat_mixture(run):
    rows, _, scopes = validate(run)
    with pytest.raises(ValueError, match="across runs"):
        analysis.summarize(rows + rows, scopes)
    rows[0]["status"] = "UNSAT"
    with pytest.raises(ValueError, match="disagreement"):
        analysis.summarize(rows, scopes)


def test_render_diagnostic_exports(run):
    output = ROOT / "diagnostics/analysis/fixtures" / ("export-" + uuid.uuid4().hex)
    audit = analysis.analyze([run], output, mode="diagnostic")
    assert audit["mode"] == "diagnostic" and audit["observed_rows"] == 6
    assert "NOT FINAL" in audit["notice"]
    for name in ("summary.csv", "summary.tex", "instances.csv", "matched-pairs.csv", "cnf.csv", "cnf.tex",
                 "run-par2.csv", "cnf-variables.png", "cnf-clauses.pdf", "status-counts.png"):
        assert (output / name).stat().st_size > 0
    assert list(output.glob("matched-time-*.png"))
    with pytest.raises(FileExistsError):
        analysis.analyze([run], output, mode="diagnostic")


def test_final_refuses_partial_and_diagnostic_location(run, tmp_path):
    with pytest.raises(ValueError, match="complete"):
        analysis.validate_run(run, partial=False, diagnostic=True)
    with pytest.raises(ValueError, match="diagnostics/analysis"):
        analysis.analyze([run], ROOT / "results/should-never-be-created", mode="diagnostic")


def test_empty_partial_preserves_missing_without_zero_medians(run):
    replace_rows(run, [])
    rows, audit, scopes = validate(run)
    assert rows == [] and len(audit["missing_executed_ids"]) == 6
    assert analysis.summarize(rows, scopes) == ([], [], [])
    output = ROOT / "diagnostics/analysis/fixtures" / ("empty-" + uuid.uuid4().hex)
    result = analysis.analyze([run], output, mode="diagnostic")
    assert result["observed_rows"] == 0
    assert "No eligible observations" in (output / "summary.tex").read_text(encoding="utf-8")


def test_unsat_only_artificial_fixture_is_not_solved(run):
    rows = csv_rows(run)
    for row in rows:
        row.update(status="UNSAT", validation="", solution_artifact="")
    replace_rows(run, rows)
    checked, _, scopes = validate(run)
    _, summary, pairs = analysis.summarize(checked, scopes)
    assert all(s["solved_runs"] == s["solved_instances_three"] == 0 for s in summary)
    assert all(p["matched_count"] == 0 for p in pairs)

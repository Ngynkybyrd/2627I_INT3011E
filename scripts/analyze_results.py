"""Validate runner v1 artifacts and generate traceable tables/figures; never solve."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import itertools
import json
import math
import os
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sudoku.model import load_puzzle
from sudoku.runner import (CSV_FIELDS, RunnerConfig, make_schedule, read_json,
                           sha256, verify_dataset)
from sudoku.validation import check_solution

STATUSES = {"SAT", "UNSAT", "TIMEOUT", "ERROR", "INVALID_INPUT", "UNAVAILABLE", "LICENSE_LIMIT"}
TIMES = ("build_seconds", "solve_seconds", "total_seconds")
COUNTS = ("primary_variables", "auxiliary_variables", "total_variables", "clauses")
PHASES = {"complete", "startup", "measurement", "postprocessing", "protocol", "validation", "guard", "cleanup"}


def contained(root, relative):
    path = (root / relative).resolve()
    if not relative or not path.is_relative_to(root.resolve()):
        raise ValueError("Artifact path escapes its root")
    return path


def number(value, *, integer=False):
    if value == "":
        return None
    parsed = int(value) if integer else float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError("Negative or nonfinite numeric value")
    return parsed


def validate_run(run_dir, *, root=ROOT, partial=False, diagnostic=False):
    """Return checked rows and audit; partial permits missing executed rows only."""
    root, run_dir = Path(root).resolve(), Path(run_dir).resolve()
    scopes, index = verify_dataset(root)
    metadata = read_json(run_dir / "run.json")
    if metadata.get("diagnostic_artificial") and not diagnostic:
        raise ValueError("Artificial fixture cannot be used as research results")
    if metadata["schema_version"] != 1 or metadata["run_id"] != run_dir.name:
        raise ValueError("run.json schema/run_id mismatch")
    if metadata["dataset_freeze_sha256"] != sha256(root / "data/freeze.json"):
        raise ValueError("Run dataset freeze hash mismatch")
    config = RunnerConfig(**metadata["config"])
    schedule = read_json(run_dir / "schedule.json")
    if schedule != make_schedule(config, root=root):
        raise ValueError("Schedule identity/count/order mismatch")
    planned = {job["job_id"]: job for job in schedule}
    executed = read_json(run_dir / "executed-job-ids.json")
    if (not isinstance(executed, list) or len(executed) != len(set(executed))
            or not set(executed) <= planned.keys()
            or executed != [job["job_id"] for job in schedule if job["job_id"] in set(executed)]):
        raise ValueError("Invalid executed-job-ids identity/order/duplicates")
    if not partial and (config.repetitions != 3 or set(executed) != planned.keys()):
        raise ValueError("Final mode requires complete three-repetition schedule")
    rows, seen, artifacts = [], set(), []
    with (run_dir / "results.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(CSV_FIELDS):
            raise ValueError("CSV schema mismatch")
        for line, raw in enumerate(reader, 2):
            if None in raw or None in raw.values():
                raise ValueError(f"Malformed CSV row {line}")
            row = dict(raw)
            job_id = row["job_id"]
            if job_id in seen or job_id not in executed:
                raise ValueError("Duplicate or unscheduled result job_id")
            seen.add(job_id)
            job = planned[job_id]
            if row["schema_version"] != "1" or row["run_id"] != metadata["run_id"]:
                raise ValueError("Row schema/run_id mismatch")
            for key in ("instance_id", "method", "encoding", "scope", "repetition", "cutoff_seconds"):
                actual = row[key]
                expected = job[key]
                if key == "repetition":
                    actual = int(actual)
                elif key == "cutoff_seconds":
                    actual = number(actual)
                else:
                    expected = expected or ""
                if actual != expected:
                    raise ValueError(f"Row/schedule mismatch: {key}")
            row["repetition"] = int(row["repetition"])
            row["cutoff_seconds"] = number(row["cutoff_seconds"])
            status = row["status"]
            if status not in STATUSES or row["guard_phase"] not in PHASES:
                raise ValueError("Invalid status/guard_phase")
            if status == "UNSAT" and not (diagnostic and metadata.get("diagnostic_artificial") is True):
                raise ValueError(f"UNSAT disagrees with frozen SAT evidence: {job_id}; stop using this configuration")
            if status == "TIMEOUT" and row["guard_phase"] not in ("measurement", "complete"):
                raise ValueError("TIMEOUT outside measurement phase")
            if status in ("SAT", "UNSAT") and row["guard_phase"] != "complete":
                raise ValueError("Completed status outside complete phase")
            if row["validation"] not in ("", "pass", "fail"):
                raise ValueError("Invalid validation token")
            for key in TIMES + COUNTS:
                row[key] = number(row[key], integer=key in COUNTS)
            build, solve, total = (row[key] for key in TIMES)
            if total is not None and build is not None and solve is not None:
                if not math.isclose(total, build + solve, rel_tol=1e-7, abs_tol=1e-7):
                    raise ValueError("Total differs from build+solve")
            if status in ("SAT", "UNSAT"):
                if any(row[key] is None for key in TIMES) or total > row["cutoff_seconds"]:
                    raise ValueError("Completed result missing timing or beyond cutoff")
            record = index[row["instance_id"]]
            puzzle_path = contained(root, record["file"])
            if sha256(puzzle_path) != record["sha256"]:
                raise ValueError("Input checksum mismatch")
            puzzle = load_puzzle(puzzle_path)
            if (puzzle.n, puzzle.N, puzzle.clue_count) != (record["n"], record["N"], record["clue_count"]):
                raise ValueError("Manifest/input n/N/clues mismatch")
            if row["method"] != "sat" and any(row[key] is not None for key in COUNTS):
                raise ValueError("Baseline has SAT CNF counts")
            counts = [row[key] for key in COUNTS]
            if row["method"] == "sat" and any(value is not None for value in counts):
                if (any(value is None for value in counts) or counts[0] != puzzle.N**3
                        or counts[2] != counts[0] + counts[1] or counts[3] <= 0):
                    raise ValueError("Invalid CNF counts")
                if row["encoding"] == "pairwise" and (counts[1] != 0 or counts[3] !=
                        4 * puzzle.N**2 * (1 + puzzle.N * (puzzle.N - 1) // 2) + puzzle.clue_count):
                    raise ValueError("Pairwise formula mismatch")
            elif row["method"] == "sat" and status == "SAT":
                raise ValueError("SAT result missing CNF counts")
            if status == "SAT":
                if row["validation"] != "pass":
                    raise ValueError("SAT lacks checker pass")
                artifact = contained(run_dir, row["solution_artifact"])
                solution = read_json(artifact)
                if (solution["job_id"] != job_id or solution["instance_id"] != row["instance_id"]
                        or solution.get("validation", {}).get("valid") is not True):
                    raise ValueError("Solution artifact identity/validation mismatch")
                checked = check_solution(puzzle, solution["solution"])
                if not checked.valid:
                    raise ValueError(f"Solution checker rejected artifact: {checked.message}")
                artifacts.append({"job_id": job_id, "path": row["solution_artifact"],
                                  "sha256": sha256(artifact), "checker": "pass"})
            elif row["solution_artifact"] or row["validation"] == "pass":
                raise ValueError("Non-SAT row carries accepted solution")
            row.update({key: record.get(key) for key in
                        ("source", "n", "N", "clue_count", "clue_density_requested")})
            row["configuration"] = row["method"] + (":" + row["encoding"] if row["encoding"] else "")
            row["par2_seconds"] = (2 * row["cutoff_seconds"] if status == "TIMEOUT" else
                                   total if status in ("SAT", "UNSAT") else None)
            rows.append(row)
    if [row["job_id"] for row in rows] != [job_id for job_id in executed if job_id in seen]:
        raise ValueError("CSV does not follow execution order")
    missing = [job_id for job_id in executed if job_id not in seen]
    if missing and not partial:
        raise ValueError("Missing executed rows")
    audit = {"run_id": run_dir.name, "planned_jobs": len(schedule), "selected_jobs": len(executed),
             "observed_rows": len(rows), "missing_executed_ids": missing,
             "unselected_jobs": len(schedule) - len(executed), "config": metadata["config"],
             "dataset_freeze_sha256": metadata["dataset_freeze_sha256"],
             "code_sha256": metadata["code_sha256"], "machine": metadata["machine"],
             "packages": metadata["packages"], "solutions": artifacts,
             "schedule_counts": dict(Counter(j["method"] + (":" + j["encoding"] if j["encoding"] else "") for j in schedule)),
             "selected_counts": dict(Counter(planned[i]["method"] + (":" + planned[i]["encoding"] if planned[i]["encoding"] else "") for i in executed)),
             "inputs": {name: sha256(run_dir / name) for name in
                        ("run.json", "schedule.json", "executed-job-ids.json", "results.csv")}}
    return rows, audit, scopes


def summarize(rows, scopes):
    """Keep strata and statuses separate; paired speeds use per-instance medians."""
    repeats = defaultdict(list)
    for row in rows:
        repeats[(row["instance_id"], row["configuration"])].append(row)
    instances = []
    for (instance_id, configuration), group in sorted(repeats.items()):
        by_rep = {row["repetition"] for row in group}
        if len(by_rep) != len(group):
            raise ValueError("Repeated configuration/instance/repetition across runs")
        statuses = {row["status"] for row in group}
        if "SAT" in statuses and "UNSAT" in statuses:
            raise ValueError("SAT/UNSAT disagreement")
        complete = by_rep == {1, 2, 3} and statuses == {"SAT"}
        first = group[0]
        item = {key: first[key] for key in ("instance_id", "configuration", "scope", "source", "n", "N",
                                           "clue_count", "clue_density_requested")}
        item.update(observed_repetitions=len(group), three_sat_repetitions=complete)
        item.update({"median_" + key: statistics.median(row[key] for row in group) if complete else None
                     for key in TIMES})
        for key in COUNTS:
            values = {row[key] for row in group if row[key] is not None}
            if len(values) > 1:
                raise ValueError("CNF counts changed across repetitions")
            item[key] = next(iter(values), None)
        instances.append(item)
    statuses_by_instance = defaultdict(set)
    for row in rows:
        statuses_by_instance[row["instance_id"]].add(row["status"])
    if any({"SAT", "UNSAT"} <= values for values in statuses_by_instance.values()):
        raise ValueError("Cross-method SAT/UNSAT disagreement")
    groups = defaultdict(list)
    for row in rows:
        groups[(row["configuration"], row["scope"], row["source"], row["N"],
                row["clue_density_requested"])].append(row)
    summary = []
    for key, group in sorted(groups.items(), key=lambda pair: str(pair[0])):
        config, scope, source, size, density = key
        successful = [item for item in instances if item["configuration"] == config
                      and item["source"] == source and item["N"] == size
                      and item["clue_density_requested"] == density and item["three_sat_repetitions"]]
        counts = Counter(row["status"] for row in group)
        penalties = [row["par2_seconds"] for row in group if row["par2_seconds"] is not None]
        summary.append(dict(configuration=config, scope=scope, source=source, N=size,
                            clue_density_requested=density, observed_runs=len(group),
                            observed_instances=len({row["instance_id"] for row in group}),
                            solved_runs=counts["SAT"],
                            solved_instances_any=len({row["instance_id"] for row in group if row["status"] == "SAT"}),
                            solved_instances_three=len(successful),
                            **{status + "_runs": counts[status] for status in sorted(STATUSES)},
                            par2_eligible_runs=len(penalties),
                            mean_par2_seconds=statistics.mean(penalties) if penalties else None,
                            **{"median_instance_" + t: statistics.median(item["median_" + t] for item in successful)
                               if successful else None for t in TIMES}))
    paired = []
    configs = sorted({row["configuration"] for row in rows})
    eligible = {(item["instance_id"], item["configuration"]): item for item in instances
                if item["three_sat_repetitions"]}
    for a, b in itertools.combinations(configs, 2):
        scope = "C10" if any(c.split(":")[0] in ("gurobi", "cplex_mip", "cpoptimizer") for c in (a, b)) else (
            "S80" if a.startswith("sat:") and b.startswith("sat:") else "B16")
        common = [instance_id for instance_id in scopes[scope]
                  if (instance_id, a) in eligible and (instance_id, b) in eligible]
        # Pair each source/size/density stratum; never combine public with synthetic.
        strata = defaultdict(list)
        for instance_id in common:
            item = eligible[(instance_id, a)]
            strata[(item["source"], item["N"], item["clue_density_requested"])].append(instance_id)
        if not strata:
            strata[("", "", "")] = []
        for (source, size, density), ids in strata.items():
            av = [eligible[(i, a)]["median_total_seconds"] for i in ids]
            bv = [eligible[(i, b)]["median_total_seconds"] for i in ids]
            paired.append(dict(configuration_a=a, configuration_b=b, scope=scope, source=source, N=size,
                               clue_density_requested=density, matched_count=len(ids), instance_ids=";".join(ids),
                               median_a_seconds=statistics.median(av) if av else None,
                               median_b_seconds=statistics.median(bv) if bv else None,
                               median_paired_a_over_b=statistics.median([x/y for x, y in zip(av, bv)])
                               if bv and all(y > 0 for y in bv) else None))
    return instances, summary, paired


def write_table(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: f"{value:.6f}" if isinstance(value, float) else value
                          for key, value in row.items()} for row in rows)


def latex_escape(value):
    text = str(value)
    return "".join({"\\": r"\textbackslash{}", "_": r"\_", "%": r"\%", "&": r"\&",
                    "#": r"\#", "$": r"\$", "{": r"\{", "}": r"\}"}.get(c, c) for c in text)


def write_latex(path, rows, mode):
    fields = list(rows[0]) if rows else []
    if not fields:
        path.write_text(f"% {mode.upper()} — no eligible observations\n"
                        "\\begin{tabular}{l}\nNo eligible observations \\\\\n\\end{tabular}\n", encoding="utf-8")
        return
    def cell(value):
        return "--" if value is None else f"{value:.6f}" if isinstance(value, float) else latex_escape(value)
    lines = [f"% {mode.upper()} — automatically generated; seconds; six decimals", 
             r"\begin{tabular}{" + "l" * len(fields) + "}", r"\hline",
             " & ".join(map(latex_escape, fields)) + r" \\"]
    lines.extend(" & ".join(cell(row[field]) for field in fields) + r" \\" for row in rows)
    lines += [r"\hline", r"\end{tabular}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot_tables(output, instances, summary, paired, mode):
    os.environ.setdefault("MPLCONFIGDIR", str(output / "mplconfig"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    groups = defaultdict(list)
    for item in instances:
        if item["clauses"] is not None:
            groups[(item["configuration"], item["source"], item["clue_density_requested"])].append(item)
    paths = []
    for metric, filename in (("total_variables", "cnf-variables"), ("clauses", "cnf-clauses"),
                             ("median_total_seconds", "total-time")):
        fig, ax = plt.subplots(figsize=(8, 5.5))
        plotted = False
        available = groups if metric != "median_total_seconds" else defaultdict(list)
        for label, items in sorted(available.items(), key=lambda pair: str(pair[0])):
            sizes = sorted({item["N"] for item in items})
            values = [statistics.median(item[metric] for item in items if item["N"] == n) for n in sizes]
            ax.plot(sizes, values, marker="o", label=" / ".join(map(str, label)))
            plotted = True
        ax.set(xlabel="Board side N", ylabel="Seconds" if metric.endswith("seconds") else metric,
               title=f"{mode.upper()}: {filename}")
        ax.set_xticks(sorted({i["N"] for i in instances}) or [4, 9, 16, 25])
        if plotted:
            ax.legend(fontsize=6, loc="best")
        else:
            ax.text(.5, .5, "Runtime comparisons use matched pairs only.\nSee matched-time figures when three SAT repetitions exist.",
                    ha="center", va="center", transform=ax.transAxes)
        fig.text(.5, .02, "Source: checked CSV; pre-preprocessing CNF. Runtime: build + setup + solve.\n"
                 "Strata shown separately; runtime excludes incomplete/timeout groups; see counts and PAR-2 tables."
                 if metric.endswith("seconds") else "Source: checked CSV; CNF counts before preprocessing; median per size/stratum.",
                 ha="center", fontsize=8)
        fig.tight_layout(rect=(0, .10, 1, 1))
        for suffix in ("png", "pdf"):
            path = output / f"{filename}.{suffix}"
            fig.savefig(path, dpi=220)
            paths.append(path.name)
        plt.close(fig)
    pair_groups = defaultdict(list)
    for row in paired:
        if row["matched_count"]:
            pair_groups[(row["configuration_a"], row["configuration_b"], row["scope"])].append(row)
    for (a, b, scope), pair_rows in sorted(pair_groups.items()):
        strata = sorted({(row["source"], row["clue_density_requested"]) for row in pair_rows}, key=str)
        fig, axes = plt.subplots(1, len(strata), figsize=(max(8, 5 * len(strata)), 5.2), squeeze=False)
        for ax, stratum in zip(axes[0], strata):
            group = sorted([r for r in pair_rows if (r["source"], r["clue_density_requested"]) == stratum],
                           key=lambda r: r["N"])
            for config, key in ((a, "median_a_seconds"), (b, "median_b_seconds")):
                ax.plot([r["N"] for r in group], [r[key] for r in group], marker="o", label=config)
            ax.set(title=f"{stratum[0]} / density {stratum[1]}", xlabel="Board side N", ylabel="Total seconds")
            ax.set_xticks([r["N"] for r in group])
            ax.margins(y=.25)
            ax.legend(fontsize=8)
            for row in group:
                ax.annotate(f"n={row['matched_count']}", (row["N"], row["median_a_seconds"]),
                            xytext=(0, 8), textcoords="offset points", fontsize=8)
        fig.suptitle(f"{mode.upper()}: {a} vs {b} / {scope}", fontsize=12)
        fig.text(.5, .02, "Checked CSV; common IDs, three SAT repeats per method.\n"
                 "Median of per-instance totals; includes build/setup/solve.\n"
                 "Timeouts excluded here; see status counts and PAR-2 tables for full coverage.",
                 ha="center", fontsize=8)
        fig.tight_layout(rect=(0, .12, 1, .92))
        stem = "matched-time-" + a.replace(":", "-") + "-vs-" + b.replace(":", "-")
        for suffix in ("png", "pdf"):
            path = output / f"{stem}.{suffix}"
            fig.savefig(path, dpi=220)
            paths.append(path.name)
        plt.close(fig)
    counts = Counter()
    for row in summary:
        for status in STATUSES:
            counts[status] += row[status + "_runs"]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(list(sorted(STATUSES)), [counts[s] for s in sorted(STATUSES)])
    ax.set(title=f"{mode.upper()}: observed status counts", ylabel="Runs")
    from matplotlib.ticker import MaxNLocator
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.tick_params(axis="x", labelrotation=25)
    fig.tight_layout()
    fig.savefig(output / "status-counts.png", dpi=220)
    plt.close(fig)
    return paths + ["status-counts.png"]


def analyze(run_dirs, output, *, root=ROOT, mode="partial"):
    """Validate all inputs before creating a NEW output directory."""
    if mode not in ("final", "pilot", "partial", "diagnostic"):
        raise ValueError("Unknown mode")
    output = Path(output).resolve()
    if mode == "diagnostic" and not output.is_relative_to(Path(root).resolve() / "diagnostics/analysis"):
        raise ValueError("Artificial diagnostic output must stay in diagnostics/analysis")
    rows, audits, run_ids = [], [], set()
    for path in run_dirs:
        checked, audit, scopes = validate_run(path, root=root, partial=mode != "final", diagnostic=mode == "diagnostic")
        if audit["run_id"] in run_ids:
            raise ValueError("Duplicate run_id")
        run_ids.add(audit["run_id"])
        rows.extend(checked)
        audits.append(audit)
    if not audits:
        raise ValueError("At least one input run is required")
    # Cross-run aggregation is allowed only for identical experimental conditions.
    for audit in audits[1:]:
        for key in ("code_sha256", "machine", "packages", "dataset_freeze_sha256"):
            if audit[key] != audits[0][key]:
                raise ValueError(f"Incompatible runs: {key}")
        for key in ("cutoff_seconds", "startup_seconds", "postprocessing_seconds", "schedule_seed"):
            if audit["config"][key] != audits[0]["config"][key]:
                raise ValueError(f"Incompatible configs: {key}")
    if len({row["cutoff_seconds"] for row in rows}) > 1:
        raise ValueError("Mixed cutoff values")
    instances, summary, paired = summarize(rows, scopes)
    configurations = sorted(set().union(*(a["schedule_counts"] for a in audits)))
    coverage = []
    for configuration in configurations:
        method = configuration.split(":")[0]
        scope = "S80" if method == "sat" else "B16" if method in ("cpsat", "highs") else "C10"
        group = [r for r in rows if r["configuration"] == configuration]
        coverage.append(dict(configuration=configuration, scope=scope,
                             scope_instances=len(scopes[scope]),
                             planned_jobs=sum(a["schedule_counts"].get(configuration, 0) for a in audits),
                             selected_jobs=sum(a["selected_counts"].get(configuration, 0) for a in audits),
                             observed_jobs=len(group), solved_runs=sum(r["status"] == "SAT" for r in group),
                             solved_instances_three=sum(i["configuration"] == configuration and i["three_sat_repetitions"]
                                                        for i in instances)))
    output.mkdir(parents=True, exist_ok=False)
    tables = {"coverage": coverage, "instances": instances, "summary": summary, "matched-pairs": paired,
              "run-par2": [{key: row[key] for key in ("run_id", "job_id", "status", "cutoff_seconds", "par2_seconds")}
                           for row in rows]}
    for name, table in tables.items():
        write_table(output / f"{name}.csv", table)
    # Compact paper-ready columns, rather than an unusably wide status table.
    paper = [{key: row[key] for key in ("configuration", "scope", "source", "N", "clue_density_requested",
                                       "observed_runs", "solved_runs", "TIMEOUT_runs", "solved_instances_three",
                                       "median_instance_total_seconds", "mean_par2_seconds")} for row in summary]
    write_latex(output / "summary.tex", paper, mode)
    cnf = [{key: item[key] for key in ("instance_id", "configuration", "source", "N", "clue_count", *COUNTS)}
           for item in instances if item["clauses"] is not None]
    write_table(output / "cnf.csv", cnf)
    write_latex(output / "cnf.tex", cnf, mode)
    figures = plot_tables(output, instances, summary, paired, mode)
    audit = {"analysis_api_version": 1, "mode": mode,
             "analyzer_sha256": sha256(Path(__file__)),
             "notice": "FINAL DATA ANALYSIS" if mode == "final" else "NOT FINAL RESEARCH RESULTS",
             "runs": audits, "observed_rows": len(rows), "figures": figures,
             "rules": {"median": "exact repetitions 1,2,3 all SAT; median per instance then group median",
                       "matched": "pairwise common IDs with three SAT repetitions per configuration, stratified",
                       "par2": "per run: SAT/UNSAT total; TIMEOUT 2*cutoff; all other statuses excluded",
                       "solution_checksum": "SHA-256 recorded at analysis; schema v1 provides no prior solution hash"}}
    audit["output_sha256"] = {p.name: sha256(p) for p in sorted(output.iterdir()) if p.is_file()}
    (output / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("final", "pilot", "partial", "diagnostic"))
    args = parser.parse_args()
    audit = analyze(args.run, args.output, mode=args.mode)
    print(f"analysis-api v1: {args.mode}; validated {audit['observed_rows']} rows; {args.output}")


if __name__ == "__main__":
    main()

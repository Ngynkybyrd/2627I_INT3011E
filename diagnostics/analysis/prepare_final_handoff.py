"""Independent arithmetic audit and compact paper exports; no solver calls."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics as st

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "results/raw/main-20261016-01"
EXPECTED = "aac4cde1fed90857ea81a1575e326049be71a528f27a6a744435b94c42dfdda7"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def same(actual, expected):
    assert math.isclose(float(actual), expected, rel_tol=1e-6, abs_tol=5.01e-7), (actual, expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=ROOT / "results/summary/main-20261016-01")
    args = parser.parse_args()
    output = args.summary.resolve()
    assert sha(RAW / "results.csv") == EXPECTED
    rows = read(RAW / "results.csv")
    audit = load(output / "audit.json")
    accepted = load(ROOT / "diagnostics/main-acceptance/main-20261016-01.json")
    assert audit["mode"] == "final" and len(rows) == audit["observed_rows"] == 906
    assert Counter(r["status"] for r in rows) == {"SAT": 903, "TIMEOUT": 3}
    assert len(audit["runs"]) == 1 and audit["runs"][0]["missing_executed_ids"] == []
    assert {r["scope"]: sum(x["scope"] == r["scope"] for x in rows) for r in rows} == {"S80": 720, "B16": 96, "C10": 90}
    assert audit["runs"][0]["inputs"]["results.csv"] == EXPECTED == accepted["results_sha256"]
    previous = {r["job_id"]: r["sha256"] for r in accepted["audit"]["solutions"]}
    current = {r["job_id"]: r["sha256"] for r in audit["runs"][0]["solutions"]}
    assert previous == current and len(current) == 903
    for name, digest in audit["output_sha256"].items():
        assert sha(output / name) == digest
    groups = defaultdict(list)
    line_ids = {}
    for line, row in enumerate(rows, 2):
        config = row["method"] + (":" + row["encoding"] if row["encoding"] else "")
        groups[(row["instance_id"], config)].append(row)
        line_ids[row["job_id"]] = line
    instances = read(output / "instances.csv")
    eligible = {}
    for item in instances:
        group = groups[item["instance_id"], item["configuration"]]
        complete = len(group) == 3 and {r["repetition"] for r in group} == {"1", "2", "3"} and all(r["status"] == "SAT" for r in group)
        assert (item["three_sat_repetitions"] == "True") == complete
        if complete:
            for key in ("build_seconds", "solve_seconds", "total_seconds"):
                same(item["median_" + key], st.median(float(r[key]) for r in group))
            eligible[item["instance_id"], item["configuration"]] = item
        else:
            assert all(item["median_" + k] == "" for k in ("build_seconds", "solve_seconds", "total_seconds"))
    penalties = {r["job_id"]: r for r in read(output / "run-par2.csv")}
    for row in rows:
        expected = 20.0 if row["status"] == "TIMEOUT" else float(row["total_seconds"])
        same(penalties[row["job_id"]]["par2_seconds"], expected)
    scopes = load(ROOT / "data/scopes.json")
    manifest = {r["instance_id"]: r for r in load(ROOT / "data/manifest.json")["records"]}
    pairs = read(output / "matched-pairs.csv")
    for pair in pairs:
        a, b = pair["configuration_a"], pair["configuration_b"]
        expected = [i for i in scopes[pair["scope"]] if (i, a) in eligible and (i, b) in eligible
                    and manifest[i]["source"] == pair["source"] and str(manifest[i]["N"]) == pair["N"]
                    and ("" if manifest[i]["clue_density_requested"] is None else f"{manifest[i]['clue_density_requested']:.6f}") == pair["clue_density_requested"]]
        assert pair["instance_ids"].split(";") == expected and int(pair["matched_count"]) == len(expected)
        av = [st.median(float(r["total_seconds"]) for r in groups[i, a]) for i in expected]
        bv = [st.median(float(r["total_seconds"]) for r in groups[i, b]) for i in expected]
        same(pair["median_a_seconds"], st.median(av))
        same(pair["median_b_seconds"], st.median(bv))
        same(pair["median_paired_a_over_b"], st.median(x/y for x, y in zip(av, bv)))
    timeout = [r for r in rows if r["status"] == "TIMEOUT"]
    assert len(timeout) == 3 and all(r["instance_id"] == "synthetic-N25-p30-s0" and r["method"] == "highs" for r in timeout)
    assert next(r for r in timeout if r["repetition"] == "3")["total_seconds"] == ""
    paper = output / "paper"
    paper.mkdir(exist_ok=False)
    spec = importlib.util.spec_from_file_location("analysis_api", ROOT / "scripts/analyze_results.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    coverage = read(output / "coverage.csv")
    api.write_latex(paper / "coverage.tex", coverage, "final")
    api.write_table(paper / "coverage.csv", coverage)
    selected_pairs = [r for r in pairs if r["configuration_b"] == "sat:pairwise" and
                      r["configuration_a"] in ("cpsat", "highs", "gurobi", "cplex_mip", "cpoptimizer")]
    api.write_table(paper / "baseline-matched.csv", selected_pairs)
    compact = []
    for r in selected_pairs:
        compact.append(dict(method=r["configuration_a"], scope=r["scope"], source="synthetic" if r["source"] == "synthetic" else "public",
                            N=int(r["N"]), density=float(r["clue_density_requested"]) if r["clue_density_requested"] else None,
                            matched=int(r["matched_count"]), backend_s=float(r["median_a_seconds"]),
                            pairwise_s=float(r["median_b_seconds"]), ratio=float(r["median_paired_a_over_b"])))
    api.write_latex(paper / "baseline-matched.tex", compact, "final")
    cnf = read(output / "cnf.csv")
    encs = ("pairwise", "seqcounter", "bitwise")
    selected_cnf = [r for r in cnf if r["instance_id"] in {f"synthetic-N{n:02}-p50-s0" for n in (4, 9, 16, 25)}]
    api.write_table(paper / "cnf-size.csv", selected_cnf)
    api.write_latex(paper / "cnf-size.tex", [{k: int(r[k]) if k in ("N", "clue_count", "primary_variables", "auxiliary_variables", "total_variables", "clauses") else r[k]
                                           for k in ("N", "configuration", "clue_count", "primary_variables", "auxiliary_variables", "total_variables", "clauses")} for r in selected_cnf], "final")
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "diagnostics/analysis/mplconfig"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = ("#24587a", "#bd581e", "#387b53")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, metric, label in zip(axes, ("total_variables", "clauses"), ("Variables (primary + auxiliary)", "Clauses")):
        for enc, color in zip(encs, colors):
            g = sorted([r for r in selected_cnf if r["configuration"] == "sat:" + enc], key=lambda r: int(r["N"]))
            ax.plot([int(r["N"]) for r in g], [int(r[metric]) for r in g], "o-", label=enc, color=color)
        ax.set(xlabel="Board side N", ylabel=label, yscale="log", xticks=[4, 9, 16, 25])
        ax.legend(fontsize=9)
        ax.grid(alpha=.2)
    fig.suptitle("CNF size: fixed 50% clue density (synthetic)")
    fig.text(.5, .02, "Measured before preprocessing; seed 0 representative (counts identical across five seeds per size/density).\n"
             "Source: main-20261016-01, cnf.csv; exact counts in paper/cnf-size.csv.", ha="center", fontsize=8)
    fig.tight_layout(rect=(0, .12, 1, .94))
    for ext in ("png", "pdf", "svg"):
        fig.savefig(paper / ("figure-cnf-size." + ext), dpi=300)
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(11, 4.3), sharey=True)
    runtime_data = []
    for ax, density in zip(axes, (.3, .5, .7)):
        for enc, color in zip(encs, colors):
            values = []
            for n in (4, 9, 16, 25):
                ids = [i for i in scopes["S80"] if manifest[i]["source"] == "synthetic" and manifest[i]["N"] == n and manifest[i]["clue_density_requested"] == density]
                assert len(ids) == 5 and all((i, "sat:" + e) in eligible for i in ids for e in encs)
                median = st.median(st.median(float(r["total_seconds"]) for r in groups[i, "sat:" + enc]) for i in ids)
                values.append(median)
                runtime_data.append(dict(encoding=enc, N=n, density=density, matched_instances=5, total_seconds=median, instance_ids=";".join(ids)))
            ax.plot([4, 9, 16, 25], values, "o-", label=enc, color=color)
        ax.set(title=f"Clues {density:.0%}", xlabel="Board side N", xticks=[4, 9, 16, 25], yscale="log")
        ax.grid(alpha=.2)
    axes[0].set_ylabel("Median total time (s)")
    axes[1].legend(fontsize=9, loc="upper left")
    fig.suptitle("SAT encoding runtime on identical synthetic instances")
    fig.text(.5, .02, "Each point: five common IDs, median of three-repeat SAT medians; all encodings solved all 60 synthetic instances.\n"
             "10 s cutoff includes build + setup + solve; no SAT timeouts. Public 9×9 is reported separately in summary.csv.", ha="center", fontsize=8)
    fig.tight_layout(rect=(0, .13, 1, .94))
    for ext in ("png", "pdf", "svg"):
        fig.savefig(paper / ("figure-runtime." + ext), dpi=300)
    plt.close(fig)
    api.write_table(paper / "runtime-matched.csv", runtime_data)
    claims = []
    for r in rows:
        claims.append(dict(csv_line=line_ids[r["job_id"]], job_id=r["job_id"], instance_id=r["instance_id"],
                           method=r["method"], encoding=r["encoding"], repetition=r["repetition"], status=r["status"]))
    api.write_table(paper / "raw-row-index.csv", claims)
    assert sha(RAW / "results.csv") == EXPECTED
    verification = dict(accepted=True, raw_sha256_before=EXPECTED, raw_sha256_after=sha(RAW / "results.csv"),
                        rows=906, independently_recomputed_medians=len(eligible), checked_pairs=len(pairs),
                        solution_hashes_equal_root_acceptance=903, statuses=dict(Counter(r["status"] for r in rows)),
                        no_pilot_or_diagnostic_merge=True, timeout_penalty_each=20, timeout_penalty_sum=60,
                        raw_missing_timeout_timing_preserved=True,
                        analyzer_unchanged=sha(ROOT / "scripts/analyze_results.py") == audit["analyzer_sha256"],
                        paper_outputs_sha256={p.name: sha(p) for p in paper.iterdir() if p.is_file()})
    (output / "verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in verification.items() if k != "paper_outputs_sha256"}, indent=2))


if __name__ == "__main__":
    main()

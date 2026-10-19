"""Independent final CSV/paired/quantile/receipt checks, no solver or live DB."""
import csv
import hashlib
import json
import math
from collections import Counter,defaultdict
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"results/final-analysis/final-20261020-rep1"
csv.field_size_limit(16*1024*1024)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):
    with (OUT/n).open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))


def main():
    summary=json.loads((OUT/"summary.json").read_text());receipt=json.loads((OUT/"analysis-hashes.json").read_text())
    rows=read("instances.csv");pairs=read("runtime-common.csv");coverage=read("coverage.csv")
    assert len(rows)==110000 and len({r["instance_id"] for r in rows})==16000
    assert Counter(r["status"] for r in rows)=={"SAT":109664,"TIMEOUT":335,"ERROR":1}
    assert sum(int(r["observed_primary"]) for r in coverage)==110000
    assert all(sha(OUT/name)==expected for name,expected in receipt["files_sha256"].items())
    keys=("profile","session_id","workers","N","source","source_group","family","clue_percent")
    lookup=defaultdict(dict)
    grouped=defaultdict(list)
    for r in rows:
        grouped[tuple(r[k] for k in keys)+(r["configuration"],)].append(r)
        if r["status"]=="SAT":lookup[tuple(r[k] for k in keys)][r["instance_id"],r["configuration"]]=float(r["total_seconds"])
    for row in coverage:
        g=grouped[tuple(row[k] for k in keys)+(row["configuration"],)]
        assert len(g)==int(row["observed_primary"])
        for status in ("SAT","TIMEOUT","ERROR"):assert sum(r["status"]==status for r in g)==int(row[status])
    for pair in pairs:
        assert int(pair["workers"]) not in (24,40)
        values=lookup[tuple(pair[k] for k in keys)];a,b=pair["configuration_a"],pair["configuration_b"]
        ids=set(json.loads(pair["instance_ids"]))
        assert ids==({i for i,c in values if c==a}&{i for i,c in values if c==b}) and len(ids)==int(pair["matched_instances"])
        ratios=sorted(values[i,a]/values[i,b] for i in ids if values[i,b]>0)
        if len(ratios)==len(ids):
            mid=(len(ratios)-1)*.5;lo=math.floor(mid);hi=math.ceil(mid)
            assert math.isclose(ratios[lo]+(mid-lo)*(ratios[hi]-ratios[lo]),float(pair["median_single_run_ratio"]),rel_tol=1e-12)
        else:assert pair["median_single_run_ratio"]==""
        for side,c in (("a",a),("b",b)):
            data=sorted(values[i,c] for i in ids)
            for label,prob in (("median",.5),("p90",.9),("p95",.95)):
                h=(len(data)-1)*prob;lo=math.floor(h);hi=math.ceil(h);expected=data[lo]+(h-lo)*(data[hi]-data[lo])
                assert math.isclose(expected,float(pair[label+"_"+side+"_single_run_seconds"]),rel_tol=1e-12,abs_tol=1e-12)
    errors=[r for r in rows if r["status"]=="ERROR"];assert len(errors)==1 and errors[0]["guard_phase"]=="guard"
    assert all(errors[0][k]=="" for k in ("build_seconds","solve_seconds","total_seconds"))
    non=read("noncompletion.csv");assert sum(int(r["non_completed"]) for r in non)==336
    by_n=Counter()
    for r in non:by_n[r["N"]]+=int(r["non_completed"])
    assert dict(by_n)=={"9":0,"16":2,"25":334}
    puzzles=read("puzzle-completion.csv")
    assert sum(int(r["attempted_unique_puzzles"]) for r in puzzles)==sum(int(r["puzzles_with_any_primary_SAT"]) for r in puzzles)==16000
    scope=json.loads((OUT/"figure-scope.json").read_text());ids=scope["common_SAT_encoding_ids"]
    for code in ("PW","SC","BW"):
        with (OUT/f"ecdf-{code}.dat").open() as f:points=list(csv.DictReader(f,delimiter=" "))
        assert len(points)==len(ids) and float(points[-1]["cdf"])==1
    for tex in OUT.glob("figure-*.tex"):
        for name in re.findall(r"\{([^{}]+\.dat)\}",tex.read_text()):assert (OUT/name).exists()
    assert summary["error_free"] is False and summary["original_three_repetition_experiment_complete"] is False
    assert sha(ROOT/"results/final-snapshots/final-20261020-rep1/snapshot.json")==summary["snapshot_sha256"]
    evidence=dict(status="PASS",quality=summary["status"],observations=110000,instances=16000,counts=summary["status_counts"],non_completed=336,puzzles_any_primary_SAT=16000,paired_strata_independently_checked=len(pairs),paired_quantiles_checked=True,common_encoding_figure_sample=len(ids),profile_pooling=False,raw_error_none_preserved=True,diagnostic_retry_included=False,output_files_checked=len(receipt["files_sha256"]),receipt_sha256=sha(OUT/"analysis-hashes.json"),snapshot_sha256=summary["snapshot_sha256"],solver_calls=0,rendering_and_report_layout="SAT09 downstream; not claimed here")
    (ROOT/"diagnostics/expansion/final-analysis/final-QA.json").write_text(json.dumps(evidence,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(evidence,indent=2))


if __name__=="__main__":main()

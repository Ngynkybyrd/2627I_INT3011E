"""Derived reporting metrics/PGFPlots from receipt-verified final analysis only."""
import argparse
from collections import Counter,defaultdict
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import statistics as st


def derived_counts(rows):
    by=defaultdict(Counter);puzzles=defaultdict(set);sat_puzzles=defaultdict(set)
    for r in rows:
        by[int(r["N"]),r["configuration"]][r["status"]]+=1
        puzzles[int(r["N"])].add(r["instance_id"])
        if r["status"]=="SAT":sat_puzzles[int(r["N"])].add(r["instance_id"])
    non=[dict(N=n,configuration=c,observed_primary=sum(v.values()),completed_SAT=v["SAT"],non_completed=v["TIMEOUT"]+v["ERROR"],noncompletion_fraction=(v["TIMEOUT"]+v["ERROR"])/sum(v.values()),TIMEOUT=v["TIMEOUT"],ERROR=v["ERROR"]) for (n,c),v in sorted(by.items())]
    puzzle=[dict(N=n,attempted_unique_puzzles=len(ids),puzzles_with_any_primary_SAT=len(sat_puzzles[n]),puzzles_without_any_primary_SAT=len(ids-sat_puzzles[n])) for n,ids in sorted(puzzles.items())]
    return non,puzzle


def completion_points(non,n,configs):
    return sorted([(configs.index(r["configuration"])+1,100*r["noncompletion_fraction"]) for r in non if r["N"]==n],key=lambda p:p[0])


def finish(output):
    csv.field_size_limit(16*1024*1024);output=Path(output).resolve()
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    receipt=json.loads((output/"analysis-hashes.json").read_text())
    assert all(sha(output/n)==h for n,h in receipt["files_sha256"].items()),"Pre-existing producer receipt mismatch"
    def read(name):
        with (output/name).open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
    def table(name,values):
        with (output/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(values[0]));w.writeheader();w.writerows(values)
    def tex_table(name,rows):
        keys=list(rows[0]);lines=[r"\begin{tabular}{"+"l"*len(keys)+"}",r"\hline"," & ".join(keys)+r" \\",r"\hline"]
        lines += [" & ".join(str(v) for v in r.values())+r" \\" for r in rows]
        (output/name).write_text("\n".join(lines+[r"\hline",r"\end{tabular}"])+"\n",encoding="utf-8")
    def data(name,header,values):
        (output/name).write_text(" ".join(header)+"\n"+"".join(" ".join(str(x) for x in row)+"\n" for row in values),encoding="utf-8")
    def fig(name,options,plots,caption):
        (output/name).write_text("% "+caption+"\n"+r"\begin{tikzpicture}\begin{axis}[width=.94\linewidth,height=6cm,"+options+"]\n"+"\n".join(plots)+"\n"+r"\end{axis}\end{tikzpicture}"+"\n",encoding="utf-8")
    rows=read("instances.csv");profiles=read("profile-timeline.csv");cnf=read("encoding-counts.csv")
    assert len(rows)==110000 and Counter(r["status"] for r in rows)=={"SAT":109664,"TIMEOUT":335,"ERROR":1}
    non,puzzle=derived_counts(rows);assert sum(r["non_completed"] for r in non)==336
    assert [(r["N"],r["attempted_unique_puzzles"],r["puzzles_with_any_primary_SAT"]) for r in puzzle]==[(9,10000,10000),(16,5000,5000),(25,1000,1000)]
    table("noncompletion.csv",non);table("puzzle-completion.csv",puzzle)
    labels={"sat:pairwise":"PW","sat:seqcounter":"SC","sat:bitwise":"BW","cpsat":"CP","highs":"HG","gurobi":"GR","cplex_mip":"CX","cpoptimizer":"CO"};configs=list(labels)
    tex_table("coverage-main.tex",[dict(N=r["N"],Method=labels[r["configuration"]],Jobs=r["observed_primary"],SAT=r["completed_SAT"],NC=r["non_completed"]) for r in non])
    tex_table("puzzle-completion.tex",[dict(N=r["N"],Attempted=r["attempted_unique_puzzles"],AnySAT=r["puzzles_with_any_primary_SAT"],NoSAT=r["puzzles_without_any_primary_SAT"]) for r in puzzle])
    tex_table("profile-timeline-main.tex",[dict(Session=r["session_id"][:8],W=r["workers"],Jobs=r["observed_primary"],SAT=r["SAT"],NC=int(r["TIMEOUT"])+int(r["ERROR"])) for r in profiles])
    for n in (9,16,25):data(f"completion-N{n}.dat",["method","NCpercent"],completion_points(non,n,configs))
    fig("figure-completion.tex","xlabel={Method},ylabel={Non-completed (\\%)},xtick={1,...,8},xticklabels={PW,SC,BW,CP,HG,GR,CX,CO},legend pos=north west",[f"\\addplot+[only marks,mark=*] table[x=method,y=NCpercent] {{completion-N{n}.dat}};\\addlegendentry{{$N={n}$}}" for n in (9,16,25)],"Categorical methods, no connecting line. Post-hoc non-completed=TIMEOUT+ERROR; counts only, not timing/hardness. Denominators in noncompletion.csv; absent commercial sizes remain absent.")
    main=max(profiles,key=lambda r:int(r["observed_primary"]));sid=main["session_id"];methods=list(labels)[:3]
    fixed=[r for r in rows if r["session_id"]==sid and r["N"]=="25" and r["family"]=="permutation" and r["clue_percent"]=="40"]
    values={(r["instance_id"],r["configuration"]):r for r in fixed if r["status"]=="SAT"}
    ids=sorted(set.intersection(*[{i for i,c in values if c==method} for method in methods]));assert ids,"Fixed comparison scope has no common SAT sample"
    scope=dict(session_id=sid,workers=int(main["workers"]),N=25,family="permutation",clue_percent=40,common_SAT_encoding_ids=ids,configurations=methods,selection="Largest session by coverage, fixed N25/permutation/40%, no speed selection",CI=False)
    (output/"figure-scope.json").write_text(json.dumps(scope,indent=2)+"\n")
    def q(v,p):
        v=sorted(v);h=(len(v)-1)*p;lo=int(h);hi=min(lo+1,len(v)-1);return v[lo]+(h-lo)*(v[hi]-v[lo])
    quantiles=[];components=[]
    for k,m in enumerate(methods,1):
        times=sorted(float(values[i,m]["total_seconds"]) for i in ids)
        data(f"ecdf-{labels[m]}.dat",["seconds","cdf"],[(t,(j+1)/len(times)) for j,t in enumerate(times)])
        quantiles.append((k,q(times,.5),q(times,.9),q(times,.95),len(ids)))
        components.append((k,st.median(float(values[i,m]["build_seconds"]) for i in ids),st.median(float(values[i,m]["solve_seconds"]) for i in ids)))
    data("common-quantiles.dat",["method","median","p90","p95","matched"],quantiles);data("common-build-solve.dat",["method","build","solve"],components)
    caption=f"Same {len(ids)} common SAT IDs, N25/permutation/40%, session {sid}, {main['workers']} workers, resource-contended. Single measured repetition; no missing/censored runtime imputed."
    fig("figure-ecdf.tex","xlabel={Single-run total (s)},ylabel={ECDF},legend pos=south east",[f"\\addplot+[const plot,mark=none] table[x=seconds,y=cdf] {{ecdf-{labels[m]}.dat}};\\addlegendentry{{{labels[m]}}}" for m in methods],caption)
    fig("figure-quantiles.tex","ybar,xlabel={Method},ylabel={Total (s)},xtick={1,...,3},xticklabels={PW,SC,BW},legend pos=north west",[f"\\addplot table[x=method,y={metric}] {{common-quantiles.dat}};\\addlegendentry{{{metric}}}" for metric in ("median","p90","p95")],caption+" Across matched single-run instances, not repeat medians.")
    fig("figure-build-solve.tex","ybar,xlabel={Method},ylabel={Component median (s)},xtick={1,...,3},xticklabels={PW,SC,BW},legend pos=north west",[f"\\addplot table[x=method,y={metric}] {{common-build-solve.dat}};\\addlegendentry{{{metric}}}" for metric in ("build","solve")],caption+" Build includes setup. Independent component medians must not be summed to claim median total.")
    clue_plots=[]
    for family in ("permutation","row_cycle"):
        points=[]
        for clue in (20,30,40,50,60):
            g=[r for r in rows if r["session_id"]==sid and r["N"]=="25" and r["family"]==family and r["clue_percent"]==str(clue) and r["configuration"]=="sat:seqcounter"]
            sat=[float(r["total_seconds"]) for r in g if r["status"]=="SAT"]
            if sat:points.append((clue,st.median(sat),len(sat),len(g)))
        name=f"clue-{family}.dat";data(name,["clue","seconds","SAT","observed"],points)
        clue_plots.append(f"\\addplot+[mark=*] table[x=clue,y=seconds] {{{name}}};\\addlegendentry{{{family.replace('_','-')}}}")
    fig("figure-clue-runtime.tex","xlabel={Requested clues (\\%)},ylabel={SC SAT single-run median (s)},legend pos=north east",clue_plots,f"Same session {sid}, N25 seqcounter, families separate; sample counts in dat. Correlated masks, no monotone hardness or independent CI claim.")
    completion_plots=[]
    for family in ("permutation","row_cycle"):
        points=[]
        for clue in (20,30,40,50,60):
            g=[r for r in rows if r["session_id"]==sid and r["N"]=="25" and r["family"]==family and r["clue_percent"]==str(clue) and r["configuration"]=="highs"]
            if g:points.append((clue,100*sum(r["status"]!="SAT" for r in g)/len(g),len(g)))
        name=f"clue-completion-{family}.dat";data(name,["clue","NCpercent","observed"],points)
        completion_plots.append(f"\\addplot+[mark=*] table[x=clue,y=NCpercent] {{{name}}};\\addlegendentry{{{family.replace('_','-')}}}")
    fig("figure-clue-completion.tex","xlabel={Requested clues (\\%)},ylabel={HiGHS non-completed (\\%)},legend pos=north east",completion_plots,f"Same session {sid}, N25 HiGHS; observed denominators in dat; family/root dependence retained. Not proof sparse clues are harder.")
    (output/"figure-clues.tex").write_text(r"\begin{minipage}{.48\linewidth}\input{figure-clue-runtime.tex}\end{minipage}\hfill\begin{minipage}{.48\linewidth}\input{figure-clue-completion.tex}\end{minipage}"+"\n")
    chunks=[]
    for m in methods[:3]:data(f"cnf-{labels[m]}.dat",["N","variables","clauses"],[(r["N"],int(r["theoretical_primary"])+int(r["auxiliary_min"]),r["clauses_without_clues"]) for r in cnf if r["configuration"]==m])
    for metric in ("variables","clauses"):
        chunks.append(r"\begin{minipage}{.48\linewidth}\begin{tikzpicture}\begin{axis}[width=\linewidth,height=5cm,xlabel={$N$},ymode=log,ylabel={"+metric+"},xtick={9,16,25}]\n"+"\n".join(f"\\addplot+[mark=*] table[x=N,y={metric}] {{cnf-{labels[m]}.dat}};\\addlegendentry{{{labels[m]}}}" for m in methods[:3])+"\n"+r"\end{axis}\end{tikzpicture}\end{minipage}")
    (output/"figure-cnf.tex").write_text("% Measured pre-preprocessing variables incl auxiliaries; clauses excluding clue units; not generic shortcut theory.\n"+"\n".join(chunks)+"\n")
    pair_ids=sorted({i for i,c in values if c=="sat:pairwise"}&{i for i,c in values if c=="sat:seqcounter"})
    points=[(float(values[i,"sat:pairwise"]["total_seconds"]),float(values[i,"sat:seqcounter"]["total_seconds"])) for i in pair_ids]
    data("paired-scatter.dat",["PW","SC"],points);hi=max(max(x,y) for x,y in points)
    fig("figure-paired-scatter.tex","xlabel={PW total (s)},ylabel={SC total (s)}",[r"\addplot[only marks,mark size=1.2pt] table[x=PW,y=SC] {paired-scatter.dat};",f"\\addplot[domain=0:{hi},mark=none,dashed] {{x}};"],f"Same {len(points)} paired SAT IDs in {sid}, N25/permutation/40%; diagonal is equal observed total, not isolated speedup.")
    profiles.sort(key=lambda r:r["started_utc"]);first=datetime.fromisoformat(profiles[0]["started_utc"])
    data("profile-coverage.dat",["order","minutes","jobs","workers"],[(k,(datetime.fromisoformat(p["started_utc"])-first).total_seconds()/60,p["observed_primary"],p["workers"]) for k,p in enumerate(profiles,1)])
    fig("figure-profile-coverage.tex","xlabel={Session start (minutes from first)},ylabel={Primary jobs contributed},ymode=log",[r"\addplot[only marks] table[x=minutes,y=jobs] {profile-coverage.dat};"],"Chronological operational coverage, not execution rate. Includes noisy24/40-worker trials without speed interpretation; exact mapping in profile-timeline.csv.")
    summary=json.loads((output/"summary.json").read_text());summary["derived_display_grouping"]={"definition":"non-completed = TIMEOUT + ERROR, post-hoc only; raw statuses/timing unchanged","non_completed":336,"by_N":{"9":0,"16":2,"25":334},"puzzles_any_primary_SAT":16000,"does_not_mean_every_engine_solved_every_puzzle":True}
    (output/"summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    doc="""# Derived presentation: completion and non-completion

Headline: 109664 completed SAT primary jobs and 336 non-completed primary jobs.
Non-completed is a POST-HOC display group, TIMEOUT+ERROR; it does not recode raw
statuses or timing. Counts by N9/N16/N25 are 0/2/334. Raw335TIMEOUT+1ERROR remain
in audit/receipt/status-N-config.csv and the error case in the appendix artifact.
All16000 puzzles have at least one primary SAT across methods; this does NOT mean
every engine solved each puzzle. puzzle-completion.csv records this separate unit.

Eight native figure groups: completion by N/config; conditional common-SAT ECDF;
common quantiles; clues vs seqcounter runtime by family; CNF variables/clauses;
common build/solve components; paired PW/SC scatter; chronological profile coverage.
No PDF/render build was done here. Copy accompanying dat files to the TeX build
directory or set the PGFPlots table search path. PW/SC/BW/CP/HG/GR/CX/CO mean
pairwise/seqcounter/bitwise/CP-SAT/HiGHS/Gurobi/CPLEX MIP/CP Optimizer.

The fixed runtime panels use the largest session BY COVERAGE (not fastest),
N25/permutation/40% clues and exact common SAT IDs from figure-scope.json. ECDF,
quantiles and components share one common set across the three SAT encodings; scatter
uses its stated PW/SC paired set. Do not combine profiles or infer isolated
speedup. All observations are1rep. Component medians do not add to median total.
Clue panels condition on SAT and publish counts, keep family/root dependence,
and are not a calibrated difficulty or independent-sample causal comparison.
24/40-worker trial rows remain coverage only. No censored/None runtime is10-filled.

For report tables use coverage-main.tex (NC display grouping), puzzle-completion.tex,
profile-timeline-main.tex and runtime-common-compact.tex. Full audit counts/statuses
and declared-error.csv remain available without a dedicated ERROR body section.
runtime-common-report.csv is compact; sample_row links to runtime-common.csv,
whose full JSON ID sets can exceed Python's default CSV field size. For that full
audit artifact use csv.field_size_limit(16*1024*1024); never print all IDs in PDF.
"""
    (output/"FIGURE-HANDOFF.md").write_text(doc,encoding="utf-8")
    findings=(output/"FINDINGS.md").read_text(encoding="utf-8")
    findings=findings.replace("# Full rep1 analysis — declared infrastructure error retained","# Full rep1 analysis — completion and non-completion")
    (output/"FINDINGS.md").write_text(findings,encoding="utf-8")
    receipt["files_sha256"]={p.name:sha(p) for p in sorted(output.iterdir()) if p.is_file() and p.name!="analysis-hashes.json"}
    (output/"analysis-hashes.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return dict(non_completed=336,puzzles_any_SAT=16000,figures=8,common_runtime_sample=len(ids),receipt_sha256=sha(output/"analysis-hashes.json"))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--analysis",required=True,type=Path);args=parser.parse_args();print(json.dumps(finish(args.analysis)))

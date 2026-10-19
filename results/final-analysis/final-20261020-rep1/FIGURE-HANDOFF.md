# Derived presentation: completion and non-completion

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

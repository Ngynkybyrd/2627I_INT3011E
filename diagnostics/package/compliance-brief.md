# BTL1 compliance brief — 2026-10-16

Preparation summary from the frozen data, accepted final analysis, and current
report destination handoff. This is not a submission receipt.

## Requirements and evidence

| Requirement | Evidence / scope | Handoff status |
|---|---|---|
| Generalized Sudoku solver | Python CLI, three SAT encodings, CP-SAT and ILP adapters | Implemented; source and dependency closure included |
| Main experiment | 906 rows: 903 SAT, 3 TIMEOUT (all HiGHS); no missing executed IDs | Summary audit accepted; raw rows and solutions retained |
| SAT encodings | Pairwise, sequential counter, bitwise each cover 240/240 S80 runs | Complete for frozen scope |
| Larger boards | SAT, CP-SAT and HiGHS cover B16; CP-SAT 48/48 SAT, HiGHS 45/48 SAT and 3 TIMEOUT | Report exact counts; no universal solver claims |
| Commercial comparisons | Gurobi, CPLEX MIP and CP Optimizer each cover C10, 30/30 SAT; no large-board comparison | Limited scope disclosed |
| Data and reproducibility | 60 synthetic + 20 public inputs, provenance, witnesses, frozen source/license | Full closure included; freeze hash `fd84c10458d41fde0e2de0ebb204b68ea0b95f587cf6a19e00d4e1cb58de2e25` |
| Scientific report | `cas-sc`, A4/fleqn; current Vietnamese and English PDFs | Targeted content, metadata, PDF and destination QA passed |
| Repository / Data Availability | Public destination `https://github.com/Ngynkybyrd/2627I_INT3011E`, branch `main`; root verified 1,384 initial snapshot blob hashes at commit `f45d37894cfb19fe3bb890e8f0e06f13b472c2a2`, including source/data/raw/summary/report/PDF | New README and final report/provenance revisions remain to sync after final QA; LMS submission is deferred |
| Submission | User deferred LMS submission | Submission remains deferred |

Destination QA verifies the report source manifest, frozen sources, both current
PDF hashes, and clickable URL. Root also verified all 1,384 initial snapshot
blobs against the public commit. New README/final report provenance revisions
will be synchronized after final QA. Older no-URL report-acceptance notes are
historical; the repository-destination handoff supersedes them. LMS submission
remains deferred.

## Solver limits

The main-run commercial scope is C10 only. SAT04 probes found tested Gurobi and
CPLEX full 16×16 models beyond free/community size limits; tested CP Optimizer
16×16/25×25 probes hit its Community search-space limit. These are observed
limits for the probed models. Three main-run timeouts are HiGHS solve timeouts;
`LICENSE_LIMIT` is a separate status.

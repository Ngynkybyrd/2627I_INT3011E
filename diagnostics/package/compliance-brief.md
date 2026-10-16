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
| Scientific report | `cas-sc`, A4/fleqn; two current 10-page PDFs from build `20261016-213741-992` | Targeted content, metadata, PDF and destination QA passed |
| Repository / Data Availability | User-selected destination `https://github.com/Ngynkybyrd/2627I_INT3011E`; PDF link is visible/clickable | Project contents not synchronized or verified online; VI-007/DEL-007/PDF-002 remain pending |
| Submission | User deferred publication and submission | No push, upload, or submission action taken |

Destination QA verifies the 48-entry report source manifest, 32 frozen sources,
both current PDF hashes, and clickable URL. Older no-URL report-acceptance notes
are historical; the repository-destination handoff supersedes them. The
preview remains incomplete until project contents are pushed under user
direction and verified at the destination.

## Solver limits

The main-run commercial scope is C10 only. SAT04 probes found tested Gurobi and
CPLEX full 16×16 models beyond free/community size limits; tested CP Optimizer
16×16/25×25 probes hit its Community search-space limit. These are observed
limits for the probed models. Three main-run timeouts are HiGHS solve timeouts;
`LICENSE_LIMIT` is a separate status.

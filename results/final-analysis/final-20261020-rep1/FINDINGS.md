# Full rep1 analysis — completion and non-completion

110000 primary observations on 16000 puzzles were attempted: 109664 SAT,
335 TIMEOUT (censored), 1 ERROR. This is NOT full 330000/3rep completion.
No diagnostic retry replaces or augments primary observations. Runtime tables
condition on SAT and disclose sample sizes; no runtime is imputed for None.
Each profile/session/worker has its own stratum. Trials with 24/40 workers
are present in coverage/timeline but excluded from paired performance claims.
No confidence interval, repeatability or isolated speedup is estimated.

coverage.csv retains every observation including ERROR; status-N-config.csv is
counts only across sessions, not a timing leaderboard. runtime-common.csv has
exact common SAT IDs, same N/source/group/family/clues/session/worker and n;
median/p90/p95 describe single-run matched samples, never three repetitions.
The compact main runtime panel uses the largest session BY COVERAGE, fixed
N25/permutation/40% clues, with no selection by speed. Full detailed pairs stay
in artifacts; do not dump all rows into the report. Keep original906/3rep
and historical rolling480 outputs separate from this full rep1 experiment.

Dataset composition and source claims are pinned to SAT05 PASS. Synthetic
masks share 1200 roots and seed grids; do not treat 16000 inputs as independent
roots. Source labels are not a proof of hardness; no uniformity/uniqueness or
non-isomorphism claim. Acquisition witness time is not benchmark runtime.
The ERROR case is premeasurement guard WinError6, null timings, acknowledged
separately; it is not UNSAT, TIMEOUT or cleanup failure. See declared-error.csv
and original snapshot declared_error/evidence for the immutable identity.
All claims are local revision results; do not claim new files are public.

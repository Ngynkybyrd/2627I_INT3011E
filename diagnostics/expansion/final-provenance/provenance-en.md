# Dataset and limitations — report-ready prose

The frozen expanded dataset contains 16,000 puzzles: 10,000 public 9×9
puzzles, 5,000 synthetic 16×16 puzzles and 1,000 synthetic 25×25 puzzles.
The easy.txt, medium.txt, hard.txt and diabolical.txt files of Sudoku
Exchange Puzzle Bank at commit `d8c8ebaee0c08c412cfba96af1923dfa61c83317`
contribute 2,500 puzzles each. The source uses QQWing for generation and
Sukaku Explainer for ratings and dedicates the dataset to the public domain;
the accompanying LICENSE permits use, modification and distribution.
Original group labels and rating tokens are retained; they are not difficulty
scales independently calibrated by this project for the evaluated solvers.
Observed clue ranges are 22–41, 22–36, 23–36 and 23–37, respectively, with
rating ranges 1.2–1.2, 1.5–2.3, 2.5–4.7 and 5.0–9.1. These public puzzles
are also machine-generated.

The synthetic component uses two existing seed solution grids, one per size.
They yield 1,000 final 16×16 roots and 200 final 25×25 roots distinct by exact
content. Within each size, half belong to the permutation family and half
to the row_cycle family; each root supplies five masks at requested clue
densities of 20%, 30%, 40%, 50% and 60%. All 1,200 roots differ from their
respective seed grids and begin with legal permutations. The 600 row_cycle
roots additionally exchange one complete proper cycle between two rows in
the same band: 248 cycles of length 2 and 252 of length 4 for N16, and 100
cycles of length 5 for N25. These are recorded construction counts, not
counts of proven distinct isomorphism classes.

Each density has 1,000 N16 or 200 N25 puzzles, balanced across the two
families. Rounding with `floor(p*N*N/100+0.5)` gives actual clue counts of
51, 77, 102, 128 and 154 for N16, and 125, 188, 250, 313 and 375 for N25.
Actual densities can therefore differ slightly from the requested values.
The five masks sharing a root are not independent observations; even roots
derive from just two seed grids and must not automatically be treated as
fully independent. Exact deduplication confirms 16,000 distinct inputs and
1,200 distinct roots, with no input overlap with S80 or the pilot. This does
not establish uniform sampling, non-isomorphism or representativeness of all
Sudoku puzzles. Root_id must survive stratification, pairing and uncertainty
analysis.

Frozen metadata records 16,000 checked witnesses: 6,000 generator witnesses
and 10,000 acquired using the production solver. Public witness acquisition
uses its own 30-second budget, distinct from the 10-second benchmark cutoff;
its times and solutions do not replace benchmark observations. This provenance
audit performs no uniqueness solving: 10,000 public records are labelled
source_claimed with a citation and 6,000 synthetic records are unverified.
The project provides no independent uniqueness certification. A checked
witness proves existence, not benchmark success for every configuration.

Neither fewer clues nor a larger board necessarily implies greater difficulty.
Clue locations and values, construction families, source generation and the
solver can all affect observations. Comparing public N9 with synthetic
N16/N25 changes both size and data source/structure, so it does not isolate
size or establish an intrinsic complexity law. Composition counts and hashes
are audited from the frozen index, manifest, roots and pinned sources in
counts.json; no new puzzles or solver runs were introduced.

Source: https://github.com/grantm/sudoku-exchange-puzzle-bank/tree/d8c8ebaee0c08c412cfba96af1923dfa61c83317

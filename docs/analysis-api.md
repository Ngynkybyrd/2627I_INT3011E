# Analysis API v1 — RES-001..007 implementation

Entry point: `scripts/analyze_results.py`. Importable functions are
`validate_run(run_dir, *, root=ROOT, partial=False, diagnostic=False)`,
`summarize(rows, scopes)`, and
`analyze(run_dirs, output, *, root=ROOT, mode="partial")`.
They never invoke a solver. Paths with spaces are supported. Run directories
and output directories are distinct; output must be NEW and is never overwritten.
Schema v1 is `docs/results-schema.md`; the runner API remains unchanged.

## Commands from the project root

The following command uses only the saved ARTIFICIAL fixture. Its invented
timings are diagnostics, not solver/benchmark observations. Use a new output
directory name on every invocation:

```powershell
& '.\.venv\Scripts\python.exe' -B '.\scripts\analyze_results.py' --run '.\diagnostics\analysis\fixtures\sample-run' --output '.\diagnostics\analysis\sample-output-v2' --mode diagnostic
```

For an actual one-repetition pilot or an interrupted run, pass its real runner
directory instead of the fixture and explicitly select `--mode pilot` or
`--mode partial`. For example, command structure for the CLI integrator is:

```powershell
& '.\.venv\Scripts\python.exe' -B '.\scripts\analyze_results.py' --run '<actual-run-directory>' --output '<new-analysis-directory>' --mode pilot
```

`--run` is repeatable for disjoint observations under identical code, machine,
packages, dataset, cutoff, schedule seed and watchdog limits. A duplicate
instance/configuration/repetition is rejected rather than selecting a faster
rerun. Different historical source versions are not merged. The saved
`code_sha256` is propagated for provenance; analysis does not require current
source files to equal historical source files.

`--mode final` additionally requires the complete canonical three-repetition
schedule and all selected rows. Its structural acceptance is not a substitute
for RUN-012 approval or final research/report review. RES-009/010 and acceptance
on main CSV remain pending. The current default protocol has 906 planned jobs:
720 S80 SAT, 96 B16 CP-SAT/HiGHS, and 90 C10 commercial-backend jobs. A pilot
selection of 55 jobs/one repetition is allowed; this script does not manufacture
the remaining jobs or require that every partial run contain exactly 55.

## Validation and failure behavior

- Verify the frozen dataset with runner `verify_dataset`, freeze SHA-256 in
  `run.json`, canonical seeded schedule including scope/count/order, execution
  selection, run/job IDs, exact CSV schema and duplicate/order checks.
- Join case-sensitive JSON `n` and `N` to the manifest. Check input SHA-256,
  dimensions and clues. Only scheduled method/encoding/scope/repetitions are valid.
- Require finite, nonnegative timings; known total agrees with build+solve.
  Successful results require complete timings within the total cutoff. Unknown
  values remain null/empty, including killed timeouts. Validate status/guard-phase
  compatibility: startup/postprocessing/cleanup cannot count as solve timeout.
- Every SAT row needs `validation=pass`, matching solution artifact job/instance
  identities and a fresh independent `check_solution` pass preserving clues.
  Solution artifact paths cannot escape the run. Record artifact SHA-256 in the
  audit. **Schema v1 has no prior solution checksum field**: this is an analysis
  checksum plus independent validation, not proof of equality to an earlier hash.
- Check SAT CNF primary/auxiliary/total counts, pairwise count formula and
  consistency across repeats; baseline CNF fields must be empty. Counts may be
  unavailable after interrupted build, but a successful SAT row needs counts.
- All frozen research instances have SAT evidence. Any research UNSAT raises
  an error identifying the job/configuration; stop using that configuration and
  report the disagreement. Raw artifacts are never changed. Artificial UNSAT
  is permitted only when both diagnostic mode and explicit
  `run.json: diagnostic_artificial=true` apply; SAT/UNSAT mixtures still fail.
- Missing rows are listed in partial audits. Unselected jobs, selected jobs and
  observed jobs remain separate. Non-diagnostic modes reject explicitly marked
  artificial fixtures. Diagnostic output is confined to `diagnostics/analysis/`.

## Statistics and outputs

- `instances.csv`: per-instance metadata/counts; medians exist only for EXACT
  repetition IDs 1,2,3, all SAT. No mean of surviving repeats or fastest run.
- `summary.csv`: separate configuration, native scope, source, N and requested
  clue density; solved-run counts, any-SAT instance counts, all-three-SAT counts,
  each status count, median of eligible per-instance build/solve/total medians.
  These native-scope summaries must not be used for cross-scope speed claims.
- `coverage.csv`: planned/selected/observed jobs, scope instance denominator and
  solved counts for every scheduled configuration, including zero-observation ones.
- `matched-pairs.csv`: S80 for SAT encoding pairs; B16 for pairs involving
  CP-SAT/HiGHS; C10 when a commercial solver participates. Use the exact common
  IDs with three SAT repeats on BOTH sides, stratified by source/N/density.
  Publish matched count and IDs. The paired A/B ratio is median of per-instance
  ratios, not ratio of global averages. Zero denominator leaves ratio unavailable.
- `run-par2.csv`: eligible SAT total or TIMEOUT `2*cutoff` per individual run.
  ERROR, INVALID_INPUT, LICENSE_LIMIT and UNAVAILABLE have empty penalty, not
  zero. Diagnostic UNSAT may retain its measured runtime but never contributes
  to SAT medians or solved counts. Summary reports eligible denominator explicitly.
- `cnf.csv`/`cnf.tex`: measured counts per instance/configuration before solver
  preprocessing. `summary.tex` selects compact runtime/count columns. CSV display
  floats and LaTeX use six decimals, in seconds; raw CSV remains unchanged.
- Figures: CNF variables/clauses by size, observed status counts, and total-time
  figures on each matched pair only. Native S80/B16/C10 runtime means are never
  overlaid as a speed comparison. Empty pilot medians produce a clearly labeled
  placeholder, not zeros. PNG and vector PDF are generated from checked rows.
- `audit.json`: mode, non-final notice when applicable, source file hashes,
  code/package/machine records, missing/excluded observations and checked
  solution hashes. Pilot/partial/diagnostic plots carry their mode in the title.

## Verification

```powershell
& '.\.venv\Scripts\python.exe' -B -m pytest '.\tests\test_analysis.py' -q --basetemp '.\diagnostics\analysis\fixtures\pytest-fresh' --junitxml '.\diagnostics\analysis\tests-fresh.xml'
```

Use a fresh basetemp path. Tests create only artificial diagnostic CSV/solutions
and summaries; no solver executes. They cover schedule/schema/freeze/timing
corruption, checksum/checker validation, missing/duplicate observations,
three-repeat medians, source/scope matched sets, timeout penalties, UNSAT
disagreements, diagnostic isolation, and table/figure export. No main benchmark
or final research results are needed for these implementation checks.

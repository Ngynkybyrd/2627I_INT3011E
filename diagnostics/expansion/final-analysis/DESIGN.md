# SAT08 final report — WAITING_FOR_EXPORT

Checked CONTRACT.json once at task start: absent. No polling and no real data
analysis. SAT07 snapshot QA PASS and contract are required before a real reader;
SAT05 PASS is additionally required before source/provenance interpretation.
The script currently provides only a normalized internal metric kernel and
explicitly refuses real analysis. Fixture fields are not a proposed export wire.

## Planned tables and PGFPlots (after contract and QA)

1. Coverage: all observed primary rep1, by N/config/status/source/family/clues and
   exact profile/session/worker. All 110,000 observations must be retained,
   including 335 TIMEOUT and the single declared infrastructure ERROR; these are
   coordinator-provided expectations, not independently verified counts here.
2. Dataset composition: source group, N, family, root count, mask multiplicity,
   actual clues and uniqueness labels from SAT05's validated provenance receipt.
3. Encoding sizes: measured primary/auxiliary/clause counts, linked to accepted
   implementation/diagnostic evidence; do not silently equate theory to PySAT
   shortcut counts. Keep baseline 906/3rep a separate experiment.
4. Runtime distributions: SAT-only single-run median/type7 p90/p95 with eligible
   instance count; TIMEOUT reported as censored separately, missing runtime stays
   null. ERROR is neither TIMEOUT nor SAT and has no imputed time or penalty.
5. Common-SAT comparisons: identical IDs, N/source/family/clue and same exact
   session/profile/workers; disclose n and excluded/missing pairs. No isolated
   leaderboard or cross-profile speedup. Operational 24/40-worker noisy trials
   remain in coverage/timeline but are excluded from performance interpretation.
6. Timeout table by N/config and profile, with observed denominator; diagnostic
   retry remains outside primary scope. Single-error appendix preserves original
   ID/raw status/None/ack and retry evidence, without replacement.
7. Profile timeline: fixed session boundary/worker metadata and timing policy;
   original 330k/3rep manifest versus scoped rep1 completion/error status explicit.
8. Limitations: transformed roots/masks correlated, no per-repetition variance,
   no IID root bootstrap/CI, no size-only complexity inference across sources.

PGFPlots data are to be generated from the same audited tables (status coverage,
conditional SAT runtime distributions on exact common IDs, timeout proportions,
profile timeline when useful). Native LaTeX has compact main tables and detailed
appendix fragments; no raw thousands-row filler. Capped/PAR2 metrics are omitted
unless later useful and fully defined; never substitute 10 for unknown runtime.

## Final publication gate and receipt design

Pin upstream snapshot/contract/QA receipts and cross-check immutable SQLite,
primary IDs, complete rep1 selector, profiles, inputs/solutions/checker, counts,
timing/censoring/ERROR identity. The known WinError6 may pass only under SAT07's
declared-error contract; a new mismatch must fail. Reject diagnostic retry rows.
Cross-check aggregate and paired sets independently before publication.

Output namespace: results/final-analysis/final-20261020-rep1/ (not created yet).
Receipt written last, hashes all JSON/CSV/LaTeX/PGFPlots outputs, pins upstream
snapshot SHA and retains error_free=false. Publication status must be
READY_FOR_REPORT_WITH_DECLARED_ERROR, never error-free/full3rep completion.

Only focused artificial tests are run now. No old analyzer, src/fingerprint,
raw results, report, README, automation or benchmark is modified/executed.

## Contract delta
SAT07 contract now received; SHA-256 c15d3072b6b5e8f0e2baaf168ce8f92514dc4b1a6692a8ec71f6b24a8dfbaeef.
Snapshot-only reader and 7 focused tests pass, including SQLite input/witness blobs, SAT solution references and declared ERROR/None. Real analysis remains gated pending root handoff of snapshot QA PASS.

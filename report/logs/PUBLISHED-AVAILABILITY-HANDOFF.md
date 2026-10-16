# Published availability / final report handoff — 16/10/2026

Report ready for coordinator final QA/staging. No push by this task.

## Published source/data/results

Both languages now cite https://github.com/Ngynkybyrd/2627I_INT3011E and the
immutable initial snapshot f45d37894cfb19fe3bb890e8f0e06f13b472c2a2 through a
clickable tree/commit link. Source/data/results availability is supported by
diagnostics/package/initial-publication-verification.json: PASS, public/main,
remote tree not truncated, all 1,384 blobs match initial local HEAD. That
snapshot already includes report/PDFs; the revised reports are finalized after
it and will be pushed by the coordinator. No claim that this revision already
belongs to the initial snapshot. Course submission remains deferred.

## Changed files and current build

shared/data-availability.tex; verify_pdf.py; check_repository_destination.py;
reading/verify-frozen-references.py and FROZEN-CODE-ATTRIBUTION.md; BUILD.md;
updated report passports/logs. Scientific narrative/math/metrics unchanged.

Clean offline build: `20261016-214737-395`.

| Final local PDF | SHA-256 |
|---|---|
| output/pdf/sudoku-vi.pdf | 931aeed9248473fa65062c8061868e2ac79ab8a09a3fe7f2c422c454cd990282 |
| output/pdf/sudoku-en.pdf | 1a10d9c08ae776160d96498268969fa06c5e18c728ecd39f648987d039e62ee7 |

Both have 10 A4 pages. verify_pdf.py PASS: exact repository and immutable
commit links, published semantics, no obsolete unpublished/sync clauses,
Author exactly Tạ Đình Nguyên via pypdf/PDFium, 68 six-decimal metrics and
eight coverage strings per PDF; no missing glyph/ref/citation or overfull.
BibTeX has zero warnings. Compiler log: published-availability-build.log.

Pixel comparison to build 20261016-213741-992: only VI page 9 and EN page 10
changed; root visually checked both (and adjacent VI bibliography page 10).
URL/full commit readable, availability blocks intact, no clipping/overlap.
The other 18 pages are pixel-identical to the accepted baseline.

## Provenance closure after README owner finished

Final README SHA-256 from SAT10/coordinator, checked locally:
6bca274714839334c22d176cbedc9f60b5a7577cfddf999d770e45d4e96bfa8b.
Earlier intermediate hashes were not used for this final passport. README and
submission-info were only read; no external owner was writing at closure.

49 manifest entries refreshed and verified, including README, submission-info
and the initial-publication evidence. 12 locked analysis inputs and all 32
execution-frozen files match; requirements/installed package metadata match.
Raw SHA-256 remains aac4cde1fed90857ea81a1575e326049be71a528f27a6a744435b94c42dfdda7.
Full evidence: published-availability-verification.json, verification.json,
frozen-reference-verification.json, scientific-report-verification.json,
source-dependencies.json. Previous no-URL/destination-only logs are historical.

Commands from project root:

```powershell
& 'report/build.ps1' -Offline
& '<bundled-python>' -B -X utf8 report/verify_pdf.py
& '<bundled-python>' -B -X utf8 report/reading/verify-frozen-references.py
& '<bundled-python>' -B -X utf8 report/check_repository_destination.py --readme-sha256 6bca274714839334c22d176cbedc9f60b5a7577cfddf999d770e45d4e96bfa8b
```

Bundled interpreter path is in BUILD.md. No suite/benchmark rerun, push,
README/core/raw/summary/data edits, automation change, or checklist tick.
Missing repo/content blocker is resolved by initial publication evidence;
coordinator owns overall VI-007/DEL-007/PDF-002 acceptance, final QA and push
of this report revision. Course submission and the 10,000-instance work remain
deferred.

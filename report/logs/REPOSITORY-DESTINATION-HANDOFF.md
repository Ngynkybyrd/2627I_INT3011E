# Repository destination integration — 16/10/2026

User-provided destination: https://github.com/Ngynkybyrd/2627I_INT3011E .
Source of this input: coordinator handoff and docs/submission-info.md.
No publishing or network mutation was performed by this report task.

## Changes

shared/data-availability.tex uses one URL macro in both languages and states
that project contents remain in the local package, not yet synchronized;
online source/results availability is not claimed. The availability block is
kept together in a minipage. Bibliography and scientific numbers are unchanged.
verify_pdf.py checks exact clickable URL and unpublished/synchronization status,
alongside author metadata, metrics, citations and A4 layout. BUILD.md and the
current frozen-reference passport/attribution ledger reflect the destination.

## Final build / targeted QA

Build `20261016-213741-992`, clean offline. Both PDFs have 10 A4 pages.
Commands: report/build.ps1 -Offline; bundled Python -B -X utf8 with
report/verify_pdf.py, report/reading/verify-frozen-references.py and
report/check_repository_destination.py. No suite or solver/benchmark calls.

- Exact Author remains Tạ Đình Nguyên via pypdf and PDFium.
- Exact repository URI is both visible and clickable; both language clauses
  retain destination-only and not-yet-synchronized wording.
- 68 six-decimal metrics and eight coverage strings per PDF PASS; no missing
  citation/reference/glyph, BibTeX warnings or overfull errors.
- Pixel comparison to build 20261016-203236-600: only VI page 9 and EN page 10
  changed. Root visually checked those pages plus VI page 10: text/URL clear,
  no splitting, clipping or overlap. The other 18 pages are pixel-identical.
- 48 source manifest entries (including current README and submission-info),
  12 locked analysis inputs, and 32 execution-frozen files match. Raw SHA-256
  remains aac4cde1fed90857ea81a1575e326049be71a528f27a6a744435b94c42dfdda7.

Full PDF/source hashes and delta evidence:
repository-destination-verification.json, source-dependencies.json,
verification.json, scientific-report-verification.json;
compiler console: repository-destination-build.log.

| Current PDF | SHA-256 |
|---|---|
| output/pdf/sudoku-vi.pdf | d1f221a983b812cbde5e9394afa831b6ea266a7e3ee7354451841edc725420fc |
| output/pdf/sudoku-en.pdf | 131f3126d415ae47eced047e83600e59538ab7e26d7b29a428032fea49956d9f |

VI-007/DEL-007/PDF-002 remain pending publication and verification of actual
project contents in the destination repository. A real destination URL alone
does not complete them. No README/core/raw/summary/checklist/status changes.
Earlier metadata/no-URL acceptance files remain historical snapshots.

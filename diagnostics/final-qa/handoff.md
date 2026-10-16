# DEL-009 final technical QA — 16/10/2026

Technical core PASS; document metadata/provenance notes below remain for owners.
This is not a claim that the whole project is ready for submission.

Commands from project root (PowerShell):

```powershell
& '.\.venv\Scripts\python.exe' -B -X utf8 diagnostics/final-qa/check_integrity.py before
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\.venv\Scripts\python.exe' -B -X utf8 -m pytest tests -q -p no:cacheprovider -o junit_family=xunit1 --basetemp 'D:\KHMT\Project solo\diagnostics\final-qa\pytest-temp-del009-01' --junitxml diagnostics/final-qa/suite.xml
& '<bundled-python>' -B -X utf8 diagnostics/final-qa/check_report.py
& '.\.venv\Scripts\python.exe' -B -X utf8 diagnostics/final-qa/check_integrity.py after
```

Bundled Python used:
`C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`.
The basetemp above was new at execution; choose a new path for any later run.

## Verified

- Current suite **653 passed in 33.86s**, no failures/errors/skips; `suite.xml`
  and `suite-output.txt`. Its hash is in `integrity-after.json`.
- All **32 execution-frozen files** and **169 data-frozen files** match.
  Historical frozen suite XML still has its original hash and 653 passes.
- `validate_run` was called read-only, not the old audit_main module whose
  top-level code opens an old output with mode x. All **906** schedule/raw
  identities match: S80=720, B16=96, C10=90; **903 SAT + 3 TIMEOUT**.
  All **903** saved SAT solutions were checked again; artifact hashes equal
  final analysis audit. No benchmark rerun, pilot merge or observation change.
- Raw SHA256:
  `aac4cde1fed90857ea81a1575e326049be71a528f27a6a744435b94c42dfdda7`.
  Findings/summary/final analysis hashes and 12 report-provenance inputs match.
- Run ID is consistently `main-20261016-01`; Python 3.13.5 and all installed
  pinned requirements/main-run package versions match. Archived runtime
  passports/environment evidence and frozen-reference passport hashes match.
- Build **20261016-200959-661**: both PDFs match their build-directory bytes,
  10 A4 pages each; all **68** six-decimal table metrics and 8 coverage strings
  appear in each; visible author, teacher TS. Tô Vân Khánh, student/course and
  version strings match. Latest build logs have no missing glyph, undefined
  reference/citation or overfull warnings. Existing root visual acceptance
  remains the visual evidence; this audit does not assert a new visual review.
- 1,253 tracked artifacts stayed byte-identical during QA. Only README changed
  in the shared checkout; no such edit was made by this chat.

## PDF and entrypoint SHA256

| Artifact | SHA256 |
|---|---|
| sudoku-vi.pdf | 99e33562607aa10c37309a3fbf7da8793989caf4f8938a15476f00e195b6ed73 |
| sudoku-en.pdf | 592e65050e7f566eb5aebe0130c49a29eb6994c0d6217faefe413723b25fecdc |
| main-vi.tex | 659492baa931dd336b5713bc647ca45c4998721e78a5a5fbe456802bc649da23 |
| main-en.tex | 15b58f667437962bba7ab629bbd6970c049e5f3fe4ae03d84c4e639c827f23a7 |

## Issues for owners; no out-of-scope fixes

1. Known mandatory repository URL remains missing (VI-007/PDF-002). No fake URL
   or overall completion claim is made.
2. Both PDF `/Author` fields are `Tạ Đình NguyênⰠ`, with an extra U+2C20.
   Independently reproduced with pypdf and pdfium. Visible page author text is
   correct. Narrow report_medium review located likely cause in vendor
   `cas-common.sty:988–990` (ASCII comma/space appended to a PDF string) and
   `cas-sc.cls:136` assigning it to pdfauthor. Suggested owner fix:
   `\hypersetup{pdfauthor={Tạ Đình Nguyên}}` immediately after `\maketitle`
   in shared/document.tex, without changing vendor. Rebuild/reverify belongs
   to report owner; no change was made here.
3. README changed during QA from `e0a6d0ef...` to `1e4e7d23...`.
   `report/logs/source-dependencies.json` still records the previous README
   hash. Report-only dependency entries and frozen implementation/data/raw/
   summary/PDF hashes remain correct. Owner should refresh document provenance
   after final README/report edits; see exact before/after in integrity-after.

DEL-009 achieved for the frozen technical code/data/raw/analysis and current
suite. Final document closure remains partial until these notes are resolved
and the final version is checked. Automation/checklists were not changed.

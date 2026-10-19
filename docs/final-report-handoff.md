# Final report handoff — local reports verified

## Verified scope and evidence

Final report scope is repetition 1: 16,000 puzzles, 110,000 primary
observations, 10-second cutoff. Counts remain 109,664 SAT, 335 TIMEOUT, and
1 declared infrastructure ERROR. The diagnostic retry is excluded from primary
counts. Display 336 as post-hoc non-completion while retaining the two raw
statuses. Session/profile provenance remains separated. The original
906-attempt, three-repetition baseline is a different experiment.

SAT05 provenance PASS receipt: `diagnostics/expansion/final-provenance/receipt.json`
SHA-256 `7c11accf78f831d33542b621b06d80d00420cae5fc9a7ec89e291322d9871efc`.
SAT07 snapshot SHA-256 `70eaaf0acb6c74ba02f4ca65d8ca3db5d42d83cdbafe6620865d42d5b8af4781`;
its root check is PASS for 48 hashes (receipt SHA-256
`0b7b0db486ff23b27b7f0ea383d396acd903dc27afb6b62b1162713b8832e5cc`).
SAT08 analysis receipt SHA-256
`c109097df642a7a3709e13093dbf98cb489806ebcceeabd73c13862d2f43d069`;
its handoff SHA-256 is
`f0c35c5e4452f5ea0f0f3546be32b12d926c2c5709c376f3b084ab7c60c41ea2`.
SAT09 QA confirms these three input hashes and the same primary counts.

## SAT09 reports and source inventory

SAT09 QA is PASS for build `20261019-200351-099Z`. Stable PDFs are both A4 and
21 pages. Independent checks confirm each stable PDF matches its accepted
build copy and recorded SHA-256:

- VI: `report/final-20261020/output/pdf/sudoku-vi.pdf` —
  `c5cd05f2c4f703d0f8c8f2adbe8cd769dbd649f6bef4c27e9df394bc0c64aa63`.
- EN: `report/final-20261020/output/pdf/sudoku-en.pdf` —
  `3353037d0794d7e36e7433c87c32a6ee6230de78b0666ea8c52886e0f3ddf9a4`.

The accepted source inventory is
`report/final-20261020/build/20261019-200351-099Z/source-hashes.json`,
SHA-256 `477239cea6ebf27817c56a595508e359a10a9e2df4bd00942d2cf577c97f8ef8`.
All 91 manifest entries match current files (zero mismatches); the source
manifest hash matches SAT09 QA and `latest-build.json`. Its inventory covers
TeX, bibliography, build script, font config, figure sources, and CSV/data
inputs. The stable PDFs, QA, source manifest, latest build record, and bitmap
identity proof are listed with paths and hashes in
`diagnostics/expansion/final-package/manifest.json`.

Reproduce offline in PowerShell 7 with:

```powershell
& 'D:\KHMT\Project solo\report\final-20261020\build-final.ps1' -Offline
```

The report-local Tectonic 0.17.0 executable, font/package cache, CAS template
vendor directory, and font configuration are present. SAT09 QA records 42
rendered pages matching the accepted manual-review bitmaps with zero mismatches.
I verified the source-manifest entries, receipt crosslinks, stable/build PDF
bytes, and page counts. Root is completing the separate final text/font/box
review; its 42-page visual review was not repeated here.

## Release state

`READY_LOCAL_FINAL_REPORTS_VERIFIED` means the local report artifacts and
manifest are pinned. The report remains local and has not been pushed or
submitted. Root acceptance of its final review is still pending; publication
or course submission requires an explicitly selected target and a real
completion receipt. No ZIP or staging package was created. Root plans an
Overleaf discussion only after all work is complete; no Overleaf upload or
account activity is recorded.


Root final PDF review PASS receipt: `diagnostics/expansion/root-wave3/final-report-root-check.json` SHA-256 `970b7c853712de2a7a1eb93e445ba5b31ae02da6976978fe2ec5e808ef01b822`. It confirms source hashes, A4, at least 21 pages per language, embedded fonts, character bounds, headline counts, and bitmap proof. Raw counts remain 335 TIMEOUT + 1 ERROR (rror_free=false); display non-completion is 336. Stable PDF paths and hashes are pinned in the package status/manifest. 


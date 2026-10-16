"""Read-only report DEL009 checks with bundled PDF libraries, no rebuild."""
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
REPORT = ROOT / "report"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    build = (REPORT / "logs/latest-build.txt").read_text(encoding="utf-8-sig").strip()
    verification = read(REPORT / "logs/verification.json")
    visual = read(REPORT / "logs/final-visual-delta.json")
    provenance = read(REPORT / "logs/final-results-provenance.json")
    run = read(ROOT / "results/raw/main-20261016-01/run.json")
    assert verification["build_id"] == build
    if visual["final_build"] != build:
        closure = read(REPORT / "logs/metadata-closure-verification.json")
        assert closure["status"] == "PASS"
        assert closure["baseline_build"] == visual["final_build"]
        assert closure["build_id"] == build and len(closure["documents"]) == 2
        import pypdfium2 as pdfium
        for entry in closure["documents"]:
            lang = entry["language"]
            current_path = REPORT / f"output/pdf/sudoku-{lang}.pdf"
            assert sha(current_path) == entry["pdf_sha256"]
            assert entry["text_identical_to_baseline"] and entry["all_10_pages_pixel_identical"]
            current = pdfium.PdfDocument(str(current_path))
            baseline = pdfium.PdfDocument(str(REPORT / f"build/{closure['baseline_build']}/{lang}/main-{lang}.pdf"))
            try:
                assert len(current) == len(baseline) == 10
                for index in range(10):
                    assert current[index].render(scale=1.5).to_pil().tobytes() == baseline[index].render(scale=1.5).to_pil().tobytes()
            finally:
                current.close()
                baseline.close()
    assert run["run_id"] == "main-20261016-01"
    for path, expected in provenance["input_sha256"].items():
        assert run["run_id"] in path and sha(ROOT / path) == expected
    tables = list((REPORT / "tables").glob("final-*.tex"))
    assert len(tables) == 6
    metrics = set()
    for table in tables:
        metrics.update(re.findall(r"\d+\.\d{6}", table.read_text(encoding="utf-8")))
    assert len(metrics) == 68
    macros = (REPORT / "shared/result-values.tex").read_text(encoding="utf-8")
    for value in provenance["values"].values():
        assert value in macros
    document = (REPORT / "shared/document.tex").read_text(encoding="utf-8")
    setup = (REPORT / "shared/experimental-setup.tex").read_text(encoding="utf-8")
    assert "TS. Tô Vân Khánh" in document and "24021587" in document and "INT3301E\\_4" in document
    assert run["run_id"] in setup
    for version in run["packages"].values():
        assert version in setup, version
    assert run["machine"]["python"] in setup
    summaries = []
    metadata_issues = []
    for lang in ("vi", "en"):
        source = REPORT / f"main-{lang}.tex"
        source_text = source.read_text(encoding="utf-8")
        assert run["run_id"] in source_text
        assert "\\input{shared/document}" in source_text
        pdf = REPORT / f"output/pdf/sudoku-{lang}.pdf"
        assert sha(pdf) == sha(REPORT / f"build/{build}/{lang}/main-{lang}.pdf")
        reader = PdfReader(pdf)
        assert len(reader.pages) == 10
        if reader.metadata.author != "Tạ Đình Nguyên":
            metadata_issues.append({"language": lang, "field": "/Author",
                                    "actual": reader.metadata.author,
                                    "expected": "Tạ Đình Nguyên",
                                    "severity": "minor metadata; visible author text is correct"})
        text = unicodedata.normalize("NFC", "\n".join(p.extract_text() or "" for p in reader.pages))
        assert all(metric in text for metric in metrics)
        for value in provenance["values"].values():
            assert value in text
        for token in ("Tạ Đình Nguyên", "TS. Tô Vân Khánh", "24021587", "INT3301E", "906", "903", "S80", "B16", "C10", run["run_id"]):
            assert token in text, token
        for version in run["packages"].values():
            assert version in text, version
        for count in ("240/240", "80/80", "48/48", "16/16", "45/48", "15/16", "30/30", "10/10"):
            assert count in text
        blocker = "Chưa có URL repository" if lang == "vi" else "No online repository URL"
        assert blocker in text
        for obsolete in ("TEMPLATE ONLY", "CHỈ LÀ TEMPLATE", "technical prototype", "Technical prototype", "runs have not executed", "freeze is pending", "Preprint submitted", "\ufffd"):
            assert obsolete not in text, obsolete
        for page in reader.pages:
            assert abs(float(page.mediabox.width) - 595.276) < 1
            assert abs(float(page.mediabox.height) - 841.89) < 1
        log = (REPORT / f"build/{build}/{lang}/main-{lang}.log").read_text(encoding="utf-8", errors="replace")
        failures = re.findall(r"(?im)^.*(?:Missing character:|Overfull \\[hv]box|Citation .*undefined|Reference .*undefined|There were undefined|^! |Package .* Error).*$", log)
        assert not failures, failures
        (OUT / f"report-{lang}-text.txt").write_text(text, encoding="utf-8")
        summaries.append({"language": lang, "pages": 10, "six_decimal_metrics": 68,
                          "coverage_strings": 8, "pdf_sha256": sha(pdf),
                          "entrypoint_sha256": sha(source), "a4": True,
                          "versions_and_visible_teacher_author": "PASS",
                          "pdf_metadata": {str(k): str(v) for k,v in reader.metadata.items()},
                          "build_pdf_identical": True})
    result = {"technical_status": "PASS_WITH_METADATA_NOTE" if metadata_issues else "PASS", "submission_ready": False,
              "known_blocker": "VI-007/PDF-002: mandatory real repository URL is missing",
              "run_id": run["run_id"], "build_id": build,
              "documents": summaries, "packages_match_main_run": run["packages"],
              "metadata_issues": metadata_issues,
              "provenance_sha256": sha(REPORT / "logs/final-results-provenance.json"),
              "metrics": sorted(metrics),
              "visual_review": "Existing root 20-page acceptance plus verified final-build identity; no new visual/layout claim"}
    (OUT / "report-qa.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k != "metrics"}, ensure_ascii=False))


if __name__ == "__main__":
    main()

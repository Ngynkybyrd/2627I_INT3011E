"""Render and inspect both scientific reports; does not run solvers."""
from pathlib import Path
import json
import re
import unicodedata

import pypdfium2 as pdfium
from pypdf import PdfReader

root = Path(__file__).resolve().parent
render_root = root / "output" / "preview"
render_root.mkdir(parents=True, exist_ok=True)
build_id = (root / "logs" / "latest-build.txt").read_text(encoding="utf-8-sig").strip()
summary = {"build_id": build_id, "documents": []}
for language in ("vi", "en"):
    pdf_path = root / "output" / "pdf" / f"sudoku-{language}.pdf"
    reader = PdfReader(pdf_path)
    assert reader.metadata.author == "Tạ Đình Nguyên", repr(reader.metadata.author)
    text = unicodedata.normalize("NFC", "\n".join(page.extract_text() or "" for page in reader.pages))
    assert "Tạ Đình Nguyên" in text, "Vietnamese author text missing"
    assert "TS. Tô Vân Khánh" in text, "Confirmed instructor text missing"
    assert "Instructor information has not been supplied" not in text
    assert "Thông tin giảng viên chưa được cung cấp" not in text
    assert "hook is being added" not in text and "hook đang được bổ sung" not in text
    for token in ("24021587", "INT3301E", "S80", "B16", "C10", "906"):
        assert token in text, f"Missing expected token: {token}"
    assert "\ufffd" not in text, "Replacement character in PDF"
    for obsolete in ("TEMPLATE ONLY", "CHỈ LÀ TEMPLATE", "technical prototype", "Technical prototype", "chưa có kết quả", "runs have not executed", "freeze is pending"):
        assert obsolete not in text, f"Obsolete prototype/pre-main status: {obsolete}"
    assert "centering" not in text, "A float alignment option leaked into text"
    assert "Preprint submitted" not in text, "Sample submission footer remains"
    if language == "vi":
        assert "Kết quả và thảo luận" in text and "Kết luận" in text
        assert "903" in text and "Khả dụng mã nguồn và dữ liệu" in text
    else:
        assert "Results and discussion" in text and "Conclusion" in text
        assert "903" in text and "Code and data availability" in text
    for metric in ('0.402449','0.159527','0.210650','0.004748','0.006534','752688','180188','315188'):
        assert metric in text, f"Missing traced result metric: {metric}"
    table_metrics = set()
    for table in (root / 'tables').glob('final-*.tex'):
        table_metrics.update(re.findall(r'\d+\.\d{6}', table.read_text(encoding='utf-8')))
    assert all(metric in text for metric in table_metrics), 'Generated table metric missing from PDF'
    for count in ('240/240','80/80','48/48','16/16','45/48','15/16','30/30','10/10'):
        assert count in text, f'Missing coverage count: {count}'
    assert 'https://github.com/Ngynkybyrd/2627I_INT3011E' in re.sub(r'\s+', '', text)
    availability_text = re.sub(r'\s+', ' ', text)
    assert ('kết quả đã được công bố' in availability_text if language == 'vi'
            else 'results are published at' in availability_text)
    for stale in ('chưa được đồng bộ', 'not yet synchronized', 'Chưa có URL repository', 'No online repository URL'):
        assert stale not in availability_text, stale
    commit = 'f45d37894cfb19fe3bb890e8f0e06f13b472c2a2'
    assert commit in re.sub(r'\s+', '', text)
    links = [annotation.get_object().get('/A', {}).get('/URI')
             for page in reader.pages for annotation in page.get('/Annots', [])]
    assert 'https://github.com/Ngynkybyrd/2627I_INT3011E' in links
    assert f'https://github.com/Ngynkybyrd/2627I_INT3011E/tree/{commit}' in links
    for symbol in ("∈", "∧", "×"):
        assert symbol in text, f"Math symbol is not correctly mapped: {symbol}"
    for page in reader.pages:
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        assert abs(width - 595.276) < 1 and abs(height - 841.89) < 1, (width, height)
    log_path = root / "build" / build_id / language / f"main-{language}.log"
    log = log_path.read_text(encoding="utf-8", errors="replace")
    failures = re.findall(
        r"(?im)^.*(?:Missing character:|Overfull \\[hv]box|Citation .*undefined|"
        r"Reference .*undefined|There were undefined|^! |Package .* Error).*$", log
    )
    assert not failures, failures
    doc = pdfium.PdfDocument(str(pdf_path))
    assert doc.get_metadata_value("Author") == "Tạ Đình Nguyên", repr(doc.get_metadata_value("Author"))
    previews = []
    for index in range(len(doc)):
        page = doc[index]
        image_path = render_root / f"{language}-page-{index+1}.png"
        page.render(scale=1.5).to_pil().convert("RGB").save(image_path)
        previews.append(str(image_path.relative_to(root)))
    text_path = root / "logs" / f"{build_id}-{language}-extracted.txt"
    text_path.write_text(text, encoding="utf-8")
    summary["documents"].append({
        "language": language, "pages": len(reader.pages), "a4": True,
        "expected_text": "PASS", "missing_glyph_or_reference_or_overfull": "none",
        "generated_six_decimal_metrics_checked": len(table_metrics),
        "coverage_counts_checked": 8,
        "author_metadata_pypdf_pdfium": "Tạ Đình Nguyên",
        "published_repository_and_immutable_commit_links": "PASS",
        "previews": previews,
    })
(root / "logs" / "verification.json").write_text(
    json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
)
print(json.dumps(summary, indent=2, ensure_ascii=False))

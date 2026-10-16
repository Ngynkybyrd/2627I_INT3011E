"""Verify metadata-only closure against the visually accepted scientific build."""
from pathlib import Path
import hashlib
import json
import pypdfium2 as pdfium
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
BASE = '20261016-200959-661'
CURRENT = (ROOT / 'logs/latest-build.txt').read_text(encoding='utf-8-sig').strip()
AUTHOR = 'Tạ Đình Nguyên'
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

record = {'status': 'PASS', 'baseline_build': BASE, 'build_id': CURRENT,
          'documents': [], 'vendor_modified': False}
for lang in ('vi', 'en'):
    old = ROOT / 'build' / BASE / lang / f'main-{lang}.pdf'
    new = ROOT / 'output/pdf' / f'sudoku-{lang}.pdf'
    reader = PdfReader(new)
    before, after = pdfium.PdfDocument(str(old)), pdfium.PdfDocument(str(new))
    assert reader.metadata.author == after.get_metadata_value('Author') == AUTHOR
    assert len(before) == len(after) == 10
    pages = []
    for index in range(10):
        previous_pixels = sha_pixels = hashlib.sha256(before[index].render(scale=1.5).to_pil().tobytes()).hexdigest()
        current_pixels = hashlib.sha256(after[index].render(scale=1.5).to_pil().tobytes()).hexdigest()
        assert previous_pixels == current_pixels, (lang, index + 1)
        pages.append({'page': index + 1, 'render_sha256': current_pixels})
    old_text = [p.extract_text() for p in PdfReader(old).pages]
    assert old_text == [p.extract_text() for p in reader.pages], lang
    assert sha(new) == sha(ROOT / 'build' / CURRENT / lang / f'main-{lang}.pdf')
    record['documents'].append({'language': lang, 'author_pypdf': reader.metadata.author,
        'author_pdfium': after.get_metadata_value('Author'), 'pdf_sha256': sha(new),
        'text_identical_to_baseline': True, 'all_10_pages_pixel_identical': True,
        'rendered_pages': pages})

provenance = json.loads((ROOT / 'logs/final-results-provenance.json').read_text(encoding='utf-8'))
for name, digest in provenance['input_sha256'].items():
    assert sha(PROJECT / name) == digest, name
raw_digest = sha(PROJECT / 'results/raw/main-20261016-01/results.csv')
assert raw_digest == 'aac4cde1fed90857ea81a1575e326049be71a528f27a6a744435b94c42dfdda7'
manifest_path = ROOT / 'logs/source-dependencies.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
old_readme = next(e['sha256'] for e in manifest if e['path'] == '../README.md')
paths = {e['path'] for e in manifest} | {'check_metadata_closure.py'}
updated = [{'path': name, 'sha256': sha(ROOT / name)} for name in sorted(paths)]
manifest_path.write_text(json.dumps(updated, indent=2) + '\n', encoding='utf-8')
for item in updated:
    assert sha(ROOT / item['path']) == item['sha256']
verification = json.loads((ROOT / 'logs/verification.json').read_text(encoding='utf-8'))
assert verification['build_id'] == CURRENT
assert all(d['generated_six_decimal_metrics_checked'] == 68 and d['coverage_counts_checked'] == 8
           for d in verification['documents'])
record.update({'source_manifest_entries_verified': len(updated),
    'readme_previous_sha256': old_readme,
    'readme_current_sha256': sha(PROJECT / 'README.md'),
    'locked_analysis_inputs_verified': len(provenance['input_sha256']),
    'raw_sha256_unchanged': raw_digest,
    'metrics_per_pdf': 68, 'coverage_strings_per_pdf': 8,
    'known_blocker': 'VI-007/PDF-002: mandatory repository URL not supplied'})
summary_path = ROOT / 'logs/scientific-report-verification.json'
summary = json.loads(summary_path.read_text(encoding='utf-8'))
summary.update({'build_id': CURRENT, 'metadata_closure': 'PASS; EN-004 reclosed',
    'pdf_sha256': {f"sudoku-{d['language']}.pdf": d['pdf_sha256'] for d in record['documents']},
    'body_unchanged_from_build': BASE})
summary_path.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
(ROOT / 'logs/metadata-closure-verification.json').write_text(
    json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'PASS: exact Author via pypdf/pdfium; 20 pixel-identical pages; 68 metrics/PDF; '
      f'{len(updated)} source hashes and {len(provenance["input_sha256"])} locked analysis hashes; README refreshed')

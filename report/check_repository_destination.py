"""Check the destination-only availability update; no publishing/network calls."""
from pathlib import Path
import hashlib
import json
import pypdfium2 as pdfium
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
BASE = '20261016-203236-600'
CURRENT = (ROOT / 'logs/latest-build.txt').read_text(encoding='utf-8-sig').strip()
URL = 'https://github.com/Ngynkybyrd/2627I_INT3011E'
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

record = {'status': 'PASS', 'baseline_build': BASE, 'build_id': CURRENT,
          'destination_repository': URL, 'online_project_contents_confirmed': False,
          'published_by_this_task': False, 'documents': []}
for lang in ('vi', 'en'):
    old = ROOT / 'build' / BASE / lang / f'main-{lang}.pdf'
    new = ROOT / 'output/pdf' / f'sudoku-{lang}.pdf'
    before, after = pdfium.PdfDocument(str(old)), pdfium.PdfDocument(str(new))
    assert len(before) == len(after) == 10
    assert PdfReader(new).metadata.author == after.get_metadata_value('Author') == 'Tạ Đình Nguyên'
    changed = []
    for i in range(10):
        a = hashlib.sha256(before[i].render(scale=1.5).to_pil().tobytes()).hexdigest()
        b = hashlib.sha256(after[i].render(scale=1.5).to_pil().tobytes()).hexdigest()
        if a != b:
            changed.append(i + 1)
    assert set(changed).issubset({9, 10} if lang == 'vi' else {10}), (lang, changed)
    assert sha(new) == sha(ROOT / 'build' / CURRENT / lang / f'main-{lang}.pdf')
    record['documents'].append({'language': lang, 'pages': 10, 'changed_pages': changed,
        'other_pages_pixel_identical': True, 'author': 'Tạ Đình Nguyên', 'pdf_sha256': sha(new)})

inputs = json.loads((ROOT / 'logs/final-results-provenance.json').read_text(encoding='utf-8'))
for name, digest in inputs['input_sha256'].items():
    assert sha(PROJECT / name) == digest, name
freeze = json.loads((PROJECT / 'results/raw/main-20261016-01/execution-freeze.json').read_text())
for name, digest in freeze['files_sha256'].items():
    assert sha(PROJECT / name) == digest, name
raw_digest = sha(PROJECT / 'results/raw/main-20261016-01/results.csv')
assert raw_digest == 'aac4cde1fed90857ea81a1575e326049be71a528f27a6a744435b94c42dfdda7'
manifest_path = ROOT / 'logs/source-dependencies.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
paths = {e['path'] for e in manifest} | {'check_repository_destination.py', '../docs/submission-info.md'}
updated = [{'path': p, 'sha256': sha(ROOT / p)} for p in sorted(paths)]
manifest_path.write_text(json.dumps(updated, indent=2) + '\n', encoding='utf-8')
assert all(sha(ROOT / e['path']) == e['sha256'] for e in updated)
verified = json.loads((ROOT / 'logs/verification.json').read_text(encoding='utf-8'))
assert verified['build_id'] == CURRENT
assert all(d['generated_six_decimal_metrics_checked'] == 68 and
           d['destination_repository_link_and_unpublished_status'] == 'PASS' for d in verified['documents'])
for lang in ('vi', 'en'):
    blg = (ROOT / 'build' / CURRENT / lang / f'main-{lang}.blg').read_text()
    assert 'warning' not in blg.lower() and 'error' not in blg.lower()
record.update({'source_manifest_entries_verified': len(updated),
    'readme_sha256': sha(PROJECT / 'README.md'),
    'submission_info_sha256': sha(PROJECT / 'docs/submission-info.md'),
    'source_manifest_sha256': sha(manifest_path),
    'locked_analysis_inputs_verified': len(inputs['input_sha256']),
    'execution_frozen_files_verified': len(freeze['files_sha256']),
    'raw_sha256_unchanged': raw_digest,
    'metrics_per_pdf': 68, 'coverage_strings_per_pdf': 8,
    'known_blocker': 'VI-007/DEL-007/PDF-002: destination contents await publishing and verification'})
summary_path = ROOT / 'logs/scientific-report-verification.json'
summary = json.loads(summary_path.read_text(encoding='utf-8'))
summary.update({'build_id': CURRENT, 'destination_repository': URL,
    'blocked_tasks': {key: 'destination contents await publishing and verification' for key in ('VI-007', 'DEL-007', 'PDF-002')},
    'pdf_sha256': {f"sudoku-{d['language']}.pdf": d['pdf_sha256'] for d in record['documents']}})
summary.pop('body_unchanged_from_build', None)
summary['visual_delta_baseline'] = BASE
summary_path.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
(ROOT / 'logs/repository-destination-verification.json').write_text(
    json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(record, ensure_ascii=False, indent=2))

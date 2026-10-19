"""Prepare a NEW native-LaTeX package from a hash-pinned SAT08 v2 analysis.

No solver, SQLite, model import, LaTeX compilation or existing report mutation.
Production needs a producer/coordinator receipt; diagnostic mode is not final.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parent
CSV_FILES = ('coverage.csv', 'blocks.csv', 'instances.csv', 'strata.csv',
             'matched-pairs.csv', 'primary-par2.csv', 'clusters.csv')
REQUIRED = {'summary.json', *CSV_FILES}
CONFIGS = ('sat:pairwise', 'sat:seqcounter', 'sat:bitwise', 'cpsat', 'highs',
           'gurobi', 'cplex_mip', 'cpoptimizer')
STATUSES = {'SAT', 'TIMEOUT', 'ERROR', 'UNSAT', 'INVALID_INPUT', 'UNAVAILABLE', 'LICENSE_LIMIT'}
STRATA = ('board_side', 'source', 'source_group', 'rating_original',
          'clue_percent_requested', 'family')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def payload(content):
    return content if isinstance(content, bytes) else content.encode('utf-8')


def load_json(path):
    def invalid(value):
        raise ValueError(f'Nonfinite JSON: {value}')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=invalid, object_pairs_hook=unique)


def contained(root, relative):
    require(isinstance(relative, str) and relative and '\\' not in relative and ':' not in relative,
            'Receipt paths must be relative POSIX paths')
    rel = PurePosixPath(relative)
    require(not rel.is_absolute() and '..' not in rel.parts, 'Receipt path traversal')
    path = (root / relative).resolve()
    require(path.is_relative_to(root), 'Receipt symlink escape')
    return path


def read_csv(path, columns):
    # Empty optional statistics tables are emitted as zero-byte files by SAT08.
    if path.stat().st_size == 0:
        return []
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames and len(set(reader.fieldnames)) == len(reader.fieldnames),
                f'Duplicate/missing CSV header: {path.name}')
        require(set(columns) <= set(reader.fieldnames), f'CSV schema mismatch: {path.name}')
        rows = list(reader)
    require(all(None not in row and None not in row.values() for row in rows),
            f'Malformed CSV: {path.name}')
    return rows


def count(value, name):
    require(type(value) is int and value >= 0, f'Invalid integer count: {name}')
    return value


def integer(value):
    require(re.fullmatch(r'0|[1-9]\d*', str(value)) is not None, 'Invalid CSV count')
    return int(value)


def number(value):
    if value in (None, ''):
        return '--'
    require(not isinstance(value, bool), 'Boolean measurement')
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid measurement') from exc
    require(math.isfinite(numeric) and numeric >= 0, 'Nonfinite/negative measurement')
    return f'{numeric:.6f}'


def tex(value):
    # Escape every data/source/rating label. Never execute CSV content as TeX.
    mapping = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
               '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}',
               '^': r'\textasciicircum{}'}
    return ''.join(mapping.get(c, c if c not in '\r\n\t' else ' ') for c in str(value))


def validate(analysis, *, receipt=None, receipt_sha256=None, diagnostic=False):
    analysis = Path(analysis).resolve(strict=True)
    require(analysis.is_dir(), 'Analysis must be a directory')
    receipt = Path(receipt).resolve(strict=True) if receipt else analysis / 'analysis-hashes.json'
    require(isinstance(receipt_sha256, str) and re.fullmatch('[0-9a-f]{64}', receipt_sha256),
            'Pass the producer/coordinator --receipt-sha256; no automatic real-data sealing')
    require(digest(receipt) == receipt_sha256, 'Analysis receipt SHA-256 mismatch')
    inventory = load_json(receipt)
    require(inventory.get('schema_version') == 2 and isinstance(inventory.get('files_sha256'), dict),
            'Analysis receipt needs schema_version=2 and files_sha256')
    hashes = inventory['files_sha256']
    require(REQUIRED <= hashes.keys(), 'Receipt must cover summary.json and all seven SAT08 CSVs')
    for name, expected in hashes.items():
        require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), 'Invalid receipt digest')
        path = contained(analysis, name)
        require(path != receipt, 'Recursive receipt inventory')
        require(digest(path) == expected, f'Analysis hash mismatch: {name}')
    summary = load_json(analysis / 'summary.json')
    require(summary.get('schema_version') == 2 and summary.get('analysis_api_version') == 2,
            'Unsupported SAT08 summary version')
    require(type(summary.get('artificial')) is bool and type(summary.get('report_ready')) is bool,
            'Missing explicit artificial/report_ready identity')
    require(isinstance(summary.get('experiment_id'), str) and summary['experiment_id'] and
            isinstance(summary.get('dataset_id'), str) and summary['dataset_id'], 'Missing experiment/dataset identity')
    if diagnostic:
        require(summary['artificial'] is True and summary['report_ready'] is False,
                'Diagnostic formatting requires artificial=true/report_ready=false')
        require(summary.get('label') == 'ARTIFICIAL_DIAGNOSTIC', 'Missing artificial label')
    else:
        require(summary.get('phase') == 'main' and summary['artificial'] is False and
                summary['report_ready'] is True and summary.get('label') == 'COMPLETE_BLOCKS',
                'Only REAL main report_ready=true COMPLETE_BLOCKS may produce a report package')
        require(not any('artificial' in summary[k].lower() or 'fixture' in summary[k].lower()
                        for k in ('experiment_id', 'dataset_id')), 'Artificial identity in real claim')
        state, reason = summary.get('snapshot_state'), summary.get('halt_reason')
        allowed_reasons = (None, '', 'stop requested/deadline', 'disk reserve', 'stop before launch')
        require(state in ('COMPLETED', 'PAUSED', 'PREPARED', 'RUNNING') and
                reason in (allowed_reasons if state == 'PAUSED' else (None, '')),
                'Halted/unknown snapshot is not report-ready')
        require(re.fullmatch('[0-9a-f]{64}', str(summary.get('scientific_sha256', ''))), 'Missing scientific fingerprint')
        config = summary.get('config', {})
        require(config.get('repetitions') == 3 and config.get('cutoff_seconds') == 10 and
                config.get('startup_seconds') == 60 and config.get('postprocessing_seconds') == 30,
                'Scientific configuration differs from accepted protocol')
    require(isinstance(summary.get('input_hashes'), dict) and summary['input_hashes'],
            'Missing SAT08 export-input provenance')
    require(re.fullmatch('[0-9a-f]{64}', str(summary.get('hashes_json_sha256', ''))),
            'Missing upstream export receipt digest')
    require(inventory.get('upstream_export_hashes_json_sha256') == summary['hashes_json_sha256'],
            'Producer receipt/export provenance mismatch')
    for value in summary['input_hashes'].values():
        require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'Bad upstream input digest')
    coverage = summary['coverage']
    selected = coverage['selected_blocks']
    complete = coverage['selected_complete_blocks']
    require(isinstance(selected, list) and selected and len(selected) == len(set(selected)) and
            isinstance(complete, list) and set(selected) == set(complete), 'Partial/empty block selection')
    blocks = read_csv(analysis / 'blocks.csv', ('batch_id', 'expected_jobs', 'observed_primary_jobs', 'qa_complete', 'execution_complete'))
    require(len({b['batch_id'] for b in blocks}) == len(blocks), 'Duplicate block identity')
    block_index = {b['batch_id']: b for b in blocks}
    for bid in selected:
        require(bid in block_index and block_index[bid]['qa_complete'] == 'True' and
                block_index[bid]['execution_complete'] == 'True', 'Selected block lacks complete QA')
        b = block_index[bid]
        require(integer(b['expected_jobs']) == integer(b['observed_primary_jobs']), 'Missing block jobs')
    jobs = count(coverage['selected_complete_jobs'], 'selected_complete_jobs')
    require(jobs > 0 and jobs == sum(integer(block_index[b]['expected_jobs']) for b in selected), 'Block job denominator mismatch')
    require(jobs == count(coverage['observed_primary_jobs'], 'observed_primary_jobs') ==
            count(coverage['selected_matrix_jobs'], 'selected_matrix_jobs'), 'Incomplete selected matrix')
    counts = coverage['status_counts']
    require(isinstance(counts, dict) and set(counts) <= STATUSES, 'Unknown status counter')
    for key, value in counts.items():
        count(value, key)
    require(sum(counts.values()) == jobs and sum(v for k, v in counts.items() if k not in ('SAT', 'TIMEOUT')) == 0,
            'Selected QA data contains fatal/excluded statuses')
    require(coverage['solved_primary_jobs'] == counts.get('SAT', 0), 'Solved coverage mismatch')
    if not diagnostic:
        require(coverage['target_counts'] == {'puzzles': 16000, 'jobs': 330000}, 'Unexpected real target')
        require(coverage['matrix_planned_jobs'] == 330000 and len(selected) <= 100 and
                jobs == 3300 * len(selected) and
                coverage['complete_block_unique_instances'] == 160 * len(selected), 'Real batch quotas mismatch')
        require(all(re.fullmatch(r'b(?:00[1-9]|0[1-9]\d|100)', b) for b in selected), 'Invalid real block ID')
        require(selected == sorted(selected), 'Real block order must retain frozen ordinals')
    config_rows = read_csv(analysis / 'coverage.csv', ('configuration', 'selected_matrix_jobs', 'observed_primary_jobs', 'all_three_sat_instances', 'status_counts'))
    require(config_rows and len({r['configuration'] for r in config_rows}) == len(config_rows), 'Missing/duplicate configuration coverage')
    require(sum(integer(r['observed_primary_jobs']) for r in config_rows) == jobs, 'Configuration job count mismatch')
    if not diagnostic:
        require({r['configuration'] for r in config_rows} == set(CONFIGS), 'Real matrix configuration missing')
    for row in config_rows:
        require(integer(row['selected_matrix_jobs']) == integer(row['observed_primary_jobs']), 'Missing configuration jobs')
        status = json.loads(row['status_counts'])
        require(isinstance(status, dict) and all(type(v) is int and v >= 0 for v in status.values()), 'Invalid configuration counter')
        require(set(status) <= {'SAT', 'TIMEOUT'} and sum(status.values()) == integer(row['observed_primary_jobs']),
                'Invalid configuration statuses')
        if not diagnostic:
            per_block = 300 if row['configuration'] in ('gurobi', 'cplex_mip', 'cpoptimizer') else 480
            require(integer(row['selected_matrix_jobs']) == per_block * len(selected), 'Real configuration quota mismatch')
    strata = read_csv(analysis / 'strata.csv', ('configuration', *STRATA, 'runtime_instances', 'mixed_instances',
               'median_total_seconds', 'p90_total_seconds', 'p95_total_seconds', 'mean_instance_par2_seconds',
               'par2_instances', 'par2_primary_attempts', 'root_clusters'))
    paired = read_csv(analysis / 'matched-pairs.csv', ('configuration_a', 'configuration_b', *STRATA,
               'matched_instances', 'instance_ids', 'median_paired_a_over_b'))
    for row in strata:
        m = integer(row['runtime_instances'])
        require(row['configuration'] in CONFIGS, 'Unknown stratum configuration')
        integer(row['mixed_instances'])
        require(integer(row['par2_primary_attempts']) == 3 * integer(row['par2_instances']), 'PAR-2 denominator mismatch')
        integer(row['root_clusters'])
        for field in ('median_total_seconds', 'p90_total_seconds', 'p95_total_seconds'):
            number(row[field])
            require((row[field] != '') == (m > 0), 'Missing runtime represented as a number or vice versa')
        if m:
            require(float(row['median_total_seconds']) <= float(row['p90_total_seconds']) <= float(row['p95_total_seconds']),
                    'Non-monotone runtime quantiles')
        number(row['mean_instance_par2_seconds'])
        require((row['mean_instance_par2_seconds'] != '') == (integer(row['par2_instances']) > 0),
                'Missing PAR-2 represented as a number or vice versa')
    for row in paired:
        require(row['configuration_a'] in CONFIGS and row['configuration_b'] in CONFIGS and
                row['configuration_a'] != row['configuration_b'], 'Invalid paired configuration')
        ids = json.loads(row['instance_ids'])
        require(isinstance(ids, list) and len(ids) == len(set(ids)) == integer(row['matched_instances']), 'Paired IDs/count mismatch')
        number(row['median_paired_a_over_b'])
    return {'summary': summary, 'coverage': config_rows, 'strata': strata, 'paired': paired,
            'receipt_sha256': receipt_sha256, 'analysis_hashes': hashes, 'receipt': str(receipt)}


def native_tables(rows, columns, caption):
    chunks = []
    for start in range(0, len(rows), 18):
        part = [r'\begin{table}[pos=H]', r'\centering', r'\small',
                r'\caption{' + caption + '}', r'\begin{tabular}{' + 'l' * len(columns) + '}', r'\hline',
                ' & '.join(tex(c) for c in columns) + r'\\', r'\hline']
        part += [' & '.join(row) + r'\\' for row in rows[start:start+18]]
        part += [r'\hline', r'\end{tabular}', r'\end{table}']
        chunks.append('\n'.join(part))
    return '\n\n'.join(chunks) + '\n'


def prepare(analysis, output, *, receipt=None, receipt_sha256=None, diagnostic=False):
    output = Path(output).absolute()
    require(not output.exists() and not output.is_symlink(), 'Output must be NEW; overwrite refused')
    require(output.parent.exists(), 'Output parent must exist')
    analysis = Path(analysis).resolve(strict=True)
    require(not output.resolve().is_relative_to(analysis) and not analysis.is_relative_to(output.resolve()), 'Output overlaps analysis')
    if diagnostic:
        allowed = (ROOT / 'diagnostics').resolve()
        require(output.resolve().is_relative_to(allowed), 'Diagnostic output must stay under report/diagnostics')
    else:
        forbidden = [ROOT / 'shared', ROOT / 'output', ROOT / 'build', ROOT / 'vendor', ROOT / '.tools',
                     ROOT.parent / 'data', ROOT.parent / 'results', ROOT.parent / 'src']
        require(not any(output.resolve().is_relative_to(p.resolve()) for p in forbidden), 'Output overlaps protected artifacts')
    data = validate(analysis, receipt=receipt, receipt_sha256=receipt_sha256, diagnostic=diagnostic)
    summary = data['summary']; coverage = summary['coverage']; counts = coverage['status_counts']
    files = {}
    values = {'ExpandedBlocks': len(coverage['selected_complete_blocks']),
              'ExpandedPuzzles': coverage['complete_block_unique_instances'],
              'ExpandedJobs': coverage['selected_complete_jobs'], 'ExpandedSat': counts.get('SAT', 0),
              'ExpandedTimeout': counts.get('TIMEOUT', 0), 'ExpandedTargetPuzzles': coverage['target_counts']['puzzles'],
              'ExpandedTargetJobs': coverage['target_counts']['jobs']}
    for key, value in values.items(): count(value, key)
    files['metrics.tex'] = ''.join(f'\\newcommand{{\\{key}}}{{{value}}}\n' for key, value in values.items())
    for i, row in enumerate(data['strata']):
        for label, field in [('Median','median_total_seconds'),('Pninety','p90_total_seconds'),
                             ('Pninetyfive','p95_total_seconds'),('ParTwo','mean_instance_par2_seconds')]:
            files['metrics.tex'] += f'\\expandafter\\def\\csname ExpandedStratum{i:06d}{label}\\endcsname{{{number(row[field])}}}\n'
    cov_rows = []
    tikz = [('% ARTIFICIAL DIAGNOSTIC ONLY; NOT FINAL' if diagnostic else '% REAL main QA-complete selection'),
            r'\begin{tikzpicture}[x=5cm,y=0.65cm]']
    for i, row in enumerate(data['coverage']):
        status = json.loads(row['status_counts']); total = integer(row['observed_primary_jobs']); sat = status.get('SAT', 0)
        require(total > 0, 'No observations in configuration')
        cov_rows.append([tex(row['configuration']), str(total), str(sat), str(status.get('TIMEOUT', 0)), str(integer(row['all_three_sat_instances']))])
        tikz += [f'\\draw (0,{-i}) rectangle (1,{-i+0.45});',
                 f'\\fill[black!35] (0,{-i}) rectangle ({sat/total:.8f},{-i+0.45});',
                 f'\\node[anchor=east] at (-0.02,{-i+0.225}) {{{tex(row["configuration"])}}};',
                 f'\\node[anchor=west] at (1.02,{-i+0.225}) {{{sat}/{total}}};']
    tikz.append(r'\end{tikzpicture}')
    files['coverage-tikz.tex'] = '\n'.join(tikz) + '\n'
    diagnostic_banner = r'\textbf{ARTIFICIAL DIAGNOSTIC ONLY --- NOT FINAL RESULTS.}\par' if diagnostic else ''
    for lang in ('vi', 'en'):
        title = 'Kết quả mở rộng: phạm vi được QA' if lang == 'vi' else 'Expanded results: QA-approved coverage'
        note = ('Đây là tập batch hoàn tất được chọn; không suy đã đạt toàn bộ mục tiêu. Runtime chỉ dùng ba SAT/ID; mixed status giữ riêng. Median các cột không cộng được; PAR-2 TIMEOUT là 20 giây. Repetitions/masks cùng root không độc lập.' if lang == 'vi' else
                'This is the selected complete-batch subset, not a claim that the full target was reached. Runtime requires three SAT runs/ID; mixed statuses remain separate. Component medians are not additive; TIMEOUT PAR-2 is 20 seconds. Repetitions/masks sharing a root are not independent.')
        note += (' SAT/CP-SAT/HiGHS có phạm vi N9/16/25; thương mại chỉ N9. So runtime phải lọc đúng tập ID chung.' if lang == 'vi' else
                 ' SAT/CP-SAT/HiGHS cover N9/16/25; commercial engines cover N9 only. Runtime comparisons require matching IDs.')
        sentence = (r'Có \ExpandedBlocks{} batch đạt QA, \ExpandedPuzzles{} đề và \ExpandedJobs{} lượt: \ExpandedSat{} SAT, \ExpandedTimeout{} TIMEOUT. Mục tiêu là \ExpandedTargetPuzzles{} đề/\ExpandedTargetJobs{} lượt.' if lang == 'vi' else
                    r'There are \ExpandedBlocks{} QA-complete batches, \ExpandedPuzzles{} puzzles and \ExpandedJobs{} runs: \ExpandedSat{} SAT and \ExpandedTimeout{} TIMEOUT. The target is \ExpandedTargetPuzzles{} puzzles/\ExpandedTargetJobs{} runs.')
        files[f'results-{lang}.tex'] = diagnostic_banner + '\n\\section{' + title + '}\n' + sentence + '\n\n' + note + f'\n\\input{{coverage-{lang}.tex}}\n\\begin{{figure}}[pos=H]\n\\centering\n\\input{{coverage-tikz.tex}}\n\\caption{{' + ('Tỷ lệ SAT trên các lượt được chọn; nhãn là SAT/tổng.' if lang == 'vi' else 'SAT fraction among selected runs; labels show SAT/total.') + '}\n\\end{figure}\n'
        files[f'coverage-{lang}.tex'] = diagnostic_banner + native_tables(cov_rows,
            ('Config', 'Jobs', 'SAT', 'TIMEOUT', '3 SAT IDs'), 'Coverage' if lang == 'en' else 'Độ phủ')
        # Full strata are native TeX, separate from compact default inclusion; no performance-based row selection.
        for index, row in enumerate(data['strata']):
            label = '; '.join(f'{k}={row[k]}' for k in STRATA if row[k] != '')
            label += f'; PAR-2 instances={integer(row["par2_instances"])}, primary attempts={integer(row["par2_primary_attempts"])}; roots={integer(row["root_clusters"])}'
            table_row = [[tex(row['configuration']), str(integer(row['runtime_instances'])), str(integer(row['mixed_instances'])),
                          number(row['median_total_seconds']), number(row['p90_total_seconds']), number(row['p95_total_seconds']), number(row['mean_instance_par2_seconds'])]]
            files[f'strata/{lang}-{index:06d}.tex'] = diagnostic_banner + native_tables(table_row,
                ('Config', 'm', 'Mixed', 'Median s', 'p90 s', 'p95 s', 'PAR-2 s'), tex(label))
        for index, row in enumerate(data['paired']):
            label = '; '.join(f'{k}={row[k]}' for k in STRATA if row[k] != '')
            files[f'paired/{lang}-{index:06d}.tex'] = diagnostic_banner + native_tables(
                [[tex(row['configuration_a']), tex(row['configuration_b']), str(integer(row['matched_instances'])),
                  number(row['median_paired_a_over_b'])]], ('A', 'B', 'Matched IDs', 'Median A/B'), tex(label))
        files[f'expanded-{lang}.tex'] = '% Include from this package directory; preserve the existing STIX/CAS preamble.\n\\input{metrics.tex}\n' + f'\\input{{results-{lang}.tex}}\n'
    # All exact IDs, denominators, root links and paired statistics remain available for reviewer selection.
    for name in CSV_FILES:
        files[f'analysis/{name}'] = (analysis / name).read_bytes()
    files['analysis/summary.json'] = (analysis / 'summary.json').read_bytes()
    files['analysis/analysis-hashes.json'] = Path(data['receipt']).read_bytes()
    files['table-index.json'] = json.dumps({
        'strata': [{'row': row, 'vi': f'strata/vi-{i:06d}.tex', 'en': f'strata/en-{i:06d}.tex'}
                   for i, row in enumerate(data['strata'])],
        'paired': [{'row': row, 'vi': f'paired/vi-{i:06d}.tex', 'en': f'paired/en-{i:06d}.tex'}
                   for i, row in enumerate(data['paired'])]}, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    for lang in ('vi', 'en'):
        files[f'methods-reference-{lang}.tex'] = (ROOT / f'shared/expanded-methods-{lang}.tex').read_text(encoding='utf-8')
    files['INTEGRATION.md'] = ('This package does not replace existing PDFs or authorize publication. Keep the current STIX/CAS/TikZ preamble. '
        'Build from this package as the working/search directory and input expanded-vi.tex OR expanded-en.tex once. '
        'methods-reference-* are the existing PLANNED design for review, not automatically included or rewritten as completed execution. '
        'Full strata native tables are under strata/; compact default fragments show coverage only. Exact paired/cluster/instance data are retained under analysis/. '
        'A reviewer must select scientifically justified strata/figures before a final paper; no universal winner/Abstract/Conclusion is generated. '
        'manifest.json is written last; a directory without it is incomplete and must not be consumed. '
        'Pinned checksums establish integrity against the supplied receipt, not root approval or producer authenticity.\n')
    manifest = {'schema_version': 2, 'package_kind': 'ARTIFICIAL_DIAGNOSTIC_NOT_FINAL' if diagnostic else 'REAL_MAIN_REPORT_PACKAGE',
                'report_ready': not diagnostic, 'artificial': diagnostic, 'experiment_id': summary['experiment_id'],
                'dataset_id': summary['dataset_id'], 'selected_blocks': coverage['selected_complete_blocks'],
                'metrics': values, 'analysis_receipt_sha256': data['receipt_sha256'], 'analysis_file_sha256': data['analysis_hashes'],
                'upstream_export_hashes_json_sha256': summary['hashes_json_sha256'],
                'scientific_sha256': summary.get('scientific_sha256'),
                'root_approval': 'external execution/QA gate; not granted or independently authenticated by this formatter',
                'tool_sha256': digest(__file__), 'font_policy': 'existing STIX/CAS; native TeX/TikZ; no preamble mutation',
                'methods_source_sha256': {lang: digest(ROOT / f'shared/expanded-methods-{lang}.tex') for lang in ('vi', 'en')},
                'files_sha256': {name: hashlib.sha256(payload(content)).hexdigest() for name, content in files.items()}}
    # Recheck source hashes before writing; directory creation is exclusive, never delete/overwrite on failure.
    for name, expected in data['analysis_hashes'].items(): require(digest(contained(analysis, name)) == expected, f'Input changed during formatting: {name}')
    require(digest(data['receipt']) == data['receipt_sha256'], 'Receipt changed during formatting')
    output.mkdir(exist_ok=False)
    for name, content in files.items():
        path = output / name; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream: stream.write(payload(content))
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--analysis-receipt', type=Path)
    parser.add_argument('--receipt-sha256', required=True)
    parser.add_argument('--diagnostic-fixture', action='store_true')
    args = parser.parse_args()
    try:
        result = prepare(args.analysis, args.output, receipt=args.analysis_receipt,
                         receipt_sha256=args.receipt_sha256, diagnostic=args.diagnostic_fixture)
    except (ValueError, KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, f'Report package rejected: {exc}\n')
    print(json.dumps({k: result[k] for k in ('package_kind', 'report_ready', 'experiment_id')}, ensure_ascii=False))

"""Bounded artificial formatter/guard checks; never executes analysis or solvers."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import subprocess
import sys
import re
from copy import deepcopy

import prepare_expanded_report as tool


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def fixture(folder):
    folder.mkdir()
    summary = {'analysis_api_version': 2, 'schema_version': 2, 'experiment_id': 'ARTIFICIAL-REPORT-09',
        'dataset_id': 'ARTIFICIAL-REPORT-DATA', 'phase': 'main', 'artificial': True,
        'report_ready': False, 'label': 'ARTIFICIAL_DIAGNOSTIC',
        'input_hashes': {'export.json': 'a'*64}, 'hashes_json_sha256': 'b'*64,
        'coverage': {'target_counts': {'jobs': 330000, 'puzzles': 16000},
            'selected_blocks': ['b001'], 'selected_complete_blocks': ['b001'],
            'selected_complete_jobs': 12, 'selected_matrix_jobs': 12, 'matrix_planned_jobs': 12,
            'observed_primary_jobs': 12, 'solved_primary_jobs': 9,
            'complete_block_unique_instances': 2, 'status_counts': {'SAT': 9, 'TIMEOUT': 3}}}
    tables = {
        'blocks.csv': [{'batch_id': 'b001', 'expected_jobs': 12, 'observed_primary_jobs': 12,
                        'execution_complete': 'True', 'qa_complete': 'True'}],
        'coverage.csv': [{'configuration': c, 'selected_matrix_jobs': 6, 'observed_primary_jobs': 6,
                          'all_three_sat_instances': n, 'status_counts': json.dumps(s)}
                         for c, n, s in [('sat:pairwise', 2, {'SAT': 6}), ('cpsat', 1, {'SAT': 3, 'TIMEOUT': 3})]],
        'strata.csv': [{'configuration': 'cpsat', 'board_side': 16, 'source': 'synthetic',
                       'source_group': r'bad_#%\input{evil}', 'rating_original': '', 'clue_percent_requested': 20,
                       'family': 'row_cycle', 'runtime_instances': 0, 'mixed_instances': 0,
                       'median_total_seconds': '', 'p90_total_seconds': '', 'p95_total_seconds': '',
                       'mean_instance_par2_seconds': 20, 'par2_instances':1, 'par2_primary_attempts':3, 'root_clusters':1}],
        'matched-pairs.csv': [{'configuration_a': 'cpsat', 'configuration_b': 'sat:pairwise',
                       'board_side': 9, 'source': 'sudoku_exchange', 'source_group': 'easy',
                       'rating_original': '1.0', 'clue_percent_requested': '', 'family': '',
                       'matched_instances': 1, 'instance_ids': json.dumps(['ARTIFICIAL-p9']),
                       'median_paired_a_over_b': 0}],
        'instances.csv': [{'instance_id': 'ARTIFICIAL-p9', 'statuses': '["SAT","SAT","SAT"]'}],
        'primary-par2.csv': [{'attempt_id': 'ARTIFICIAL-a1', 'par2_seconds': 20}],
        'clusters.csv': [{'cluster_id': 'ARTIFICIAL-root', 'instance_ids': '["ARTIFICIAL-p16"]'}],
    }
    return summary, tables


def seal(folder, summary, tables):
    write_json(folder / 'summary.json', summary)
    for name, rows in tables.items():
        with (folder / name).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    receipt = {'schema_version': 2, 'files_sha256': {name: tool.digest(folder/name) for name in tool.REQUIRED},
               'upstream_export_hashes_json_sha256': summary['hashes_json_sha256']}
    write_json(folder/'analysis-hashes.json', receipt)
    return tool.digest(folder/'analysis-hashes.json')


def main(output):
    output = output.resolve()
    allowed = (tool.ROOT / 'diagnostics').resolve()
    assert output.is_relative_to(allowed) and not output.exists()
    output.mkdir(parents=True)
    protected = [tool.ROOT/'shared/document.tex', tool.ROOT/'shared/preamble.tex',
                 tool.ROOT/'output/pdf/sudoku-vi.pdf', tool.ROOT/'output/pdf/sudoku-en.pdf']
    before = {str(p): tool.digest(p) for p in protected}
    analysis = output/'ARTIFICIAL-analysis'
    original, original_tables = fixture(analysis)
    passes = []
    def reject(label, mutate=None, *, diagnostic=True):
        s, t = deepcopy(original), deepcopy(original_tables)
        if mutate: mutate(s, t)
        pin = seal(analysis, s, t)
        try: tool.validate(analysis, receipt_sha256=pin, diagnostic=diagnostic)
        except (ValueError, KeyError, TypeError): passes.append(label)
        else: raise AssertionError('Did not reject: '+label)
    reject('artificial rejected in production', diagnostic=False)
    reject('pilot rejected in production', lambda s,t: s.update(phase='pilot'), diagnostic=False)
    reject('partial rejected', lambda s,t: s['coverage'].update(selected_complete_blocks=[]))
    reject('schema mismatch', lambda s,t: s.update(schema_version=1))
    reject('no QA completion', lambda s,t: t['blocks.csv'][0].update(qa_complete='False'))
    reject('missing primary', lambda s,t: t['blocks.csv'][0].update(observed_primary_jobs=11))
    reject('excluded status cannot shrink denominator', lambda s,t: s['coverage'].update(status_counts={'SAT':8,'TIMEOUT':3,'ERROR':1}))
    reject('zero not substituted for missing median', lambda s,t: t['strata.csv'][0].update(median_total_seconds='0'))
    reject('paired ID count mismatch', lambda s,t: t['matched-pairs.csv'][0].update(matched_instances=2))
    reject('negative configuration counter', lambda s,t: t['coverage.csv'][0].update(status_counts='{"SAT":7,"TIMEOUT":-1}'))
    reject('unknown pair method', lambda s,t: t['matched-pairs.csv'][0].update(configuration_a='unknown'))
    reject('PAR2 denominator mismatch', lambda s,t: t['strata.csv'][0].update(par2_primary_attempts=0))
    def real_claim(s,t):
        s.update(artificial=False,report_ready=True,label='COMPLETE_BLOCKS',experiment_id='real-e',dataset_id='real-d',
                 snapshot_state='PAUSED',halt_reason=None,scientific_sha256='c'*64,
                 config={'repetitions':3,'cutoff_seconds':10,'startup_seconds':60,'postprocessing_seconds':30})
    reject('unverified real quota claim', real_claim, diagnostic=False)
    def halted(s,t):
        real_claim(s,t);s['snapshot_state']='HALTED';s['halt_reason']='fixture halt'
    reject('halted real claim rejected', halted, diagnostic=False)
    pin = seal(analysis, original, original_tables)
    with (analysis/'coverage.csv').open('a') as stream: stream.write('tampered\n')
    try: tool.validate(analysis,receipt_sha256=pin,diagnostic=True)
    except ValueError: passes.append('CSV tamper rejected by hash')
    else: raise AssertionError('tamper accepted')
    pin = seal(analysis, original, original_tables)
    try: tool.validate(analysis,receipt_sha256='0'*64,diagnostic=True)
    except ValueError: passes.append('receipt tamper rejected by pinned hash')
    else: raise AssertionError('bad pin accepted')
    receipt = tool.load_json(analysis/'analysis-hashes.json')
    receipt['files_sha256']['../escape'] = 'a'*64
    write_json(analysis/'analysis-hashes.json',receipt)
    try: tool.validate(analysis,receipt_sha256=tool.digest(analysis/'analysis-hashes.json'),diagnostic=True)
    except ValueError: passes.append('receipt traversal rejected')
    else: raise AssertionError('traversal accepted')
    pin = seal(analysis,original,original_tables)
    package = output/'ARTIFICIAL-package'
    manifest = tool.prepare(analysis,package,receipt_sha256=pin,diagnostic=True)
    assert manifest['report_ready'] is False and manifest['artificial'] is True
    assert manifest['package_kind']=='ARTIFICIAL_DIAGNOSTIC_NOT_FINAL'
    assert (package/'strata/en-000000.tex').read_text().count('--') >= 3
    assert r'\#' in (package/'strata/en-000000.tex').read_text()
    assert r'\input{evil}' not in (package/'strata/en-000000.tex').read_text()
    assert '0.000000' in (package/'paired/en-000000.tex').read_text()
    assert r'\begin{tikzpicture}' in (package/'coverage-tikz.tex').read_text()
    for lang in ('vi','en'):
        assert 'ARTIFICIAL DIAGNOSTIC ONLY' in (package/f'results-{lang}.tex').read_text(encoding='utf-8')
    for name, expected in manifest['files_sha256'].items(): assert tool.digest(package/name)==expected
    assert tool.digest(package/'analysis/analysis-hashes.json') == pin
    for name in tool.REQUIRED: assert tool.digest(package/'analysis'/name)==tool.digest(analysis/name)
    for path in package.rglob('*.tex'):
        source='\n'.join(re.split(r'(?<!\\)%',line)[0] for line in path.read_text(encoding='utf-8').splitlines())
        stack=[]
        for mode,env in re.findall(r'\\(begin|end)\{([^}]+)\}',source):
            if mode=='begin':stack.append(env)
            else:assert stack and stack.pop()==env,path
        assert not stack and source.count('$')%2==0,path
        depth=0
        for ch in re.findall(r'(?<!\\)[{}]',source):
            depth+=1 if ch=='{' else -1
            assert depth>=0,path
        assert depth==0,path
    passes += ['diagnostic manifest never final','null rendered as dash, real zero retained','TeX labels escaped',
               'native TikZ/native tables and shared metrics','all output hashes match','producer receipt and 8 analysis files copied byte-identically',
               'all emitted TeX environment/brace/math delimiters balanced']
    try: tool.prepare(analysis,package,receipt_sha256=pin,diagnostic=True)
    except ValueError: passes.append('existing output not overwritten')
    else: raise AssertionError('overwrite accepted')
    for target, diagnostic in [(tool.ROOT/'output'/'DO-NOT-CREATE',False), (tool.ROOT/'DO-NOT-CREATE',True)]:
        try: tool.prepare(analysis,target,receipt_sha256=pin,diagnostic=diagnostic)
        except ValueError: passes.append('protected/diagnostic path rejected')
        else: raise AssertionError('unsafe output accepted')
        assert not target.exists()
    result = subprocess.run([sys.executable,'-B',str(tool.ROOT/'prepare_expanded_report.py'),
        '--analysis',str(analysis),'--output',str(output/'CLI-ARTIFICIAL'), '--receipt-sha256',pin,
        '--diagnostic-fixture'],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0 and 'ARTIFICIAL_DIAGNOSTIC_NOT_FINAL' in result.stdout,result.stderr
    passes.append('CLI diagnostic smoke')
    for name, expected in before.items(): assert tool.digest(name)==expected
    passes.append('main/preamble/final PDF hashes unchanged')
    evidence = {'status':'PASS','artificial':True,'report_ready':False,'checks':passes,'check_count':len(passes),
                'tool_sha256':tool.digest(tool.ROOT/'prepare_expanded_report.py'),
                'selfcheck_sha256':tool.digest(__file__),'protected_sha256':before,
                'solver_calls':0,'analysis_calls':0,'pdf_builds':0}
    write_json(output/'evidence.json',evidence)
    print(json.dumps(evidence,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    main(parser.parse_args().output)

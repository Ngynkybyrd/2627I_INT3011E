"""Read pinned dataset/index only; no solver, web, generation or benchmark."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RUN = ROOT / 'results/expanded/wave3-20261019-212023-main'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(n, grid):
    return (json.dumps({'n': n, 'grid': grid}, sort_keys=True, separators=(',', ':'), ensure_ascii=False)+'\n').encode()


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines()]


def write(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)+'\n', encoding='utf-8')


def main():
    index = read(RUN/'dataset-index.json')
    experiment = read(RUN/'experiment.json')
    dataset = Path(index['dataset_dir'])
    freeze = read(dataset/'freeze.json')
    provenance = read(dataset/'provenance.json')
    meta = read(dataset/'dataset.json')
    assert index['phase'] == 'main' and index['artificial'] is False and meta['frozen'] is True
    assert sha(dataset/'freeze.json') == index['freeze_sha256'] == experiment['dataset_freeze_sha256']
    for name in ('manifest.jsonl','roots.jsonl','dataset.json','batches.json','provenance.json','dedup.jsonl','completion-evidence.json'):
        assert sha(dataset/name) == freeze['files_sha256'][name], name
    records = list(index['records'].values())
    manifest = lines(dataset/'manifest.jsonl')
    roots = list(index['roots'].values())
    assert {r['instance_id']:r for r in manifest} == index['records']
    assert {r['root_id']:r for r in lines(dataset/'roots.jsonl')} == index['roots']
    assert len(records) == len({r['content_sha256'] for r in records}) == 16000
    assert len(roots) == len({r['root_content_sha256'] for r in roots}) == 1200
    source_hashes=[]
    for source in provenance['sources']:
        path=dataset/source['dataset_file']
        assert sha(path) == source['sha256'] == freeze['files_sha256'][source['dataset_file']]
        source_hashes.append(dict(source))
    by_group=defaultdict(dict)
    by_root=defaultdict(list)
    actual_hist=defaultdict(Counter)
    for r in records:
        path=dataset/r['input_file'];raw=path.read_bytes();p=json.loads(raw)
        assert hashlib.sha256(raw).hexdigest() == r['input_sha256'] == freeze['files_sha256'][r['input_file']]
        assert hashlib.sha256(canonical(p['n'],p['grid'])).hexdigest() == r['content_sha256']
        assert p['n']**2 == r['N'] and len(p['grid']) == r['N']
        assert all(len(row)==r['N'] and all(type(v) is int and 0<=v<=r['N'] for v in row) for row in p['grid'])
        count=sum(v!=0 for row in p['grid'] for v in row)
        assert count==r['actual_clues']
        actual_hist[str(r['N'])][str(count)]+=1
        assert r['witness_validation']['valid'] is True and r['witness_file'] in freeze['files_sha256']
        assert r['witness_sha256']==freeze['files_sha256'][r['witness_file']]
        if r['root_id'] is not None: by_root[r['root_id']].append(r)
        else: by_group[r['source_group']][r['source_line']]=r
    # Match all 10,000 selected public records to original pinned source lines.
    source_rows=[]
    for source in provenance['sources']:
        group=source['file'].removesuffix('.txt')
        if group not in by_group: continue
        wanted=dict(by_group[group]);source_count=0
        with (dataset/source['dataset_file']).open(encoding='ascii') as stream:
            for number,line in enumerate(stream,1):
                source_count+=1
                if number not in wanted: continue
                r=wanted.pop(number);tokens=line.split()
                assert len(tokens)==3 and tokens[0]==r['source_record_id'] and tokens[2]==r['rating_original']
                grid=[[int(v) for v in tokens[1][k:k+9]] for k in range(0,81,9)]
                assert hashlib.sha256(canonical(3,grid)).hexdigest()==r['content_sha256']
                assert r['source_url']==source['url'] and r['source_file_sha256']==source['sha256']
        assert not wanted
        source_rows.append({'group':group,'source_records':source_count,'selected':len(by_group[group])})
    changed=0;cycles=Counter();root_details={}
    for root in roots:
        path=dataset/root['grid_file'];p=read(path)
        assert sha(path)==root['grid_sha256']==freeze['files_sha256'][root['grid_file']]
        assert hashlib.sha256(canonical(p['n'],p['grid'])).hexdigest()==root['root_content_sha256']
        children=by_root[root['root_id']]
        assert len(children)==5 and sorted(r['clue_percent_requested'] for r in children)==[20,30,40,50,60]
        assert all(r['family']==root['family'] and r['root_content_sha256']==root['root_content_sha256'] for r in children)
        assert len({r['batch_id'] for r in children})==1
        changed+=root['root_content_sha256']!=root['base_content_sha256']
        if root['trade'] is not None:
            trade=root['trade'];cols=trade['columns'];a,b=trade['row_a'],trade['row_b'];n=root['n'];N=root['N']
            assert root['family']=='row_cycle' and a!=b and a//n==b//n and 2<=len(cols)<N and len(set(cols))==len(cols)
            before=[list(row) for row in p['grid']]
            for c in cols: before[a][c],before[b][c]=before[b][c],before[a][c]
            assert hashlib.sha256(canonical(n,before)).hexdigest()==trade['base_content_sha256']!=root['root_content_sha256']
            values=trade['values'];mapping={before[a][c]:before[b][c] for c in range(N)}
            assert [before[a][c] for c in cols]==values
            assert all(mapping[v]==values[(k+1)%len(values)] for k,v in enumerate(values))
            cycles[f"N{N}:length{len(cols)}"]+=1
        root_details[root['root_id']]={'N':root['N'],'family':root['family'],'masks':len(children),
            'actual_clues_by_requested_percent':{str(r['clue_percent_requested']):r['actual_clues'] for r in children}}
    synthetic=[r for r in records if r['source']=='synthetic']
    strata=[]
    for N in (16,25):
        for family in ('permutation','row_cycle'):
            for percent in (20,30,40,50,60):
                rows=[r for r in synthetic if (r['N'],r['family'],r['clue_percent_requested'])==(N,family,percent)]
                counts=Counter(r['actual_clues'] for r in rows)
                assert len(rows)==(500 if N==16 else 100) and list(counts)==[(percent*N*N+50)//100]
                strata.append({'N':N,'family':family,'requested_percent':percent,'puzzles':len(rows),
                    'roots':len({r['root_id'] for r in rows}),'actual_clues':next(iter(counts)),
                    'actual_percent':100*next(iter(counts))/(N*N)})
    groups=[]
    for group in ('easy','medium','hard','diabolical'):
        rows=list(by_group[group].values());assert len(rows)==2500
        groups.append({'group':group,'puzzles':len(rows),'clues_min':min(r['actual_clues'] for r in rows),
            'clues_max':max(r['actual_clues'] for r in rows),'rating_min':min(r['rating_value'] for r in rows),
            'rating_max':max(r['rating_value'] for r in rows),
            'rating_original_counts':dict(Counter(r['rating_original'] for r in rows))})
    fingerprints={r['content_sha256'] for r in records}
    assert not fingerprints.intersection(provenance['old_content_sha256'])
    assert not fingerprints.intersection(provenance['other_phase_content_sha256'])
    completion=read(dataset/'completion-evidence.json')
    assert completion['worker_mode']=='production_run_job' and completion['cutoff_seconds']==30
    assert len(completion['records'])==10000
    assert all(r['result']['status']=='SAT' and r['result']['validation']['valid'] is True for r in completion['records'])
    proofs={r['instance_id']:r for r in completion['records']}
    public=[r for r in records if r['source']=='sudoku_exchange']
    assert set(proofs)=={r['instance_id'] for r in public}
    assert all(proofs[r['instance_id']]['input_sha256']==r['input_sha256'] for r in public)
    batch_sizes=Counter(len(b['instance_ids']) for b in index['batches'])
    assert batch_sizes=={160:100}
    hashes={str(path.relative_to(ROOT)).replace('\\','/'):sha(path) for path in
        [RUN/'dataset-index.json',RUN/'experiment.json',dataset/'freeze.json',dataset/'manifest.jsonl',
         dataset/'roots.jsonl',dataset/'provenance.json',dataset/'dedup.jsonl',dataset/'completion-evidence.json']}
    result={'status':'PASS','scope':'Main dataset provenance only, not benchmark success/QA',
        'dataset_id':index['dataset_id'],'dataset_dir':str(dataset),'schema_version':2,'artificial':False,'puzzles':16000,
        'by_N':dict(Counter(str(r['N']) for r in records)),'by_source':dict(Counter(r['source'] for r in records)),
        'public_groups':groups,'source_file_records':source_rows,'source_commit':provenance['source_commit'],
        'source_files':source_hashes,'by_family':dict(Counter(str(r['family']) for r in synthetic)),
        'roots':1200,'roots_by_N_family':dict(Counter(f"N{r['N']}:{r['family']}" for r in roots)),
        'root_masks_histogram':dict(Counter(str(len(v)) for v in by_root.values())),
        'roots_distinct_from_seed_base':changed,'base_source_grids':provenance['base_sources'],
        'proper_cycle_lengths':dict(cycles),'per_root':root_details,'synthetic_strata':strata,
        'actual_clues_histogram_by_N':{k:dict(v) for k,v in actual_hist.items()},
        'uniqueness_labels':dict(Counter(r['uniqueness'] for r in records)),
        'self_proven_uniqueness':0,'sat_evidence':dict(Counter(r['sat_evidence'] for r in records)),
        'indexed_valid_witnesses':sum(r['witness_validation']['valid'] is True for r in records),
        'witness_acquisition_cutoff_seconds':30,'benchmark_cutoff_seconds':10,
        'exact_duplicate_inputs':0,'exact_duplicate_roots':0,'overlap_old_S80':0,'overlap_pilot':0,
        'dedup_log_reasons':dict(Counter(r['reason'] for r in lines(dataset/'dedup.jsonl'))),
        'batch_sizes':dict(batch_sizes),'pinned_inputs_sha256':hashes,
        'checks':{'frozen_index_equals_manifest_and_roots':True,'all_16000_actual_input_hashes_clues':True,
            'all_10000_original_public_source_lines':True,'all_1200_root_hashes_and_600_inverse_cycle_trades':True,
            'witness_metadata_and_pinned_completion_evidence':True,'new_witness_or_uniqueness_solver_calls':0,
            'web_calls':0,'benchmark_calls':0,'fullsuite_rerun':False},
        'limitations':['Source group/rating labels are not independently calibrated solver difficulty.',
            'Public files are also machine-generated (QQWing); source uniqueness claims are not self-proved.',
            'Synthetic roots come from two existing seed grids; exact distinctness is not independence or non-isomorphism.',
            'Each synthetic root supplies five correlated masks; source/root dependence must remain in statistics.',
            'No uniform sampling, uniqueness, size-only hardness or monotonic clue-density hardness is guaranteed.',
            'Witness acquisition30s is outside benchmark10s and is not a benchmark observation.']}
    write('counts.json',result)
    print(json.dumps({k:result[k] for k in ('status','puzzles','by_N','roots','roots_by_N_family','proper_cycle_lengths','uniqueness_labels')},sort_keys=True))


if __name__=='__main__':main()

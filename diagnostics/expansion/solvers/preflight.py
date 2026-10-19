"""EXP-04 only: eight guarded refresh jobs, reuse unchanged large-board evidence."""
import csv
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from sudoku import runner
from sudoku.model import load_puzzle
from sudoku.validation import check_solution

def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,data): (OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')

def main():
    if (OUT/'result.json').exists(): raise RuntimeError('Refuse to overwrite preflight evidence')
    old=ROOT/'results/raw/main-20261016-01'
    metadata=read(old/'run.json')
    packages=runner.package_versions()
    assert packages==metadata['packages'],'Runtime versions changed; cannot reuse evidence'
    assert platform.python_version()==metadata['machine']['python']
    assert all(sha(ROOT/k)==v for k,v in metadata['code_sha256'].items())
    assert sha(ROOT/'data/freeze.json')==metadata['dataset_freeze_sha256']
    manifest=read(ROOT/'data/manifest.json')['records']
    byid={r['instance_id']:r for r in manifest}
    rows=list(csv.DictReader((old/'results.csv').open(encoding='utf-8',newline='')))
    protected={str(p.relative_to(ROOT)):sha(p) for p in [old/'run.json',old/'results.csv',ROOT/'data/freeze.json',ROOT/'data/manifest.json']}
    combos=[('sat',e) for e in ('pairwise','seqcounter','bitwise')]+[('cpsat',None),('highs',None)]
    reused=[]
    for N in (16,25):
        for method,encoding in combos:
            r=next(r for r in rows if byid[r['instance_id']]['N']==N and r['method']==method and
                   (r['encoding'] or None)==encoding and r['status']=='SAT' and r['validation']=='pass' and r['guard_phase']=='complete')
            data=byid[r['instance_id']]
            assert sha(ROOT/data['file'])==data['sha256']
            witness=old/r['solution_artifact']
            assert check_solution(load_puzzle(ROOT/data['file']),read(witness)['solution']).valid
            reused.append({'N':N,'method':method,'encoding':encoding,'source_job':r['job_id'],
                           'source_csv_sha256':sha(old/'results.csv'),'witness':str(witness.relative_to(ROOT)),
                           'witness_sha256':sha(witness),'status':'SAT','checker_recheck':'PASS',
                           'cleanup_basis':'original run_job complete; frozen runner verifies active JobObject count=0 before returning'})
    save('reused-evidence.json',reused)
    runtime=Path(sys.prefix)/'Scripts/cpoptimizer.exe'
    save('inventory.json',{'timestamp_utc':datetime.now(timezone.utc).isoformat(),'python':sys.version,
        'executable':sys.executable,'packages':packages,'cpoptimizer_executable':str(runtime),
        'cpoptimizer_sha256':sha(runtime),'source_sha256':metadata['code_sha256'],
        'old_code_hashes_match':True,'old_package_versions_match':True,'old_run_json_sha256':sha(old/'run.json'),
        'fresh_env_fingerprint':'Root to cross-check EXP-01; this is local EXP-04 inventory'})
    # Instrument only this process's wrapper; no production file changes.
    cleanup=[]
    Base=runner.JobObject
    class AuditedJob(Base):
        def __init__(self):
            super().__init__(); self.record={'assigned':False,'zero_active_after_terminate':False,'closed':False}; cleanup.append(self.record)
        def assign(self,pid):
            super().assign(pid); self.record.update(assigned=True,pid=pid)
        def terminate_and_wait(self,timeout=5.0):
            super().terminate_and_wait(timeout); self.record['zero_active_after_terminate']=True
        def close(self):
            super().close(); self.record['closed']=True
    runner.JobObject=AuditedJob
    chosen=byid['synthetic-N09-p70-s0']
    assert sha(ROOT/chosen['file'])==chosen['sha256']
    config=runner.RunnerConfig(cutoff_seconds=10.0,repetitions=1)
    results=[]
    for method,encoding in combos+[('gurobi',None),('cplex_mip',None),('cpoptimizer',None)]:
        job={'job_id':f'exp04-{method}-{encoding or "none"}','instance_id':chosen['instance_id'],
             'file':chosen['file'],'method':method,'encoding':encoding,'repetition':1,'cutoff_seconds':10.0}
        started=time.perf_counter()
        result=runner.run_job(job,config,root=ROOT)
        elapsed=time.perf_counter()-started
        item={'N':9,'job':job,'input_sha256':chosen['sha256'],'wall_seconds':elapsed,'result':result,'cleanup':cleanup[-1] if cleanup else None}
        results.append(item); save('result.json',results); save('cleanup.json',cleanup)
        print(method,encoding or '-',result['status'],result.get('guard_phase'),flush=True)
        assert result['status']=='SAT' and result['validation']['valid'],result
        assert check_solution(load_puzzle(ROOT/chosen['file']),result['solution']).valid
        assert result['guard_phase']=='complete'
        assert all(cleanup[-1][k] for k in ('assigned','zero_active_after_terminate','closed'))
    assert all(sha(ROOT/k)==v for k,v in protected.items())
    assert all(sha(ROOT/k)==v for k,v in metadata['code_sha256'].items())
    matrix=[{'N':N,'method':m,'encoding':e,'included':True,
             'evidence':'fresh guarded diagnostic' if N==9 else 'reused frozen run + checker recheck'}
            for N in (9,16,25) for m,e in combos+([('gurobi',None),('cplex_mip',None),('cpoptimizer',None)] if N==9 else [])]
    exclusions=[{'N':N,'method':m,'included':False,'reason':'declared scope; full MIP exceeds known variable cap' if m!='cpoptimizer' else
                 'declared scope; prior low-clue CP probes exceeded search-space cap; not universal impossibility'}
                for N in (16,25) for m in ('gurobi','cplex_mip','cpoptimizer')]
    save('matrix.json',{'schema_version':'exp04-preflight-v1','matrix':matrix,'exclusions':exclusions,
        'projected_jobs':330000,'projected_block_jobs':3300,'projected_pilot_jobs':164,
        'not_dataset_freeze':True,'not_benchmark':True})
    save('verification.json',{'fresh_jobs':len(results),'fresh_sat':len(results),'fresh_cleanup_pass':len(cleanup),
        'reused_cells':len(reused),'all_reused_witnesses_rechecked':True,'preserved_sha256':protected,
        'protected_unchanged':True,'source_unchanged':True,'result':'PASS'})

if __name__=='__main__': main()

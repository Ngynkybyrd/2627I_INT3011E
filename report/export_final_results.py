"""Format locked SAT08 tables for both languages; no raw analysis or solver calls."""
import csv
import hashlib
import json
import shutil
from pathlib import Path

REPORT = Path(__file__).resolve().parent
SOURCE = REPORT.parent / 'results/summary/main-20261016-01'
PAPER = SOURCE / 'paper'
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):
    with p.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))
verification = json.loads((SOURCE / 'verification.json').read_text())
assert verification['accepted'] and verification['rows'] == 906
assert verification['statuses'] == {'SAT': 903, 'TIMEOUT': 3}
for name, digest in verification['paper_outputs_sha256'].items():
    assert sha(PAPER / name) == digest, name
names = {'sat:pairwise':'Glucose3 pairwise', 'sat:seqcounter':'Glucose3 sequential',
         'sat:bitwise':'Glucose3 bitwise', 'cpsat':'CP-SAT', 'highs':'HiGHS ILP',
         'gurobi':'Gurobi MIP', 'cplex_mip':'CPLEX MIP', 'cpoptimizer':'CP Optimizer'}
def table(name, caption, label, columns, header, data, note=''):
    text = '\\begin{table}[pos=H]\n\\centering\n\\small\n'
    text += f'\\caption{{{caption}}}\n\\label{{{label}}}\n'
    text += f'\\begin{{tabular}}{{{columns}}}\n\\toprule\n'
    text += header + '\\\\\n\\midrule\n'
    text += ''.join(' & '.join(map(str, r)) + '\\\\\n' for r in data)
    text += '\\bottomrule\n\\end{tabular}\n'
    if note:
        text += '\\par\\smallskip\\begin{minipage}{0.97\\linewidth}\\footnotesize\n' + note + '\n\\end{minipage}\n'
    text += '\\end{table}\n'
    (REPORT / 'tables' / name).write_text(text, encoding='utf-8')
coverage = rows(PAPER / 'coverage.csv')
assert sum(int(r['observed_jobs']) for r in coverage) == 906
order = ['sat:pairwise','sat:seqcounter','sat:bitwise','cpsat','highs','gurobi','cplex_mip','cpoptimizer']
coverage = sorted(coverage, key=lambda r: order.index(r['configuration']))
data = []
for r in coverage:
    data.append([names[r['configuration']],r['scope'],f"{r['solved_runs']}/{r['observed_jobs']}",
                 f"{r['solved_instances_three']}/{r['scope_instances']}",int(r['observed_jobs'])-int(r['solved_runs'])])
table('final-coverage.tex',r'\lang{Độ phủ của 906 lượt chính.}{Coverage of the 906 main runs.}',
      'tab:coverage','llrrr',r'\lang{Cấu hình}{Configuration} & \lang{Tập}{Scope} & SAT/\lang{lượt}{runs} & \lang{Đề đủ 3 SAT}{Instances with 3 SAT} & TIMEOUT',data)

summary = rows(SOURCE / 'summary.csv')
selected = []
for enc in ('pairwise','seqcounter','bitwise'):
    r = next(r for r in summary if r['configuration']=='sat:'+enc and r['source']=='synthetic' and r['N']=='25' and r['clue_density_requested']=='0.300000')
    assert r['solved_instances_three']=='5'
    selected.append([names[r['configuration']].replace('Glucose3 ',''),r['median_instance_build_seconds'],r['median_instance_solve_seconds'],r['median_instance_total_seconds']])
table('final-build-solve.tex',r'\lang{Synthetic $25\times25$, 30\% clues: năm ID chung, giây.}{Synthetic $25\times25$, 30\% clues: five common IDs, seconds.}',
      'tab:buildsolve','lrrr','Encoding & Median build & Median solve & Median total',selected,
      r'\lang{Mỗi cột là median của median ba lượt theo đề, tổng hợp độc lập; không cộng hai median nhóm để suy median total.}{Each column is an independently aggregated median of per-instance three-run medians; the group build and solve medians do not sum to the group total median.}')
values = {'PairTotal': selected[0][3], 'SeqTotal': selected[1][3], 'BitTotal': selected[2][3]}
for enc, prefix in [('pairwise','Pair'),('seqcounter','Seq'),('bitwise','Bit')]:
    r = next(r for r in summary if r['configuration']=='sat:'+enc and r['source']=='synthetic' and r['N']=='4' and r['clue_density_requested']=='0.300000')
    values[prefix+'SmallTotal'] = r['median_instance_total_seconds']

cnf = rows(SOURCE / 'cnf.csv')
cnfdata = []
for enc in ('pairwise','seqcounter','bitwise'):
    r = next(r for r in cnf if r['instance_id']=='synthetic-N25-p30-s0' and r['configuration']=='sat:'+enc)
    assert r['clue_count']=='188'
    cnfdata.append([names[r['configuration']].replace('Glucose3 ',''),r['primary_variables'],r['auxiliary_variables'],r['total_variables'],r['clauses']])
table('final-cnf-example.tex',r'\lang{CNF thực của synthetic-N25-p30-s0, 188 clues; trước preprocessing.}{Measured CNF for synthetic-N25-p30-s0, 188 clues; before preprocessing.}',
      'tab:cnfactual','lrrrr',r'Encoding & \lang{Biến chính}{Primary} & \lang{Biến phụ}{Auxiliary} & \lang{Tổng biến}{Total variables} & Clauses',cnfdata)

matched = rows(PAPER / 'baseline-matched.csv')
def get(method,N,density,source='synthetic'):
    found = [r for r in matched if r['configuration_a']==method and r['N']==str(N) and r['clue_density_requested']==density and r['source']==source]
    assert len(found)<=1
    return found[0] if found else None
bdata=[]
for N in (4,9,16,25):
    for density in ('0.300000','0.500000','0.700000'):
        cp,h=get('cpsat',N,density),get('highs',N,density)
        assert cp and cp['matched_count']=='1'
        if h: assert h['median_b_seconds']==cp['median_b_seconds'] and h['matched_count']=='1'
        bdata.append([N,int(float(density)*100),'1/1' if h else '1/0',cp['median_a_seconds'],h['median_a_seconds'] if h else '--',cp['median_b_seconds']])
table('final-baseline-b16.tex',r'\lang{B16 synthetic: median total trên từng ID chung, giây.}{B16 synthetic: median total on each common ID, seconds.}',
      'tab:b16','rrrrrr',r'$N$ & \lang{Clues (\%)}{Clues (\%)} & $m_{CP}/m_H$ & CP-SAT & HiGHS & Pairwise',bdata,
      r'\lang{$m$ là số ID đủ ba SAT ở cả hai bên. Mỗi hàng chỉ có một ID, khác năm ID/hàng của S80. Dấu --: HiGHS có 3 TIMEOUT ở N25/30\%, không có median SAT.}{Here $m$ counts IDs with three SAT runs in both configurations. Each row has one ID, unlike five IDs per S80 stratum. A dash denotes three HiGHS timeouts at N25/30\%, with no SAT median.}')
cdata=[]
for N in (4,9):
    for density in ('0.300000','0.500000','0.700000'):
        group=[get(method,N,density) for method in ('gurobi','cplex_mip','cpoptimizer')]
        assert all(r['matched_count']=='1' for r in group)
        cdata.append([N,int(float(density)*100),1,*[r['median_a_seconds'] for r in group],group[0]['median_b_seconds']])
table('final-baseline-c10.tex',r'\lang{C10 synthetic: một ID chung mỗi hàng, median total (giây).}{C10 synthetic: one common ID per row, median total (seconds).}',
      'tab:c10','rrrrrrr',r'$N$ & Clues (\%) & $m$ & Gurobi & CPLEX MIP & CP Optimizer & Pairwise',cdata)
pdata=[]
for method in ('cpsat','highs','gurobi','cplex_mip','cpoptimizer'):
    r=get(method,9,'','public_sudoku_exchange_hard')
    assert r['matched_count']=='4'
    pdata.append([names[method],r['scope'],4,r['median_a_seconds'],r['median_b_seconds']])
    values[{'cpsat':'Cp','highs':'Highs','gurobi':'Gurobi','cplex_mip':'Cplex','cpoptimizer':'Cpo'}[method]+'PublicTotal']=r['median_a_seconds']
values['PairPublicTotal']=pdata[0][-1]
table('final-baseline-public.tex',r'\lang{Bốn public $9\times9$ chung của B16/C10, median total (giây).}{Four common public $9\times9$ instances in B16/C10, median total (seconds).}',
      'tab:public','llrrr',r'\lang{Backend}{Backend} & \lang{Tập}{Scope} & $m$ & \lang{Backend}{Backend} & Pairwise',pdata,
      r'\lang{Cùng bốn ID L069940, L293964, L269904, L215069 (prefix public-se-hard-). Pairwise là mốc cố định; không chọn encoding nhanh nhất cho từng đối thủ.}{The same four IDs are L069940, L293964, L269904, and L215069 (prefix public-se-hard-). Pairwise is a fixed reference, not the fastest encoding selected separately for each opponent.}')
(REPORT/'shared/result-values.tex').write_text(''.join(f'\\newcommand{{\\{key}}}{{{value}}}\n' for key,value in values.items()),encoding='utf-8')
for name in ('figure-cnf-size.pdf','figure-runtime.pdf'):
    shutil.copyfile(PAPER/name,REPORT/'figures'/name)
inputs=[SOURCE/'findings.md',SOURCE/'final-checks.json',SOURCE/'verification.json',SOURCE/'audit.json',SOURCE/'summary.csv',SOURCE/'cnf.csv',PAPER/'coverage.csv',PAPER/'baseline-matched.csv',PAPER/'runtime-matched.csv',PAPER/'cnf-size.csv',PAPER/'figure-cnf-size.pdf',PAPER/'figure-runtime.pdf']
record={'status':'PASS','source':'locked SAT08 final analysis','no_solver_or_raw_reanalysis':True,
        'input_sha256':{str(p.relative_to(REPORT.parent)):sha(p) for p in inputs},
        'values':values,'tables':['coverage','build-solve','cnf-example','baseline-b16','baseline-c10','baseline-public'],
        'trace':{'coverage':'paper/coverage.csv; verification.json statuses',
                 'buildsolve':'summary.csv: synthetic, N=25, density=0.300000, sat:pairwise/seqcounter/bitwise',
                 'cnfactual':'cnf.csv: synthetic-N25-p30-s0, all three SAT configurations',
                 'baselines':'paper/baseline-matched.csv; configuration_a, N, source, density; exact ID sets retained upstream',
                 'timeout':'findings.md Timeout and PAR-2; verification.json penalty_each=20 and sum=60'}}
(REPORT/'logs/final-results-provenance.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('PASS: locked paper hashes; six bilingual tables, numeric macros and two copied PDF figures; report/ only')

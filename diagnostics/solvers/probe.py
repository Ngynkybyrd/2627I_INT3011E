"""Isolated runtime diagnostics, not production adapters or benchmark results."""
import importlib.metadata as md
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent

def groups(n):
    N = n*n
    idx = lambda r,c,v: (r*N+c)*N+v
    out = [[idx(r,c,v) for v in range(N)] for r in range(N) for c in range(N)]
    out += [[idx(r,c,v) for c in range(N)] for r in range(N) for v in range(N)]
    out += [[idx(r,c,v) for r in range(N)] for c in range(N) for v in range(N)]
    out += [[idx(br+i,bc+j,v) for i in range(n) for j in range(n)]
            for br in range(0,N,n) for bc in range(0,N,n) for v in range(N)]
    return out

def check(grid,n):
    N=n*n; target=set(range(1,N+1))
    assert len(grid)==N and all(len(row)==N for row in grid)
    assert all(set(row)==target for row in grid)
    assert all({grid[r][c] for r in range(N)}==target for c in range(N))
    assert all({grid[r+i][c+j] for i in range(n) for j in range(n)}==target
               for r in range(0,N,n) for c in range(0,N,n))
    assert grid[0][0]==1

def decode(values,n):
    N=n*n
    assert all(abs(v-round(v))<=1e-6 and -1e-6<=v<=1+1e-6 for v in values)
    grid=[]
    for r in range(N):
        row=[]
        for c in range(N):
            selected=[v+1 for v in range(N) if values[(r*N+c)*N+v]>0.5]
            assert len(selected)==1
            row.append(selected[0])
        grid.append(row)
    check(grid,n)
    return grid

def run(engine,n):
    N=n*n; gs=groups(n); result={'engine':engine,'N':N,'clues':1}
    if engine in ('gurobi','cplex','glucose'):
        result.update(variables=N**3,exo_groups=len(gs),linear_constraints=len(gs)+1)
    else:
        result.update(variables=N*N,alldifferent_constraints=3*N,constraints=3*N+1)
    start=time.perf_counter()
    try:
        if engine=='gurobi':
            import gurobipy as gp
            # Inspect actual runtime/license outcome; do not supply credentials.
            with gp.Env(empty=True) as env:
                env.setParam('OutputFlag',0)
                env.start()
                with gp.Model(env=env) as m:
                    m.Params.Threads=1; m.Params.TimeLimit=5
                    x=m.addVars(N**3,vtype=gp.GRB.BINARY)
                    for group in gs: m.addConstr(gp.quicksum(x[i] for i in group)==1)
                    m.addConstr(x[0]==1); m.update()
                    result.update(runtime_version=gp.gurobi.version(),threads=m.Params.Threads,
                                  variables=m.NumVars,linear_constraints=m.NumConstrs)
                    m.optimize(); result['raw_status']=m.Status
                    if m.SolCount: result['grid']=decode([x[i].X for i in range(N**3)],n)
        elif engine=='cplex':
            import cplex
            with cplex.Cplex() as m:
                m.set_log_stream(None); m.set_results_stream(None)
                m.set_warning_stream(None); m.set_error_stream(None)
                m.parameters.threads.set(1); m.parameters.timelimit.set(5)
                m.variables.add(types='B'*(N**3))
                m.linear_constraints.add(lin_expr=[cplex.SparsePair(g,[1]*len(g)) for g in gs]+[cplex.SparsePair([0],[1])],senses='E'*(len(gs)+1),rhs=[1]*(len(gs)+1))
                result.update(runtime_version=m.get_version(),threads=m.parameters.threads.get())
                m.solve(); result['raw_status']=m.solution.get_status_string()
                if m.solution.is_primal_feasible(): result['grid']=decode(m.solution.get_values(),n)
        elif engine=='cpoptimizer':
            from docplex.cp.model import CpoModel
            import cplex
            executables=list(Path(sys.prefix).rglob('cpoptimizer.exe'))
            result['executable']=str(executables[0]) if executables else None
            if not executables: raise FileNotFoundError('No cpoptimizer.exe under cplex package')
            m=CpoModel(); x=[[m.integer_var(1,N,name=f'x_{r}_{c}') for c in range(N)] for r in range(N)]
            for row in x: m.add(m.all_diff(row))
            for c in range(N): m.add(m.all_diff([x[r][c] for r in range(N)]))
            for r in range(0,N,n):
                for c in range(0,N,n): m.add(m.all_diff([x[r+i][c+j] for i in range(n) for j in range(n)]))
            m.add(x[0][0]==1)
            sol=m.solve(execfile=str(executables[0]),Workers=1,TimeLimit=5,LogVerbosity='Quiet')
            result.update(raw_status=str(sol.get_solve_status()),workers=1,
                          runtime_version=sol.get_process_infos().get_solver_version(),
                          solver_infos=dict(sol.get_solver_infos()))
            if sol.is_solution():
                result['grid']=[[sol[v] for v in row] for row in x]; check(result['grid'],n)
        elif engine=='cpsat':
            from ortools.sat.python import cp_model
            m=cp_model.CpModel(); x=[[m.new_int_var(1,N,f'x{r}_{c}') for c in range(N)] for r in range(N)]
            for row in x: m.add_all_different(row)
            for c in range(N): m.add_all_different([x[r][c] for r in range(N)])
            for r in range(0,N,n):
                for c in range(0,N,n): m.add_all_different([x[r+i][c+j] for i in range(n) for j in range(n)])
            m.add(x[0][0]==1); s=cp_model.CpSolver(); s.parameters.num_search_workers=1; s.parameters.max_time_in_seconds=5
            status=s.solve(m); result.update(raw_status=s.status_name(status),workers=1)
            if status in (cp_model.FEASIBLE,cp_model.OPTIMAL):
                result['grid']=[[s.value(v) for v in row] for row in x]; check(result['grid'],n)
        elif engine=='glucose':
            from pysat.solvers import Glucose3
            from itertools import combinations
            clauses=[]
            for g in gs:
                clauses.append([i+1 for i in g]); clauses.extend([[-i-1,-j-1] for i,j in combinations(g,2)])
            clauses.append([1]); result['clauses']=len(clauses)
            with Glucose3(bootstrap_with=clauses) as s:
                ok=s.solve(); result['raw_status']=ok
                if ok:
                    positive=set(v for v in s.get_model() if v>0)
                    result['grid']=decode([int(i+1 in positive) for i in range(N**3)],n)
        result['status']='SAT' if 'grid' in result else 'NO_SOLUTION_RETURNED'
        result['validation']='PASS' if 'grid' in result else None
    except Exception as e:
        message=str(e)
        result.update(status='LICENSE_LIMIT' if any(t in message.lower() for t in ('too large','1016','2^1000','size limit','size-limit','community edition solves')) else 'ERROR',error_type=type(e).__name__,error=message)
    result['diagnostic_seconds']=time.perf_counter()-start
    return result

if __name__=='__main__':
    if len(sys.argv)>1:
        item=run(sys.argv[1],int(sys.argv[2])); Path(sys.argv[3]).write_text(json.dumps(item,indent=2,default=str),encoding='utf-8')
    else:
        versions={'python':sys.version,'executable':sys.executable,'packages':{p:md.version(p) for p in ('gurobipy','cplex','docplex','python-sat','ortools','highspy')}}
        (ROOT/'versions.json').write_text(json.dumps(versions,indent=2),encoding='utf-8')
        for engine,ns in [('glucose',[2]),('cpsat',[2]),('gurobi',[2,3,4]),('cplex',[2,3,4]),('cpoptimizer',[2,3,4,5])]:
            for n in ns:
                target=ROOT/f'{engine}-{n*n}.json'
                with (ROOT/f'{engine}-{n*n}.log').open('w',encoding='utf-8') as log:
                    try:
                        subprocess.run([sys.executable,__file__,engine,str(n),str(target)],stdout=log,stderr=subprocess.STDOUT,timeout=25,check=True)
                    except (subprocess.TimeoutExpired,subprocess.CalledProcessError) as e:
                        target.write_text(json.dumps({'engine':engine,'N':n*n,'status':'PROBE_PROCESS_ERROR','error':str(e)}),encoding='utf-8')
                data=json.loads(target.read_text(encoding='utf-8')); print(engine,n*n,data['status'],flush=True)

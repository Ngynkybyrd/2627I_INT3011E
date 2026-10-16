"""Adapter-specific checks; independent checker tests remain owned by SAT03."""
import math
import time
import threading
from unittest.mock import patch
from types import SimpleNamespace

import pytest

from sudoku.model import Puzzle
from sudoku.contracts import SolveStatus as S, ValidationResult
from sudoku.baselines import METHODS, solve_baseline, prepare_backend
from sudoku.baselines import adapters as a


def fixture(n, conflict=False):
    N=n*n
    grid=[[((r*n+r//n+c)%N)+1 for c in range(N)] for r in range(N)]
    if conflict:
        grid[0][1]=grid[0][0]
    else:
        for r in range(N):
            grid[r][(r+1)%N]=0
    return Puzzle(n,grid)


@pytest.mark.parametrize('method',METHODS)
@pytest.mark.parametrize('conflict',[False,True])
def test_real_small_models(method,conflict):
    prepare_backend(method)
    result=solve_baseline(fixture(2,conflict),method)
    assert result.status==(S.UNSAT if conflict else S.SAT),result
    assert result.raw_status
    assert result.total_seconds==pytest.approx(result.build_seconds+result.solve_seconds)
    assert result.encoding is None and result.stats is None
    if not conflict:
        assert result.validation.valid and result.solution


@pytest.mark.parametrize('method',METHODS)
def test_real_nine_and_fresh_call(method):
    result=solve_baseline(fixture(3),method)
    assert result.status==S.SAT,result
    assert result.validation.valid
    assert solve_baseline(fixture(2,True),method).status==S.UNSAT


@pytest.mark.parametrize('method',['cpsat','highs'])
@pytest.mark.parametrize('n',[4,5])
def test_large_smoke(method,n):
    result=solve_baseline(fixture(n),method)
    assert result.status==S.SAT,result
    assert result.validation.valid


@pytest.mark.parametrize('method',['gurobi','cplex_mip','cpoptimizer'])
def test_installed_free_runtime_limit(method):
    p=Puzzle(4,[[0]*16 for _ in range(16)])
    result=solve_baseline(p,method)
    assert result.status==S.LICENSE_LIMIT,result
    assert result.solution is None and result.error


@pytest.mark.parametrize('method',METHODS)
def test_expired_deadline_never_builds(method):
    with patch.object(a,'_run',side_effect=AssertionError('must not build')):
        result=solve_baseline(fixture(2),method,deadline=time.perf_counter()-1)
    assert result.status==S.TIMEOUT and result.solve_seconds==0


@pytest.mark.parametrize('cutoff',[0,-1,math.inf,math.nan,True,'10'])
def test_invalid_cutoff(cutoff):
    with pytest.raises(ValueError): solve_baseline(fixture(2),'cpsat',cutoff_seconds=cutoff)


def test_invalid_method_and_deadline():
    with pytest.raises(ValueError): prepare_backend('other')
    with pytest.raises(ValueError): solve_baseline(fixture(2),'cpsat',deadline=math.nan)


def test_missing_dependency():
    with patch.object(a,'prepare_backend',side_effect=ImportError('missing dependency')):
        result=solve_baseline(fixture(2),'highs')
    assert result.status==S.UNAVAILABLE and result.total_seconds is None


def fake_run(outcome, late=False):
    def run(p,method,clock,stack):
        clock.build_end=clock.start
        clock.end=clock.deadline+1 if late else clock.start+0.001
        return outcome
    return run


def test_unknown_not_unsat_and_native_time_limit():
    for state in (S.ERROR,S.TIMEOUT):
        with patch.object(a,'_run',fake_run(a._Outcome('unknown/limit',state))):
            assert solve_baseline(fixture(2),'highs').status==state


def test_late_incumbent_rejected_before_validation():
    with patch.object(a,'_run',fake_run(a._Outcome('time limit',decode=lambda: ()),True)),patch.object(a,'check_solution',side_effect=AssertionError('late result')):
        result=solve_baseline(fixture(2),'highs')
    assert result.status==S.TIMEOUT and result.solution is None


def test_checker_rejection_and_exception():
    for validator in (lambda *x: ValidationResult(False,'bad clue'),lambda *x: (_ for _ in ()).throw(ValueError('bad decode'))):
        with patch.object(a,'_run',fake_run(a._Outcome('feasible',decode=lambda: ()))),patch.object(a,'check_solution',validator):
            result=solve_baseline(fixture(2),'highs')
        assert result.status==S.ERROR and not result.validation.valid and result.solution is None


def test_timelimit_incumbent_on_time_requires_checker():
    full=Puzzle(2,[[((r*2+r//2+c)%4)+1 for c in range(4)] for r in range(4)])
    with patch.object(a,'_run',fake_run(a._Outcome('TIME_LIMIT',decode=lambda: full.grid))):
        result=solve_baseline(full,'gurobi')
    assert result.status==S.SAT and result.validation.valid and result.raw_status=='TIME_LIMIT'


@pytest.mark.parametrize('bad',[0.5,math.nan,math.inf,1.01,-0.01])
def test_mip_rejects_nonbinary(bad):
    vals=[0.0]*64; vals[0]=bad
    with pytest.raises(ValueError): a._decode_mip(vals,4)


def test_mip_rejects_missing_multiple_and_wrong_length():
    for vals in ([0.0]*64,[1.0]*64,[0.0]*63):
        with pytest.raises(ValueError): a._decode_mip(vals,4)


def test_remaining_budget_after_setup():
    clock=a._Clock(1,None)
    clock.start-=0.25; clock.deadline-=0.25
    limits=[]
    clock.solve(limits.append,lambda: None)
    assert 0<limits[0]<=0.75
    assert clock.timings()['build_seconds']>=0.25


def test_cleanup_failure_is_error_with_original_raw_status():
    def failing_cleanup():
        raise RuntimeError('cleanup exploded')
    def run(p,method,clock,stack):
        stack.callback(failing_cleanup)
        clock.build_end=clock.start; clock.end=clock.start+0.001
        return a._Outcome('UNKNOWN',S.ERROR)
    with patch.object(a,'_run',run):
        result=solve_baseline(fixture(2),'highs')
    assert result.status==S.ERROR and 'Cleanup failed' in result.error
    assert result.raw_status=='UNKNOWN'


@pytest.mark.parametrize('elapsed,expected',[(0.0,S.ERROR),(100.0,S.TIMEOUT)])
def test_cpsat_unknown_native_evidence(elapsed,expected):
    from ortools.sat.python import cp_model as cp
    fake=SimpleNamespace(parameters=SimpleNamespace(),wall_time=elapsed,
                         solve=lambda model: cp.UNKNOWN,status_name=lambda code: 'UNKNOWN')
    with patch.object(a,'build_cpsat',return_value=SimpleNamespace(solver=fake,model=None)):
        result=solve_baseline(fixture(2),'cpsat')
    assert result.status==expected and result.raw_status=='UNKNOWN'


def test_budget_exhausted_during_setup_still_cleans():
    cleaned=[]
    def run(p,method,clock,stack):
        stack.callback(cleaned.append,True)
        clock.deadline=clock.start-1
        clock.remaining()
    with patch.object(a,'_run',run):
        result=solve_baseline(fixture(2),'highs')
    assert result.status==S.TIMEOUT and cleaned==[True] and result.solve_seconds==0


def test_highs_fractional_timeout_is_not_decode_error():
    import highspy as hs
    real=hs.Highs
    class TimedHighs:
        def __init__(self): self.h=real()
        def __getattr__(self,name): return getattr(self.h,name)
        def run(self): return hs.HighsStatus.kWarning
        def getModelStatus(self): return hs.HighsModelStatus.kTimeLimit
        def getSolution(self): return SimpleNamespace(value_valid=True,col_value=[0.5]*64)
        def getInfo(self): return SimpleNamespace(primal_solution_status=hs.SolutionStatus.kSolutionStatusInfeasible,max_integrality_violation=0.5)
    with patch.object(hs,'Highs',TimedHighs):
        result=solve_baseline(fixture(2),'highs')
    assert result.status==S.TIMEOUT and result.solution is None


def test_cpoptimizer_cooperative_remaining_deadline_and_cleanup():
    from docplex.cp.solver import solver as module
    aborted=threading.Event(); closed=[]
    class FakeCpo:
        def __init__(self,*args,**kwargs):
            self.context=SimpleNamespace(params=SimpleNamespace())
            self.agent=SimpleNamespace(_init_model_in_solver=lambda: time.sleep(0.01))
        def __enter__(self): return self
        def __exit__(self,*args): closed.append(True)
        def abort_search(self): aborted.set()
        def solve(self):
            assert aborted.wait(1),'deadline abort not called'
            return SimpleNamespace(get_solve_status=lambda:'Unknown',get_stop_cause=lambda:'SearchStoppedByAbort')
    prepare_backend('cpoptimizer')
    with patch.object(module,'CpoSolver',FakeCpo):
        result=solve_baseline(fixture(2),'cpoptimizer',cutoff_seconds=0.08)
    assert result.status==S.TIMEOUT and aborted.is_set() and closed==[True]
    assert result.build_seconds>=0.01 and result.solution is None


@pytest.mark.parametrize('method',METHODS)
def test_measurement_hook_real_backend(method):
    calls=[]
    result=solve_baseline(fixture(2),method,on_measurement_end=lambda end,t: calls.append((end,t)))
    assert result.status==S.SAT and len(calls)==1
    end,timings=calls[0]
    assert end<=time.perf_counter()
    assert timings==dict(build_seconds=result.build_seconds,solve_seconds=result.solve_seconds,total_seconds=result.total_seconds)


def test_measurement_hook_precedes_slow_validation_and_cleanup():
    events=[]; received=[]
    full=Puzzle(2,[[((r*2+r//2+c)%4)+1 for c in range(4)] for r in range(4)])
    def run(p,method,clock,stack):
        stack.callback(events.append,'cleanup')
        clock.solve(lambda t: None,lambda: None)
        events.append('after_native')
        return a._Outcome('feasible',decode=lambda: full.grid)
    def callback(end,timings):
        events.append('END'); received.append((end,timings))
    def validate(*args):
        events.append('validation'); time.sleep(0.015)
        return ValidationResult(True)
    with patch.object(a,'_run',run),patch.object(a,'check_solution',validate):
        result=solve_baseline(full,'cpsat',on_measurement_end=callback)
    assert events==['END','after_native','validation','cleanup']
    assert len(received)==1 and result.status==S.SAT
    assert time.perf_counter()-received[0][0]>=0.015
    assert received[0][1]['total_seconds']==result.total_seconds


@pytest.mark.parametrize('failure',[RuntimeError('build failed'),a._BudgetExpired('build expired')])
def test_measurement_hook_failed_build(failure):
    events=[]; received=[]
    def run(p,method,clock,stack):
        stack.callback(events.append,'cleanup')
        raise failure
    def callback(end,t): events.append('END'); received.append(t)
    with patch.object(a,'_run',run):
        result=solve_baseline(fixture(2),'cpsat',on_measurement_end=callback)
    assert events==['END','cleanup'] and len(received)==1
    assert received[0]['solve_seconds']==0
    assert received[0]['total_seconds']==result.total_seconds
    assert result.status==(S.TIMEOUT if isinstance(failure,a._BudgetExpired) else S.ERROR)


def test_measurement_hook_expired_before_build_and_unavailable():
    calls=[]
    result=solve_baseline(fixture(2),'cpsat',deadline=time.perf_counter()-1,
                          on_measurement_end=lambda end,t:calls.append(t))
    assert result.status==S.TIMEOUT and len(calls)==1 and calls[0]['solve_seconds']==0
    calls.clear()
    with patch.object(a,'prepare_backend',side_effect=ImportError('missing')):
        result=solve_baseline(fixture(2),'cpsat',on_measurement_end=lambda end,t:calls.append(t))
    assert result.status==S.UNAVAILABLE and calls==[dict(build_seconds=None,solve_seconds=None,total_seconds=None)]


@pytest.mark.parametrize('native_failure',[False,True])
def test_measurement_hook_callback_failure_cleanup_and_original_error(native_failure):
    events=[]
    def callback(end,t):
        events.append('END')
        raise RuntimeError('publisher broken')
    def call():
        if native_failure: raise RuntimeError('native broken')
    def run(p,method,clock,stack):
        stack.callback(events.append,'cleanup')
        clock.solve(lambda t: None,call)
        return a._Outcome('FEASIBLE',decode=lambda: ())
    with patch.object(a,'_run',run),patch.object(a,'check_solution',side_effect=AssertionError('must not validate')):
        result=solve_baseline(fixture(2),'cpsat',on_measurement_end=callback)
    assert events==['END','cleanup'] and result.status==S.ERROR
    assert 'publisher broken' in result.error
    if native_failure: assert 'native broken' in result.error


def test_measurement_hook_cpo_before_timer_join_even_on_callback_failure():
    from docplex.cp.solver import solver as module
    events=[]
    class FakeTimer:
        def __init__(self,*args): pass
        def start(self): pass
        def cancel(self): events.append('cancel')
        def join(self): events.append('join')
    class FakeCpo:
        def __init__(self,*args,**kwargs):
            self.context=SimpleNamespace(params=SimpleNamespace())
            self.agent=SimpleNamespace(_init_model_in_solver=lambda: None)
        def __enter__(self): return self
        def __exit__(self,*args): events.append('cleanup')
        def solve(self):
            return SimpleNamespace(get_solve_status=lambda:'Infeasible',get_stop_cause=lambda:'SearchHasNotBeenStopped',is_solution=lambda:False)
    def callback(end,t):
        events.append('END'); raise RuntimeError('publisher broken')
    with patch.object(module,'CpoSolver',FakeCpo),patch.object(a.threading,'Timer',FakeTimer):
        result=solve_baseline(fixture(2),'cpoptimizer',on_measurement_end=callback)
    assert events==['END','cancel','join','cleanup'] and result.status==S.ERROR


def test_measurement_hook_missing_import_callback_failure():
    calls=[]
    def callback(end,t):
        calls.append(t)
        raise RuntimeError('publisher broken')
    with patch.object(a,'prepare_backend',side_effect=ImportError('missing engine')):
        result=solve_baseline(fixture(2),'highs',on_measurement_end=callback)
    assert len(calls)==1 and result.status==S.ERROR and result.total_seconds is None
    assert 'publisher broken' in result.error and 'missing engine' in result.error

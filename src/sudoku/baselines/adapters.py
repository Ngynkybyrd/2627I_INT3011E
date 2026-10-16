"""Fresh baseline solves with shared deadline, strict decoding and validation."""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
import importlib
import math
import time
import threading

from sudoku.contracts import SolveResult, SolveStatus as S, ValidationResult
from sudoku.model import Puzzle
from sudoku.validation import check_solution
from .cp import build_cpsat, build_cpoptimizer
from .ilp import build_ilp

METHODS = ('cpsat', 'gurobi', 'cplex_mip', 'cpoptimizer', 'highs')


def prepare_backend(method: str) -> None:
    """Import optional dependencies before measurement; safe to call repeatedly."""
    if method not in METHODS:
        raise ValueError(f'Unknown baseline method: {method}')
    modules = {
        'cpsat': ('ortools.sat.python.cp_model',),
        'gurobi': ('numpy', 'scipy.sparse', 'gurobipy'),
        'cplex_mip': ('numpy', 'scipy.sparse', 'cplex'),
        'cpoptimizer': ('docplex.cp.model', 'docplex.cp.solver.solver',
                        'docplex.cp.solver.solver_local'),
        'highs': ('numpy', 'scipy.sparse', 'highspy'),
    }
    for module in modules[method]:
        importlib.import_module(module)


def _decode_mip(values, N: int):
    """Accept only near-binary values, then require one selected value per cell."""
    if len(values) != N**3:
        raise ValueError('MIP solution length differs from N^3')
    bits=[]
    for v in values:
        if not math.isfinite(v):
            raise ValueError('Nonfinite MIP value')
        if abs(v) <= 1e-6:
            bits.append(0)
        elif abs(v-1) <= 1e-6:
            bits.append(1)
        else:
            raise ValueError('MIP value is not within 1e-6 of binary')
    cells=[]
    for offset in range(0,N**3,N):
        selected=[i+1 for i,b in enumerate(bits[offset:offset+N]) if b]
        if len(selected)!=1:
            raise ValueError('MIP cell must select exactly one value')
        cells.append(selected[0])
    return tuple(tuple(cells[r*N:(r+1)*N]) for r in range(N))


@dataclass
class _Outcome:
    raw: str
    status: S = S.ERROR
    decode: object = None


class _BudgetExpired(Exception):
    pass


class _Clock:
    def __init__(self, cutoff, deadline, on_measurement_end=None):
        self.start=time.perf_counter()
        self.deadline=min(self.start+cutoff, deadline) if deadline is not None else self.start+cutoff
        self.build_end=None
        self.end=None
        self.native_limit=None
        self.on_measurement_end=on_measurement_end
        self.published=False
        self.callback_error=None

    def finish(self):
        """Freeze measurement and notify once, even when the callback fails."""
        if self.end is None:
            self.end=time.perf_counter()
        if self.published:
            return
        self.published=True
        if self.on_measurement_end is not None:
            try:
                self.on_measurement_end(self.end,self.timings())
            except Exception as exc:
                # Preserve a simultaneous native/build exception; report both
                # from _execute after resources have been scheduled for cleanup.
                self.callback_error=exc

    def remaining(self):
        value=self.deadline-time.perf_counter()
        if value<=0:
            raise _BudgetExpired('Deadline exhausted before solve')
        return value

    def solve(self, set_limit, call):
        self.native_limit=self.remaining()
        set_limit(self.native_limit)
        self.remaining()
        self.build_end=time.perf_counter()
        try:
            return call()
        finally:
            self.end=time.perf_counter()
            self.finish()

    def timings(self):
        end=self.end if self.end is not None else time.perf_counter()
        build_end=self.build_end if self.build_end is not None else end
        return dict(build_seconds=build_end-self.start,
                    solve_seconds=end-build_end,total_seconds=end-self.start)


def _run(puzzle, method, clock, stack):
    N=puzzle.N
    if method=='cpsat':
        from ortools.sat.python import cp_model as cp
        b=build_cpsat(puzzle)
        code=clock.solve(lambda t: setattr(b.solver.parameters,'max_time_in_seconds',t),
                         lambda: b.solver.solve(b.model))
        raw=b.solver.status_name(code)
        if code in (cp.OPTIMAL,cp.FEASIBLE):
            return _Outcome(raw,decode=lambda: tuple(tuple(int(b.solver.value(v)) for v in row) for row in b.variables))
        return _Outcome(raw,S.UNSAT if code==cp.INFEASIBLE else
                        S.TIMEOUT if code==cp.UNKNOWN and b.solver.wall_time>=clock.native_limit else S.ERROR)

    if method=='cpoptimizer':
        from docplex.cp.solver.solver import CpoSolver
        b=build_cpoptimizer(puzzle)
        solver=stack.enter_context(CpoSolver(b.model,execfile=str(b.executable),
                                             Workers=1,LogVerbosity='Quiet'))
        # DOcplex embeds TimeLimit in CPO. Preload is measured as build; a
        # cooperative deadline timer supplies the reduced budget after loading.
        # This pinned private hook needs integration review on DOcplex upgrades.
        solver.context.params.TimeLimit=clock.remaining()
        solver.agent._init_model_in_solver()
        expired=threading.Event()
        def abort():
            expired.set()
            try:
                solver.abort_search()
            except Exception:
                pass  # hard runner guard remains authoritative
        timer=threading.Timer(clock.remaining(),abort)
        timer.daemon=True
        timer.start()
        try:
            try:
                sol=clock.solve(lambda t: None,solver.solve)
            except Exception as exc:
                if expired.is_set() and clock.end is not None and clock.end>clock.deadline:
                    raise _BudgetExpired(f'Deadline abort: {exc}') from exc
                raise
        finally:
            clock.finish()
            timer.cancel()
            timer.join()
        raw=f'{sol.get_solve_status()}; stop={sol.get_stop_cause()}'
        if expired.is_set() and clock.end>clock.deadline:
            return _Outcome(raw,S.TIMEOUT)
        if sol.is_solution():
            return _Outcome(raw,decode=lambda: tuple(tuple(sol[v] for v in row) for row in b.variables))
        status=S.UNSAT if sol.get_solve_status()=='Infeasible' else (
            S.TIMEOUT if sol.get_stop_cause()=='SearchStoppedByLimit' and
            sol.get_solver_infos().get('SolveTime',0)>=solver.context.params.TimeLimit else S.ERROR)
        return _Outcome(raw,status)

    ilp=build_ilp(puzzle)
    clock.remaining()
    if method=='gurobi':
        import gurobipy as gp
        env=stack.enter_context(gp.Env(empty=True))
        env.setParam('OutputFlag',0); env.start()
        m=stack.enter_context(gp.Model(env=env))
        m.Params.Threads=1
        x=m.addMVar(ilp.variable_count,lb=ilp.lower_bounds,ub=ilp.upper_bounds,
                   obj=ilp.objective,vtype=gp.GRB.BINARY)
        m.addMConstr(ilp.matrix,x,'=',ilp.rhs); m.update()
        clock.solve(lambda t: setattr(m.Params,'TimeLimit',t),m.optimize)
        raw=str(m.Status)
        if m.SolCount>0:
            return _Outcome(raw,decode=lambda: _decode_mip(x.X,N))
        return _Outcome(raw,S.UNSAT if m.Status==gp.GRB.INFEASIBLE else
                        S.TIMEOUT if m.Status==gp.GRB.TIME_LIMIT else S.ERROR)

    if method=='cplex_mip':
        import cplex
        m=stack.enter_context(cplex.Cplex())
        for name in ('log','results','warning','error'):
            getattr(m,f'set_{name}_stream')(None)
        m.parameters.threads.set(1)
        m.variables.add(obj=ilp.objective.tolist(),lb=ilp.lower_bounds.tolist(),
                        ub=ilp.upper_bounds.tolist(),types='B'*ilp.variable_count)
        A=ilp.matrix
        rows=[cplex.SparsePair(A.indices[A.indptr[i]:A.indptr[i+1]].tolist(),
                               A.data[A.indptr[i]:A.indptr[i+1]].tolist()) for i in range(A.shape[0])]
        m.linear_constraints.add(lin_expr=rows,senses='E'*A.shape[0],rhs=ilp.rhs.tolist())
        clock.solve(m.parameters.timelimit.set,m.solve)
        code=m.solution.get_status(); raw=f'{code}: {m.solution.get_status_string()}'
        if m.solution.is_primal_feasible():
            return _Outcome(raw,decode=lambda: _decode_mip(m.solution.get_values(),N))
        return _Outcome(raw,S.UNSAT if code==m.solution.status.MIP_infeasible else
                        S.TIMEOUT if code in (107,108) else S.ERROR)

    import highspy as hs
    import numpy as np
    h=hs.Highs(); stack.callback(h.clear)
    def checked(status):
        if status==hs.HighsStatus.kError:
            raise RuntimeError('HiGHS API returned kError')
    checked(h.setOptionValue('output_flag',False))
    checked(h.setOptionValue('threads',1))
    if h.getOptionValue('threads')[1]!=1:
        raise RuntimeError('HiGHS threads setting was not accepted')
    lp=hs.HighsLp()
    lp.num_col_=ilp.variable_count; lp.num_row_=ilp.constraint_count
    lp.col_cost_=ilp.objective; lp.col_lower_=ilp.lower_bounds; lp.col_upper_=ilp.upper_bounds
    lp.row_lower_=ilp.rhs; lp.row_upper_=ilp.rhs
    lp.integrality_=[hs.HighsVarType.kInteger]*ilp.variable_count
    lp.a_matrix_.format_=hs.MatrixFormat.kRowwise
    lp.a_matrix_.start_=np.asarray(ilp.matrix.indptr,dtype=np.int32)
    lp.a_matrix_.index_=np.asarray(ilp.matrix.indices,dtype=np.int32)
    lp.a_matrix_.value_=ilp.matrix.data
    checked(h.passModel(lp))
    clock.solve(lambda t: checked(h.setOptionValue('time_limit',t)),lambda: checked(h.run()))
    code=h.getModelStatus(); raw=h.modelStatusToString(code)
    info=h.getInfo()
    if (h.getSolution().value_valid and
        info.primal_solution_status==hs.SolutionStatus.kSolutionStatusFeasible and
        math.isfinite(info.max_integrality_violation) and info.max_integrality_violation<=1e-6):
        return _Outcome(raw,decode=lambda: _decode_mip(h.getSolution().col_value,N))
    return _Outcome(raw,S.UNSAT if code==hs.HighsModelStatus.kInfeasible else
                    S.TIMEOUT if code==hs.HighsModelStatus.kTimeLimit else S.ERROR)


def _exception_status(exc):
    message=str(exc).lower()
    if any(s in message for s in ('size-limited','problem size limit','error  1016','2^1000')):
        return S.LICENSE_LIMIT
    if isinstance(exc,(ImportError,FileNotFoundError)) or any(s in message for s in (
        'no gurobi license','unable to open cplex','could not execute command',
        'license expired','no license found','failed to create process')):
        return S.UNAVAILABLE
    return S.ERROR


def solve_baseline(puzzle: Puzzle, method: str, *, cutoff_seconds: float = 10.0,
                   deadline: float | None = None, on_measurement_end=None) -> SolveResult:
    """Solve within cooperative limits; runner must enforce hard process deadline.

    on_measurement_end(end_timestamp, timings) is called once before decoding,
    checking, timer join and cleanup. Callback errors produce ERROR. Missing
    imports publish unknown timings because measured work never began.
    """
    if method not in METHODS:
        raise ValueError(f'Unknown baseline method: {method}')
    if isinstance(cutoff_seconds,bool) or not isinstance(cutoff_seconds,(int,float)) or not math.isfinite(cutoff_seconds) or cutoff_seconds<=0:
        raise ValueError('cutoff_seconds must be finite and positive')
    if deadline is not None and (isinstance(deadline,bool) or not isinstance(deadline,(int,float)) or not math.isfinite(deadline)):
        raise ValueError('deadline must be a finite perf_counter timestamp')
    if not isinstance(puzzle,Puzzle):
        raise TypeError('puzzle must be a validated Puzzle')
    try:
        prepare_backend(method)
    except (ImportError,OSError) as exc:
        if on_measurement_end is not None:
            try:
                on_measurement_end(time.perf_counter(),dict(
                    build_seconds=None,solve_seconds=None,total_seconds=None))
            except Exception as callback_exc:
                return SolveResult(S.ERROR,method,raw_status=type(exc).__name__,
                                   error=f'Measurement-end callback failed: {callback_exc}; backend import failed: {exc}')
        return SolveResult(S.UNAVAILABLE,method,error=str(exc),raw_status=type(exc).__name__)
    clock=_Clock(cutoff_seconds,deadline,on_measurement_end)
    result=None
    try:
        with ExitStack() as stack:
            result=_execute(puzzle,method,clock,stack)
        return result
    except Exception as exc:
        timings=clock.timings() if result is None else dict(
            build_seconds=result.build_seconds,solve_seconds=result.solve_seconds,total_seconds=result.total_seconds)
        return SolveResult(S.ERROR,method,raw_status=result.raw_status if result else type(exc).__name__,
                           error=f'Cleanup failed: {exc}'+(f'; prior error: {result.error}' if result and result.error else ''),**timings)


def _execute(puzzle,method,clock,stack):
    try:
        clock.remaining()
        outcome=_run(puzzle,method,clock,stack)
    except _BudgetExpired as exc:
        clock.finish()
        if clock.callback_error is not None:
            return _callback_failure(method,clock,'DEADLINE_EXHAUSTED',exc)
        return SolveResult(S.TIMEOUT,method,raw_status='DEADLINE_EXHAUSTED',error=str(exc),**clock.timings())
    except Exception as exc:
        clock.finish()
        if clock.callback_error is not None:
            return _callback_failure(method,clock,f'{type(exc).__name__}: {exc}',exc)
        return SolveResult(_exception_status(exc),method,raw_status=f'{type(exc).__name__}: {exc}',error=str(exc),**clock.timings())
    clock.finish()
    if clock.callback_error is not None:
        return _callback_failure(method,clock,outcome.raw)
    timings=clock.timings()
    if clock.end>clock.deadline:
        return SolveResult(S.TIMEOUT,method,raw_status=outcome.raw,**timings)
    if outcome.decode is None:
        return SolveResult(outcome.status,method,raw_status=outcome.raw,**timings)
    try:
        solution=outcome.decode()
        validation=check_solution(puzzle,solution)
    except Exception as exc:
        return SolveResult(S.ERROR,method,raw_status=outcome.raw,error=str(exc),
                           validation=ValidationResult(False,str(exc)),**timings)
    if not validation.valid:
        return SolveResult(S.ERROR,method,raw_status=outcome.raw,validation=validation,
                           error=validation.message,**timings)
    return SolveResult(S.SAT,method,raw_status=outcome.raw,solution=solution,
                       validation=validation,**timings)


def _callback_failure(method,clock,raw,original=None):
    error=f'Measurement-end callback failed: {clock.callback_error}'
    if original is not None:
        error+=f'; original failure: {original}'
    return SolveResult(S.ERROR,method,raw_status=raw,error=error,**clock.timings())

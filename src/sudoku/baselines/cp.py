"""Integer/AllDifferent models with one worker; solving belongs to adapters."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sudoku.model import Puzzle, iter_clues

if TYPE_CHECKING:
    from docplex.cp.expression import CpoIntVar
    from docplex.cp.model import CpoModel
    from ortools.sat.python.cp_model import CpModel, CpSolver, IntVar


def _cell_groups(n: int):
    """Rows, columns, then blocks; one tuple of (r,c) per AllDifferent."""
    N = n * n
    for r in range(N):
        yield tuple((r, c) for c in range(N))
    for c in range(N):
        yield tuple((r, c) for r in range(N))
    for br in range(0, N, n):
        for bc in range(0, N, n):
            yield tuple((br + dr, bc + dc) for dr in range(n) for dc in range(n))


@dataclass(frozen=True, slots=True)
class CpSatBuild:
    model: CpModel
    variables: tuple[tuple[IntVar, ...], ...]
    solver: CpSolver


def build_cpsat(puzzle: Puzzle) -> CpSatBuild:
    """Build N² integer variables, 3N AllDifferent and one equality per clue.

    Imports are lazy; callers should import the backend before starting measured
    build time. No deadline is set here: adapters must supply remaining time.
    """
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    N = puzzle.N
    variables = tuple(tuple(model.new_int_var(1, N, f"x_{r}_{c}")
                            for c in range(N)) for r in range(N))
    for group in _cell_groups(puzzle.n):
        model.add_all_different([variables[r][c] for r, c in group])
    for r, c, v in iter_clues(puzzle):
        model.add(variables[r][c] == v)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    return CpSatBuild(model, variables, solver)


@dataclass(frozen=True, slots=True)
class CpOptimizerBuild:
    model: CpoModel
    variables: tuple[tuple[CpoIntVar, ...], ...]
    executable: Path


def build_cpoptimizer(puzzle: Puzzle, *, executable: str | Path | None = None) -> CpOptimizerBuild:
    """Build the equivalent CP model and resolve the active venv's executable.

    Does not spawn the executable or check its license. A missing runtime raises
    FileNotFoundError for the future adapter to map to UNAVAILABLE. Future solve
    must pass execfile=str(build.executable) and the remaining TimeLimit.
    """
    from docplex.cp.model import CpoModel

    runtime = (Path(executable) if executable is not None else
               Path(sys.prefix) / "Scripts" / "cpoptimizer.exe").resolve()
    if not runtime.is_file():
        raise FileNotFoundError(f"CP Optimizer executable not found: {runtime}")
    model = CpoModel(name="sudoku")
    N = puzzle.N
    variables = tuple(tuple(model.integer_var(1, N, name=f"x_{r}_{c}")
                            for c in range(N)) for r in range(N))
    for group in _cell_groups(puzzle.n):
        model.add(model.all_diff([variables[r][c] for r, c in group]))
    for r, c, v in iter_clues(puzzle):
        model.add(variables[r][c] == v)
    model.set_parameters(Workers=1)
    return CpOptimizerBuild(model, variables, runtime)

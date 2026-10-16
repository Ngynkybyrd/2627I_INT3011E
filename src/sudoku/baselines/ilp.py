"""Engine-independent sparse binary feasibility model, without preprocessing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sudoku.model import Puzzle, iter_clues, iter_exo_groups, variable_id

if TYPE_CHECKING:
    import numpy as np
    from scipy.sparse import csr_matrix


@dataclass(frozen=True, slots=True)
class ILPModel:
    """Minimize objective @ y, subject to matrix @ y == rhs and bounds.

    All variables are integer with bounds [0,1], hence binary. Column index is
    variable_id(n,r,c,v)-1. Rows retain all EXO groups then row-major clues.
    Arrays/matrix are mutable for backend interoperability; treat as read-only.
    This is not CNFStats and must not populate SolveResult.stats.
    """
    matrix: csr_matrix
    rhs: np.ndarray
    objective: np.ndarray
    lower_bounds: np.ndarray
    upper_bounds: np.ndarray
    integrality: np.ndarray
    n: int
    exo_groups: int
    clues: int

    @property
    def variable_count(self) -> int:
        return self.matrix.shape[1]

    @property
    def constraint_count(self) -> int:
        return self.matrix.shape[0]


def build_ilp(puzzle: Puzzle) -> ILPModel:
    """Build N³ binaries, 4N²+g equalities, 4N³+g nonzeros, zero objective.

    No solver imports or backend-specific simplification; contradictory clues
    are retained. Adapters should import numpy/scipy before measured build.
    """
    import numpy as np
    from scipy.sparse import csr_matrix

    indices = []
    indptr = [0]
    for group in iter_exo_groups(puzzle.n):
        indices.extend(v - 1 for v in group)
        indptr.append(len(indices))
    for r, c, v in iter_clues(puzzle):
        indices.append(variable_id(puzzle.n, r, c, v) - 1)
        indptr.append(len(indices))
    N = puzzle.N
    variables = N ** 3
    rows = 4 * N * N + puzzle.clue_count
    matrix = csr_matrix((np.ones(len(indices), dtype=np.float64),
                         np.asarray(indices, dtype=np.int64),
                         np.asarray(indptr, dtype=np.int64)), shape=(rows, variables))
    return ILPModel(matrix, np.ones(rows), np.zeros(variables),
                    np.zeros(variables), np.ones(variables),
                    np.ones(variables, dtype=np.uint8), puzzle.n,
                    4 * N * N, puzzle.clue_count)

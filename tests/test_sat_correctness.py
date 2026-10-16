import itertools

import pytest
from pysat.solvers import Glucose3

from sudoku.decoding import decode_model
from sudoku.model import Puzzle, iter_exo_groups, variable_coordinates, variable_id
from sudoku.sat import ENCODINGS, build_cnf, encode_amo
from sudoku.validation import check_solution
from tests.oracle_4x4 import solutions_4x4
from tests.test_validation import FULL


BLANK = ((0, 0, 0, 0),) * 4
# No direct duplicate clues: the top-left block needs 3 and 4 in row 1,
# but that row already has a 3 outside the block.
NONTRIVIAL_UNSAT = ((1, 2, 0, 0), (0, 0, 3, 0), (0, 0, 0, 0), (0, 0, 0, 0))
CASES = [
    ("complete", FULL, 1),
    ("single_hole", ((0, 2, 3, 4),) + FULL[1:], 1),
    ("blank_multiple", BLANK, 2),
    ("sparse_multiple", ((1, 0, 0, 0),) + BLANK[1:], 2),
    ("row_conflict", ((1, 0, 0, 1),) + BLANK[1:], 0),
    ("column_conflict", ((1, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0), (1, 0, 0, 0)), 0),
    ("block_conflict", ((1, 0, 0, 0), (0, 1, 0, 0)) + BLANK[2:], 0),
    ("nontrivial_unsat", NONTRIVIAL_UNSAT, 0),
]


@pytest.mark.parametrize("name,grid,expected_count", CASES, ids=[case[0] for case in CASES])
def test_oracle_known_cases(name, grid, expected_count):
    before = tuple(tuple(row) for row in grid)
    solutions = solutions_4x4(grid)
    assert len(solutions) == expected_count
    assert grid == before
    assert len(set(solutions)) == len(solutions)
    for solution in solutions:
        assert check_solution(Puzzle(2, grid), solution).valid


def test_nontrivial_unsat_has_no_direct_clue_conflict():
    units = list(NONTRIVIAL_UNSAT)
    units += [tuple(row[c] for row in NONTRIVIAL_UNSAT) for c in range(4)]
    units += [tuple(NONTRIVIAL_UNSAT[r][c] for r in range(br, br + 2)
                    for c in range(bc, bc + 2)) for br in (0, 2) for bc in (0, 2)]
    for unit in units:
        clues = [v for v in unit if v]
        assert len(clues) == len(set(clues))
    assert solutions_4x4(NONTRIVIAL_UNSAT) == []


@pytest.mark.parametrize("encoding", ENCODINGS)
@pytest.mark.parametrize("name,grid,expected_count", CASES, ids=[case[0] for case in CASES])
def test_cnf_agrees_with_oracle_and_solution_passes_checker(encoding, name, grid, expected_count):
    puzzle = Puzzle(2, grid)
    expected = bool(solutions_4x4(grid, limit=1))
    assert expected == bool(expected_count)
    cnf = build_cnf(puzzle, encoding)
    with Glucose3(bootstrap_with=cnf.clauses) as solver:
        assert solver.solve() == expected
        if expected:
            solution = decode_model(puzzle.n, solver.get_model())
            validation = check_solution(puzzle, solution)
            assert validation.valid, validation.message
            # Do not compare to the oracle's first solution: many are allowed.


ASSIGNMENTS = [(encoding, size, bits) for encoding in ENCODINGS for size in (3, 4, 5)
               for bits in itertools.product((False, True), repeat=size)]


@pytest.mark.parametrize("encoding,size,bits", ASSIGNMENTS)
def test_amo_exo_truth_tables_with_existential_auxiliaries(encoding, size, bits):
    inputs = [2 * i + 1 for i in range(size)]
    clauses, top = encode_amo(inputs, encoding, top_id=100)
    assert top >= 100
    aux = {abs(lit) for clause in clauses for lit in clause} - set(inputs)
    assert all(100 < variable <= top for variable in aux)
    assumptions = [literal if bit else -literal for literal, bit in zip(inputs, bits)]
    assert {abs(lit) for lit in assumptions} == set(inputs)
    assert not (set(map(abs, assumptions)) & aux)
    with Glucose3(bootstrap_with=clauses) as solver:
        assert solver.solve(assumptions=assumptions) == (sum(bits) <= 1)
    with Glucose3(bootstrap_with=clauses + [inputs]) as solver:
        assert solver.solve(assumptions=assumptions) == (sum(bits) == 1)


@pytest.mark.parametrize("n", (2, 3, 4, 5))
def test_mapping_and_all_groups_including_block_boundaries(n):
    N = n * n
    for r in range(N):
        for c in range(N):
            for v in range(1, N + 1):
                variable = variable_id(n, r, c, v)
                assert variable == 1 + (r * N + c) * N + v - 1
                assert variable_coordinates(n, variable) == (r, c, v)
    groups = list(iter_exo_groups(n))
    assert len(groups) == 4 * N * N
    occurrences = [0] * (N**3 + 1)
    for index, group in enumerate(groups):
        assert len(group) == len(set(group)) == N
        coordinates = [variable_coordinates(n, variable) for variable in group]
        family, offset = divmod(index, N * N)
        if family == 0:
            r, c = divmod(offset, N)
            expected = [(r, c, v) for v in range(1, N + 1)]
        elif family == 1:
            r, value = divmod(offset, N)
            expected = [(r, c, value + 1) for c in range(N)]
        elif family == 2:
            c, value = divmod(offset, N)
            expected = [(r, c, value + 1) for r in range(N)]
        else:
            block, value = divmod(offset, N)
            br, bc = divmod(block, n)
            expected = [(r, c, value + 1) for r in range(N) for c in range(N)
                        if r // n == br and c // n == bc]
        assert coordinates == expected
        for variable in group:
            occurrences[variable] += 1
    assert set(occurrences[1:]) == {4}

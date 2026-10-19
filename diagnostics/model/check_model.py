"""Focused model/CNF checks; does not replace SAT03's independent test suite.

Run with the project's Python. Output stays beside this script; no benchmark
timings or production SAT success claims are generated.
"""

from __future__ import annotations

import gc
import itertools
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

import pysat
from pysat.card import CardEnc, EncType
from pysat.solvers import Glucose3

from sudoku.contracts import InvalidInputError, SolveResult, SolveStatus
from sudoku.model import (
    Puzzle,
    iter_clues,
    iter_exo_groups,
    load_puzzle,
    parse_json,
    parse_puzzle,
    variable_coordinates,
    variable_id,
)
from sudoku.sat import ENCODINGS, build_cnf, encode_amo


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_invalid(operation) -> None:
    try:
        operation()
    except InvalidInputError as exc:
        require(exc.status is SolveStatus.INVALID_INPUT, "wrong invalid input status")
    else:
        raise AssertionError("invalid input was accepted")


def blank(n: int) -> list[list[int]]:
    return [[0] * (n * n) for _ in range(n * n)]


def check_input() -> int:
    good = {"n": 2, "grid": blank(2), "id": "ignored metadata"}
    puzzle = parse_puzzle(good)
    require(puzzle.grid == tuple((0, 0, 0, 0) for _ in range(4)), "immutable grid")
    good["grid"][0][0] = 4
    require(puzzle.grid[0][0] == 0, "input alias leaked into puzzle")
    require(parse_json(json.dumps(good)).clue_count == 1, "clue counting")
    invalid = [None, [], {}, {"n": 2}, {"grid": blank(2)}]
    invalid.extend({"n": n, "grid": blank(2)} for n in [True, False, 1, 0, -2, 2.0, "2", None])
    invalid.extend({"n": 2, "grid": grid} for grid in [None, {}, [], blank(2)[:-1]])
    wrong_row = blank(2)
    wrong_row[0].pop()
    invalid.append({"n": 2, "grid": wrong_row})
    for value in [True, False, -1, 5, 1.0, "1", None]:
        grid = blank(2)
        grid[0][0] = value
        invalid.append({"n": 2, "grid": grid})
    for data in invalid:
        expect_invalid(lambda data=data: parse_puzzle(data))
    for text in ["{", "null", "[]", "NaN", "", "{\"n\":2,\"grid\":[]}"]:
        expect_invalid(lambda text=text: parse_json(text))
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
        path = Path(directory) / "đề có dấu cách.json"
        path.write_text(json.dumps(good), encoding="utf-8-sig")
        require(load_puzzle(path).clue_count == 1, "UTF-8/BOM loading")
        path.write_bytes(b"\xff")
        expect_invalid(lambda: load_puzzle(path))
        expect_invalid(lambda: load_puzzle(Path(directory) / "missing.json"))
    try:
        SolveResult(status=SolveStatus.SAT, method="sat")
    except ValueError:
        pass
    else:
        raise AssertionError("SAT accepted without independent validation")
    exported = SolveResult(status=SolveStatus.UNSAT, method="sat").to_dict()
    require(json.loads(json.dumps(exported))["status"] == "UNSAT", "result JSON contract")
    return len(invalid) + 6 + 2


def check_mapping_and_groups(n: int) -> dict[str, int]:
    N = n * n
    for variable in range(1, N**3 + 1):
        r, c, v = variable_coordinates(n, variable)
        expected_cell, expected_v = divmod(variable - 1, N)
        require((r, c, v) == (expected_cell // N, expected_cell % N, expected_v + 1), "mapping inverse")
        require(variable_id(n, r, c, v) == variable, "mapping round trip")
    groups = list(iter_exo_groups(n))
    require(len(groups) == 4 * N * N, "group count")
    occurrences = [0] * (N**3 + 1)
    for index, group in enumerate(groups):
        require(len(group) == N and len(set(group)) == N, "group length/duplicates")
        coordinates = [variable_coordinates(n, variable) for variable in group]
        family, offset = divmod(index, N * N)
        if family == 0:
            r, c = divmod(offset, N)
            expected = [(r, c, v) for v in range(1, N + 1)]
        elif family == 1:
            r, value_offset = divmod(offset, N)
            expected = [(r, c, value_offset + 1) for c in range(N)]
        elif family == 2:
            c, value_offset = divmod(offset, N)
            expected = [(r, c, value_offset + 1) for r in range(N)]
        else:
            block, value_offset = divmod(offset, N)
            block_r, block_c = divmod(block, n)
            # Scan the whole board independently to identify this block.
            expected = [(r, c, value_offset + 1) for r in range(N) for c in range(N)
                        if r // n == block_r and c // n == block_c]
        require(coordinates == expected, f"EXO family/order {family}")
        for variable in group:
            occurrences[variable] += 1
    require(set(occurrences[1:]) == {4}, "each primary must belong to four groups")
    for variable in [0, -1, N**3 + 1, True, 1.0]:
        try:
            variable_coordinates(n, variable)
        except ValueError:
            pass
        else:
            raise AssertionError("out-of-domain ID accepted")
    return {"n": n, "N": N, "primary_ids_checked": N**3, "groups_checked": len(groups)}


def check_amo() -> tuple[list[dict], int]:
    counts = []
    assignments = 0
    for encoding in ENCODINGS:
        for length in [0, 1, 2, 3, 4, 5, 9, 16, 25]:
            inputs = [3 * i + 1 for i in range(length)]
            clauses, top = encode_amo(inputs, encoding, top_id=100)
            require(top >= 100, "allocator went backwards")
            auxiliary = {abs(lit) for clause in clauses for lit in clause} - set(inputs)
            require(all(100 < variable <= top for variable in auxiliary), "auxiliary collision")
            require(len(auxiliary) == top - 100, "unexpected allocator holes")
            library_type = {"pairwise": EncType.pairwise, "seqcounter": EncType.seqcounter,
                            "bitwise": EncType.bitwise}[encoding]
            library = CardEnc.atmost(inputs, bound=1, top_id=100, encoding=library_type)
            require(len(clauses) == len(library.clauses), "library clause count mismatch")
            require(top == max(100, library.nv), "library variable count mismatch")
            counts.append({"encoding": encoding, "length": length,
                           "auxiliary_variables": top - 100, "amo_clauses": len(clauses)})
            if 2 <= length <= 5:
                with Glucose3(bootstrap_with=clauses) as amo_solver, Glucose3(
                    bootstrap_with=clauses + [inputs]
                ) as exo_solver:
                    for bits in itertools.product([False, True], repeat=length):
                        assumptions = [lit if bit else -lit for lit, bit in zip(inputs, bits)]
                        # Auxiliary variables are intentionally NEVER assigned.
                        require(amo_solver.solve(assumptions=assumptions) == (sum(bits) <= 1), "AMO iff failed")
                        require(exo_solver.solve(assumptions=assumptions) == (sum(bits) == 1), "EXO iff failed")
                        assignments += 2
        allocated = set()
        top = 64
        for group in iter_exo_groups(2):
            old_top = top
            clauses, top = encode_amo(group, encoding, top_id=old_top)
            auxiliary = {abs(lit) for clause in clauses for lit in clause} - set(group)
            require(not (auxiliary & allocated), "reused auxiliary between groups")
            require(all(old_top < variable <= top for variable in auxiliary), "auxiliary crosses reservation")
            allocated.update(auxiliary)
    return counts, assignments


def check_cnf(n: int, encoding: str) -> dict:
    N = n * n
    grid = blank(n)
    grid[0][0] = 1
    grid[N - 1][N - 1] = N
    puzzle = Puzzle(n, grid)
    built = build_cnf(puzzle, encoding)
    require(built.stats.primary_variables == N**3, "primary count")
    require(built.stats.exo_groups == 4 * N * N and built.stats.clues == 2, "group/clue stats")
    require(built.stats.clauses == len(built.clauses), "clause count")
    require(built.stats.total_variables == max(abs(lit) for clause in built.clauses for lit in clause), "top count")
    require(built.stats.auxiliary_variables == built.stats.total_variables - N**3, "aux count")
    cursor = 0
    top = N**3
    for group in iter_exo_groups(n):
        require(built.clauses[cursor] == list(group), "ALO/order differs")
        amo, top = encode_amo(group, encoding, top_id=top)
        require(built.clauses[cursor + 1:cursor + 1 + len(amo)] == amo, "AMO/order differs")
        cursor += 1 + len(amo)
    expected_clues = [[variable_id(n, r, c, v)] for r, c, v in iter_clues(puzzle)]
    require(built.clauses[cursor:] == expected_clues, "clue order/units")
    if encoding == "pairwise":
        require(built.stats.auxiliary_variables == 0, "pairwise auxiliary")
        require(built.stats.clauses == 4 * N * N * (1 + N * (N - 1) // 2) + 2, "pairwise formula")
    result = {"n": n, "N": N, "encoding": encoding, **asdict(built.stats)}
    del built
    gc.collect()
    return result


def check_small_cnf_logic() -> list[dict]:
    complete = [[1, 2, 3, 4], [3, 4, 1, 2], [2, 1, 4, 3], [4, 3, 2, 1]]
    cases = [("blank", blank(2), True), ("complete", complete, True)]
    for name, first, second in [
        ("row_conflict", (0, 0), (0, 3)),
        ("column_conflict", (0, 0), (3, 0)),
        ("block_conflict", (0, 0), (1, 1)),
    ]:
        grid = blank(2)
        grid[first[0]][first[1]] = grid[second[0]][second[1]] = 1
        cases.append((name, grid, False))
    outcomes = []
    for encoding in ENCODINGS:
        for name, grid, expected in cases:
            # Contradictions must pass parsing and be refuted by CNF solving.
            built = build_cnf(parse_puzzle({"n": 2, "grid": grid}), encoding)
            with Glucose3(bootstrap_with=built.clauses) as solver:
                actual = solver.solve()
            require(actual == expected, f"CNF logic failed: {encoding}/{name}")
            outcomes.append({"encoding": encoding, "case": name, "satisfiable": actual})
    return outcomes


def main() -> None:
    report = {"python": sys.version.split()[0], "python_sat": pysat.__version__}
    report["invalid_input_checks"] = check_input()
    report["mapping_groups"] = [check_mapping_and_groups(n) for n in [2, 3, 4, 5]]
    report["amo_counts"], report["amo_exo_assignment_checks"] = check_amo()
    report["cnf_counts"] = [check_cnf(n, encoding) for n in [2, 3, 4, 5] for encoding in ENCODINGS]
    report["small_cnf_logic"] = check_small_cnf_logic()
    report["result"] = "PASS"
    destination = Path(__file__).with_name("results.json")
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {report['invalid_input_checks']} invalid-input checks; "
          f"{report['amo_exo_assignment_checks']} AMO/EXO assignments; "
          f"{len(report['cnf_counts'])} CNF builds; "
          f"{len(report['small_cnf_logic'])} 4x4 logic cases. Evidence: {destination}")


if __name__ == "__main__":
    main()

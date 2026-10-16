"""Command-line entry point for solving one Sudoku puzzle."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Sequence, TextIO

from sudoku.baselines import METHODS as BASELINE_METHODS, solve_baseline
from sudoku.contracts import InvalidInputError, SolveResult, SolveStatus
from sudoku.model import load_puzzle
from sudoku.sat import ENCODINGS, solve_sat

METHODS = ("sat", *BASELINE_METHODS)


def _positive_finite_float(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("must be finite and greater than zero")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m sudoku",
        description="Solve one generalized Sudoku puzzle from a UTF-8 JSON file.",
    )
    parser.add_argument("puzzle", type=Path, help="JSON file containing n and grid")
    parser.add_argument("--method", choices=METHODS, default="sat",
                        help="solver method (default: sat)")
    parser.add_argument("--encoding", choices=ENCODINGS,
                        help="SAT AMO encoding (default for SAT: pairwise)")
    parser.add_argument("--cutoff", type=_positive_finite_float, default=10.0,
                        metavar="SECONDS", help="cooperative solver cutoff (default: 10)")
    parser.add_argument("--json-output", type=Path, metavar="PATH",
                        help="also save the JSON result to PATH; JSON is always written to stdout")
    return parser


def _render_grid(grid: Sequence[Sequence[int]], n: int) -> str:
    """Render a grid with block separators and enough width for two-digit values."""
    N = n * n
    width = max(2, len(str(N)))
    chunks: list[str] = []
    for row_index, row in enumerate(grid):
        blocks = [
            " ".join(str(value).rjust(width) for value in row[start:start + n])
            for start in range(0, N, n)
        ]
        chunks.append(" | ".join(blocks))
        if (row_index + 1) % n == 0 and row_index + 1 < N:
            chunks.append("-+-".join("-" * len(block) for block in blocks))
    return "\n".join(chunks)


def _render_human(result: SolveResult, n: int | None) -> str:
    lines = [f"Status: {result.status.value}", f"Method: {result.method}"]
    if result.encoding is not None:
        lines.append(f"Encoding: {result.encoding}")
    if result.solution is not None and n is not None:
        lines.extend(("Solution:", _render_grid(result.solution, n)))
    for key in ("build_seconds", "solve_seconds", "total_seconds"):
        value = getattr(result, key)
        lines.append(f"{key}: {value:.6f}" if value is not None else f"{key}: unavailable")
    if result.raw_status:
        lines.append(f"Raw status: {result.raw_status}")
    if result.error:
        lines.append(f"Error: {result.error}")
    return "\n".join(lines)


def _emit_result(result: SolveResult, n: int | None, json_output: Path | None,
                 *, stdout: TextIO, stderr: TextIO) -> None:
    """Keep stdout machine-readable JSON and send the human table to stderr."""
    payload = json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
    if json_output is not None:
        try:
            json_output.write_text(payload, encoding="utf-8")
        except OSError as exc:
            print(f"Cannot write JSON result to {json_output}: {exc}", file=stderr)
    print(_render_human(result, n), file=stderr)
    stdout.write(payload)


def _exit_code(status: SolveStatus) -> int:
    if status is SolveStatus.SAT:
        return 0
    if status is SolveStatus.INVALID_INPUT:
        return 2
    return 1


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None,
         stderr: TextIO | None = None) -> int:
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.method != "sat" and args.encoding is not None:
        parser.error("--encoding applies only when --method=sat")

    encoding = None
    if args.method == "sat":
        encoding = args.encoding if args.encoding is not None else "pairwise"
    puzzle = None
    try:
        puzzle = load_puzzle(args.puzzle)
    except InvalidInputError as exc:
        result = SolveResult(
            status=SolveStatus.INVALID_INPUT,
            method=args.method,
            encoding=encoding,
            error=str(exc),
        )
        _emit_result(result, None, args.json_output, stdout=stdout, stderr=stderr)
        return _exit_code(result.status)

    try:
        if args.method == "sat":
            result = solve_sat(puzzle, encoding, cutoff_seconds=args.cutoff)
        else:
            result = solve_baseline(puzzle, args.method, cutoff_seconds=args.cutoff)
    except Exception as exc:
        # A backend/API failure should be reported as a result, not a traceback.
        result = SolveResult(
            status=SolveStatus.ERROR,
            method=args.method,
            encoding=encoding,
            raw_status=type(exc).__name__,
            error=f"{type(exc).__name__}: {exc}",
        )
    _emit_result(result, puzzle.n, args.json_output, stdout=stdout, stderr=stderr)
    return _exit_code(result.status)


if __name__ == "__main__":  # pragma: no cover - exercised by python -m sudoku
    raise SystemExit(main())

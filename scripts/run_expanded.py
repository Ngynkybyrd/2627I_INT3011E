"""CLI for preparing, running, inspecting, resuming, and exporting expanded runs.

The runner API is imported only after argument parsing, so ``--help`` and
syntax diagnostics work while ``sudoku.expanded_runner`` is being developed.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import importlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class CliRuntimeError(RuntimeError):
    """The expanded runner API cannot be loaded or returned an invalid value."""


def _iso8601(raw: str) -> str:
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "must be an ISO8601 date/time with a UTC offset, e.g. 2026-10-19T22:30:00+07:00"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("must include a UTC offset")
    return raw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_expanded.py",
        description="Operate versioned expanded Sudoku experiments through the runner API.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="validate inputs and prepare a new experiment")
    prepare.add_argument("--dataset", type=Path, required=True)
    prepare.add_argument("--experiment", type=Path, required=True)
    prepare.add_argument("--config", type=Path, required=True)
    prepare.add_argument("--matrix", type=Path, required=True)
    prepare.add_argument("--phase", choices=("main", "pilot"), required=True)

    for command in ("pilot", "run"):
        run = commands.add_parser(command, help=f"execute the {command} phase")
        run.add_argument("--experiment", type=Path, required=True)
        run.add_argument("--stop-starting-at", type=_iso8601, metavar="ISO8601")

    status = commands.add_parser("status", help="show read-only experiment progress")
    status.add_argument("--experiment", type=Path, required=True)
    status.add_argument("--json", action="store_true", help="write the original progress dict as JSON")

    resume = commands.add_parser("resume", help="verify and resume an interrupted experiment")
    resume.add_argument("--experiment", type=Path, required=True)
    resume.add_argument("--reason", required=True)
    resume.add_argument("--stop-starting-at", type=_iso8601, required=True, metavar="ISO8601")

    export = commands.add_parser("export", help="export a consistent SQLite snapshot")
    export.add_argument("--experiment", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--complete-blocks", action="store_true",
                        help="select only QA-complete main blocks")
    return parser


def _load_api() -> Any:
    try:
        api = importlib.import_module("sudoku.expanded_runner")
    except (ImportError, OSError) as exc:
        raise CliRuntimeError(f"expanded runner API is unavailable: {exc}") from None
    required = (
        "ExpandedError", "prepare_expanded", "pilot_expanded", "run_expanded",
        "expanded_status", "resume_expanded", "export_expanded",
    )
    missing = [name for name in required if not hasattr(api, name)]
    if missing:
        raise CliRuntimeError("expanded runner API is missing: " + ", ".join(missing))
    return api


def _invoke(api: Any, args: argparse.Namespace) -> dict[str, object]:
    if args.command == "prepare":
        result = api.prepare_expanded(
            args.dataset, args.experiment, args.config, args.matrix, phase=args.phase,
        )
    elif args.command == "pilot":
        result = api.pilot_expanded(
            args.experiment, stop_starting_at=args.stop_starting_at,
        )
    elif args.command == "run":
        result = api.run_expanded(
            args.experiment, stop_starting_at=args.stop_starting_at,
        )
    elif args.command == "status":
        result = api.expanded_status(args.experiment)
    elif args.command == "resume":
        result = api.resume_expanded(
            args.experiment,
            reason=args.reason,
            stop_starting_at=args.stop_starting_at,
        )
    elif args.command == "export":
        result = api.export_expanded(
            args.experiment, args.output, complete_blocks=args.complete_blocks,
        )
    else:  # pragma: no cover - argparse constrains command values
        raise CliRuntimeError(f"unsupported command: {args.command}")

    if not isinstance(result, dict):
        raise CliRuntimeError(f"{args.command} API must return a JSON-compatible dict")
    try:
        json.dumps(result, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise CliRuntimeError(f"{args.command} API returned a non-JSON-compatible dict: {exc}") from None
    return result


def _print_status(result: dict[str, object]) -> None:
    for key, value in result.items():
        rendered = json.dumps(value, ensure_ascii=False, allow_nan=False)
        print(f"{key}: {rendered}")


def _print_result(command: str, result: dict[str, object], *, as_json: bool = False) -> None:
    if command == "status" and not as_json:
        _print_status(result)
        return
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


def _exit_code(command: str, result: dict[str, object]) -> int:
    if command not in ("pilot", "run", "resume"):
        return 0
    api_exit = result.get("exit_code")
    if type(api_exit) is int:
        return api_exit if api_exit in (0, 4, 5) else 5
    state = result.get("state")
    if state == "PAUSED":
        return 4
    if state in ("COMPLETE", "COMPLETED"):
        return 0
    # A missing or unfamiliar execution state must never look successful.
    return 5


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        api = _load_api()
        result = _invoke(api, args)
    except Exception as exc:
        expanded_error = getattr(api if "api" in locals() else None, "ExpandedError", None)
        if expanded_error is not None and isinstance(exc, expanded_error):
            code = getattr(exc, "exit_code", 2)
            if type(code) is not int or code not in (2, 3, 5):
                code = 5
            print(str(exc), file=sys.stderr)
            return code
        if isinstance(exc, CliRuntimeError):
            print(str(exc), file=sys.stderr)
            return 5
        print(f"expanded command failed: {exc}", file=sys.stderr)
        return 5

    _print_result(args.command, result, as_json=getattr(args, "json", False))
    return _exit_code(args.command, result)


if __name__ == "__main__":  # pragma: no cover - covered by script smoke checks
    raise SystemExit(main())

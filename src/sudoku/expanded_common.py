"""Schema2 shared utilities; deliberately independent of v1 schema validation."""
from __future__ import annotations
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import math
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STOP = "2026-10-19T22:30:00+07:00"
CONFIGURATIONS = ("sat:pairwise", "sat:seqcounter", "sat:bitwise", "cpsat", "highs", "gurobi", "cplex_mip", "cpoptimizer")
CSV_FIELDS = "schema_version experiment_id dataset_id phase batch_id job_id attempt_id attempt_no instance_id method encoding repetition block_side board_side source source_group rating_original rating_value family root_id clue_percent_requested actual_clues input_sha256 cutoff_seconds status raw_status build_seconds solve_seconds total_seconds attempt_wall_seconds checkpoint_seconds primary_variables auxiliary_variables total_variables clauses validation validation_message solution_ref solution_sha256 guard_phase error".split()


class ExpandedError(Exception):
    def __init__(self, message, exit_code=2):
        super().__init__(message)
        self.exit_code = exit_code


def public(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ExpandedError:
            raise
        except (sqlite3.DatabaseError, RuntimeError) as exc:
            raise ExpandedError(f"{type(exc).__name__}: {exc}",5) from exc
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            raise ExpandedError(f"{type(exc).__name__}: {exc}") from exc
    return wrapper


def require(condition, message, code=2):
    if not condition:
        raise ExpandedError(message, code)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def diagnostic_value(value):
    """Loss-aware diagnostic encoding; never turn invalid timing into a number."""
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite_float":repr(value)}
    if value is None or type(value) in (str,int,float,bool):
        return value
    if isinstance(value, dict):
        return {str(k):diagnostic_value(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [diagnostic_value(v) for v in value]
    return {"unsupported_type":type(value).__name__}


def canonical(n, grid):
    return (dumps(dict(n=n, grid=grid)) + "\n").encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(dumps(value) + "\n")


def lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def contained(root, relative):
    root = Path(root).resolve()
    require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), "Expected relative contained path")
    result = (root / relative).resolve()
    require(result.is_relative_to(root), f"Path escapes root: {relative}")
    return result


def stamp():
    return datetime.now(timezone.utc).isoformat()


def deadline(value):
    result = datetime.fromisoformat(value or DEFAULT_STOP)
    require(result.tzinfo is not None, "Deadline requires timezone")
    return result


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def rank(label, item):
    return digest(f"20261019|{label}|{item}".encode("utf-8"))

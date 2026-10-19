"""Independent contract-v2 reference functions, not a production generator.

These fixtures can be checked now. They do not certify expanded_data/runner,
whose implementation-specific execution remains a separate QA step.
"""
import hashlib
import json

from sudoku.model import Puzzle
from sudoku.validation import check_solution


def canonical(n, grid):
    puzzle = Puzzle(n, grid)
    payload = {"n": puzzle.n, "grid": [list(row) for row in puzzle.grid]}
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def content_hash(n, grid):
    return hashlib.sha256(canonical(n, grid)).hexdigest()


def instance_id(n, grid, phase="main"):
    return f"e2-{phase}-N{n*n}-{content_hash(n, grid)}"


def job_id(experiment, instance, method, encoding, rep):
    payload = [experiment, instance, method, encoding or "", rep]
    return "j2-" + hashlib.sha256(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def rank(label, item):
    return hashlib.sha256(f"20261019|{label}|{item}".encode("utf-8")).hexdigest()


def full(n):
    N = n*n
    return tuple(tuple((r*n + r//n + c) % N + 1 for c in range(N)) for r in range(N))


def mask(n, root, percent, root_id, phase="main", attempt=0):
    N = n*n
    label = f"mask|{phase}|{root_id}|{percent}|{attempt}"
    positions = sorted(range(N*N), key=lambda i: (rank(label, str(i)), str(i)))
    keep = set(positions[:(percent*N*N + 50)//100])
    return tuple(tuple(root[r][c] if r*N+c in keep else 0 for c in range(N)) for r in range(N))


def assert_whole_cycle(n, before, after, first, second, columns):
    """Audit recorded trade independently; does not call a generator function."""
    N = n*n
    assert first != second and first//n == second//n
    assert len(columns) == len(set(columns)) and 2 <= len(columns) < N
    assert all(type(c) is int and 0 <= c < N for c in columns)
    assert check_solution(Puzzle(n, [[0]*N for _ in range(N)]), before).valid
    assert check_solution(Puzzle(n, [[0]*N for _ in range(N)]), after).valid
    permutation = dict(zip(before[first], before[second]))
    assert len(permutation) == N and len(set(permutation.values())) == N
    start = before[first][columns[0]]
    values, cursor = [], start
    while cursor not in values:
        values.append(cursor)
        cursor = permutation[cursor]
    assert cursor == start and len(values) == len(columns)
    assert {before[first][c] for c in columns} == set(values)
    assert {c for c in range(N) if before[first][c] in values} == set(columns)
    for r in range(N):
        for c in range(N):
            expected = before[second if r == first else first][c] if r in (first, second) and c in columns else before[r][c]
            assert after[r][c] == expected


def trade_fixture(n):
    before = full(n)
    # Rows 0 and 1 map v -> v+n modulo N: a proper n-cycle.
    columns = tuple(range(0, n*n, n))
    after = [list(row) for row in before]
    for c in columns:
        after[0][c], after[1][c] = after[1][c], after[0][c]
    return before, tuple(tuple(row) for row in after), columns


# Fault injection fixtures. They require the real 07 storage implementation;
# no SQL imitation or mock-only pass is substituted for production recovery.
PERSISTENCE_CASES = (
    {"id": "pre_claim", "fault": "before_claim_commit", "primary": 0, "retry": "pending", "must_preserve": "no fabricated attempt/result"},
    {"id": "claimed", "fault": "after_claim_commit_before_launch", "primary": 0, "retry": "interrupted", "must_preserve": "RUNNING attempt retained then INTERRUPTED"},
    {"id": "during_solve", "fault": "parent_kill_with_worker_and_child", "primary": 0, "retry": "interrupted", "must_preserve": "process tree dead before writer reacquisition"},
    {"id": "solved", "fault": "after_solve_before_result_transaction", "primary": 0, "retry": "interrupted", "must_preserve": "lost observation not invented as TIMEOUT"},
    {"id": "result_inserted", "fault": "after_result_insert_before_solution", "primary": 0, "retry": "interrupted", "must_preserve": "completion transaction rolls back"},
    {"id": "solution_inserted", "fault": "after_solution_before_primary_and_commit", "primary": 0, "retry": "interrupted", "must_preserve": "no accepted orphan solution"},
    {"id": "committed", "fault": "after_completion_commit_before_ack", "primary": 1, "retry": "never", "must_preserve": "FINISHED/result/solution/primary atomic"},
    {"id": "telemetry_missing", "fault": "after_commit_before_checkpoint_event", "primary": 1, "retry": "never", "must_preserve": "checkpoint null; committed result unchanged"},
    {"id": "terminal_timeout", "fault": "resume_with_committed_TIMEOUT", "primary": 1, "retry": "never", "must_preserve": "TIMEOUT neither deleted nor retried"},
    {"id": "terminal_error", "fault": "resume_with_committed_ERROR", "primary": 1, "retry": "never", "must_preserve": "HALTED and raw failure retained"},
    {"id": "second_writer", "fault": "concurrent_writer_same_persistent_lock", "primary": None, "retry": "busy_exit_3", "must_preserve": "no second worker/import; no unlink lock"},
    {"id": "live_stale", "fault": "expired_heartbeat_with_live_OS_lock", "primary": None, "retry": "busy_exit_3", "must_preserve": "age does not permit stealing"},
    {"id": "resume_mismatch", "fault": "mutate_each_fingerprint_component", "primary": None, "retry": "refuse_before_launch", "must_preserve": "code/data/config/env/matrix/schedule/checker"},
    {"id": "db_write_failure", "fault": "disk_full_or_busy_during_commit", "primary": None, "retry": "stop_inspect", "must_preserve": "no successful checkpoint acknowledgement"},
    {"id": "export_crash", "fault": "during_snapshot_staging_publication", "primary": None, "retry": "new_export", "must_preserve": "no partial final destination; DB unchanged"},
)

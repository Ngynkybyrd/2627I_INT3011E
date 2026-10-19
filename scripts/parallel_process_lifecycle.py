"""Process-local CPython 3.13 lifecycle serialization for threaded spawn users.

Hypothesis: BaseProcess.start -> _cleanup can poll a sibling's saved _popen
while that sibling's owner closes its Windows handle. The interleaving is
reproducible; the historical generic WinError 6 does not prove its origin.

Install once in the coordinator BEFORE creating its worker thread pool. This
does not wrap run_job, solver execution, pipes, measurement or Job Objects.
Blocking joins are implemented as short, locked nonblocking joins with waits
outside the lock, so one joining thread cannot hold up other watchdogs.
"""
from functools import wraps
import multiprocessing.process as process
import os
import platform
import sys
import threading
import time

_MARKER = "_sudoku_parallel_lifecycle_adapter_v1"
_INSTALL_LOCK = threading.Lock()


def install():
    """Install idempotently; all changes are confined to this interpreter."""
    if platform.python_implementation() != "CPython" or sys.version_info[:2] != (3, 13):
        raise RuntimeError("Lifecycle adapter requires reviewed CPython 3.13 implementation")
    with _INSTALL_LOCK:
        existing = getattr(process, _MARKER, None)
        if existing is not None:
            return dict(existing["metadata"])
        lock = threading.RLock()
        originals = {}

        def serialize(function):
            @wraps(function)
            def locked(*args, **kwargs):
                with lock:
                    return function(*args, **kwargs)
            return locked

        originals["_cleanup"] = process._cleanup
        process._cleanup = serialize(process._cleanup)
        for name in ("start", "close", "is_alive", "terminate", "kill", "__repr__"):
            original = getattr(process.BaseProcess, name)
            originals[name] = original
            setattr(process.BaseProcess, name, serialize(original))

        original_join = process.BaseProcess.join
        originals["join"] = original_join

        @wraps(original_join)
        def join(self, timeout=None):
            deadline = None if timeout is None else time.monotonic()+max(0, timeout)
            while True:
                with lock:
                    original_join(self, timeout=0)
                    if self._popen.returncode is not None:
                        return None
                if deadline is not None:
                    remaining = deadline-time.monotonic()
                    if remaining <= 0:
                        return None
                else:
                    remaining = .01
                time.sleep(min(.01, remaining))

        process.BaseProcess.join = join
        original_exitcode = process.BaseProcess.exitcode
        originals["exitcode"] = original_exitcode
        process.BaseProcess.exitcode = property(serialize(original_exitcode.fget), doc=original_exitcode.__doc__)
        metadata = dict(profile="cpython313-process-lifecycle-lock-v1", pid=os.getpid(),
                        python=sys.version, stdlib_source=process.__file__,
                        serialized=["_cleanup", "start", "close", "is_alive", "terminate", "kill", "__repr__", "exitcode"],
                        join_policy="nonblocking joins under lock; at most 10ms sleep outside lock",
                        scope="parent interpreter lifecycle calls; solves and hard guards unchanged",
                        incident_attribution="plausible race reproduced independently; historical WinError6 source unproven")
        setattr(process, _MARKER, dict(metadata=metadata, lock=lock, originals=originals))
        return dict(metadata)


def uninstall():
    """Test/diagnostic teardown only; call after all lifecycle threads stop."""
    with _INSTALL_LOCK:
        state = getattr(process, _MARKER, None)
        if state is None:
            return
        with state["lock"]:
            for name, original in state["originals"].items():
                if name == "_cleanup":
                    process._cleanup = original
                else:
                    setattr(process.BaseProcess, name, original)
            delattr(process, _MARKER)

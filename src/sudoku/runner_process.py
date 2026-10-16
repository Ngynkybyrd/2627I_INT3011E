"""Windows process-tree ownership. No solver may start before assignment."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import os
import time


class JobObject:
    """Parent-owned, non-inheritable kill-on-close Job Object (Windows only)."""

    def __init__(self):
        if os.name != "nt":
            raise OSError("Runner hard guard currently requires Windows")
        k = self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
            "SetInformationJobObject": ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
            "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
            "TerminateJobObject": ([w.HANDLE, w.UINT], w.BOOL),
            "QueryInformationJobObject": ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p], w.BOOL),
            "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            "CloseHandle": ([w.HANDLE], w.BOOL),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(k, name)
            fn.argtypes, fn.restype = args, result

        class BasicLimits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                        ("flags", w.DWORD), ("min_ws", ctypes.c_size_t),
                        ("max_ws", ctypes.c_size_t), ("active_limit", w.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", w.DWORD),
                        ("scheduling", w.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

        class Extended(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io", IO),
                        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]

        self.handle = k.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway
        if not k.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, pid):
        process = self.k.OpenProcess(0x0100 | 0x0001, False, pid)  # SET_QUOTA | TERMINATE
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.k.AssignProcessToJobObject(self.handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.k.CloseHandle(process)

    def terminate_and_wait(self, timeout=5.0):
        if not self.k.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

        class Accounting(ctypes.Structure):
            _fields_ = [("user", ctypes.c_int64), ("kernel", ctypes.c_int64),
                        ("period_user", ctypes.c_int64), ("period_kernel", ctypes.c_int64),
                        ("faults", w.DWORD), ("total", w.DWORD),
                        ("active", w.DWORD), ("terminated", w.DWORD)]

        deadline = time.perf_counter() + timeout
        while True:
            info = Accounting()
            if not self.k.QueryInformationJobObject(self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if info.active == 0:
                return
            if time.perf_counter() >= deadline:
                raise RuntimeError("Job Object still contains live processes after termination")
            time.sleep(0.01)

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            if not self.k.CloseHandle(handle):
                raise ctypes.WinError(ctypes.get_last_error())

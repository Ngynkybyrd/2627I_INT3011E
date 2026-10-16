"""Small environment probes, not Sudoku adapters or performance measurements."""
import ctypes
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import sys
import winreg
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".mplconfig"))
os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout.reconfigure(encoding="utf-8")


def main():
    from pysat.solvers import Glucose3
    from ortools.sat.python import cp_model
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp
    import highspy
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    checks = {}
    for feasible in (True, False):
        label = "sat" if feasible else "unsat"
        clauses = [[1]] if feasible else [[1], [-1]]
        with Glucose3(bootstrap_with=clauses) as solver:
            assert solver.solve() is feasible
            if feasible:
                assert 1 in solver.get_model()
        checks[f"glucose3_{label}"] = "PASS"

        model = cp_model.CpModel()
        x = model.new_bool_var("x")
        model.add(x == 1)
        if not feasible:
            model.add(x == 0)
        cp = cp_model.CpSolver()
        cp.parameters.num_search_workers = 1
        cp.parameters.max_time_in_seconds = 5
        status = cp.solve(model)
        if feasible:
            assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        else:
            assert status == cp_model.INFEASIBLE
        if feasible:
            assert cp.value(x) == 1
        checks[f"cp_sat_{label}"] = cp.status_name(status)

        result = milp(c=np.array([0.0]), integrality=np.array([1]),
                      bounds=Bounds([0], [1]),
                      constraints=LinearConstraint([[1.0]], [1 if feasible else 2], [np.inf]),
                      options={"time_limit": 5})
        assert result.status == (0 if feasible else 2), result.message
        if feasible:
            assert abs(result.x[0] - 1) < 1e-7
        checks[f"scipy_milp_{label}"] = {"status": result.status, "message": result.message}

        h = highspy.Highs()
        assert h.setOptionValue("output_flag", False) == highspy.HighsStatus.kOk
        assert h.setOptionValue("threads", 1) == highspy.HighsStatus.kOk
        h.setOptionValue("time_limit", 5.0)
        assert h.getOptionValue("threads") == (highspy.HighsStatus.kOk, 1)
        v = h.addVariable(lb=0, ub=1, type=highspy.HighsVarType.kInteger)
        h.addConstr(v >= (1 if feasible else 2))
        assert h.run() == highspy.HighsStatus.kOk
        expected = highspy.HighsModelStatus.kOptimal if feasible else highspy.HighsModelStatus.kInfeasible
        assert h.getModelStatus() == expected
        if feasible:
            assert abs(h.getSolution().col_value[0] - 1) < 1e-7
        checks[f"highspy_{label}"] = {"status": str(h.getModelStatus()), "threads": 1}

    # Exercise UTF-8 and the project's path containing spaces, removing the probe afterwards.
    path_probe = ROOT / "diagnostics" / "kiểm tra UTF-8.txt"
    text = "Tạ Đình Nguyên — Sudoku tổng quát"
    try:
        path_probe.write_text(text, encoding="utf-8")
        assert path_probe.read_text(encoding="utf-8") == text
    finally:
        path_probe.unlink(missing_ok=True)
    checks["utf8_path"] = "PASS"

    fig, ax = plt.subplots(figsize=(4, 2.5))
    ax.plot([0, 1, 2], [0, 1, 4], marker="o")
    ax.set(title="Matplotlib environment smoke", xlabel="x", ylabel="x squared")
    fig.tight_layout()
    fig.savefig(ROOT / "diagnostics" / "smoke_plot.png", dpi=120)
    plt.close(fig)
    checks["matplotlib_png"] = "PASS"

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in
            ("total_phys", "avail_phys", "total_page", "avail_page", "total_virtual", "avail_virtual", "avail_extended")]
    mem = MemoryStatus()
    mem.length = ctypes.sizeof(mem)
    ram = mem.total_phys if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)) else None
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
        cpu_name = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    packages = ["python-sat", "ortools", "scipy", "highspy", "matplotlib", "pytest", "numpy", "pip", "setuptools"]
    evidence = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "python": sys.version, "executable": sys.executable,
                "prefix": sys.prefix, "base_prefix": sys.base_prefix,
                "os": platform.platform(), "cpu": cpu_name,
                "logical_cpus": os.cpu_count(), "ram_bytes": ram,
                "utf8_mode": sys.flags.utf8_mode,
                "packages": {p: metadata.version(p) for p in packages},
                "highspy_engine_version": highspy.Highs().version(),
                "glucose3_engine": "Glucose3 via python-sat; native version API unavailable",
                "checks": checks}
    (ROOT / "diagnostics" / "smoke_results.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

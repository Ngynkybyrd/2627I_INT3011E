"""Root release check for code/tests only; never calls a solver or downloads data."""
import ast
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main():
    execution = read(ROOT / "results/raw/main-20261016-01/execution-freeze.json")
    data = read(ROOT / "data/freeze.json")
    for evidence in (execution, data):
        for name, expected in evidence["files_sha256"].items():
            assert sha(ROOT / name) == expected, f"Protected file changed: {name}"
    assert sha(ROOT / "results/raw/main-20261016-01/results.csv") == "aac4cde1fed90857ea81a1575e326049be71a528f27a6a744435b94c42dfdda7"
    expected_pdfs = {
        "sudoku-vi.pdf": "e0e3a294639371c5dc07398afd02cbac1afcc6a527cea02bc4ec1464ddd0fd64",
        "sudoku-en.pdf": "bae7455b3584612371c7c51ce533369a40b98795841f974d7be4c63cfe823075",
    }
    for name, expected in expected_pdfs.items():
        assert sha(ROOT / "report/output/pdf" / name) == expected, f"Existing PDF changed: {name}"
    sources = sorted((ROOT / "src/sudoku").glob("expanded*.py"))
    sources += [ROOT / name for name in (
        "scripts/prepare_expanded_data.py", "scripts/run_expanded.py",
        "scripts/analyze_expanded.py", "report/prepare_expanded_report.py",
        "scripts/complete_expanded_witnesses.py", "scripts/authorize_expanded_local.py",
    )]
    for path in sources:
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    artifacts = sources + [ROOT / name for name in (
        "scripts/local_expanded_pipeline.ps1", "docs/expanded-local-run.md",
        "scripts/start_full_expanded_run.ps1", "docs/expanded-terminal-policy.md",
        "docs/expanded-contract.md", "docs/expanded-acceptance.md",
        "configs/expanded/main.json", "configs/expanded/pilot.json",
        "configs/expanded/matrix.json",
    )]
    artifacts += sorted((ROOT / "tests").rglob("*.py"))
    # Include the unchanged v1 dependencies explicitly as well as checking the
    # protected execution freeze, so collector and auditor share one closure.
    artifacts += [ROOT / name for name in execution["files_sha256"]]
    suite_path = HERE / "regression-final.xml"
    suite = ET.parse(suite_path).getroot()
    cases = suite.findall(".//testcase")
    failures = suite.findall(".//failure") + suite.findall(".//error")
    skipped = suite.findall(".//skipped")
    assert len(cases) >= execution["passed_tests"] and not failures and not skipped, "Regression is not fully passing"
    result = {
        "schema_version": 2, "status": "PASS", "scope": "code/tests release, not research results",
        "passed_tests": len(cases), "failed_tests": len(failures), "skipped_tests": len(skipped),
        "regression_xml_sha256": sha(suite_path),
        "regression": {"path": str(suite_path.relative_to(ROOT)).replace("\\", "/"),
                       "sha256": sha(suite_path), "scope": "full", "tests": len(cases),
                       "failures": 0, "errors": 0, "skipped": 0},
        "protected_execution_files": len(execution["files_sha256"]),
        "protected_data_files": len(data["files_sha256"]),
        "existing_two_pdfs_unchanged": True,
        "source_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p) for p in artifacts},
        "approved_explicit_terminal_execution": True,
        "research_solving_started_by_verifier": False,
        "permitted_next_action": "visible_terminal_only_after_code_release_then_verified_runtime_gates",
        "automation": "PAUSED",
    }
    (HERE / "code-release.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "source_sha256"}, indent=2))


if __name__ == "__main__":
    main()

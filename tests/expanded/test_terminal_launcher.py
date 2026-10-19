"""Exercise the final PowerShell owner-interface check without any execution."""
from pathlib import Path
import shutil
import subprocess


def test_launcher_accepts_wrapped_real_help_without_launching_workers():
    root = Path(__file__).resolve().parents[2]
    pwsh = shutil.which("pwsh")
    assert pwsh is not None, "PowerShell is required for the local launcher"
    command = (
        ". './scripts/start_full_expanded_run.ps1'; "
        "$null=Assert-OwnerInterfaces; "
        "Write-Output 'OWNER_INTERFACES_PASS_NO_SOLVER'"
    )
    result = subprocess.run(
        [pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OWNER_INTERFACES_PASS_NO_SOLVER" in result.stdout
    assert "[DRY_RUN]" in result.stdout


def test_python_wrapper_preserves_arguments_and_finishes_without_stdin(tmp_path):
    root = Path(__file__).resolve().parents[2]
    probe = tmp_path / "argv probe.py"
    probe.write_text("import json,sys; print(json.dumps(sys.argv[1:]))", encoding="utf-8")
    script = root / "scripts/start_full_expanded_run.ps1"
    command = (
        f". '{script.as_posix()}'; "
        f"$result=Invoke-PythonText @('{probe.as_posix()}','argument with spaces','--sentinel'); "
        "$parsed=ConvertFrom-Json $result; "
        "if($parsed.Count -ne 2 -or $parsed[0] -ne 'argument with spaces' -or $parsed[1] -ne '--sentinel'){throw 'Lost Python arguments'}; "
        "$frozenCheck=ConvertFrom-Json '{\"counts\":{\"9\":10000,\"16\":5000,\"25\":1000}}'; "
        "$datasetCount=($frozenCheck.counts.PSObject.Properties.Value | Measure-Object -Sum).Sum; "
        "if($datasetCount -ne 16000){throw 'Wrong JSON count'}; "
        "Write-Output 'PYTHON_ARGUMENTS_PASS'"
    )
    result = subprocess.run(
        [shutil.which("pwsh"), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=root, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PYTHON_ARGUMENTS_PASS" in result.stdout


def test_completed_witness_with_empty_stderr_is_success(tmp_path):
    root = Path(__file__).resolve().parents[2]
    command = r"""
. './scripts/start_full_expanded_run.ps1'
$script:EvidenceDir='__FIXTURE__'
function Start-Process {
 param($FilePath,$ArgumentList,$WorkingDirectory,[switch]$PassThru,[switch]$NoNewWindow,$RedirectStandardOutput,$RedirectStandardError)
 [IO.File]::WriteAllText($RedirectStandardError,'')
 [IO.File]::WriteAllText($RedirectStandardOutput,'{"state":"COMPLETE","admitted_status_counts":{"SAT":10000},"public_inputs":10000,"code_release_sha256":"fixture-only","output_reusable":true}')
 $p=[pscustomobject]@{HasExited=$true;ExitCode=0}
 $p | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value {}
 return $p
}
$result=@(Invoke-WitnessAcquisition 'main' 'fixture-draft' 'fixture-evidence' 'fixture-output')
if($result[-1].state -ne 'COMPLETE'){throw 'Witness completion rejected'}
Write-Output 'EMPTY_STDERR_PASS_NO_SOLVER'
""".replace('__FIXTURE__', tmp_path.as_posix())
    result = subprocess.run(
        [shutil.which('pwsh'), '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', command],
        cwd=root, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'EMPTY_STDERR_PASS_NO_SOLVER' in result.stdout


def test_launcher_dataset_indexes_preserve_upper_and_lower_n(tmp_path):
    root = Path(__file__).resolve().parents[2]
    (tmp_path / 'dataset-index.json').write_text(
        '{"batches":["fixture"],"instances":[{"N":9,"n":3}]}', encoding='utf-8')
    source = (root / 'scripts/start_full_expanded_run.ps1').read_text(encoding='utf-8')
    reads = [line for line in source.splitlines()
             if line.strip().startswith(('$pilotIndex=', '$mainIndex='))]
    assert len(reads) == 2
    command = f"$ErrorActionPreference='Stop';$pilotExp='{tmp_path.as_posix()}';$mainExp=$pilotExp;" + ';'.join(reads)
    command += ";foreach($index in @($pilotIndex,$mainIndex)){if($index.instances[0]['N'] -ne 9 -or $index.instances[0]['n'] -ne 3){throw 'Lost N/n'}};Write-Output 'INDEX_PASS'"
    result = subprocess.run(
        [shutil.which('pwsh'), '-NoProfile', '-NonInteractive', '-Command', command],
        cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'INDEX_PASS' in result.stdout


def test_checkpoint_uses_distinct_pilot_and_main_experiment_names(tmp_path):
    import json
    root = Path(__file__).resolve().parents[2]
    rid = '20261019-000001'
    draft = root / f'data/expanded-inputs/wave3-{rid}'
    frozen = root / f'data/expanded/wave3-{rid}'
    cp = dict(schema_version=1, run_id=rid, state='BOTH_FROZEN',
              draft_root=str(draft), dataset_root=str(frozen),
              main_draft=str(draft/'expanded-20261019-v2'),
              pilot_draft=str(draft/'expanded-pilot-20261019-v2'),
              main_dataset=str(frozen/'main'), pilot_dataset=str(frozen/'pilot'),
              pilot_experiment=str(root/f'diagnostics/expansion/pilot/wave3-{rid}-pilot'),
              main_experiment=str(root/f'results/expanded/wave3-{rid}-main'))
    (tmp_path/'full-run-checkpoint.json').write_text(json.dumps(cp), encoding='utf-8')
    command = (
        ". './scripts/start_full_expanded_run.ps1'; "
        f"$script:EvidenceDir='{tmp_path.as_posix()}'; $c=Read-FullCheckpoint; "
        "if((Split-Path $c.pilot_experiment -Leaf) -eq (Split-Path $c.main_experiment -Leaf)){throw 'Gate name collision'}; "
        "Write-Output 'DISTINCT_EXPERIMENTS_PASS'"
    )
    result = subprocess.run(
        [shutil.which('pwsh'), '-NoProfile', '-NonInteractive', '-Command', command],
        cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'DISTINCT_EXPERIMENTS_PASS' in result.stdout

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$probeRoot = Join-Path $projectRoot 'tmp\solver-probe'
$probePython = Join-Path $probeRoot '.venv\Scripts\python.exe'
$env:TEMP = Join-Path $probeRoot 'temp'
$env:TMP = $env:TEMP
$env:PYTHONDONTWRITEBYTECODE = '1'
& $probePython (Join-Path $PSScriptRoot 'probe.py')
if ($LASTEXITCODE -ne 0) { throw "Probe script failed: $LASTEXITCODE" }
& $probePython -m pip freeze | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'requirements-probe.txt') -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw "pip freeze failed: $LASTEXITCODE" }

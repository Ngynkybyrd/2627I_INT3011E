<#
.SYNOPSIS
Local, explicit driver for expanded Sudoku setup and run phases.
.DESCRIPTION
No action defaults to a read-only doctor/dry-run. StageInputs fetches pinned source
files only and writes a DRAFT cache receipt; it never creates witnessed data or
starts a solver. Pilot/run/resume are explicit commands and rely on root gates in
the expanded runner API. A complete-block export is analyzed automatically after
an explicit main run when QA-complete blocks exist.
#>
[CmdletBinding()]
param(
    [switch]$Doctor,
    [switch]$DryRun,
    [switch]$StageInputs,
    [switch]$Prepare,
    [switch]$Pilot,
    [switch]$Run,
    [switch]$Status,
    [switch]$Resume,
    [switch]$Export,
    [switch]$Analyze,
    [switch]$PrepareReport,
    [switch]$DeferPostProcessing,
    [switch]$TestArgvQuoting,
    [ValidateSet('main','pilot')][string]$Phase = 'main',
    [string]$Dataset,
    [string]$Experiment,
    [string]$Config,
    [string]$Matrix,
    [string]$ExportDirectory,
    [string]$AnalysisOutput,
    [string]$AnalysisReceipt,
    [string]$ReceiptSha256,
    [string]$DraftInputDirectory,
    [string]$Reason,
    [string]$StopStartingAt = '2026-10-19T22:30:00+07:00',
    [string]$PythonPath,
    [ValidateRange(5,600)][int]$PollSeconds = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$RunnerScript = Join-Path $Root 'scripts/run_expanded.py'
$DataScript = Join-Path $Root 'scripts/prepare_expanded_data.py'
$AnalysisScript = Join-Path $Root 'scripts/analyze_expanded.py'
$ReportScript = Join-Path $Root 'report/prepare_expanded_report.py'
$PackageEvidenceDir = Join-Path $Root 'diagnostics/expansion/package'

function Write-Result([string]$State, [string]$Message) {
    Write-Host ('[{0}] {1}' -f $State, $Message)
}

function Resolve-Python {
    if ($PythonPath) {
        if ([System.IO.Path]::IsPathRooted($PythonPath)) {
            $candidate = [System.IO.Path]::GetFullPath($PythonPath)
        } else {
            $candidate = [System.IO.Path]::GetFullPath((Join-Path $Root $PythonPath))
        }
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "Python not found: $candidate" }
        return $candidate
    }
    foreach ($candidate in @(
        (Join-Path $Root '.venv/Scripts/python.exe'),
        (Join-Path $Root 'tmp/repro-env/venv/Scripts/python.exe')
    )) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    throw 'No existing project/clean Python environment found. Install/setup manually; this script never installs packages.'
}

function Invoke-PythonText([string[]]$Arguments) {
    $output = & $script:Python @Arguments 2>&1
    $code = $LASTEXITCODE
    $text = ($output | Out-String).Trim()
    if ($code -ne 0) { throw "Command failed ($code): python $($Arguments -join ' ')`n$text" }
    return $text
}

function Invoke-PythonWithSolverThreads([string[]]$Arguments) {
    $names = @('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')
    $saved = @{}
    foreach ($name in $names) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name)
        [Environment]::SetEnvironmentVariable($name,'1')
    }
    try { return (Invoke-PythonText $Arguments) }
    finally { foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name,$saved[$name]) } }
}

function Get-ExpandedMatrixSummary {
    $path = Join-Path $Root 'configs/expanded/matrix.json'
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    $matrix = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    $eligible = @($matrix.rows | Where-Object { $_.eligible -eq $true })
    $counts = @{}
    foreach ($n in @(9,16,25)) { $counts[$n] = @($eligible | Where-Object { [int]$_.N -eq $n }).Count }
    $threadsOne = @($eligible | Where-Object { $_.threads -ne 1 }).Count -eq 0
    return [pscustomobject]@{
        rows = $eligible.Count
        n9 = $counts[9]; n16 = $counts[16]; n25 = $counts[25]
        threadsOne = $threadsOne
        mainJobs = ((10000 * $counts[9]) + (5000 * $counts[16]) + (1000 * $counts[25])) * 3
        pilotJobs = ((8 * $counts[9]) + (10 * $counts[16]) + (10 * $counts[25]))
    }
}

function Assert-OperationalMatrix([string]$ForPhase) {
    $matrixSummary = Get-ExpandedMatrixSummary
    $expectedJobs = if ($ForPhase -eq 'pilot') { 164 } else { 330000 }
    $configPath = Join-Path $Root ('configs/expanded/' + $ForPhase + '.json')
    if (-not $matrixSummary -or -not (Test-Path -LiteralPath $configPath)) { throw 'Expanded config or normalized matrix missing; no worker started.' }
    $configData = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $expectedRepetitions = if ($ForPhase -eq 'pilot') { 1 } else { 3 }
    $actualJobs = if ($ForPhase -eq 'pilot') { $matrixSummary.pilotJobs } else { $matrixSummary.mainJobs }
    if (($matrixSummary.n9 -ne 8) -or ($matrixSummary.n16 -ne 5) -or ($matrixSummary.n25 -ne 5) -or
        ($matrixSummary.threadsOne -ne $true) -or ($actualJobs -ne $expectedJobs) -or
        ([double]$configData.cutoff_seconds -ne 10.0) -or ([int]$configData.repetitions -ne $expectedRepetitions)) {
        throw "Config/matrix does not match accepted $ForPhase envelope (8/5/5, 10s, reps=$expectedRepetitions, jobs=$expectedJobs, threads=1); no worker started."
    }
}

function Invoke-Doctor {
    $stageInputAvailable = $false
    if (Test-Path -LiteralPath $DataScript) {
        $dataHelp = & $script:Python -B $DataScript --help 2>&1 | Out-String
        $stageInputAvailable = ($LASTEXITCODE -eq 0 -and $dataHelp -match 'stage-inputs')
    }
    $moduleChecks = [ordered]@{
        datasetCacheApi = (Test-Path -LiteralPath $DataScript)
        stageInputsApi = $stageInputAvailable
        expandedRunnerCli = (Test-Path -LiteralPath $RunnerScript)
        expandedRunnerApi = (Test-Path -LiteralPath (Join-Path $Root 'src/sudoku/expanded_runner.py'))
        expandedAnalysis = (Test-Path -LiteralPath $AnalysisScript)
        expandedReportPreparer = (Test-Path -LiteralPath $ReportScript)
        mainConfig = (Test-Path -LiteralPath (Join-Path $Root 'configs/expanded/main.json'))
        pilotConfig = (Test-Path -LiteralPath (Join-Path $Root 'configs/expanded/pilot.json'))
        matrix = (Test-Path -LiteralPath (Join-Path $Root 'configs/expanded/matrix.json'))
        rootGateDirectory = (Test-Path -LiteralPath (Join-Path $Root 'diagnostics/expansion/gates'))
    }
    $matrix = Get-ExpandedMatrixSummary
    $disk = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($Root))
    $pythonVersion = Invoke-PythonText @('--version')
    $reserveBytes = 1073741824
    $configFile = Join-Path $Root 'configs/expanded/main.json'
    if (Test-Path -LiteralPath $configFile) {
        $mainConfig = Get-Content -LiteralPath $configFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($mainConfig.disk_reserve_bytes) { $reserveBytes = [long]$mainConfig.disk_reserve_bytes }
    }
    Write-Result 'DOCTOR' ('root={0}' -f $Root)
    Write-Result 'DOCTOR' ('python={0}; {1}' -f $script:Python, $pythonVersion)
    foreach ($name in $moduleChecks.Keys) {
        $state = if ($moduleChecks[$name]) { 'AVAILABLE' } else { 'WAITING' }
        Write-Result $state ($name + '=' + [string]$moduleChecks[$name])
    }
    if ($matrix) {
        Write-Result 'PLAN' ('eligible configurations N9/N16/N25={0}/{1}/{2}; rows={3}; expected main jobs={4}; pilot jobs={5}; all eligible threads=1:{6}' -f $matrix.n9,$matrix.n16,$matrix.n25,$matrix.rows,$matrix.mainJobs,$matrix.pilotJobs,$matrix.threadsOne)
        if (($matrix.n9 -ne 8) -or ($matrix.n16 -ne 5) -or ($matrix.n25 -ne 5) -or ($matrix.mainJobs -ne 330000) -or ($matrix.pilotJobs -ne 164)) {
            Write-Result 'WAITING' 'matrix does not match the accepted 8/5/5, 330000-main/164-pilot envelope; do not run.'
        }
    }
    Write-Result 'DISK' ('drive={0}; free={1:N0} bytes; reserve={2:N0} bytes' -f $disk.Name,$disk.AvailableFreeSpace,$reserveBytes)
    foreach ($envName in @('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')) {
        $isSet = -not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($envName))
        Write-Result 'ENV' ($envName + '=' + $(if($isSet){'set (value hidden)'}else{'unset'}))
    }
    $draftRoot = Join-Path $Root 'data/expanded-inputs'
    $draftState = if (Test-Path -LiteralPath $draftRoot) { 'draft input directory exists; inspect its receipt' } else { 'no draft inputs staged' }
    $dataset = Join-Path $Root 'data/expanded/expanded-20261019-v2/freeze.json'
    Write-Result 'INPUTS' ('{0}; main frozen dataset {1}' -f $draftState,$(if(Test-Path -LiteralPath $dataset){'present'}else{'missing'}))
    Write-Result 'GATES' 'no gate is inferred or accepted by this wrapper; expanded_runner validates root signatures/references before any worker.'
    if (-not $moduleChecks.expandedReportPreparer) {
        Write-Result 'WAITING_SAT09' 'scripts/prepare_expanded_report.py is absent; the pipeline will stop before claiming report preparation.'
    }
    Write-Result 'SAFE_DEFAULT' 'No solver, network, data generation, install, PDF build, automation, push, or submission is run by default.'
    Write-Result 'PLAN' 'Use -DryRun with one action to print its command. Pilot/run/resume require explicit action flags and root-accepted gate references.'
}

function Test-ExperimentGate([string]$ExperimentPath) {
    $manifestPath = Join-Path $ExperimentPath 'experiment.json'
    if (-not (Test-Path -LiteralPath $manifestPath)) { throw "Experiment manifest missing: $manifestPath" }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.artificial -eq $true) { throw 'Artificial fixture experiments are never eligible for pilot/main.' }
    if (-not $manifest.gate_refs_path) { throw 'Experiment manifest has no root gate reference.' }
    $gatePath = Join-Path $Root ([string]$manifest.gate_refs_path)
    if (-not (Test-Path -LiteralPath $gatePath)) { throw "Root gate file is absent: $gatePath. No worker will start." }
    Write-Result 'GATE' ('reference file exists: {0}; the runner API still validates the gate subject and acceptance hashes.' -f $gatePath)
}

function Assert-DiskReserve([string]$ExperimentPath) {
    $reserve = 1073741824L
    if ($ExperimentPath -and (Test-Path -LiteralPath (Join-Path $ExperimentPath 'experiment.json'))) {
        $manifest = Get-Content -LiteralPath (Join-Path $ExperimentPath 'experiment.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($manifest.config.disk_reserve_bytes) { $reserve = [long]$manifest.config.disk_reserve_bytes }
    } elseif (Test-Path -LiteralPath (Join-Path $Root ('configs/expanded/' + $Phase + '.json'))) {
        $configPath = Join-Path $Root ('configs/expanded/' + $Phase + '.json')
        $configData = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($configData.disk_reserve_bytes) { $reserve = [long]$configData.disk_reserve_bytes }
    }
    $drive = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($Root))
    if ($drive.AvailableFreeSpace -lt $reserve) {
        throw "Free disk $($drive.AvailableFreeSpace) is below the reserved $reserve bytes; no run action started."
    }
}

function Enter-PipelineLock {
    New-Item -ItemType Directory -Path $PackageEvidenceDir -Force | Out-Null
    $path = Join-Path $PackageEvidenceDir 'local-pipeline.lock'
    try {
        $stream = [System.IO.File]::Open($path,[System.IO.FileMode]::OpenOrCreate,[System.IO.FileAccess]::ReadWrite,[System.IO.FileShare]::None)
    } catch { throw 'Another local expanded pipeline action holds the exclusive lock; no parallel generation/run was started.' }
    $stream.SetLength(0)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes(('pid={0}; started={1:o}' -f $PID,[DateTimeOffset]::Now))
    $stream.Write($bytes,0,$bytes.Length)
    $stream.Flush()
    return $stream
}

function Quote-ProcessArg([string]$Value) {
    $builder = [System.Text.StringBuilder]::new()
    [void]$builder.Append('"')
    $slashes = 0
    foreach ($char in $Value.ToCharArray()) {
        if ($char -eq '\') { $slashes++; continue }
        if ($char -eq '"') {
            [void]$builder.Append(('\' * (2 * $slashes + 1)))
            [void]$builder.Append('"')
        } else {
            if ($slashes -gt 0) { [void]$builder.Append(('\' * $slashes)) }
            [void]$builder.Append($char)
        }
        $slashes = 0
    }
    if ($slashes -gt 0) { [void]$builder.Append(('\' * (2 * $slashes))) }
    [void]$builder.Append('"')
    return $builder.ToString()
}

function Test-StartProcessArgvRoundTrip {
    $logs = Join-Path $PackageEvidenceDir 'argv-roundtrip'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $stdout = Join-Path $logs ($stamp + '.argv.json')
    $stderr = Join-Path $logs ($stamp + '.stderr.txt')
    $expected = @('a path with spaces\','quote"inside','slash\"quote','plain')
    $code = 'import json,sys; print(json.dumps(sys.argv[1:], ensure_ascii=False))'
    $args = @('-B','-c',$code) + $expected
    $argumentLine = ($args | ForEach-Object { Quote-ProcessArg ([string]$_) }) -join ' '
    $process = Start-Process -FilePath $script:Python -ArgumentList $argumentLine -WorkingDirectory $Root -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    if ($process.ExitCode -ne 0) { throw "argv echo process failed; see $stderr" }
    $actual = @(Get-Content -LiteralPath $stdout -Raw -Encoding UTF8 | ConvertFrom-Json)
    if (($actual -join "`n") -cne ($expected -join "`n")) { throw ('Windows argument quoting round-trip mismatch; expected {0}; got {1}' -f ($expected -join '|'),($actual -join '|')) }
    $receipt = [ordered]@{ status='PASS'; argv=$actual; solver_calls=0; network_calls=0; utc=[DateTimeOffset]::Now.ToString('o') }
    $receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $logs 'roundtrip.json') -Encoding UTF8
    Write-Result 'ARGV_QUOTE' ('PASS; evidence={0}' -f (Join-Path $logs 'roundtrip.json'))
}

function Invoke-RunnerMonitored([string[]]$RunnerArgs, [string]$ExperimentPath) {
    $logs = Join-Path $PackageEvidenceDir 'local-pipeline'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $stdout = Join-Path $logs ($stamp + '.stdout.log')
    $stderr = Join-Path $logs ($stamp + '.stderr.log')
    $args = @('-B','scripts/run_expanded.py') + $RunnerArgs
    $argumentLine = ($args | ForEach-Object { Quote-ProcessArg ([string]$_) }) -join ' '
    $saved = @{}
    foreach ($envName in @('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')) {
        $saved[$envName] = [Environment]::GetEnvironmentVariable($envName)
        [Environment]::SetEnvironmentVariable($envName,'1')
    }
    try {
        $process = Start-Process -FilePath $script:Python -ArgumentList $argumentLine -WorkingDirectory $Root -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    } finally {
        foreach ($envName in $saved.Keys) { [Environment]::SetEnvironmentVariable($envName,$saved[$envName]) }
    }
    Write-Result 'RUN' ('pid={0}; logs={1}; poll={2}s' -f $process.Id,$logs,$PollSeconds)
    while (-not $process.HasExited) {
        Start-Sleep -Seconds $PollSeconds
        $process.Refresh()
        if (-not $process.HasExited) {
            try {
                $statusText = Invoke-PythonText @('-B','scripts/run_expanded.py','status','--experiment',$ExperimentPath,'--json')
                $snapshot = $statusText | ConvertFrom-Json
                $eta = if ($null -eq $snapshot.eta_seconds) { 'unknown' } else { '{0:N1}s' -f [double]$snapshot.eta_seconds }
                $free = if ($null -eq $snapshot.free_disk_bytes) { 'unknown' } else { '{0:N0} bytes' -f [long]$snapshot.free_disk_bytes }
                Write-Result 'PROGRESS' ('state={0}; jobs={1}/{2}; blocks={3}; QA-complete blocks={4}; ETA={5}; free={6}; statuses={7}' -f $snapshot.state,$snapshot.completed_jobs,$snapshot.planned_jobs,$snapshot.completed_blocks,$snapshot.qa_complete_blocks,$eta,$free,$(if($snapshot.primary_counts){($snapshot.primary_counts | ConvertTo-Json -Compress)}else{'none'}))
            } catch { Write-Result 'STATUS_UNAVAILABLE' $_.Exception.Message }
        }
    }
    $process.WaitForExit()
    $stdoutText = if (Test-Path -LiteralPath $stdout) { Get-Content -LiteralPath $stdout -Raw -Encoding UTF8 } else { '' }
    $stderrText = if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr -Raw -Encoding UTF8 } else { '' }
    if ($stderrText) { Write-Result 'RUN_STDERR' $stderrText.Trim() }
    if ($stdoutText) { Write-Result 'RUN_LOG' ('runner summary retained in {0}' -f $stdout) }
    $statusText = Invoke-PythonText @('-B','scripts/run_expanded.py','status','--experiment',$ExperimentPath,'--json')
    return [pscustomobject]@{ ExitCode=[int]$process.ExitCode; Snapshot=($statusText | ConvertFrom-Json); StdoutLog=$stdout; StderrLog=$stderr }
}

function Invoke-ReportPreparation([string]$AnalysisPath,[string]$ExperimentPath) {
    if (-not (Test-Path -LiteralPath $ReportScript)) {
        Write-Result 'WAITING_SAT09' ('Report preparer missing: {0}; analysis remains available, no report PASS claimed.' -f $ReportScript)
        return 3
    }
    $summary = Get-Content -LiteralPath (Join-Path $AnalysisPath 'summary.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($summary.report_ready -ne $true -or $summary.phase -ne 'main' -or $summary.artificial -eq $true) {
        throw 'Report preparation requires real main analysis with report_ready=true.'
    }
    $helpText = & $script:Python -B $ReportScript --help 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -or $helpText -notmatch '--analysis' -or $helpText -notmatch '--output' -or $helpText -notmatch '--receipt-sha256') {
        Write-Result 'WAITING_SAT09' 'Report preparer help does not expose its analysis, output, and receipt hash inputs; no guessed invocation made.'
        return 3
    }
    $receiptPath = if ($AnalysisReceipt) { $AnalysisReceipt } else { Join-Path $AnalysisPath 'analysis-hashes.json' }
    if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) {
        Write-Result 'WAITING_SAT08' ('Analysis hash receipt missing: {0}' -f $receiptPath)
        return 3
    }
    $receiptHash = (Get-FileHash -LiteralPath $receiptPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ReceiptSha256 -and $ReceiptSha256.ToLowerInvariant() -ne $receiptHash) { throw 'Provided receipt SHA-256 does not match the selected analysis receipt.' }
    $reportOutput = Join-Path $Root ('report/expanded-prepared/' + (Split-Path $ExperimentPath -Leaf) + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    $result = Invoke-PythonText @('-B',$ReportScript,'--analysis',$AnalysisPath,'--output',$reportOutput,'--analysis-receipt',$receiptPath,'--receipt-sha256',$receiptHash)
    if (-not (Test-Path -LiteralPath $reportOutput)) { throw 'Report command returned success without creating its declared output directory.' }
    Write-Result 'REPORT' ('preparer output={0}' -f $reportOutput)
    Write-Result 'REPORT_RESULT' $result
    return 0
}

function Invoke-PostRun([string]$ExperimentPath,[object]$Snapshot) {
    if ([int]$Snapshot.qa_complete_blocks -le 0) {
        Write-Result 'NO_EXPORT' 'No QA-complete block exists; partial attempts remain in the runner database.'
        return 0
    }
    if (-not $ExportDirectory) {
        $ExportDirectory = Join-Path $Root ('results/expanded-exports/' + (Split-Path $ExperimentPath -Leaf) + '-complete-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    }
    if (-not $AnalysisOutput) {
        $AnalysisOutput = Join-Path $Root ('results/expanded-analysis/' + (Split-Path $ExperimentPath -Leaf) + '-complete-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    }
    $exportText = Invoke-PythonText @('-B','scripts/run_expanded.py','export','--experiment',$ExperimentPath,'--output',$ExportDirectory,'--complete-blocks')
    $exportResult = $exportText | ConvertFrom-Json
    $selected = @($exportResult.selected_blocks)
    if ($selected.Count -eq 0) { Write-Result 'NO_EXPORT' 'Runner API selected no QA-complete blocks.'; return 0 }
    Write-Result 'EXPORT' ('complete blocks={0}; path={1}' -f $selected.Count,$ExportDirectory)
    $analysisText = Invoke-PythonText @('-B','scripts/analyze_expanded.py','--export',$ExportDirectory,'--output',$AnalysisOutput)
    $analysis = $analysisText | ConvertFrom-Json
    Write-Result 'ANALYSIS' ('label={0}; report_ready={1}; path={2}' -f $analysis.label,$analysis.report_ready,$AnalysisOutput)
    if ($analysis.report_ready -ne $true) { Write-Result 'PARTIAL' 'Analysis is retained with its non-final label; no report preparation.'; return 0 }
    return (Invoke-ReportPreparation $AnalysisOutput $ExperimentPath)
}

function Invoke-Main {
    $actions = @()
    foreach ($candidate in @('StageInputs','Prepare','Pilot','Run','Status','Resume','Export','Analyze','PrepareReport','TestArgvQuoting')) {
        $value = Get-Variable -Name $candidate -Scope Script -ValueOnly -ErrorAction SilentlyContinue
        if ($value) { $actions += $candidate }
    }
    if ($actions.Count -gt 1) { Write-Error 'Choose one action switch.'; return 2 }
    if ($actions.Count -eq 0) { $script:Doctor = $true }
    try { $script:Python = Resolve-Python } catch { Write-Result 'WAITING' $_.Exception.Message; return 3 }
    if ($Doctor) { Invoke-Doctor; if (-not $DryRun -and $actions.Count -eq 0) { return 0 } }
    if ($actions.Count -eq 0) { Write-Result 'DRY_RUN' 'No action supplied; doctor only, no input/output changes.'; return 0 }
    $action = $actions[0]
    if ($DryRun) {
        switch ($action) {
            'StageInputs' { Write-Result 'DRY_RUN' 'Would run prepare_expanded_data.py stage-inputs under data/expanded-inputs, then verify both main/pilot DRAFT datasets with verify-inputs. No cache-sources fallback is allowed.' }
            'Prepare' { Write-Result 'DRY_RUN' 'Would validate frozen dataset/config/matrix and create a new experiment manifest/SQLite database; prepare does not solve.' }
            'Pilot' { Write-Result 'DRY_RUN' 'Would invoke the explicitly requested pilot; runner must validate root-accepted gates before any worker.' }
            'Run' { Write-Result 'DRY_RUN' 'Would invoke the explicitly requested main run; runner must validate root-accepted gates before any worker. Complete blocks auto-export/analyze afterward.' }
            'Status' { Write-Result 'DRY_RUN' 'Would read the current experiment status; no lock stealing or solver calls.' }
            'Resume' { Write-Result 'DRY_RUN' 'Would invoke explicit recovery with reason and stop time; runner revalidates fingerprint/cleanup/gates.' }
            'Export' { Write-Result 'DRY_RUN' 'Would create a new complete-block snapshot; no raw DB mutation or solver.' }
            'Analyze' { Write-Result 'DRY_RUN' 'Would analyze an immutable schema-2 export; never starts a solver.' }
            'PrepareReport' { Write-Result 'DRY_RUN' 'Would call SAT09 report preparer only if present and report_ready=true.' }
            'TestArgvQuoting' { Write-Result 'DRY_RUN' 'Would launch a Python argv echo only; no solver/network.' }
        }
        return 0
    }

    $pipelineLock = $null
    if ($action -ne 'Status') {
        try { $pipelineLock = Enter-PipelineLock } catch { Write-Result 'BUSY' $_.Exception.Message; return 3 }
    }
    try {
        switch ($action) {
            'StageInputs' {
                if (-not $DraftInputDirectory) { $DraftInputDirectory = Join-Path $Root ('data/expanded-inputs/draft-stageinput-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
                if ([System.IO.Path]::IsPathRooted($DraftInputDirectory)) { $draft = [System.IO.Path]::GetFullPath($DraftInputDirectory) }
                else { $draft = [System.IO.Path]::GetFullPath((Join-Path $Root $DraftInputDirectory)) }
                $allowedDraftRoot = [System.IO.Path]::GetFullPath((Join-Path $Root 'data/expanded-inputs')) + [System.IO.Path]::DirectorySeparatorChar
                if (-not $draft.StartsWith($allowedDraftRoot,[System.StringComparison]::OrdinalIgnoreCase)) { throw 'Draft input output must remain under data/expanded-inputs and outside frozen dataset paths.' }
                if (Test-Path -LiteralPath $draft) { throw "Refusing to overwrite draft inputs: $draft" }
                $topHelp = Invoke-PythonText @('-B','scripts/prepare_expanded_data.py','--help')
                if ($topHelp -notmatch 'stage-inputs') { Write-Result 'WAITING_SAT05' 'prepare_expanded_data.py has no stage-inputs command yet. Current generate command creates public witnesses with SAT, so it is not used as a fallback.'; return 3 }
                $stageHelp = Invoke-PythonText @('-B','scripts/prepare_expanded_data.py','stage-inputs','--help')
                if ($stageHelp -notmatch '--output' -or $stageHelp -notmatch 'DRAFT|draft') { Write-Result 'WAITING_SAT05' 'stage-inputs help does not document a DRAFT output path; no data command invoked.'; return 3 }
                $verifyHelp = Invoke-PythonText @('-B','scripts/prepare_expanded_data.py','verify-inputs','--help')
                if ($verifyHelp -notmatch '--dataset') { Write-Result 'WAITING_SAT05' 'verify-inputs help does not expose --dataset; no data command invoked.'; return 3 }
                Write-Result 'STAGE_INPUTS' 'Invoking the SAT05 stage-inputs API only; it must create source/input puzzles as DRAFT with solver_calls=0.'
                $stageText = Invoke-PythonText @('-B','scripts/prepare_expanded_data.py','stage-inputs','--output',$draft)
                $stageResult = $stageText | ConvertFrom-Json
                foreach ($phaseName in @('main','pilot')) {
                    $datasetPath = [string]$stageResult.$phaseName
                    if (-not $datasetPath) { throw "SAT05 stage-inputs omitted the $phaseName DRAFT dataset path." }
                    $verifyText = Invoke-PythonText @('-B','scripts/prepare_expanded_data.py','verify-inputs','--dataset',$datasetPath)
                    $verifyResult = $verifyText | ConvertFrom-Json
                    if ($verifyResult.status -ne 'PASS_INPUTS_ONLY' -or [int]$verifyResult.solver_calls -ne 0 -or $verifyResult.frozen -ne $false -or [int]$verifyResult.public_witness_pending -le 0) { throw "SAT05 $phaseName output did not verify as an unfrozen no-solver DRAFT." }
                    Write-Result 'DRAFT' ('phase={0}; path={1}; pending public witnesses={2}' -f $phaseName,$datasetPath,$verifyResult.public_witness_pending)
                }
                Write-Result 'PENDING' 'Witness, freeze, and runner admission remain pending.'
                return 0
            }
            'Prepare' {
                Assert-OperationalMatrix $Phase
                if (-not $Dataset) { $datasetId = if ($Phase -eq 'pilot') { 'expanded-pilot-20261019-v2' } else { 'expanded-20261019-v2' }; $Dataset = Join-Path $Root ('data/expanded/' + $datasetId) }
                if (-not $Experiment) { $name = if ($Phase -eq 'pilot') { 'pilot' } else { 'main' }; $Experiment = Join-Path $Root ('results/expanded/' + $name + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
                if (-not $Config) { $Config = Join-Path $Root ('configs/expanded/' + $Phase + '.json') }
                if (-not $Matrix) { $Matrix = Join-Path $Root 'configs/expanded/matrix.json' }
                $args = @('-B','scripts/run_expanded.py','prepare','--dataset',$Dataset,'--experiment',$Experiment,'--config',$Config,'--matrix',$Matrix,'--phase',$Phase)
                Invoke-PythonWithSolverThreads $args | Write-Output
                return 0
            }
            'Status' {
                if (-not $Experiment) { throw '-Status requires -Experiment.' }
                Invoke-PythonText @('-B','scripts/run_expanded.py','status','--experiment',$Experiment,'--json') | Write-Output
                return 0
            }
            'Pilot' {
                if (-not $Experiment) { throw '-Pilot requires -Experiment.' }
                Assert-OperationalMatrix 'pilot'
                Assert-DiskReserve $Experiment; $null = Test-ExperimentGate $Experiment
                $outcome = Invoke-RunnerMonitored @('pilot','--experiment',$Experiment,'--stop-starting-at',$StopStartingAt) $Experiment
                Write-Output ($outcome.Snapshot | ConvertTo-Json -Depth 30)
                return [int]$outcome.ExitCode
            }
            'Run' {
                if (-not $Experiment) { throw '-Run requires -Experiment.' }
                Assert-OperationalMatrix 'main'
                Assert-DiskReserve $Experiment; $null = Test-ExperimentGate $Experiment
                $outcome = Invoke-RunnerMonitored @('run','--experiment',$Experiment,'--stop-starting-at',$StopStartingAt) $Experiment
                $postCode = 0
                if (-not $DeferPostProcessing -and $outcome.ExitCode -in @(0,4)) { $postCode = Invoke-PostRun $Experiment $outcome.Snapshot }
                Write-Output ($outcome.Snapshot | ConvertTo-Json -Depth 30)
                if ($outcome.ExitCode -ne 0) { return [int]$outcome.ExitCode }
                return [int]$postCode
            }
            'Resume' {
                if (-not $Experiment -or -not $Reason) { throw '-Resume requires -Experiment and -Reason.' }
                $resumeManifest = Get-Content -LiteralPath (Join-Path $Experiment 'experiment.json') -Raw -Encoding UTF8 | ConvertFrom-Json
                Assert-OperationalMatrix ([string]$resumeManifest.phase)
                Assert-DiskReserve $Experiment; $null = Test-ExperimentGate $Experiment
                $outcome = Invoke-RunnerMonitored @('resume','--experiment',$Experiment,'--reason',$Reason,'--stop-starting-at',$StopStartingAt) $Experiment
                $postCode = 0
                $manifest = Get-Content -LiteralPath (Join-Path $Experiment 'experiment.json') -Raw -Encoding UTF8 | ConvertFrom-Json
                if (-not $DeferPostProcessing -and $manifest.phase -eq 'main' -and $outcome.ExitCode -in @(0,4)) { $postCode = Invoke-PostRun $Experiment $outcome.Snapshot }
                Write-Output ($outcome.Snapshot | ConvertTo-Json -Depth 30)
                if ($outcome.ExitCode -ne 0) { return [int]$outcome.ExitCode }
                return [int]$postCode
            }
            'Export' { if (-not $Experiment -or -not $ExportDirectory) { throw '-Export requires -Experiment and -ExportDirectory.' }; Invoke-PythonText @('-B','scripts/run_expanded.py','export','--experiment',$Experiment,'--output',$ExportDirectory,'--complete-blocks') | Write-Output; return 0 }
            'Analyze' { if (-not $ExportDirectory -or -not $AnalysisOutput) { throw '-Analyze requires -ExportDirectory and -AnalysisOutput.' }; Invoke-PythonText @('-B','scripts/analyze_expanded.py','--export',$ExportDirectory,'--output',$AnalysisOutput) | Write-Output; return 0 }
            'PrepareReport' { if (-not $AnalysisOutput) { throw '-PrepareReport requires -AnalysisOutput.' }; return (Invoke-ReportPreparation $AnalysisOutput $(if($Experiment){$Experiment}else{'expanded-report'})) }
            'TestArgvQuoting' { Test-StartProcessArgvRoundTrip; return 0 }
        }
    } catch { Write-Result 'STOP' $_.Exception.Message; return 5 }
    finally { if ($null -ne $pipelineLock) { $pipelineLock.Dispose() } }
    return 0
}

$exitCode = Invoke-Main
if ($exitCode -ne 0) { exit $exitCode }

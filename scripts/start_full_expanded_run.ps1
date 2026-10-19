<#
.SYNOPSIS
Fail-closed coordinator for the expanded local experiment.
.DESCRIPTION
Default is a read-only plan. -Execute is required for staging, witness finalization,
pilot, main, export, analysis, or report preparation. A root release approval and
owner command interfaces are checked before any source staging starts.
#>
[CmdletBinding()]
param(
    [switch]$Execute,
    [switch]$Resume,
    [switch]$TestWitnessLogSeparation,
    [string]$Experiment,
    [string]$Reason,
    [string]$StopStartingAt = '9999-12-31T23:59:59+00:00',
    [ValidateRange(5,600)][int]$PollSeconds = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Python = Join-Path $Root '.venv/Scripts/python.exe'
$Release = Join-Path $Root 'diagnostics/expansion/root-wave3/code-release.json'
$EvidenceDir = Join-Path $Root 'diagnostics/expansion/package/full-run'
$StageCli = Join-Path $Root 'scripts/prepare_expanded_data.py'
$WitnessCli = Join-Path $Root 'scripts/complete_expanded_witnesses.py'
$AuthorizeCli = Join-Path $Root 'scripts/authorize_expanded_local.py'
$RunnerCli = Join-Path $Root 'scripts/run_expanded.py'
$Analyzer = Join-Path $Root 'scripts/analyze_expanded.py'
$Report = Join-Path $Root 'report/prepare_expanded_report.py'
$Pipeline = Join-Path $Root 'scripts/local_expanded_pipeline.ps1'
$script:ContinueFullFlow = $false
$script:ReleaseHash = $null

function Say([string]$Kind,[string]$Message) { Write-Host ('[{0}] {1}' -f $Kind,$Message) }

function Invoke-PythonText([string[]]$PythonArguments) {
    $lines = & $script:Python -B @PythonArguments 2>&1
    $code = $LASTEXITCODE
    $text = ($lines | Out-String).Trim()
    if ($code -ne 0) { throw "Python command exit ${code}: $text" }
    return $text
}

function Invoke-WitnessAcquisition([string]$Phase,[string]$Draft,[string]$Evidence,[string]$Output) {
    $launcherLogs=Join-Path $script:EvidenceDir 'launcher-logs'
    New-Item -ItemType Directory -Path $launcherLogs -Force | Out-Null
    $stamp=Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $stdout=Join-Path $launcherLogs ($Phase+'-'+$stamp+'.stdout.json')
    $stderr=Join-Path $launcherLogs ($Phase+'-'+$stamp+'.stderr.log')
    $arguments=@('-B',$script:WitnessCli,'--dataset',$Draft,'--evidence-dir',$Evidence,'--output',$Output,
        '--code-release',$script:Release,'--progress-every','25','--execute')
    $quoted=($arguments | ForEach-Object { Quote-ProcessArg ([string]$_) }) -join ' '
    $process=Start-Process -FilePath $script:Python -ArgumentList $quoted -WorkingDirectory $Root -PassThru -NoNewWindow -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $database=Join-Path $Evidence 'witnesses.sqlite3'
    $statusCode=@'
import json, pathlib, sqlite3, sys
uri=pathlib.Path(sys.argv[1]).resolve().as_uri()+"?mode=ro"
c=sqlite3.connect(uri,uri=True,timeout=2); c.row_factory=sqlite3.Row
total=c.execute("select count(*) from inputs").fetchone()[0]
done=c.execute("select count(*) from attempts where state='FINISHED'").fetchone()[0]
active=c.execute("select count(*) from attempts where state='RUNNING'").fetchone()[0]
last=c.execute("select i.instance_id,a.state,a.raw_log from attempts a join inputs i using(instance_id) order by a.attempt_id desc limit 1").fetchone()
counts={r[0]:r[1] for r in c.execute("select admitted_status,count(*) from attempts where state='FINISHED' group by admitted_status")}
print(json.dumps({"inputs":total,"finished":done,"active":active,"last_instance":last["instance_id"] if last else None,"last_log":last["raw_log"] if last else None,"statuses":counts})); c.close()
'@
    Say 'WITNESS' ("phase={0}; dataset={1}; evidence/checkpoint={2}; stdout={3}" -f $Phase,$Draft,$Evidence,$stdout)
    while (-not $process.HasExited) {
        Start-Sleep -Seconds $PollSeconds
        $process.Refresh()
        if($process.HasExited){break}
        if(Test-Path -LiteralPath $database){
            try {
                $snapshotText=& $script:Python -B -c $statusCode $database 2>$null
                $snapshot=$snapshotText | ConvertFrom-Json
                Say 'WITNESS_PROGRESS' ('phase={0}; instances={1}/{2}; active={3}; last={4}; statuses={5}; checkpoint={6}' -f $Phase,$snapshot.finished,$snapshot.inputs,$snapshot.active,$snapshot.last_instance,($snapshot.statuses | ConvertTo-Json -Compress),$(if($snapshot.last_log){Join-Path $Evidence $snapshot.last_log}else{$Evidence}))
            } catch { Say 'WITNESS_PROGRESS' ("phase={0}; checkpoint initializing/locked; evidence={1}" -f $Phase,$Evidence) }
        } else { Say 'WITNESS_PROGRESS' ("phase={0}; initializing checkpoint at {1}" -f $Phase,$database) }
    }
    $process.WaitForExit()
    if(Test-Path -LiteralPath $stderr){$errorText=[System.IO.File]::ReadAllText($stderr).Trim();if($errorText){Say 'WITNESS_ERROR' $errorText}}
    if($process.ExitCode -ne 0){throw "SAT05 witness CLI exited $($process.ExitCode); checkpoint retained at $Evidence."}
    $finalLine=Get-Content -LiteralPath $stdout -Encoding UTF8 | Where-Object {-not [string]::IsNullOrWhiteSpace($_)} | Select-Object -Last 1
    $result=$finalLine | ConvertFrom-Json
    if($result.state -ne 'COMPLETE' -or $result.admitted_status_counts.SAT -ne $result.public_inputs -or
       $result.code_release_sha256 -eq $null -or ($result.output_reusable -eq $false -and -not (Test-Path -LiteralPath $Output))){
        throw "SAT05 did not return a complete all-SAT checkpoint for phase $Phase; status=$($result.state); checkpoint retained at $Evidence."
    }
    Write-Output ($result | ConvertTo-Json -Depth 10)
    return $result
}

function Test-WitnessLogSeparation {
    $fixture=Join-Path $script:EvidenceDir ('log-separation-fixture-'+[guid]::NewGuid().ToString('N'))
    $logDir=Join-Path $fixture 'launcher-logs'
    $witnessDir=Join-Path $fixture 'witness-evidence'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $stdout=Join-Path $logDir 'fake.stdout.txt';$stderr=Join-Path $logDir 'fake.stderr.txt'
    $code='import json; print(json.dumps({"kind":"namespace-echo","solver_calls":0,"network_calls":0}))'
    $args=@('-B','-c',$code)
    $quoted=($args | ForEach-Object { Quote-ProcessArg ([string]$_) }) -join ' '
    $process=Start-Process -FilePath $script:Python -ArgumentList $quoted -WorkingDirectory $Root -PassThru -Wait -NoNewWindow -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    if($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $stdout) -or (Test-Path -LiteralPath $witnessDir)){
        throw 'Launcher log namespace fixture failed; fake logs must not create or populate witness evidence.'
    }
    $echo=Get-Content -LiteralPath $stdout -Raw -Encoding UTF8 | ConvertFrom-Json
    if($echo.kind -ne 'namespace-echo' -or $echo.solver_calls -ne 0 -or $echo.network_calls -ne 0){throw 'Fake process returned an unexpected namespace diagnostic.'}
    $receipt=[ordered]@{status='PASS';fake_process_exit=$process.ExitCode;launcher_logs=$logDir;witness_evidence_path=$witnessDir;
        witness_evidence_created=$false;solver_calls=0;network_calls=0;utc=[DateTimeOffset]::UtcNow.ToString('o')}
    $receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $fixture 'receipt.json') -Encoding UTF8
    Say 'NAMESPACE_TEST' ('PASS; fake logs={0}; witness evidence remained absent; receipt={1}' -f $logDir,(Join-Path $fixture 'receipt.json'))
}

function Get-HelpText([string]$Path,[string[]]$Prefix=@()) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required owner CLI missing: $Path" }
    $args = @('-B',$Path) + $Prefix + @('--help')
    $text = & $script:Python @args 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { throw "Owner help failed: $Path $($Prefix -join ' ') --help" }
    return $text
}

function Assert-ReleaseApproval {
    if (-not (Test-Path -LiteralPath $Release -PathType Leaf)) { throw "Root code release missing: $Release" }
    $release = Get-Content -LiteralPath $Release -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($release.approved_explicit_terminal_execution -ne $true) { throw 'Root code release does not explicitly approve terminal execution.' }
    if (-not $release.source_sha256) { throw 'Root code release has no source_sha256 evidence map.' }
    foreach ($property in $release.source_sha256.PSObject.Properties) {
        $relative = [string]$property.Name
        if ([System.IO.Path]::IsPathRooted($relative) -or $relative.Contains('..')) { throw "Unsafe code-release hash path: $relative" }
        $path = [System.IO.Path]::GetFullPath((Join-Path $Root $relative))
        $prefix = $Root.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
        if (-not $path.StartsWith($prefix,[System.StringComparison]::OrdinalIgnoreCase)) { throw "Code-release path escapes project: $relative" }
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Code-release evidence file missing: $relative" }
        $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne ([string]$property.Value).ToLowerInvariant()) { throw "Code-release source hash mismatch: $relative" }
    }
    if (-not $release.regression -or $release.regression.scope -ne 'full' -or
        [int]$release.regression.tests -le 0 -or [int]$release.regression.failures -ne 0 -or
        [int]$release.regression.errors -ne 0 -or [int]$release.regression.skipped -ne 0) { throw 'Code release lacks clean full-regression evidence.' }
    if($release.existing_two_pdfs_unchanged -ne $true -or [int]$release.protected_execution_files -le 0 -or
       [int]$release.protected_data_files -le 0){throw 'Code release lacks frozen-v1/PDF preservation evidence.'}
    foreach($requiredPath in @('scripts/start_full_expanded_run.ps1','scripts/local_expanded_pipeline.ps1',
        'scripts/complete_expanded_witnesses.py','scripts/authorize_expanded_local.py',
        'scripts/prepare_expanded_data.py','scripts/run_expanded.py','scripts/analyze_expanded.py',
        'report/prepare_expanded_report.py')) {
        if(@($release.source_sha256.PSObject.Properties | ForEach-Object {$_.Name}) -notcontains $requiredPath){throw "Code release does not hash required workflow source: $requiredPath"}
    }
    $regressionPath=[string]$release.regression.path
    if([System.IO.Path]::IsPathRooted($regressionPath) -or $regressionPath.Contains('..')){throw 'Unsafe regression evidence path in code release.'}
    $regressionFile=[System.IO.Path]::GetFullPath((Join-Path $Root $regressionPath))
    if(-not (Test-Path -LiteralPath $regressionFile -PathType Leaf) -or
       (Get-FileHash -LiteralPath $regressionFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne ([string]$release.regression.sha256).ToLowerInvariant()) {
        throw 'Regression XML is absent or its SHA-256 differs from the code release.'
    }
    $settings=[System.Xml.XmlReaderSettings]::new();$settings.DtdProcessing=[System.Xml.DtdProcessing]::Prohibit;$settings.XmlResolver=$null
    $reader=[System.Xml.XmlReader]::Create($regressionFile,$settings)
    try {$suite=[System.Xml.XmlDocument]::new();$suite.XmlResolver=$null;$suite.Load($reader)} finally {$reader.Dispose()}
    $cases=@($suite.SelectNodes('//*[local-name()="testcase"]'))
    $badCases=@($suite.SelectNodes('//*[local-name()="failure" or local-name()="error" or local-name()="skipped"]'))
    if($cases.Count -ne [int]$release.regression.tests -or $badCases.Count -ne 0){throw 'Root code release regression XML has failed/skipped/mismatched test evidence.'}
    foreach($node in @($suite.SelectNodes('//*[local-name()="testsuite" or local-name()="testsuites"]'))){
        foreach($key in @('failures','errors','skipped')){if([int]$node.GetAttribute($key) -ne 0){throw "Regression suite declares ${key}: $($node.GetAttribute($key))"}}
    }
    foreach($pair in @(
        @{path='results/raw/main-20261016-01/execution-freeze.json';count=$release.protected_execution_files},
        @{path='data/freeze.json';count=$release.protected_data_files}
    )){
        $freeze=Get-Content -LiteralPath (Join-Path $Root $pair.path) -Raw -Encoding UTF8 | ConvertFrom-Json
        if(@($freeze.files_sha256.PSObject.Properties).Count -ne [int]$pair.count){throw "Protected freeze count mismatch: $($pair.path)"}
        foreach($property in $freeze.files_sha256.PSObject.Properties){
            $file=[System.IO.Path]::GetFullPath((Join-Path $Root ([string]$property.Name)))
            if(-not (Test-Path -LiteralPath $file -PathType Leaf) -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne ([string]$property.Value).ToLowerInvariant()){
                throw "Protected v1 hash changed: $($property.Name)"
            }
        }
    }
    foreach($pdf in @(
        @{name='sudoku-vi.pdf';sha256='e0e3a294639371c5dc07398afd02cbac1afcc6a527cea02bc4ec1464ddd0fd64'},
        @{name='sudoku-en.pdf';sha256='bae7455b3584612371c7c51ce533369a40b98795841f974d7be4c63cfe823075'}
    )){
        $pdfPath=Join-Path $Root ('report/output/pdf/'+$pdf.name)
        if((Get-FileHash -LiteralPath $pdfPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pdf.sha256){throw "Protected PDF hash changed: $($pdf.name)"}
    }
    $script:ReleaseHash=(Get-FileHash -LiteralPath $script:Release -Algorithm SHA256).Hash.ToLowerInvariant()
    return $release
}

function Assert-OwnerInterfaces {
    $stageHelp = Get-HelpText $StageCli
    if ($stageHelp -notmatch 'stage-inputs' -or $stageHelp -notmatch 'verify-inputs') { throw 'SAT05 stage-inputs/verify-inputs interface is unavailable.' }
    $witnessHelp = Get-HelpText $WitnessCli
    foreach ($required in @('--dataset','--evidence-dir','--output','--code-release','--progress-every','--execute')) {
        if ($witnessHelp -notmatch [regex]::Escape($required)) { throw "SAT05 witness completion CLI is missing $required." }
    }
    $witnessModule=Get-Content -LiteralPath (Join-Path $Root 'src/sudoku/expanded_witnesses.py') -Raw -Encoding UTF8
    if ($witnessHelp -notmatch '30s\s+hard\s+guard' -or $witnessModule -notmatch 'WITNESS_CUTOFF_SECONDS\s*=\s*30\.0' -or
        $witnessModule -notmatch 'Witness acquisition, not benchmark observations') { throw 'SAT05 witness implementation does not pin the separate 30-second acquisition scope.' }
    $authorizeHelp = Get-HelpText $AuthorizeCli
    foreach ($required in @('--experiment','--code-release','--pilot-experiment')) {
        if ($authorizeHelp -notmatch [regex]::Escape($required)) { throw "SAT07 authorizer/auditor CLI is missing $required." }
    }
    $prepareHelp = Get-HelpText $RunnerCli @('prepare')
    if ($prepareHelp -notmatch '--dataset' -or $prepareHelp -notmatch '--phase') { throw 'Runner prepare interface is incomplete.' }
    $runHelp = Get-HelpText $RunnerCli @('run')
    $pilotHelp = Get-HelpText $RunnerCli @('pilot')
    $resumeHelp = Get-HelpText $RunnerCli @('resume')
    $exportHelp = Get-HelpText $RunnerCli @('export')
    if ($runHelp -notmatch '--stop-starting-at' -or $pilotHelp -notmatch '--stop-starting-at' -or $resumeHelp -notmatch '--reason' -or $exportHelp -notmatch '--complete-blocks') { throw 'Runner execution/recovery/export CLI does not match the accepted contract.' }
    $analysisHelp = Get-HelpText $Analyzer
    if ($analysisHelp -notmatch '--export' -or $analysisHelp -notmatch '--output') { throw 'SAT08 analyzer interface is unavailable.' }
    $reportHelp = Get-HelpText $Report
    foreach ($required in @('--analysis','--output','--receipt-sha256')) {
        if ($reportHelp -notmatch [regex]::Escape($required)) { throw "SAT09 report CLI is missing $required." }
    }
    return $true
}

function Invoke-LocalPipeline([string[]]$Arguments) {
    $ps = [System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
    $all = @('-NoProfile','-File',$script:Pipeline) + $Arguments
    $quoted = ($all | ForEach-Object { Quote-ProcessArg ([string]$_) }) -join ' '
    $process = Start-Process -FilePath $ps -ArgumentList $quoted -WorkingDirectory $Root -PassThru -Wait -NoNewWindow
    if ($process.ExitCode -ne 0) { throw "local_expanded_pipeline.ps1 exited $($process.ExitCode); stopping the full flow." }
}

function Quote-ProcessArg([string]$Value) {
    $builder=[System.Text.StringBuilder]::new(); [void]$builder.Append('"'); $slashes=0
    foreach($char in $Value.ToCharArray()) {
        if($char -eq '\') { $slashes++; continue }
        if($char -eq '"') { [void]$builder.Append(('\' * (2*$slashes+1))); [void]$builder.Append('"') }
        else { if($slashes -gt 0){[void]$builder.Append(('\' * $slashes))}; [void]$builder.Append($char) }
        $slashes=0
    }
    if($slashes -gt 0){[void]$builder.Append(('\' * (2*$slashes)))}
    [void]$builder.Append('"'); return $builder.ToString()
}

function Write-RunAudit([string]$State,[string]$Detail) {
    New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
    $path=Join-Path $EvidenceDir 'run-audit.jsonl'
    $record=[ordered]@{utc=[DateTimeOffset]::UtcNow.ToString('o');state=$State;detail=$Detail;stop_starting_at=$StopStartingAt;threads=1}
    Add-Content -LiteralPath $path -Value ($record | ConvertTo-Json -Compress) -Encoding UTF8
}

function Save-FullCheckpoint([System.Collections.IDictionary]$Checkpoint) {
    $Checkpoint.updated_utc=[DateTimeOffset]::UtcNow.ToString('o')
    $path=Join-Path $EvidenceDir 'full-run-checkpoint.json'; $temp=$path+'.tmp'
    $Checkpoint | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $temp -Encoding UTF8
    Move-Item -LiteralPath $temp -Destination $path -Force
}

function Read-FullCheckpoint {
    $path=Join-Path $EvidenceDir 'full-run-checkpoint.json'
    if(-not (Test-Path -LiteralPath $path -PathType Leaf)){throw "No full-run checkpoint exists: $path"}
    $checkpoint=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json -AsHashtable
    if($checkpoint.schema_version -ne 1 -or $checkpoint.run_id -notmatch '^\d{8}-\d{6}$' -or $checkpoint.state -eq 'COMPLETE'){throw 'Full-run checkpoint is invalid or already complete.'}
    $expected=@{
        draft_root=(Join-Path $Root ('data/expanded-inputs/wave3-'+$checkpoint.run_id))
        dataset_root=(Join-Path $Root ('data/expanded/wave3-'+$checkpoint.run_id))
        pilot_experiment=(Join-Path $Root ('diagnostics/expansion/pilot/wave3-'+$checkpoint.run_id+'-pilot'))
        main_experiment=(Join-Path $Root ('results/expanded/wave3-'+$checkpoint.run_id+'-main'))
        main_dataset=(Join-Path (Join-Path $Root ('data/expanded/wave3-'+$checkpoint.run_id)) 'main')
        pilot_dataset=(Join-Path (Join-Path $Root ('data/expanded/wave3-'+$checkpoint.run_id)) 'pilot')
        main_draft=(Join-Path (Join-Path $Root ('data/expanded-inputs/wave3-'+$checkpoint.run_id)) 'expanded-20261019-v2')
        pilot_draft=(Join-Path (Join-Path $Root ('data/expanded-inputs/wave3-'+$checkpoint.run_id)) 'expanded-pilot-20261019-v2')
    }
    foreach($name in $expected.Keys){
        if([System.IO.Path]::GetFullPath([string]$checkpoint[$name]) -ne [System.IO.Path]::GetFullPath([string]$expected[$name])){throw "Full-run checkpoint namespace mismatch: $name"}
    }
    return $checkpoint
}

function Get-ExperimentStatus([string]$Path) {
    return (Invoke-PythonText @('-B',$script:RunnerCli,'status','--experiment',$Path,'--json') | ConvertFrom-Json)
}

function Assert-OrCreateGate([string]$ExperimentPath,[string[]]$RequiredGates,[string[]]$AuthorizerArgs) {
    $manifest=Get-Content -LiteralPath (Join-Path $ExperimentPath 'experiment.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $gatePath=Join-Path $Root ([string]$manifest.gate_refs_path)
    if(-not (Test-Path -LiteralPath $gatePath -PathType Leaf)){$args=@('-B',$script:AuthorizeCli)+$AuthorizerArgs;$null=Invoke-PythonText $args}
    Assert-RootGate $ExperimentPath $RequiredGates
}

function Enter-FullRunLock {
    New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
    $path=Join-Path $EvidenceDir 'full-run.lock'
    try {$stream=[System.IO.File]::Open($path,[System.IO.FileMode]::OpenOrCreate,[System.IO.FileAccess]::ReadWrite,[System.IO.FileShare]::None)}
    catch { throw 'Another full expanded workflow holds the global collector lock.' }
    $stream.SetLength(0)
    $bytes=[System.Text.Encoding]::UTF8.GetBytes(('pid={0}; started={1:o}' -f $PID,[DateTimeOffset]::Now))
    $stream.Write($bytes,0,$bytes.Length);$stream.Flush()
    return $stream
}

function Set-LauncherKeepAwake([bool]$Enabled) {
    if (-not ('ExpandedKeepAwake.Native' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace ExpandedKeepAwake {
    public static class Native {
        [DllImport("kernel32.dll", SetLastError=true)]
        public static extern uint SetThreadExecutionState(uint flags);
    }
}
'@
    }
    $flags = if ($Enabled) { [uint32]::Parse('2147483649') } else { [uint32]::Parse('2147483648') }
    $prior=[ExpandedKeepAwake.Native]::SetThreadExecutionState($flags)
    if($prior -eq 0){throw 'SetThreadExecutionState failed; no power-plan change was made.'}
}

function Invoke-Main {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { Say 'WAITING' "Python environment missing: $Python"; return 3 }
    $script:Python=$Python
    if($TestWitnessLogSeparation){if($Execute -or $Resume){throw '-TestWitnessLogSeparation cannot be combined with -Execute or -Resume.'};Test-WitnessLogSeparation;return 0}
    if (-not $Execute) {
        Say 'DRY_RUN' 'Full flow requires -Execute and the root code-release approval.'
        Say 'PLAN' 'Verify code-release hashes; verify owner CLIs; doctor/thread=1; stage DRAFT; witness/freeze both phases; prepare and authorize/run pilot; prepare and authorize/run main with pilot audit; export/analyze/prepare report.'
        foreach ($path in @($Release,$WitnessCli,$AuthorizeCli)) { Say $(if(Test-Path -LiteralPath $path){'AVAILABLE'}else{'WAITING'}) $path }
        Say 'RESUME' 'Full-flow checkpoint: add -Execute -Resume -Reason <reason>. Runner-only recovery also accepts -Experiment <path>; witness uses the same checkpoint namespace.'
        return 0
    }
    if ($Resume) {
        if (-not $Reason) { throw '-Resume requires -Reason.' }
        if ($Experiment) {
            $null=Assert-ReleaseApproval; $null=Assert-OwnerInterfaces
            $resumeLock=Enter-FullRunLock
            $envNames=@('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'); $old=@{}
            foreach($name in $envNames){$old[$name]=[Environment]::GetEnvironmentVariable($name);[Environment]::SetEnvironmentVariable($name,'1')}
            $awake=$false
            try {
                Set-LauncherKeepAwake $true; $awake=$true
                Say 'POWER' 'System sleep is inhibited for the launcher process only; connect the computer to power for this long run.'
                Write-RunAudit 'RESUME_START' ("experiment={0}; reason={1}" -f $Experiment,$Reason)
                Invoke-LocalPipeline @('-Resume','-Experiment',$Experiment,'-Reason',$Reason,'-StopStartingAt',$StopStartingAt,'-PollSeconds',[string]$PollSeconds)
                Write-RunAudit 'RESUME_FINISHED' ("experiment={0}" -f $Experiment)
            } finally { foreach($name in $envNames){[Environment]::SetEnvironmentVariable($name,$old[$name])};if($awake){Set-LauncherKeepAwake $false};$resumeLock.Dispose() }
            return 0
        }
        $script:ContinueFullFlow=$true
    }

    $null=Assert-ReleaseApproval
    $null=Assert-OwnerInterfaces
    $envNames=@('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'); $old=@()
    foreach($name in $envNames){$old+=,[pscustomobject]@{name=$name;value=[Environment]::GetEnvironmentVariable($name)};[Environment]::SetEnvironmentVariable($name,'1')}
    $lock=$null; $awake=$false
    try {
        $lock=Enter-FullRunLock
        Set-LauncherKeepAwake $true; $awake=$true
        Say 'POWER' 'System sleep is inhibited for the launcher process only; connect the computer to power for this long run.'
        Invoke-LocalPipeline @('-Doctor','-PythonPath',$Python)
        $matrix = Get-Content -LiteralPath (Join-Path $Root 'configs/expanded/matrix.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $eligible=@($matrix.rows | Where-Object {$_.eligible -eq $true})
        if (@($eligible | Where-Object {$_.threads -ne 1}).Count -gt 0) { throw 'Eligible solver matrix contains threads != 1.' }
        $checkpointPath=Join-Path $EvidenceDir 'full-run-checkpoint.json'
        if($script:ContinueFullFlow){
            $checkpoint=Read-FullCheckpoint
            if($checkpoint.release_sha256 -ne $script:ReleaseHash){throw 'Full-run checkpoint is bound to a different code release.'}
            $runId=[string]$checkpoint.run_id;$draftRoot=[string]$checkpoint.draft_root
            $datasetRoot=[string]$checkpoint.dataset_root;$pilotExp=[string]$checkpoint.pilot_experiment
            $mainExp=[string]$checkpoint.main_experiment
            Say 'RESUME_CHECKPOINT' ("run_id={0}; state={1}; draft={2}; pilot={3}; main={4}" -f $runId,$checkpoint.state,$draftRoot,$pilotExp,$mainExp)
        } else {
            if(Test-Path -LiteralPath $checkpointPath){throw 'A full-run checkpoint already exists; use -Execute -Resume -Reason <reason> to reuse it.'}
            $runId=Get-Date -Format 'yyyyMMdd-HHmmss'
            $draftRoot=Join-Path $Root ('data/expanded-inputs/wave3-'+$runId)
            $datasetRoot=Join-Path $Root ('data/expanded/wave3-'+$runId)
            $pilotExp=Join-Path $Root ('diagnostics/expansion/pilot/wave3-'+$runId+'-pilot')
            $mainExp=Join-Path $Root ('results/expanded/wave3-'+$runId+'-main')
            foreach($path in @($draftRoot,$datasetRoot,$pilotExp,$mainExp)){if(Test-Path -LiteralPath $path){throw "Refusing to overwrite existing checkpoint: $path"}}
            $checkpoint=@{schema_version=1;run_id=$runId;release_sha256=$script:ReleaseHash;state='INITIALIZING';
                draft_root=$draftRoot;dataset_root=$datasetRoot;pilot_experiment=$pilotExp;main_experiment=$mainExp;
                main_dataset=(Join-Path $datasetRoot 'main');pilot_dataset=(Join-Path $datasetRoot 'pilot');
                main_draft=(Join-Path $draftRoot 'expanded-20261019-v2');pilot_draft=(Join-Path $draftRoot 'expanded-pilot-20261019-v2')}
            Save-FullCheckpoint $checkpoint
            Write-RunAudit 'FLOW_START' ("release={0}; run_id={1}" -f $Release,$runId)
        }
        Say 'CHECKPOINT' ('draft={0}; datasets={1}; pilot={2}; main={3}; audit={4}' -f $draftRoot,$datasetRoot,$pilotExp,$mainExp,$EvidenceDir)

        $drafts=@{main=[string]$checkpoint.main_draft;pilot=[string]$checkpoint.pilot_draft}
        if($checkpoint.state -eq 'INITIALIZING'){
            if(Test-Path -LiteralPath $draftRoot){
                foreach($phase in @('main','pilot')){
                    if(-not (Test-Path -LiteralPath $drafts[$phase])){throw "Interrupted SAT05 staging left an incomplete namespace at $draftRoot; preserving it for owner review."}
                    $verified=(Invoke-PythonText @('-B',$StageCli,'verify-inputs','--dataset',$drafts[$phase]) | ConvertFrom-Json)
                    if($verified.status -ne 'PASS_INPUTS_ONLY' -or $verified.solver_calls -ne 0 -or $verified.frozen -ne $false){throw "Existing $phase DRAFT did not pass input-only verification."}
                }
            } else {
                Say 'PHASE' 'Stage inputs as main/pilot DRAFT datasets.'
                $stageResult=Invoke-PythonText @('-B',$StageCli,'stage-inputs','--output',$draftRoot) | ConvertFrom-Json
                foreach($phase in @('main','pilot')){
                    if([System.IO.Path]::GetFullPath([string]$stageResult.$phase) -ne [System.IO.Path]::GetFullPath($drafts[$phase])){throw "SAT05 stage-inputs returned an unexpected $phase DRAFT identity/path."}
                }
                foreach($phase in @('main','pilot')){
                    if(-not (Test-Path -LiteralPath $drafts[$phase])){throw "SAT05 stage-inputs omitted the $phase DRAFT directory."}
                    $verified=(Invoke-PythonText @('-B',$StageCli,'verify-inputs','--dataset',$drafts[$phase]) | ConvertFrom-Json)
                    if($verified.status -ne 'PASS_INPUTS_ONLY' -or $verified.solver_calls -ne 0 -or $verified.frozen -ne $false -or [int]$verified.public_witness_pending -le 0){throw "SAT05 $phase DRAFT did not pass input-only verification."}
                }
            }
            $checkpoint.state='STAGED';Save-FullCheckpoint $checkpoint
        }
        $frozen=@{main=[string]$checkpoint.main_dataset;pilot=[string]$checkpoint.pilot_dataset}
        foreach($phase in @('main','pilot')) {
            Say 'PHASE' ("Verify DRAFT and acquire/finalize {0} public witnesses." -f $phase)
            $draft=[string]$drafts[$phase]
            if(-not $draft -or -not (Test-Path -LiteralPath $draft)){throw "SAT05 stage-inputs omitted the $phase DRAFT directory."}
            $verified=(Invoke-PythonText @('-B',$StageCli,'verify-inputs','--dataset',$draft) | ConvertFrom-Json)
            if($verified.status -ne 'PASS_INPUTS_ONLY' -or $verified.solver_calls -ne 0 -or $verified.frozen -ne $false -or $verified.public_witness_pending -le 0){throw "SAT05 $phase DRAFT did not pass input-only verification."}
            $output=Join-Path $datasetRoot $phase
            $witnessEvidence=Join-Path $EvidenceDir ('witness-'+$phase+'-'+$runId)
            if(Test-Path -LiteralPath $output){
                $frozenCheck=(Invoke-PythonText @('-B',$StageCli,'verify','--dataset',$output) | ConvertFrom-Json)
            } else {
                $witnessResult=Invoke-WitnessAcquisition $phase $draft $witnessEvidence $output
                $frozenCheck=(Invoke-PythonText @('-B',$StageCli,'verify','--dataset',$output) | ConvertFrom-Json)
            }
            $datasetCount=($frozenCheck.counts.PSObject.Properties.Value | Measure-Object -Sum).Sum
            if($frozenCheck.status -ne 'PASS' -or $frozenCheck.solver_calls -ne 0 -or
               $frozenCheck.all_witness_check_pass -ne $true -or $frozenCheck.witnesses_checked -ne $datasetCount){
                throw "SAT05 finalized $phase dataset did not verify every frozen witness."
            }
            $checkpoint.state=if($phase -eq 'main'){'MAIN_FROZEN'}else{'BOTH_FROZEN'};Save-FullCheckpoint $checkpoint
        }

        Say 'PHASE' ('Prepare and authorize pilot: {0}' -f $pilotExp)
        if(-not (Test-Path -LiteralPath (Join-Path $pilotExp 'experiment.json'))){
            Invoke-LocalPipeline @('-Prepare','-Phase','pilot','-Dataset',$frozen.pilot,'-Experiment',$pilotExp,'-StopStartingAt',$StopStartingAt)
        }
        $checkpoint.state='PILOT_PREPARED';Save-FullCheckpoint $checkpoint
        Assert-OrCreateGate $pilotExp @('dataset','qa','preflight') @('--experiment',$pilotExp,'--code-release',$Release)
        $checkpoint.state='PILOT_AUTHORIZED';Save-FullCheckpoint $checkpoint
        Assert-RootGate $pilotExp @('dataset','qa','preflight')
        Say 'PHASE' ('Run pilot 164 jobs: {0}' -f $pilotExp)
        $pilotStatus=Get-ExperimentStatus $pilotExp
        if($pilotStatus.state -in @('PREPARED','READY')){
            Invoke-LocalPipeline @('-Pilot','-Experiment',$pilotExp,'-StopStartingAt',$StopStartingAt,'-PollSeconds',[string]$PollSeconds)
            $pilotStatus=Get-ExperimentStatus $pilotExp
        } elseif($pilotStatus.state -eq 'PAUSED' -and $script:ContinueFullFlow){
            Invoke-LocalPipeline @('-Resume','-Experiment',$pilotExp,'-Reason',$Reason,'-StopStartingAt',$StopStartingAt,'-PollSeconds',[string]$PollSeconds)
            $pilotStatus=Get-ExperimentStatus $pilotExp
        } elseif($pilotStatus.state -notin @('COMPLETE','COMPLETED')){throw "Pilot checkpoint is $($pilotStatus.state); refusing to launch or recover an active/orphan attempt without owner proof."}
        $pilotIndex=Get-Content -LiteralPath (Join-Path $pilotExp 'dataset-index.json') -Raw -Encoding UTF8 | ConvertFrom-Json -AsHashtable
        $pilotBlocks=@($pilotIndex.batches).Count
        if($pilotStatus.state -notin @('COMPLETE','COMPLETED') -or $pilotStatus.completed_jobs -ne 164 -or
           $pilotStatus.completed_blocks -ne $pilotBlocks -or
           $pilotStatus.qa_complete_blocks -ne $pilotBlocks){throw 'Pilot is not fully executed and QA-complete; main authorization is withheld.'}
        $checkpoint.state='PILOT_COMPLETE';Save-FullCheckpoint $checkpoint

        Say 'PHASE' ('Prepare and pilot-audit main: {0}' -f $mainExp)
        if(-not (Test-Path -LiteralPath (Join-Path $mainExp 'experiment.json'))){
            Invoke-LocalPipeline @('-Prepare','-Phase','main','-Dataset',$frozen.main,'-Experiment',$mainExp,'-StopStartingAt',$StopStartingAt)
        }
        $checkpoint.state='MAIN_PREPARED';Save-FullCheckpoint $checkpoint
        Assert-OrCreateGate $mainExp @('dataset','qa','preflight','pilot','execution_freeze') @('--experiment',$mainExp,'--pilot-experiment',$pilotExp,'--code-release',$Release)
        $checkpoint.state='MAIN_AUTHORIZED';Save-FullCheckpoint $checkpoint
        Assert-RootGate $mainExp @('dataset','qa','preflight','pilot','execution_freeze')
        Say 'PHASE' ('Run main 330000 jobs, then export/analyze/report: {0}' -f $mainExp)
        $mainStatus=Get-ExperimentStatus $mainExp
        if($mainStatus.state -in @('PREPARED','READY')){
            Invoke-LocalPipeline @('-Run','-Experiment',$mainExp,'-StopStartingAt',$StopStartingAt,'-PollSeconds',[string]$PollSeconds,'-DeferPostProcessing')
            $mainStatus=Get-ExperimentStatus $mainExp
        } elseif($mainStatus.state -eq 'PAUSED' -and $script:ContinueFullFlow){
            Invoke-LocalPipeline @('-Resume','-Experiment',$mainExp,'-Reason',$Reason,'-StopStartingAt',$StopStartingAt,'-PollSeconds',[string]$PollSeconds,'-DeferPostProcessing')
            $mainStatus=Get-ExperimentStatus $mainExp
        } elseif($mainStatus.state -notin @('COMPLETE','COMPLETED')){throw "Main checkpoint is $($mainStatus.state); refusing to launch or recover an active/orphan attempt without owner proof."}
        $mainIndex=Get-Content -LiteralPath (Join-Path $mainExp 'dataset-index.json') -Raw -Encoding UTF8 | ConvertFrom-Json -AsHashtable
        $mainBlocks=@($mainIndex.batches).Count
        if($mainStatus.state -notin @('COMPLETE','COMPLETED') -or [int]$mainStatus.completed_jobs -ne 330000 -or
           $mainStatus.completed_blocks -ne $mainBlocks -or $mainStatus.qa_complete_blocks -ne $mainBlocks){
            throw 'Main execution/QA is incomplete; no full-report completion is claimed.'
        }
        Invoke-FinalResults $mainExp $runId $checkpoint
        $checkpoint.state='COMPLETE';Save-FullCheckpoint $checkpoint
        Write-RunAudit 'FLOW_FINISHED' ("main_experiment={0}; pilot_experiment={1}" -f $mainExp,$pilotExp)
        return 0
    } catch {
        Write-RunAudit 'FLOW_STOPPED' $_.Exception.Message
        Say 'HALTED' $_.Exception.Message
        return 5
    } finally {
        if($awake){Set-LauncherKeepAwake $false}
        if($null -ne $lock){$lock.Dispose()}
        foreach($entry in $old){[Environment]::SetEnvironmentVariable($entry.name,$entry.value)}
    }
}

function Assert-RootGate([string]$ExperimentPath,[string[]]$RequiredGates) {
    $manifest=Get-Content -LiteralPath (Join-Path $ExperimentPath 'experiment.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $gatePath=[System.IO.Path]::GetFullPath((Join-Path $Root ([string]$manifest.gate_refs_path)))
    if(-not (Test-Path -LiteralPath $gatePath -PathType Leaf)){throw "Owner did not create root gate file: $gatePath"}
    $gate=Get-Content -LiteralPath $gatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if($gate.experiment_id -ne $manifest.experiment_id -or $gate.scientific_sha256 -ne $manifest.scientific_sha256){throw 'Root gate subject does not match experiment.'}
    foreach($name in $RequiredGates){
        $ref=$gate.gates.$name
        if($ref.accepted_by -ne 'root' -or $ref.accepted -ne $true){throw "Root has not accepted gate: $name"}
        if($ref.code_release_sha256 -ne $script:ReleaseHash){throw "Root gate $name is bound to a different code release."}
        if([System.IO.Path]::IsPathRooted([string]$ref.path) -or ([string]$ref.path).Contains('..')){throw "Unsafe root gate evidence path: $name"}
        $evidencePath=[System.IO.Path]::GetFullPath((Join-Path $Root ([string]$ref.path)))
        $rootPrefix=$Root.TrimEnd([System.IO.Path]::DirectorySeparatorChar)+[System.IO.Path]::DirectorySeparatorChar
        if(-not $evidencePath.StartsWith($rootPrefix,[System.StringComparison]::OrdinalIgnoreCase)){throw "Gate evidence escapes project root: $name"}
        if(-not (Test-Path -LiteralPath $evidencePath -PathType Leaf)){throw "Accepted gate evidence missing: $name"}
        $digest=(Get-FileHash -LiteralPath $evidencePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if($digest -ne ([string]$ref.sha256).ToLowerInvariant()){throw "Accepted gate evidence hash mismatch: $name"}
    }
}

function Invoke-FinalResults([string]$ExperimentPath,[string]$RunId,[hashtable]$Checkpoint) {
    $exportDir=Join-Path $Root ('results/expanded-exports/wave3-'+$RunId+'-complete')
    $analysisDir=Join-Path $Root ('results/expanded-analysis/wave3-'+$RunId+'-complete')
    $reportDir=Join-Path $Root ('report/expanded-prepared/wave3-'+$RunId+'-complete')
    if(Test-Path -LiteralPath $exportDir){
        if(-not (Test-Path -LiteralPath (Join-Path $exportDir 'export.json'))){throw "Incomplete existing export checkpoint: $exportDir"}
    } else {
        Say 'PHASE' ("Export QA-complete blocks to {0}" -f $exportDir)
        $null=Invoke-PythonText @('-B',$script:RunnerCli,'export','--experiment',$ExperimentPath,'--output',$exportDir,'--complete-blocks')
    }
    if(Test-Path -LiteralPath $analysisDir){
        if(-not (Test-Path -LiteralPath (Join-Path $analysisDir 'summary.json'))){throw "Incomplete existing analysis checkpoint: $analysisDir"}
    } else {
        Say 'PHASE' ("Analyze immutable complete-block export to {0}" -f $analysisDir)
        $null=Invoke-PythonText @('-B',$script:Analyzer,'--export',$exportDir,'--output',$analysisDir)
    }
    $summary=Get-Content -LiteralPath (Join-Path $analysisDir 'summary.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if($summary.report_ready -ne $true -or $summary.phase -ne 'main' -or $summary.artificial -ne $false -or $summary.label -ne 'COMPLETE_BLOCKS'){
        throw "Analysis is not full real-main report-ready; retained at $analysisDir. No full-results package claimed."
    }
    $receipt=Join-Path $analysisDir 'analysis-hashes.json'
    if(-not (Test-Path -LiteralPath $receipt -PathType Leaf)){throw "SAT08 analysis receipt missing: $receipt"}
    if(Test-Path -LiteralPath $reportDir){
        $manifestPath=Join-Path $reportDir 'manifest.json'
        if(-not (Test-Path -LiteralPath $manifestPath)){throw "Incomplete existing report package checkpoint: $reportDir"}
        $package=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } else {
        $receiptHash=(Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash.ToLowerInvariant()
        New-Item -ItemType Directory -Path (Split-Path -Path $reportDir -Parent) -Force | Out-Null
        Say 'PHASE' ("Prepare native report package to {0}" -f $reportDir)
        $null=Invoke-PythonText @('-B',$script:Report,'--analysis',$analysisDir,'--output',$reportDir,'--analysis-receipt',$receipt,'--receipt-sha256',$receiptHash)
        $package=Get-Content -LiteralPath (Join-Path $reportDir 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    if($package.package_kind -ne 'REAL_MAIN_REPORT_PACKAGE' -or $package.report_ready -ne $true -or
       $package.artificial -ne $false -or $package.experiment_id -ne $summary.experiment_id -or
       [int]$package.metrics.ExpandedTargetPuzzles -ne 16000 -or [int]$package.metrics.ExpandedTargetJobs -ne 330000){
        throw "Report package does not validate the complete 16,000-puzzle/330,000-job target: $reportDir"
    }
    $Checkpoint.export_dir=$exportDir;$Checkpoint.analysis_dir=$analysisDir;$Checkpoint.report_dir=$reportDir
    $Checkpoint.state='RESULTS_PACKAGED';Save-FullCheckpoint $Checkpoint
    Say 'REPORT_READY' ("experiment={0}; puzzles=16000; jobs=330000; package={1}" -f $summary.experiment_id,$reportDir)
}

$code=try { Invoke-Main } catch { Say 'HALTED' $_.Exception.Message; 5 }
if($code -ne 0){exit $code}

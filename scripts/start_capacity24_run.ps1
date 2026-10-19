<# Visible monitor for the explicitly authorized parallel throughput profile. #>
[CmdletBinding()]
param([switch]$Execute,[int]$Workers=24)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location $projectRoot
$python=Join-Path $projectRoot '.venv/Scripts/python.exe'
$experiment=Join-Path $projectRoot 'results/expanded/wave3-20261019-212023-main'
$authorization=Join-Path $projectRoot 'diagnostics/expansion/root-wave3/capacity-production24-authorization.json'
$stopFile=Join-Path $projectRoot 'diagnostics/expansion/capacity-production-stop.request'
if(-not $Execute){Write-Host 'PLAN ONLY:24 guarded workers, one SQLite writer; one selected repetition, previous results preserved. Add -Execute.';return}
if($Workers -ne 24){throw 'This reviewed terminal profile is authorized for exactly24 workers.'}
$authorizationHash=(Get-FileHash -LiteralPath $authorization -Algorithm SHA256).Hash.ToLowerInvariant()
if(Test-Path -LiteralPath $stopFile){throw "Stop request exists: $stopFile. Resolve explicitly before resume."}
$logRoot=Join-Path $projectRoot 'diagnostics/expansion/capacity-production'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$stdout=Join-Path $logRoot ($stamp+'.stdout.json')
$stderr=Join-Path $logRoot ($stamp+'.stderr.log')
function Quote-ParallelArgument([string]$Value){
 $builder=[Text.StringBuilder]::new();[void]$builder.Append('"');$slashes=0
 foreach($char in $Value.ToCharArray()){
  if($char -eq '\'){$slashes++;continue}
  if($char -eq '"'){[void]$builder.Append(('\'*(2*$slashes+1)));[void]$builder.Append('"')}
  else{if($slashes){[void]$builder.Append(('\'*$slashes))};[void]$builder.Append($char)}
  $slashes=0
 }
 if($slashes){[void]$builder.Append(('\'*(2*$slashes)))}
 [void]$builder.Append('"');$builder.ToString()
}
$nativeCode=@"
using System.Runtime.InteropServices;
public static class ParallelAwake {
 [DllImport("kernel32.dll",SetLastError=true)] public static extern uint SetThreadExecutionState(uint flags);
}
"@
Add-Type -TypeDefinition $nativeCode
$awake=[ParallelAwake]::SetThreadExecutionState([uint32]::Parse('2147483649'))
if(-not $awake){throw 'Could not inhibit system sleep'}
$envKeys=@('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS');$saved=@{}
foreach($key in $envKeys){$saved[$key]=[Environment]::GetEnvironmentVariable($key);[Environment]::SetEnvironmentVariable($key,'1')}
$statusCode=@"
import json,pathlib,sqlite3,sys
c=sqlite3.connect((pathlib.Path(sys.argv[1])/'experiment.sqlite3').resolve().as_uri()+'?mode=ro',uri=True,timeout=3)
print(json.dumps({'state':c.execute('select state from experiment').fetchone()[0],'done':c.execute('select count(*) from primary_attempt p join jobs j using(job_id) where j.repetition=1').fetchone()[0],'active':c.execute("select count(*) from attempts a join jobs j using(job_id) where a.state='RUNNING' and j.repetition=1").fetchone()[0],'counts':dict(c.execute('select r.status,count(*) from primary_attempt p join results r using(attempt_id) join jobs j using(job_id) where j.repetition=1 group by r.status'))}));c.close()
"@
try {
 $pythonArguments=@('-B','scripts/run_expanded_capacity_fast.py','--experiment',$experiment,'--workers',[string]$Workers,'--authorized-workers-max','100','--min-available-ram-mb','6144','--worker-memory-reserve-mb','256','--repetition','1','--execute','--authorization',$authorization,'--authorization-sha256',$authorizationHash,'--stop-starting-at','9999-12-31T23:59:59+00:00','--stop-file',$stopFile)
 $line=($pythonArguments | ForEach-Object {Quote-ParallelArgument ([string]$_)}) -join ' '
 $child=Start-Process -FilePath $python -ArgumentList $line -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
 Write-Host "[PARALLEL] workers=$Workers; solver threads=1; pid=$($child.Id); timings=resource-contended"
 Write-Host "[STOP] To pause safely: create file $stopFile"
 Write-Host "[LOGS] stdout=$stdout; stderr=$stderr"
 while(-not $child.HasExited){
  Start-Sleep -Seconds 30;$child.Refresh()
  try {
   $summary=& $python -B -c $statusCode $experiment
   $snapshot=$summary | ConvertFrom-Json
   Write-Host ('[{0}] state={1}; jobs={2}/110000; active={3}/{4}; statuses={5}' -f (Get-Date -Format HH:mm:ss),$snapshot.state,$snapshot.done,$snapshot.active,$Workers,($snapshot.counts | ConvertTo-Json -Compress))
  }catch{Write-Host "[STATUS] $($_.Exception.Message)"}
 }
 $child.WaitForExit()
 $errorText=[IO.File]::ReadAllText($stderr)
 if($errorText){Write-Host $errorText}
 Write-Host "[EXIT] code=$($child.ExitCode); results/checkpoints retained; final analysis must separate sequential/concurrent timings by session."
} finally {
 foreach($key in $envKeys){[Environment]::SetEnvironmentVariable($key,$saved[$key])}
 [void][ParallelAwake]::SetThreadExecutionState([uint32]::Parse('2147483648'))
}
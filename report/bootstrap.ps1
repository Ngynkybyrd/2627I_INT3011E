[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$reportRoot = $PSScriptRoot
$toolRoot = Join-Path $reportRoot '.tools'
$vendorRoot = Join-Path $reportRoot 'vendor'
New-Item -ItemType Directory -Force -Path $toolRoot,$vendorRoot | Out-Null
function Get-OfficialFile([string]$Url,[string]$Destination) {
    & curl.exe -fL --retry 2 --connect-timeout 20 --max-time 180 $Url -o $Destination
    if ($LASTEXITCODE -ne 0) { throw "Download failed: $Url" }
}
if (-not (Test-Path -LiteralPath (Join-Path $toolRoot 'tectonic\tectonic.exe'))) {
    $archive = Join-Path $toolRoot 'tectonic.zip'
    Get-OfficialFile 'https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.17.0/tectonic-0.17.0-x86_64-pc-windows-msvc.zip' $archive
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $toolRoot 'tectonic') -Force
}
if (-not (Test-Path -LiteralPath (Join-Path $vendorRoot 'els-cas-templates\cas-sc.cls'))) {
    $archive = Join-Path $vendorRoot 'els-cas-templates.zip'
    Get-OfficialFile 'https://tug.ctan.org/macros/latex/contrib/els-cas-templates.zip' $archive
    Expand-Archive -LiteralPath $archive -DestinationPath $vendorRoot -Force
}
& (Join-Path $toolRoot 'tectonic\tectonic.exe') --version
if (-not (Test-Path -LiteralPath (Join-Path $toolRoot 'tectonic\LICENSE'))) {
    Get-OfficialFile 'https://raw.githubusercontent.com/tectonic-typesetting/tectonic/tectonic%400.17.0/LICENSE' (Join-Path $toolRoot 'tectonic\LICENSE')
}
if (-not (Test-Path -LiteralPath (Join-Path $vendorRoot 'LPPL-1.3c.txt'))) {
    Get-OfficialFile 'https://www.latex-project.org/lppl/lppl-1-3c.txt' (Join-Path $vendorRoot 'LPPL-1.3c.txt')
}
if (-not (Test-Path -LiteralPath (Join-Path $vendorRoot 'GUST-FONT-LICENSE.txt'))) {
    Get-OfficialFile 'https://tug.ctan.org/fonts/tex-gyre/doc/GUST-FONT-LICENSE.txt' (Join-Path $vendorRoot 'GUST-FONT-LICENSE.txt')
}
Write-Output 'Bootstrap complete. Run build.ps1 online once, then build.ps1 -Offline.'

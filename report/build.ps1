[CmdletBinding()]
param([switch]$Offline)
$ErrorActionPreference = 'Stop'
$reportRoot = $PSScriptRoot
$compiler = Join-Path $reportRoot '.tools\tectonic\tectonic.exe'
if (-not (Test-Path -LiteralPath $compiler)) {
    throw 'Missing portable compiler. Run bootstrap.ps1 first.'
}
$previousCache = $env:TECTONIC_CACHE_DIR
$previousFontconfig = $env:FONTCONFIG_FILE
$env:TECTONIC_CACHE_DIR = Join-Path $reportRoot '.tools\cache'
$fontconfigRoot = Join-Path $reportRoot '.tools\fontconfig'
New-Item -ItemType Directory -Force -Path $fontconfigRoot | Out-Null
$fontconfigPath = Join-Path $fontconfigRoot 'fonts.conf'
# Explicit font filenames are resolved by Tectonic; no system fonts needed.
'<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd"><fontconfig></fontconfig>' | Set-Content -LiteralPath $fontconfigPath -Encoding utf8
$env:FONTCONFIG_FILE = $fontconfigPath
$buildId = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$buildRoot = Join-Path $reportRoot "build\$buildId"
$pdfRoot = Join-Path $reportRoot 'output\pdf'
$logRoot = Join-Path $reportRoot 'logs'
New-Item -ItemType Directory -Force -Path $buildRoot,$pdfRoot,$logRoot | Out-Null
Push-Location $reportRoot
try {
    & $compiler --version | Set-Content -LiteralPath (Join-Path $logRoot 'compiler-version.txt') -Encoding utf8
    foreach ($language in @('vi','en')) {
        $outDir = Join-Path $buildRoot $language
        New-Item -ItemType Directory -Force -Path $outDir | Out-Null
        $compilerArgs = @('--keep-logs','--keep-intermediates','--color','never',
          '-Z',"search-path=$reportRoot\vendor\els-cas-templates",
          '--outdir',$outDir,'--makefile-rules',(Join-Path $outDir 'dependencies.mk'))
        if ($Offline) { $compilerArgs += '--only-cached' }
        $compilerArgs += "main-$language.tex"
        $consoleLog = Join-Path $logRoot "$buildId-$language-console.log"
        & $compiler @compilerArgs 2>&1 | Tee-Object -FilePath $consoleLog
        if ($LASTEXITCODE -ne 0) { throw "Compilation failed: $language (see $consoleLog)" }
        $pdf = Join-Path $outDir "main-$language.pdf"
        if (-not (Test-Path -LiteralPath $pdf)) { throw "No PDF produced: $language" }
        Copy-Item -LiteralPath $pdf -Destination (Join-Path $pdfRoot "sudoku-$language.pdf") -Force
    }
    $buildId | Set-Content -LiteralPath (Join-Path $logRoot 'latest-build.txt') -Encoding utf8
    Write-Output "Clean build PASS: $buildId"
} finally {
    Pop-Location
    $env:TECTONIC_CACHE_DIR = $previousCache
    $env:FONTCONFIG_FILE = $previousFontconfig
}

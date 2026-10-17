$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$runtimePath = Join-Path $PSScriptRoot '.runtime'
$pythonPath = Join-Path $runtimePath 'python/python.exe'
try {
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null
        $archivePath = Join-Path $runtimePath 'python.tar.gz'
        Write-Host 'Preparing Python automatically. The first download may take a few minutes...'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/astral-sh/python-build-standalone/releases/download/20261009/cpython-3.12.15%2B20261009-x86_64-pc-windows-msvc-install_only.tar.gz' -OutFile $archivePath
        if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne '194c8f0d9e0de6f1c4576e5dfa67819a48c764be87608b74b8ad43387a57b93b') {
            throw 'Python download is incomplete. Run START - WIN again.'
        }
        & tar.exe -xf $archivePath -C $runtimePath
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonPath)) { throw 'Python could not be extracted. Check available disk space and try again.' }
    }
    $env:PYTHONUTF8 = '1'
    & $pythonPath (Join-Path $PSScriptRoot 'bootstrap_local.py')
    if ($LASTEXITCODE -ne 0) { throw 'Flow2API stopped unexpectedly. Check the message above and start again.' }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}

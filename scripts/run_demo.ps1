# Verify the frozen demo files against CLAUDE.md, run the sanity checks, then start the app.
# Usage (from anywhere):  powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = "utf-8"

$failed = $false
Get-Content CLAUDE.md | ForEach-Object {
    if ($_ -match '`(data/[^`]+)`[^`]*`([0-9A-Fa-f]{64})`') {
        $file = $Matches[1]
        $expected = $Matches[2].ToUpper()
        if (-not (Test-Path $file)) {
            Write-Host "MISSING  $file"
            $script:failed = $true
        } elseif ((Get-FileHash $file -Algorithm SHA256).Hash -eq $expected) {
            Write-Host "OK       $file"
        } else {
            Write-Host "CHANGED  $file (does not match CLAUDE.md)"
            $script:failed = $true
        }
    }
}
if ($failed) {
    Write-Host "Stopped: fix the files above before the demo."
    exit 1
}

python scripts/check_data.py
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "Demo running at http://127.0.0.1:8501 (Ctrl+C to stop)"
python -m app.main

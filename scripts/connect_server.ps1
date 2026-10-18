# Open an SSH session to the demo server with a tunnel, then open the dashboard in the browser.
# The app keeps running on the server's port 8501; this laptop reaches it on port 8601,
# so a local copy of the demo on 8501 can run at the same time.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\connect_server.ps1 -Server linux1@<server-ip> -Key <path-to-key.pem>

param(
    [Parameter(Mandatory = $true)][string]$Server,
    [Parameter(Mandatory = $true)][string]$Key,
    [int]$LocalPort = 8601,
    [int]$RemotePort = 8501
)

if (-not (Test-Path $Key)) {
    Write-Host "Key file not found: $Key"
    exit 1
}
if (Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "Port $LocalPort is already in use on this laptop. Close the other program or pass -LocalPort <port>."
    exit 1
}

$url = "http://localhost:$LocalPort"
Start-Job -ScriptBlock { param($u) Start-Sleep -Seconds 5; Start-Process $u } -ArgumentList $url | Out-Null
Write-Host "Opening $url in 5 seconds. Keep this window open while you use the dashboard."

# ExitOnForwardFailure stops ssh if the tunnel can't open, instead of silently showing another app.
ssh -i $Key -o ExitOnForwardFailure=yes -L "${LocalPort}:127.0.0.1:${RemotePort}" $Server

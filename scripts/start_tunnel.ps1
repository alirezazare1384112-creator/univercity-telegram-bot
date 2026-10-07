<#
.SYNOPSIS
  Start a quick cloudflared tunnel and point WEBAPP_URL in .env at it.

.DESCRIPTION
  Stops any previous quick tunnel, starts a new one (--protocol http2, which
  works when UDP/QUIC is blocked), waits for the https://*.trycloudflare.com
  URL and rewrites WEBAPP_URL in .env. Restart the bot afterwards so the
  main-menu WebApp button picks up the new address.

.EXAMPLE
  .\scripts\start_tunnel.ps1
  .\scripts\start_tunnel.ps1 -OriginPort 8000 -TimeoutSeconds 90
#>
param(
    [int]$OriginPort = 8000,
    [int]$TimeoutSeconds = 60
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$errLog = Join-Path $root 'logs\tunnel.err'
New-Item -ItemType Directory -Force -Path (Join-Path $root 'logs') | Out-Null

# stop an older quick tunnel (never touches this PowerShell process)
Get-CimInstance Win32_Process | Where-Object {
    $_.Name -ne 'powershell.exe' -and $_.CommandLine -like '*cloudflared*tunnel*'
} | ForEach-Object {
    try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {}
}

$cmd = "npx -y cloudflared tunnel --url http://localhost:$OriginPort --protocol http2 > logs\tunnel.out 2> logs\tunnel.err"
Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', $cmd -WorkingDirectory $root -WindowStyle Hidden | Out-Null

$url = $null
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline -and -not $url) {
    Start-Sleep -Seconds 2
    if (Test-Path $errLog) {
        $found = Select-String -Path $errLog -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' |
            Select-Object -Last 1
        if ($found) { $url = $found.Matches[0].Value }
    }
}
if (-not $url) {
    throw "tunnel did not report a URL within $TimeoutSeconds s (see $errLog)"
}

$envPath = Join-Path $root '.env'
if (-not (Test-Path $envPath)) { throw ".env not found at $envPath" }
$content = Get-Content $envPath -Raw
if ($content -match '(?m)^WEBAPP_URL=') {
    $content = [regex]::Replace($content, '(?m)^WEBAPP_URL=.*$', "WEBAPP_URL=$url")
} else {
    $content = $content.TrimEnd() + "`nWEBAPP_URL=$url`n"
}
# UTF-8 without BOM: python-dotenv reads the first key as-is
[System.IO.File]::WriteAllText($envPath, $content, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "WEBAPP_URL = $url"
Write-Host 'Restart the bot so the WebApp button uses the new address.'

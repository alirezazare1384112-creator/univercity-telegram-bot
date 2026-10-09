# Start the bot + Mini App API with the proxy Telegram needs on this network.
# Usage: powershell -File scripts\start_bot.ps1
$root = Split-Path -Parent $PSScriptRoot

# Never start a second instance: two pollers make Telegram answer with
# "Conflict" and the loser exits, taking the Mini App down with it.
$running = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^(python|py)' -and $_.CommandLine -like '*run.py*'
})
if ($running.Count -gt 0) {
    Write-Host "Bot already running (PID $($running[0].ProcessId)) - not starting another."
    exit 0
}

# Proxy route: the old Psiphon build listens on port 3020; the current one
# writes a WinINET system proxy (e.g. https=127.0.0.1:3930) instead.
$proxy = $null
if (Get-NetTCPConnection -LocalPort 3020 -State Listen -ErrorAction SilentlyContinue) {
    $proxy = 'http://127.0.0.1:3020'
} else {
    $inet = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue
    if ($inet -and $inet.ProxyEnable -eq 1 -and $inet.ProxyServer) {
        $proxyServer = $inet.ProxyServer
        if ($proxyServer -match 'https=([^;]+)') {
            $proxyServer = $Matches[1]
        } elseif ($proxyServer -match '^https?=') {
            $proxyServer = ($proxyServer -split '=')[-1]
        }
        if ($proxyServer) {
            $proxy = if ($proxyServer -match '^https?://') { $proxyServer } else { "http://$proxyServer" }
        }
    }
}
if ($proxy) {
    $env:HTTP_PROXY = $proxy
    $env:HTTPS_PROXY = $proxy
    $env:NO_PROXY = "127.0.0.1,localhost"
}

Start-Process -FilePath "C:\Windows\py.exe" `
    -ArgumentList "-3.13", "run.py" `
    -WorkingDirectory $root `
    -RedirectStandardOutput "$root\logs\live_test.out" `
    -RedirectStandardError "$root\logs\live_test.err" `
    -WindowStyle Hidden

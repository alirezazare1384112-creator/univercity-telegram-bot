<#
.SYNOPSIS
  Watchdog: keeps the Mini App server and tunnel alive.

.DESCRIPTION
  Every IntervalSeconds:
    * http://127.0.0.1:8000/api/health does not answer -> restart the bot
      (scripts\start_bot.ps1 refuses to launch a second instance);
    * WEBAPP_URL from .env does not answer (checked twice, so a short
      reconnect does not count) -> scripts\start_tunnel.ps1 mints a fresh
      tunnel, rewrites .env, and the bot is restarted so the menu button,
      the pushed keyboards and the users all get the new address.
  Actions are rate limited to MinActionGapSeconds to avoid restart loops.
  Heartbeat is appended to logs\watch.log.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\watch.ps1
#>
param(
    [int]$IntervalSeconds = 30,
    [int]$MinActionGapSeconds = 90
)
$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
$logPath = Join-Path $root 'logs\watch.log'
New-Item -ItemType Directory -Force -Path (Join-Path $root 'logs') | Out-Null

# one watchdog only (PID lock: a cmdline check would also match the
# powershell process that launched us)
$lockPath = Join-Path $root 'logs\watch.pid'
if (Test-Path -LiteralPath $lockPath) {
    $lockedPid = (Get-Content -LiteralPath $lockPath -ErrorAction SilentlyContinue |
        Select-Object -First 1)
    if ($lockedPid) {
        $holder = Get-CimInstance Win32_Process -Filter "ProcessId = $lockedPid" -ErrorAction SilentlyContinue
        if ($holder -and $holder.CommandLine -like '*watch.ps1*') {
            Write-Host "watchdog already running (PID $lockedPid)"
            exit 0
        }
    }
}
Set-Content -LiteralPath $lockPath -Value $PID -Encoding ASCII

$script:LastAction = [datetime]::MinValue

function Write-WatchLog([string]$Message) {
    $line = '{0} | {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
}

function Get-WebappUrl {
    $envPath = Join-Path $root '.env'
    if (-not (Test-Path -LiteralPath $envPath)) { return $null }
    $match = Select-String -LiteralPath $envPath -Pattern '^WEBAPP_URL=(.+)$' |
        Select-Object -Last 1
    if (-not $match) { return $null }
    $value = $match.Matches[0].Groups[1].Value.Trim()
    if ($value -like 'https://*') { return $value }
    return $null
}

function Test-Url([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Get-BotProcesses {
    @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^(python|py)' -and $_.CommandLine -like '*run.py*'
    })
}

function Start-Bot {
    param([string]$Reason)
    Write-WatchLog "bot start: $Reason"
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'scripts\start_bot.ps1') | Out-Null
    Write-WatchLog 'start_bot issued'
}

function Restart-Bot {
    param([string]$Reason)
    Write-WatchLog "bot restart: $Reason"
    Get-BotProcesses | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    Start-Bot $Reason
}

function Invoke-Guarded {
    param([scriptblock]$Action, [string]$Reason)
    if (((Get-Date) - $script:LastAction).TotalSeconds -lt $MinActionGapSeconds) {
        return
    }
    $script:LastAction = Get-Date
    & $Action $Reason
}

Write-WatchLog "watchdog started (interval ${IntervalSeconds}s, gap ${MinActionGapSeconds}s)"

# the bot captures HTTP(S)_PROXY at process start: whenever the local
# proxy (port 3020) appears or disappears the bot must restart to switch
# between proxy/direct routes. First observation only records the state.
$proxyStateFile = Join-Path $root 'logs\proxy.state'
$previousProxyState = $null
if (Test-Path -LiteralPath $proxyStateFile) {
    $previousProxyState = (Get-Content -LiteralPath $proxyStateFile -ErrorAction SilentlyContinue |
        Select-Object -First 1)
}

while ($true) {
    Start-Sleep -Seconds $IntervalSeconds

    # --- local proxy (Psiphon) route switch -----------------------------
    # old build listens on 3020; the current one uses a system proxy (3930)
    $proxyUp = ((Get-NetTCPConnection -LocalPort 3020,3930,3929 -State Listen -ErrorAction SilentlyContinue |
        Measure-Object).Count -gt 0)
    if (-not $proxyUp) {
        $inet = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue
        $proxyUp = ($null -ne $inet -and $inet.ProxyEnable -eq 1)
    }
    $proxyState = if ($proxyUp) { 'up' } else { 'down' }
    if ($null -ne $previousProxyState -and $proxyState -ne $previousProxyState) {
        Invoke-Guarded {
            param($r)
            Restart-Bot $r
        } "proxy $previousProxyState -> $proxyState"
    }
    Set-Content -LiteralPath $proxyStateFile -Value $proxyState -Encoding ASCII
    $previousProxyState = $proxyState

    if (-not (Test-Url 'http://127.0.0.1:8000/api/health')) {
        if ((Get-BotProcesses).Count -gt 0) {
            Invoke-Guarded { param($r) Restart-Bot $r } 'health check failed'
        } else {
            Invoke-Guarded { param($r) Start-Bot $r } 'process missing'
        }
        continue
    }

    # two strikes: a short tunnel reconnect must not rotate the address
    $url = Get-WebappUrl
    if ($url -and -not (Test-Url $url)) {
        Start-Sleep -Seconds 5
        if (-not (Test-Url $url)) {
            Invoke-Guarded {
                param($r)
                Write-WatchLog "tunnel down: $r"
                powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'scripts\start_tunnel.ps1') | Out-Null
                Write-WatchLog 'start_tunnel issued'
                Restart-Bot 'tunnel rotated - reload WEBAPP_URL'
            } 'webapp url unreachable'
        }
    }
}

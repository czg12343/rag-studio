# RAG Studio - one-shot launcher for Windows PowerShell 5.1+
# Starts the FastAPI backend (uvicorn) and the Vite frontend, waits until each
# is actually accepting TCP connections, then opens the browser.
#
# Why TCP checks instead of Invoke-WebRequest:
#   On machines with a system proxy / VPN (e.g. Clash), PowerShell's HTTP stack
#   routes requests to 127.0.0.1 through the proxy and gets a bogus 404, so the
#   old health check never passed and the script killed the services and exited
#   (the "flash and close" symptom). A raw TCP connect bypasses every HTTP proxy.

param([switch]$Install)

$ErrorActionPreference = 'Stop'
$ProjectRoot  = Split-Path -Parent $MyInvocation.MyCommand.Path
$FrontendPath = Join-Path $ProjectRoot 'frontend'
$PythonPath   = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$LogPath      = Join-Path $ProjectRoot 'data\logs'
$BackendPort  = 8000
$FrontendPort = 5173
$BackendTimeoutSec  = 120
$FrontendTimeoutSec = 90

$StartedProcesses = @()
$BackendLog    = Join-Path $LogPath 'backend.log'
$BackendErrLog = Join-Path $LogPath 'backend-error.log'
$FrontendLog   = Join-Path $LogPath 'frontend.log'
$FrontendErrLog = Join-Path $LogPath 'frontend-error.log'

function Write-Step([string]$msg) { Write-Host "[*] $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn2([string]$msg){ Write-Host "[!] $msg" -ForegroundColor Yellow }
function Write-Err2([string]$msg) { Write-Host "[X] $msg" -ForegroundColor Red }

# Raw TCP connectivity check. Never touches the system/HTTP proxy.
function Test-TcpPort([int]$Port, [int]$TimeoutMs = 1500) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        $signaled = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if (-not $signaled) { return $false }
        try { $client.EndConnect($iar) } catch { return $false }
        return [bool]$client.Connected
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

# Wait until a port is open for two consecutive probes (uvicorn binds the
# socket a moment before app startup finishes; the second probe confirms it).
function Wait-Port([int]$Port, [string]$Name, [int]$TimeoutSec) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $stable = 0
    $elapsed = 0
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort -Port $Port) {
            $stable++
            if ($stable -ge 2) {
                Write-Ok ("{0} is ready (127.0.0.1:{1})." -f $Name, $Port)
                return $true
            }
        } else {
            $stable = 0
        }
        Start-Sleep -Seconds 1
        $elapsed++
        if (($elapsed % 5) -eq 0) {
            Write-Host ("    ...waiting for {0} ({1}s / {2}s)" -f $Name, $elapsed, $TimeoutSec)
        }
    }
    return $false
}

function Reset-LogFile([string]$path) {
    if (Test-Path $path) {
        try { Clear-Content $path -ErrorAction Stop } catch { }
    }
}

function Show-LogTail([string]$path, [int]$lines = 30) {
    if (Test-Path $path) {
        Write-Warn2 ("Tail of {0}:" -f $path)
        Get-Content $path -Tail $lines -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    }
}

function Get-PortOwner([int]$Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        if ($proc) { return ("PID {0} ({1})" -f $conn.OwningProcess, $proc.ProcessName) }
        return ("PID {0}" -f $conn.OwningProcess)
    }
    return $null
}

try {
    Write-Host '================ RAG Studio launcher ================' -ForegroundColor White

    # --- prerequisites -----------------------------------------------------
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw 'Python 3.11+ was not found on PATH. Install Python first.'
    }
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        throw 'Node.js / npm was not found on PATH. Install Node.js 20+ first.'
    }

    if (-not (Test-Path $PythonPath)) {
        Write-Step 'Creating project virtual environment (.venv)...'
        & python -m venv (Join-Path $ProjectRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Failed to create the virtual environment.' }
        $Install = $true
    }

    if ($Install) {
        Write-Step 'Installing Python dependencies (requirements.txt)...'
        & $PythonPath -m pip install -r (Join-Path $ProjectRoot 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    }

    Write-Step 'Checking native vector dependencies before starting the server...'
    & $PythonPath -X faulthandler (Join-Path $ProjectRoot 'scripts\check_runtime.py')
    if ($LASTEXITCODE -ne 0) {
        throw 'Native vector runtime check failed. Run install_and_start.bat to repair the project dependencies.'
    }

    $needNpm = $Install -or -not (Test-Path (Join-Path $FrontendPath 'node_modules'))
    if ($needNpm) {
        Write-Step 'Installing frontend dependencies (npm ci), this can take a minute...'
        Push-Location $FrontendPath
        try {
            & npm.cmd ci --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        } finally { Pop-Location }
    }

    # --- port preflight ----------------------------------------------------
    New-Item -ItemType Directory -Force $LogPath | Out-Null
    foreach ($used in @($BackendPort, $FrontendPort)) {
        $owner = Get-PortOwner $used
        if ($owner) {
            throw ("Port {0} is already in use by {1}. Stop its launcher with Ctrl+C first." -f $used, $owner)
        }
    }

    # --- start backend -----------------------------------------------------
    Reset-LogFile $BackendLog; Reset-LogFile $BackendErrLog
    Reset-LogFile $FrontendLog; Reset-LogFile $FrontendErrLog

    Write-Step 'Starting backend (uvicorn on 127.0.0.1:8000)...'
    $backend = Start-Process -FilePath $PythonPath `
        -ArgumentList '-X','faulthandler','-m','uvicorn','main:app','--host','127.0.0.1','--port',"$BackendPort",'--workers','1' `
        -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $BackendLog -RedirectStandardError $BackendErrLog
    $StartedProcesses += $backend

    if (-not (Wait-Port -Port $BackendPort -Name 'Backend' -TimeoutSec $BackendTimeoutSec)) {
        if ($backend.HasExited) { Write-Err2 'Backend process exited during startup.' }
        Show-LogTail $BackendErrLog
        Show-LogTail $BackendLog
        throw ("Backend did not become ready within {0}s. See logs in {1}." -f $BackendTimeoutSec, $LogPath)
    }

    # --- start frontend ----------------------------------------------------
    $NodePath = (Get-Command node.exe -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if (-not $NodePath) { throw 'node.exe was not found on PATH.' }
    Write-Step 'Starting frontend (Vite on 127.0.0.1:5173)...'
    $frontend = Start-Process -FilePath $NodePath `
        -ArgumentList 'node_modules/vite/bin/vite.js','--host','127.0.0.1','--strictPort' `
        -WorkingDirectory $FrontendPath -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $FrontendLog -RedirectStandardError $FrontendErrLog
    $StartedProcesses += $frontend

    if (-not (Wait-Port -Port $FrontendPort -Name 'Frontend' -TimeoutSec $FrontendTimeoutSec)) {
        if ($frontend.HasExited) { Write-Err2 'Frontend process exited during startup.' }
        Show-LogTail $FrontendErrLog
        Show-LogTail $FrontendLog
        throw ("Frontend did not become ready within {0}s. See logs in {1}." -f $FrontendTimeoutSec, $LogPath)
    }

    # --- ready -------------------------------------------------------------
    $url = 'http://127.0.0.1:5173'
    Write-Host ''
    Write-Ok ("RAG Studio is running: {0}" -f $url)
    Write-Host '    API docs: http://127.0.0.1:8000/docs' -ForegroundColor DarkGray
    Write-Host '    Logs:     data\logs\ (backend.log / frontend.log)' -ForegroundColor DarkGray
    Write-Host '    Press Ctrl+C in this window to stop both services.' -ForegroundColor Yellow
    Write-Host ''
    Start-Process $url

    while ($true) {
        Start-Sleep -Seconds 1
        foreach ($child in $StartedProcesses) {
            if ($child.HasExited) {
                throw ("A service process (PID {0}) exited unexpectedly. See logs in {1}." -f $child.Id, $LogPath)
            }
        }
    }
} catch {
    Write-Host ''
    Write-Err2 'Failed to start RAG Studio:'
    Write-Host ("    " + $_.Exception.Message) -ForegroundColor Red
    Write-Host ''
    Write-Warn2 "Check the logs under data\logs\ for details."
    Write-Host ''
    exit 1
} finally {
    foreach ($child in $StartedProcesses) {
        if ($child -and -not $child.HasExited) {
            try { Stop-Process -Id $child.Id -Force -ErrorAction SilentlyContinue } catch { }
        }
    }
}

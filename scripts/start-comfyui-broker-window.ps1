param(
    [Parameter(Mandatory = $true)]
    [string]$PythonExe,

    [Parameter(Mandatory = $true)]
    [string]$BrokerScript,

    [Parameter(Mandatory = $true)]
    [int]$Port,

    [Parameter(Mandatory = $true)]
    [string]$LogFile
)

$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = "OpenClaw ComfyUI Broker :$Port"

# Kill any stale broker processes on this port before starting
Write-Host "Comprobando procesos previos en puerto $Port..." -ForegroundColor DarkGray
$stalePids = netstat -ano | Select-String ":$Port\s+.*LISTENING" | ForEach-Object {
    if ($_ -match '\s+(\d+)\s*$') { [int]$Matches[1] }
} | Sort-Object -Unique
foreach ($pid in $stalePids) {
    if ($pid -ne 0 -and $pid -ne $PID) {
        Write-Host "  Matando proceso stale PID $pid en puerto $Port" -ForegroundColor Yellow
        try { Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue } catch {}
    }
}
if ($stalePids.Count -gt 0) {
    Start-Sleep -Milliseconds 500
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  OpenClaw ComfyUI Broker" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Python : $PythonExe" -ForegroundColor Gray
Write-Host "  Script : $BrokerScript" -ForegroundColor Gray
Write-Host "  Puerto : $Port" -ForegroundColor Gray
Write-Host "  Log    : $LogFile" -ForegroundColor Gray
Write-Host "" 

try {
    $env:PYTHONUNBUFFERED = '1'
    $env:OPENCLAW_BROKER_LOG_FILE = $LogFile
    & $PythonExe -u $BrokerScript --port $Port
    $exitCode = $LASTEXITCODE
} catch {
    $errorText = $_ | Out-String
    $errorText | Out-Host
    $exitCode = 1
}

Write-Host "" 
Write-Host "Broker finalizado con codigo $exitCode" -ForegroundColor Yellow
Read-Host "Pulsa Enter para cerrar esta ventana"
exit $exitCode
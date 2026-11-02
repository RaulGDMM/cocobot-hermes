# Reinicia SOLO el broker de ComfyUI (puerto 8791) con el mismo entorno que
# start-hermes.ps1 en modo Strata (qwen38_flashnext_nvfp4), sin tocar gateway,
# desktop backend ni Strata. Creado 2026-10-06.
# Si cambias de perfil a llama-server (27B), usa start-hermes.ps1 -Model ... en su lugar.
$ErrorActionPreference = 'Stop'
$hermesRoot   = Split-Path $PSScriptRoot -Parent
$openclawRoot = "E:\Workspace\Openclaw"
$brokerPort   = 8791

# 1. Matar broker actual: TODO proceso cuya linea de comandos contenga comfyui-broker
#    (el listener es un python nieto del launcher del venv; matar solo el PID del puerto
#    a veces no basta) + el listener del puerto por si acaso.
# 2026-11-02 (Cocobot): el puerto se busca con NETSTAT, no con Get-NetTCPConnection -State
# Listen: en esta caja los listeners del broker/monitor salen con State vacio via interop y
# el cmdlet devolvio nada dos veces (2nd instance pidio 8791 con el broker vivo -> 10048).
Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like '*comfyui-broker*' -and $_.ProcessId -ne $PID -and
    $_.CommandLine -notlike '*restart-comfyui-broker.ps1*'
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
function Get-PortOwnerPids([int]$port) {
    netstat -ano | Select-String (":" + $port + "\s.*LISTENING") | ForEach-Object {
        if ($_ -match '\s+(\d+)\s*$') { [int]$Matches[1] }
    } | Sort-Object -Unique
}
Get-PortOwnerPids $brokerPort | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
$deadline = (Get-Date).AddSeconds(15)
while ((Get-PortOwnerPids $brokerPort) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }

# 2. Entorno (copiado de start-hermes.ps1, rama Strata)
$env:OPENCLAW_BROKER_PORT = [string]$brokerPort
$env:OPENCLAW_BROKER_HOST = "0.0.0.0"
$env:OPENCLAW_BATCH_WAIT_SECONDS = "5"
$env:OPENCLAW_BATCH_MAX = "20"
$env:OPENCLAW_DEFAULT_GENERATION_TIMEOUT = "900"
$env:OPENCLAW_KEEP_COMFY_RUNNING = "0"
$env:OPENCLAW_COMFYUI_ROOT = "C:\ComfyUI"
$env:OPENCLAW_COMFYUI_USER_DIR = "C:\ComfyUI\user"
$env:OPENCLAW_COMFYUI_INPUT_DIR = "C:\ComfyUI\input"
$env:OPENCLAW_COMFYUI_OUTPUT_DIR = "C:\ComfyUI\output"
$env:OPENCLAW_COMFYUI_PYTHON = "C:\ComfyUI\.venv\Scripts\python.exe"
$env:OPENCLAW_COMFYUI_APP_DIR = "E:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI"
$env:OPENCLAW_COMFYUI_EXTRA_MODEL_PATHS_CONFIG = Join-Path $PSScriptRoot "comfyui-extra-model-paths.yaml"
$env:OPENCLAW_COMFYUI_HOST = "127.0.0.1"
$env:OPENCLAW_COMFYUI_PORT = "8000"
$env:OPENCLAW_USE_BACKEND = "llama-server"
$env:OPENCLAW_LLAMA_PORT = "8097"
$env:OPENCLAW_LLAMA_CTX_SIZE = "262144"
$key = Get-Content (Join-Path $env:USERPROFILE ".hermes\secrets\strata-api-key") -ErrorAction SilentlyContinue
if ($key) { $env:OPENCLAW_LLAMA_API_KEY = $key }
$env:OPENCLAW_STRATA_START_SCRIPT = Join-Path $openclawRoot "strata-nvfp4\strata-nvfp4\start-cocobot.cmd"
$env:OPENCLAW_LLAMA_PARALLEL = "1"
$env:OPENCLAW_LLAMA_PROFILE = "qwen38_flashnext_nvfp4"

# 3. Lanzar en ventana propia (igual que start-hermes)
$args2 = @("-NoLogo", "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "start-comfyui-broker-window.ps1"),
    "-PythonExe", "C:\ComfyUI\.venv\Scripts\python.exe",
    "-BrokerScript", (Join-Path $PSScriptRoot "comfyui-broker.py"),
    "-Port", "$brokerPort",
    "-LogFile", (Join-Path $hermesRoot "comfyui-broker.log"))
Start-Process (Join-Path $PSHOME "powershell.exe") -ArgumentList $args2 -WindowStyle Minimized
Write-Host "Broker relanzado en :$brokerPort (modo Strata)"

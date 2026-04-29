# Hermes Agent Startup Script
# ---- CONFIGURACION ----
# Instalacion de llama.cpp: "stable" (actual) o "latest" (pruebas)
$useLlamaInstall = "stable"

# Modelo LLM: "qwen36_27b", "qwen36", "qwen36q4", "qwen35", "gemma4"
$useModel = "qwen36_27b"

# Herramienta browser: $true para activarla, $false para desactivarla
$useBrowserTool = $true

# Open WebUI: $true para arrancar la interfaz web en puerto 8080
$useOpenWebUI = $false

# Hermes WebUI: $true para arrancar hermes-webui en puerto 8787 (WSL)
$useHermesWebUI = $true

# Whisper + Wyoming bridges (Home Assistant): $true para arrancar whisper-server y bridges STT/TTS
# Discord y Telegram usan el STT interno de Hermes, no necesitan esto.
$useWhisper = $false
# -----------------------

# Auto-relaunch inside Windows Terminal so all services open as tabs
if (-not $env:WT_SESSION) {
    $wtExe = Get-Command wt.exe -ErrorAction SilentlyContinue
    if ($wtExe) {
        $scriptPath = $MyInvocation.MyCommand.Path
        wt.exe new-tab --title "Hermes Startup" -- powershell.exe -ExecutionPolicy Bypass -NoExit -File $scriptPath
        exit
    }
}

Write-Host "========================================" -ForegroundColor Magenta
Write-Host "  Hermes Agent Startup Script" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "  Modelo: $useModel" -ForegroundColor Gray
Write-Host "  llama.cpp: $useLlamaInstall" -ForegroundColor Gray
Write-Host "  Browser tool: $useBrowserTool" -ForegroundColor Gray
Write-Host "  Open WebUI: $useOpenWebUI" -ForegroundColor Gray
Write-Host "  Hermes WebUI: $useHermesWebUI" -ForegroundColor Gray
Write-Host ""

# Paths: scripts in local scripts/ folder, binaries & models in Openclaw/
$scriptsRoot = Join-Path $PSScriptRoot "scripts"
$openclawRoot = Join-Path (Split-Path $PSScriptRoot) "Openclaw"

# Helper: find a script locally first, then fall back to Openclaw
function Find-Script {
    param([string]$Name)
    $local = Join-Path $scriptsRoot $Name
    if (Test-Path $local) { return $local }
    $fallback = Join-Path $openclawRoot $Name
    if (Test-Path $fallback) { return $fallback }
    return $null
}

$brokerPort = 8791
$brokerProcess = $null
$llamaNeedsWarmup = $false
$wyomingSttPid = $null
$wyomingTtsPid = $null

$useWTTabs = $null -ne $env:WT_SESSION
if ($useWTTabs) {
    Write-Host "  Windows Terminal: los servicios se abriran en pestanas" -ForegroundColor DarkCyan
} else {
    Write-Host "  Terminal clasica: los servicios se abriran en ventanas separadas" -ForegroundColor DarkCyan
}
Write-Host ""

# --- Helper: warm-up ---

function Invoke-LlamaWarmup {
    param([int]$Port = 30000)
    Write-Host "  Forzando carga del modelo en VRAM (warm-up)..." -ForegroundColor Gray
    try {
        $models = Invoke-RestMethod -Uri "http://localhost:${Port}/v1/models" -Method Get -TimeoutSec 10
        $modelId = ($models.data | Where-Object { $_.id -ne "default" -and $_.id -notmatch "draft" } | Select-Object -First 1).id
        if (-not $modelId) { $modelId = ($models.data | Where-Object { $_.id -ne "default" } | Select-Object -First 1).id }
        if (-not $modelId) { $modelId = $models.data[0].id }
    } catch {
        $modelId = "qwen3.6-27b"
    }
    Write-Host "  Modelo: $modelId" -ForegroundColor Gray
    $warmupBody = @{
        model = $modelId
        messages = @(@{ role = "user"; content = "hi" })
        max_tokens = 1
        temperature = 0
        stream = $false
    } | ConvertTo-Json -Depth 3
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $null = Invoke-RestMethod -Uri "http://localhost:${Port}/v1/chat/completions" -Method POST -Body $warmupBody -ContentType "application/json" -TimeoutSec 300
        $sw.Stop()
        Write-Host "  Modelo cargado en VRAM ($([math]::Round($sw.Elapsed.TotalSeconds, 1))s)" -ForegroundColor Gray
    } catch {
        $sw.Stop()
        Write-Host "  Warm-up fallo: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

function Get-LlamaInstallInfo {
    param([string]$InstallName)
    switch ($InstallName) {
        "stable" { return @{ Name = "stable"; DirName = "llama-cpp"; Label = "estable" } }
        "latest" { return @{ Name = "latest"; DirName = "llama-cpp-latest"; Label = "pruebas" } }
        default { throw "Valor invalido para `$useLlamaInstall`: '$InstallName'. Usa 'stable' o 'latest'." }
    }
}

$llamaInstall = Get-LlamaInstallInfo -InstallName $useLlamaInstall

Write-Host "[0] Tailscale: se arrancara en la pestana WSL del gateway" -ForegroundColor DarkCyan
Write-Host ""

# 1. Comprobar y arrancar llama-server
if ($useModel -eq "qwen36") {
    $modelLabel    = "Qwen3.6-35B-A3B-Q5_K_M"
    $modelSize     = "25 GB, vision+thinking, MoE 3B active"
    $ctxSize       = "100000"
} elseif ($useModel -eq "qwen36q4") {
    $modelLabel    = "Qwen3.6-35B-A3B-Q4_K_L"
    $modelSize     = "22 GB, vision+thinking, MoE 3B active"
    $ctxSize       = "200000"
} elseif ($useModel -eq "qwen36_27b") {
    $modelLabel    = "Qwen3.6-27B-UD-Q4_K_XL"
    $modelSize     = "17.6 GB, vision+thinking, dense 27B, Unsloth Dynamic 2.0, KV Q8_0+rot"
    $ctxSize       = "200000"
} elseif ($useModel -eq "gemma4") {
    $modelLabel    = "Gemma 4 31B-it UD-Q4_K_XL"
    $modelSize     = "17.5 GB, vision+thinking"
    $ctxSize       = "100000"
} else {
    $modelLabel    = "Qwen3.5-27B-UD-Q4_K_XL"
    $modelSize     = "17.6 GB, vision"
    $ctxSize       = "131072"
}

Write-Host "[1/6] Comprobando llama-server ($modelLabel)..." -ForegroundColor Yellow

$llamaRoot       = Join-Path $openclawRoot $llamaInstall.DirName
$llamaServerExe  = Join-Path $llamaRoot "llama-server.exe"
if ($useModel -eq "qwen36") {
    $modelFile    = Join-Path $openclawRoot "models\qwen36-35b\Qwen3.6-35B-A3B-Q5_K_M.gguf"
    $mmProjFile   = Join-Path $openclawRoot "models\qwen36-35b\mmproj-BF16.gguf"
} elseif ($useModel -eq "qwen36q4") {
    $modelFile    = Join-Path $openclawRoot "models\qwen36-35b\Qwen3.6-35B-A3B-Q4_K_L.gguf"
    $mmProjFile   = Join-Path $openclawRoot "models\qwen36-35b\mmproj-BF16.gguf"
} elseif ($useModel -eq "qwen36_27b") {
    $modelFile    = Join-Path $openclawRoot "models\qwen36-27b\Qwen3.6-27B-UD-Q4_K_XL.gguf"
    $mmProjFile   = Join-Path $openclawRoot "models\qwen36-27b\mmproj-BF16.gguf"
} elseif ($useModel -eq "gemma4") {
    $modelFile    = Join-Path $openclawRoot "models\gemma4-31b\gemma-4-31B-it-UD-Q4_K_XL.gguf"
    $mmProjFile   = Join-Path $openclawRoot "models\gemma4-31b\mmproj-BF16.gguf"
} else {
    $modelFile    = Join-Path $openclawRoot "models\qwen35-27b\Qwen3.5-27B-UD-Q4_K_XL.gguf"
    $mmProjFile   = Join-Path $openclawRoot "models\qwen35-27b\mmproj-BF16.gguf"
}
$llamaPort = 30000

if (-not (Test-Path $llamaServerExe)) {
    Write-Host "[!] No se encuentra llama-server.exe en $llamaServerExe" -ForegroundColor Red
}
elseif (-not (Test-Path $modelFile)) {
    Write-Host "[!] No se encuentra el modelo GGUF en $modelFile" -ForegroundColor Red
}
else {
    $llamaRunning = $false
    try { $null = Invoke-RestMethod -Uri "http://localhost:${llamaPort}/health" -Method Get -TimeoutSec 3 -ErrorAction Stop; $llamaRunning = $true } catch {}

    if ($llamaRunning) {
        Write-Host "[OK] llama-server ya esta corriendo en puerto $llamaPort" -ForegroundColor Green
    }
    else {
        Write-Host "[X] llama-server no esta corriendo. Iniciando..." -ForegroundColor Red
        Write-Host "  Modelo: $modelLabel ($modelSize)" -ForegroundColor Gray
        Write-Host "  Instalacion llama.cpp: $($llamaInstall.Name) ($($llamaInstall.Label))" -ForegroundColor Gray
        Write-Host "  Contexto: $ctxSize tokens" -ForegroundColor Gray
        $llamaLogFile = Join-Path $openclawRoot "llama-server.log"
        $slotCachePath = Join-Path $openclawRoot "slot-cache"
        if (-not (Test-Path $slotCachePath)) { New-Item -ItemType Directory -Path $slotCachePath -Force | Out-Null }
        $llamaArgs = @(
            "--model",               $modelFile,
            "--mmproj",              $mmProjFile,
            "--ctx-size",            $ctxSize,
            "--slot-save-path",      $slotCachePath,
            "--parallel",            "1",
            "--n-gpu-layers",        "99",
            "--flash-attn",          "on",
            "--batch-size",          "2048",
            "--host",                "0.0.0.0",
            "--port",                $llamaPort,
            "--cont-batching",
            "--log-file",            $llamaLogFile
        )
        # Model-specific flags
        if ($useModel -in @("qwen36","qwen36q4","qwen36_27b")) {
            $llamaArgs += @("--ubatch-size", "2048")
            $llamaArgs += @("--jinja")
            $llamaArgs += @("--reasoning-format", "deepseek")
            $llamaArgs += @("--image-max-tokens", "1024")
            if ($useModel -eq "qwen36_27b") {
                $llamaArgs += @("--presence-penalty", "0")
            } else {
                $llamaArgs += @("--presence-penalty", "1.5")
            }
            $llamaArgs += @("--min-p", "0")
            $llamaArgs += @("--predict", "81920")
            $llamaArgs += @("--reasoning-budget", "-1")
            $chatTemplateKwargs = '{"enable_thinking":true,"preserve_thinking":true}'
            $env:LLAMA_CHAT_TEMPLATE_KWARGS = $chatTemplateKwargs
            $llamaArgs += @("--no-prefill-assistant")
            $llamaArgs += @("--kv-unified", "--ctx-checkpoints", "32", "--cache-ram", "16384", "--no-context-shift", "--no-cache-idle-slots")
            if ($useModel -eq "qwen36_27b") {
                $llamaArgs += @("-ctk", "q8_0", "-ctv", "q8_0")
            }
        }
        elseif ($useModel -eq "qwen35") {
            $chatTemplateFile = Join-Path $openclawRoot "models\qwen35-27b\chat-template.jinja"
            $llamaArgs += @("--ubatch-size", "2048")
            $llamaArgs += @("--chat-template-file", $chatTemplateFile)
            $llamaArgs += @("--kv-unified", "--ctx-checkpoints", "32")
            $llamaArgs += @("--swa-full")
        }
        if ($useModel -eq "gemma4") {
            $llamaArgs += @("--ubatch-size", "512")
            $llamaArgs += @("--jinja")
            $llamaArgs += @("-ctk", "f16", "-ctv", "f16", "--repeat-penalty", "1.1")
            $llamaArgs += @("--no-mmap")
            $llamaArgs += @("--ctx-checkpoints", "8")
        }
        if ($useWTTabs) {
            $llamaCmd = ((@($llamaServerExe) + $llamaArgs) | ForEach-Object { if ($_ -match '\s') { "`"$_`"" } else { $_ } }) -join ' '
            $launchScript = Join-Path $openclawRoot "llama-launch.cmd"
            $launchLines = @("@echo off")
            if ($chatTemplateKwargs) {
                $launchLines += "set LLAMA_CHAT_TEMPLATE_KWARGS=$chatTemplateKwargs"
            }
            $launchLines += "$llamaCmd"
            $launchLines | Set-Content $launchScript -Encoding ASCII
            wt.exe -w 0 new-tab --title "llama-server :$llamaPort" -- cmd /c "`"$launchScript`" & exit 0"
        } else {
            Start-Process $llamaServerExe -ArgumentList $llamaArgs -WindowStyle Minimized
        }
        $llamaNeedsWarmup = $true
        Write-Host "  llama-server lanzado (modelo se carga en segundo plano)" -ForegroundColor Gray
        Write-Host "  Log: $llamaLogFile" -ForegroundColor Gray
    }
}
Write-Host ""

# Gateway WSL: launch Hermes gateway in a WSL tab
if ($useWTTabs) {
    $driveLetter = $PSScriptRoot.Substring(0,1).ToLower()
    $wslDir = "/mnt/$driveLetter" + ($PSScriptRoot.Substring(2) -replace '\\','/')
    Write-Host "  Lanzando Hermes gateway en pestana WSL..." -ForegroundColor DarkCyan
    $browserFlag = if ($useBrowserTool) { 'on' } else { 'off' }
    $tailscaleFlag = if ($useOpenWebUI -or $useHermesWebUI) { 'on' } else { 'off' }
    wt.exe -w 0 new-tab --title "Hermes Gateway (WSL)" -- wsl.exe -d Ubuntu -- bash -lc "cd '$wslDir' && USE_MODEL='$useModel' USE_BROWSER_TOOL='$browserFlag' USE_TAILSCALE='$tailscaleFlag' ./start-hermes-wsl.sh"
    Write-Host "[OK] Hermes gateway lanzado en pestana WSL" -ForegroundColor Green

    # Chat tab: opens hermes TUI after llama-server is ready
    Write-Host "  Lanzando pestana de chat con Hermes..." -ForegroundColor DarkCyan
    wt.exe -w 0 new-tab --title "Hermes Chat" -- wsl.exe -d Ubuntu -- bash -l "$wslDir/start-hermes-chat.sh"
    Write-Host "[OK] Pestana de chat lanzada (esperara a llama-server)" -ForegroundColor Green
} else {
    Write-Host "  El gateway se lanzara desde WSL manualmente" -ForegroundColor Gray
}
Write-Host ""

# 3. Arrancar servidor Whisper
if ($useWhisper) {
    Write-Host "[2/6] Iniciando servidor Whisper local..." -ForegroundColor Yellow
    $whisperScript = Find-Script "whisper-server.py"
    $whisperProcess = $null

    if ($whisperScript) {
        $whisperRunning = $false
        try { $null = Invoke-RestMethod -Uri "http://localhost:8787/health" -Method Get -TimeoutSec 2 -ErrorAction Stop; $whisperRunning = $true } catch {}

        if ($whisperRunning) {
            Write-Host "[OK] Servidor Whisper ya esta corriendo" -ForegroundColor Green
        }
        else {
            $whisperProcess = Start-Process py -ArgumentList "-3.12", $whisperScript, "--model", "medium" -WindowStyle Hidden -PassThru
            Write-Host "[OK] Servidor Whisper lanzado (PID: $($whisperProcess.Id))" -ForegroundColor Green
        }
    }
    else {
        Write-Host "[!] whisper-server.py no encontrado" -ForegroundColor Yellow
    }
} else {
    Write-Host "[2/6] Servidor Whisper desactivado (useWhisper=false)" -ForegroundColor DarkGray
}
Write-Host ""

# 4. Arrancar broker local para ComfyUI
Write-Host "[3/6] Iniciando broker local de ComfyUI..." -ForegroundColor Yellow
$brokerScript = Find-Script "comfyui-broker.py"
$brokerWindowScript = Find-Script "start-comfyui-broker-window.ps1"
$brokerPython = "C:\ComfyUI\.venv\Scripts\python.exe"
$brokerLogFile = Join-Path $PSScriptRoot "comfyui-broker.log"
$brokerModelPathsConfig = Find-Script "comfyui-extra-model-paths.yaml"

if ($brokerScript) {
    $brokerRunning = $false
    try {
        $null = Invoke-RestMethod -Uri "http://localhost:${brokerPort}/health" -Method Get -TimeoutSec 2 -ErrorAction Stop
        $brokerRunning = $true
    } catch {}

    if ($brokerRunning) {
        Write-Host "[OK] Broker de ComfyUI ya esta corriendo (puerto $brokerPort)" -ForegroundColor Green
    }
    else {
        # Kill stale processes on broker port
        $stalePids = netstat -ano | Select-String ":$brokerPort\s+.*LISTENING" | ForEach-Object {
            if ($_ -match '\s+(\d+)\s*$') { [int]$Matches[1] }
        } | Sort-Object -Unique
        foreach ($spid in $stalePids) {
            if ($spid -ne 0) {
                Write-Host "  Matando proceso stale PID $spid en puerto $brokerPort" -ForegroundColor Yellow
                try { Stop-Process -Id $spid -Force -ErrorAction SilentlyContinue } catch {}
            }
        }
        if ($stalePids.Count -gt 0) { Start-Sleep -Milliseconds 500 }

        if (-not (Test-Path $brokerPython)) {
            Write-Host "[!] No se encuentra el Python de ComfyUI: $brokerPython" -ForegroundColor Red
        }
        elseif (-not $brokerWindowScript -or -not (Test-Path $brokerWindowScript)) {
            Write-Host "[!] No se encuentra el lanzador visual del broker: $brokerWindowScript" -ForegroundColor Red
        }
        else {
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
            $env:OPENCLAW_COMFYUI_APP_DIR = "E:\Programs\ComfyUI\resources\ComfyUI"
            if ($brokerModelPathsConfig -and (Test-Path $brokerModelPathsConfig)) { $env:OPENCLAW_COMFYUI_EXTRA_MODEL_PATHS_CONFIG = $brokerModelPathsConfig }
            $env:OPENCLAW_COMFYUI_HOST = "127.0.0.1"
            $env:OPENCLAW_COMFYUI_PORT = "8000"
            $env:OPENCLAW_USE_BACKEND = "llama-server"

            $env:OPENCLAW_LLAMA_SLOT_SAVE_PATH = Join-Path $openclawRoot "slot-cache"
            if ($llamaServerExe) { $env:OPENCLAW_LLAMA_SERVER_EXE = $llamaServerExe }
            if ($modelFile) { $env:OPENCLAW_LLAMA_MODEL = $modelFile }
            if ($mmProjFile) { $env:OPENCLAW_LLAMA_MMPROJ = $mmProjFile }
            if ($llamaLogFile) { $env:OPENCLAW_LLAMA_LOG_FILE = $llamaLogFile }
            $env:OPENCLAW_LLAMA_PORT = [string]$llamaPort
            $env:OPENCLAW_LLAMA_CTX_SIZE = $ctxSize
            $env:OPENCLAW_LLAMA_PARALLEL = "1"
            $env:OPENCLAW_LLAMA_N_GPU_LAYERS = "99"
            $env:OPENCLAW_LLAMA_BATCH_SIZE = "2048"
            $env:OPENCLAW_LLAMA_PROFILE = $useModel
            if ($useModel -in @("qwen36","qwen36q4","qwen36_27b")) {
                $env:OPENCLAW_LLAMA_UBATCH_SIZE = "2048"
                $env:OPENCLAW_LLAMA_CTX_CHECKPOINTS = "32"
            } elseif ($useModel -eq "qwen35") {
                $env:OPENCLAW_LLAMA_UBATCH_SIZE = "2048"
                $env:OPENCLAW_LLAMA_CTX_CHECKPOINTS = "32"
            } else {
                $env:OPENCLAW_LLAMA_UBATCH_SIZE = "512"
            }

            $brokerLauncher = Join-Path $PSHOME "powershell.exe"
            if (-not (Test-Path $brokerLauncher)) { $brokerLauncher = "powershell.exe" }

            $brokerArgs = @(
                "-NoLogo",
                "-ExecutionPolicy", "Bypass",
                "-File", $brokerWindowScript,
                "-PythonExe", $brokerPython,
                "-BrokerScript", $brokerScript,
                "-Port", "$brokerPort",
                "-LogFile", $brokerLogFile
            )
            if ($useWTTabs) {
                wt.exe -w 0 new-tab --title "ComfyUI Broker :$brokerPort" -- $brokerLauncher $brokerArgs
                $brokerProcess = $null
                Write-Host "  Broker lanzado en pestana de Windows Terminal..." -ForegroundColor Gray
            } else {
                $brokerProcess = Start-Process $brokerLauncher -ArgumentList $brokerArgs -WindowStyle Normal -PassThru
                Write-Host "  Broker lanzado en ventana separada (PID: $($brokerProcess.Id))..." -ForegroundColor Gray
            }
            Write-Host "[OK] Broker de ComfyUI lanzado (puerto $brokerPort)" -ForegroundColor Green
        }
    }
}
else {
    Write-Host "[!] comfyui-broker.py no encontrado" -ForegroundColor Yellow
}
Write-Host ""

# 5. Arrancar Wyoming STT bridge
if ($useWhisper) {
    Write-Host "[4/6] Iniciando Wyoming STT Bridge (puerto 10300)..." -ForegroundColor Yellow
    $wyomingSttScript = Find-Script "wyoming-whisper-bridge.py"
    if ($wyomingSttScript) {
        $sttRunning = $false
        try {
            $sock = New-Object System.Net.Sockets.TcpClient
            $sock.Connect("127.0.0.1", 10300)
            $sock.Close()
            $sttRunning = $true
        } catch {}
        if ($sttRunning) {
            Write-Host "[OK] Wyoming STT Bridge ya esta corriendo" -ForegroundColor Green
        } else {
            $sttDir = Split-Path $wyomingSttScript
            $sttDriveLetter = $sttDir.Substring(0,1).ToLower()
            $wslSttDir = "/mnt/$sttDriveLetter" + ($sttDir.Substring(2) -replace '\\','/')
            $sttProc = Start-Process wsl.exe -ArgumentList "-d", "Ubuntu", "--", "python3", "$wslSttDir/wyoming-whisper-bridge.py", "--whisper-url", "http://host.docker.internal:8787", "--port", "10300" -WindowStyle Hidden -PassThru
            $wyomingSttPid = $sttProc.Id
            Write-Host "[OK] Wyoming STT Bridge lanzado (PID: $wyomingSttPid, puerto 10300)" -ForegroundColor Green
        }
    } else {
        Write-Host "[!] wyoming-whisper-bridge.py no encontrado" -ForegroundColor Yellow
    }
} else {
    Write-Host "[4/6] Wyoming STT Bridge desactivado (useWhisper=false)" -ForegroundColor DarkGray
}
Write-Host ""

# 6. Arrancar Wyoming TTS bridge
if ($useWhisper) {
    Write-Host "[5/6] Iniciando Wyoming TTS Bridge (puerto 10200)..." -ForegroundColor Yellow
    $wyomingTtsScript = Find-Script "wyoming-edge-tts-bridge.py"
    if ($wyomingTtsScript) {
        $ttsRunning = $false
        try {
            $sock = New-Object System.Net.Sockets.TcpClient
            $sock.Connect("127.0.0.1", 10200)
            $sock.Close()
            $ttsRunning = $true
        } catch {}
        if ($ttsRunning) {
            Write-Host "[OK] Wyoming TTS Bridge ya esta corriendo" -ForegroundColor Green
        } else {
            $ttsDir = Split-Path $wyomingTtsScript
            $ttsDriveLetter = $ttsDir.Substring(0,1).ToLower()
            $wslTtsDir = "/mnt/$ttsDriveLetter" + ($ttsDir.Substring(2) -replace '\\','/')
            $ttsProc = Start-Process wsl.exe -ArgumentList "-d", "Ubuntu", "--", "python3", "$wslTtsDir/wyoming-edge-tts-bridge.py", "--port", "10200" -WindowStyle Hidden -PassThru
            $wyomingTtsPid = $ttsProc.Id
            Write-Host "[OK] Wyoming TTS Bridge lanzado (PID: $wyomingTtsPid, puerto 10200)" -ForegroundColor Green
        }
    } else {
        Write-Host "[!] wyoming-edge-tts-bridge.py no encontrado" -ForegroundColor Yellow
    }
} else {
    Write-Host "[5/6] Wyoming TTS Bridge desactivado (useWhisper=false)" -ForegroundColor DarkGray
}
Write-Host ""

# 7. Arrancar Hermes WebUI (WSL, puerto 8787)
if ($useHermesWebUI) {
    Write-Host "Iniciando Hermes WebUI (puerto 8787)..." -ForegroundColor Yellow
    $hermesWebUIPort = 8787
    $hwuiRunning = $false
    try { $null = Invoke-RestMethod -Uri "http://localhost:${hermesWebUIPort}/health" -Method Get -TimeoutSec 2 -ErrorAction Stop; $hwuiRunning = $true } catch {}

    if ($hwuiRunning) {
        Write-Host "[OK] Hermes WebUI ya esta corriendo en puerto $hermesWebUIPort" -ForegroundColor Green
    } elseif ($useWTTabs) {
        # Auto-patch: fix TERMINAL_CWD duplicate kwarg bug (hermes-webui v0.50.238+)
        $patchCheck = wsl.exe -d Ubuntu -- grep -c 'pop.*TERMINAL_CWD' /root/hermes-webui/api/streaming.py 2>$null
        if ($patchCheck -eq "0" -or -not $patchCheck) {
            wsl.exe -d Ubuntu -- sed -i '/_set_thread_env(\*\*_profile_runtime_env/i\        _profile_runtime_env.pop("TERMINAL_CWD", None)' /root/hermes-webui/api/streaming.py
            Write-Host "[PATCH] Aplicado fix TERMINAL_CWD en streaming.py" -ForegroundColor Cyan
        }
        $hwuiCmd = "cd /root/.hermes/hermes-agent && HERMES_WEBUI_HOST=0.0.0.0 exec venv/bin/python /root/hermes-webui/server.py"
        wt.exe -w 0 new-tab --title "Hermes WebUI :$hermesWebUIPort" -- wsl.exe -d Ubuntu -- bash -lc $hwuiCmd
        Write-Host "[OK] Hermes WebUI lanzado en pestana WSL (puerto $hermesWebUIPort)" -ForegroundColor Green
        Write-Host "  URL: http://localhost:$hermesWebUIPort" -ForegroundColor Gray
    } else {
        Write-Host "[!] Hermes WebUI requiere Windows Terminal para pestanas WSL" -ForegroundColor Yellow
    }

    # Port proxy para acceso LAN (la IP de WSL2 cambia en cada reinicio)
    $wslIp = (wsl.exe -d Ubuntu -- hostname -I).Trim().Split()[0]
    if ($wslIp) {
        Write-Host "  Configurando port proxy LAN (WSL2 IP: $wslIp)..." -ForegroundColor DarkCyan
        $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        $netshSetup = @"
netsh interface portproxy delete v4tov4 listenport=$hermesWebUIPort listenaddress=0.0.0.0 2>`$null
netsh interface portproxy add v4tov4 listenport=$hermesWebUIPort listenaddress=0.0.0.0 connectport=$hermesWebUIPort connectaddress=$wslIp
`$fw = netsh advfirewall firewall show rule name="Hermes WebUI LAN" 2>`$null
if (`$fw -notmatch 'Hermes WebUI LAN') { netsh advfirewall firewall add rule name="Hermes WebUI LAN" dir=in action=allow protocol=tcp localport=$hermesWebUIPort }
"@
        if ($isAdmin) {
            Invoke-Expression $netshSetup
        } else {
            $tmpScript = Join-Path ([System.IO.Path]::GetTempPath()) "hermes-portproxy-setup.ps1"
            $netshSetup | Set-Content $tmpScript -Encoding UTF8
            Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$tmpScript`"" -WindowStyle Hidden -Wait
            try { Remove-Item $tmpScript -Force } catch {}
        }
        Write-Host "  [OK] Port proxy LAN activo ($hermesWebUIPort -> ${wslIp}:$hermesWebUIPort)" -ForegroundColor Green
    } else {
        Write-Host "  [!] No se pudo obtener la IP de WSL2, acceso LAN no disponible" -ForegroundColor Yellow
    }
} else {
    Write-Host "Hermes WebUI desactivado (useHermesWebUI=false)" -ForegroundColor DarkGray
}
Write-Host ""

# 8. Arrancar Open WebUI
$openWebuiProcess = $null
if ($useOpenWebUI) {
    Write-Host "[6/6] Iniciando Open WebUI (puerto 8080)..." -ForegroundColor Yellow
    $openWebuiExe = "E:\Workspace\open-webui\.venv\Scripts\open-webui.exe"
    $openWebuiPort = 8080

    if (-not (Test-Path $openWebuiExe)) {
        Write-Host "[!] No se encuentra open-webui.exe en $openWebuiExe" -ForegroundColor Red
    } else {
        $owuiRunning = $false
        try { $null = Invoke-RestMethod -Uri "http://localhost:${openWebuiPort}/health" -Method Get -TimeoutSec 2 -ErrorAction Stop; $owuiRunning = $true } catch {}

        if ($owuiRunning) {
            Write-Host "[OK] Open WebUI ya esta corriendo en puerto $openWebuiPort" -ForegroundColor Green
        } else {
            $owuiEnv = @{
                DATA_DIR                       = "E:\Workspace\open-webui\data"
                OPENAI_API_BASE_URL            = "http://localhost:8642/v1"
                OPENAI_API_KEY                 = "hermes-owui-a7f3c9e2b1d4"
                WEBUI_AUTH                     = "true"
                PORT                           = "$openWebuiPort"
                HF_HUB_OFFLINE                 = "1"
                HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
                AUDIO_STT_ENGINE               = "openai"
                AUDIO_STT_OPENAI_API_BASE_URL  = "http://localhost:8787/v1"
                AUDIO_STT_OPENAI_API_KEY       = "not-needed"
                AUDIO_STT_MODEL                = "whisper-1"
            }
            if ($useWTTabs) {
                $owuiLaunchScript = Join-Path $openclawRoot "owui-launch.cmd"
                $owuiLines = @("@echo off")
                foreach ($kv in $owuiEnv.GetEnumerator()) { $owuiLines += "set $($kv.Key)=$($kv.Value)" }
                $owuiLines += "`"$openWebuiExe`" serve"
                $owuiLines | Set-Content $owuiLaunchScript -Encoding ASCII
                wt.exe -w 0 new-tab --title "Open WebUI :$openWebuiPort" -- cmd /c "`"$owuiLaunchScript`""
            } else {
                foreach ($kv in $owuiEnv.GetEnumerator()) { [Environment]::SetEnvironmentVariable($kv.Key, $kv.Value, "Process") }
                $openWebuiProcess = Start-Process $openWebuiExe -ArgumentList "serve" -WindowStyle Minimized -PassThru
            }
            Write-Host "[OK] Open WebUI lanzado (puerto $openWebuiPort)" -ForegroundColor Green
            Write-Host "  URL: http://localhost:$openWebuiPort" -ForegroundColor Gray
        }
    }
    Write-Host ""
}

# Warm-up
if ($llamaNeedsWarmup) {
    Write-Host "  Esperando a que llama-server cargue el modelo..." -ForegroundColor Yellow
    $maxWait = 180
    $waited = 0
    $llamaReady = $false
    while ($waited -lt $maxWait) {
        Start-Sleep -Seconds 3
        $waited += 3
        try {
            $null = Invoke-RestMethod -Uri "http://localhost:${llamaPort}/health" -Method Get -TimeoutSec 3 -ErrorAction Stop
            $llamaReady = $true
            break
        } catch {}
        if ($waited % 15 -eq 0) {
            Write-Host "  Cargando modelo... ($waited s)" -ForegroundColor Gray
        }
    }
    if ($llamaReady) {
        Write-Host "[OK] llama-server listo (puerto $llamaPort)" -ForegroundColor Green
        Invoke-LlamaWarmup -Port $llamaPort
    }
    else {
        Write-Host "[!] llama-server puede seguir cargando; warm-up se hara con la primera peticion" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "  Todos los servicios lanzados" -ForegroundColor Green
Write-Host "  Hermes gateway corriendo en pestana WSL" -ForegroundColor Gray
if ($useHermesWebUI) { Write-Host "  Hermes WebUI: http://localhost:8787" -ForegroundColor Gray }
if ($useOpenWebUI) { Write-Host "  Open WebUI: http://localhost:8080" -ForegroundColor Gray }
Write-Host "  Presiona Ctrl+C para detener todo" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Magenta
Write-Host ""

# Keep alive + cleanup
try {
    while ($true) { Start-Sleep -Seconds 60 }
}
finally {
    Write-Host ""
    Write-Host "[cleanup] llama-server sigue corriendo (puerto $llamaPort). Para detenerlo: Stop-Process -Name llama-server -Force" -ForegroundColor Gray
    if ($brokerProcess -and -not $brokerProcess.HasExited) {
        Write-Host "[cleanup] Deteniendo broker ComfyUI (PID: $($brokerProcess.Id))..." -ForegroundColor Yellow
        Stop-Process -Id $brokerProcess.Id -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Broker ComfyUI detenido." -ForegroundColor Green
    }
    if ($whisperProcess -and -not $whisperProcess.HasExited) {
        Write-Host "[cleanup] Deteniendo servidor Whisper (PID: $($whisperProcess.Id))..." -ForegroundColor Yellow
        Stop-Process -Id $whisperProcess.Id -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Servidor Whisper detenido." -ForegroundColor Green
    }
    if ($wyomingSttPid) {
        Write-Host "[cleanup] Deteniendo Wyoming STT Bridge (PID: $wyomingSttPid)..." -ForegroundColor Yellow
        try { Stop-Process -Id $wyomingSttPid -Force -ErrorAction SilentlyContinue } catch {}
        wsl.exe -d Ubuntu -- pkill -f "wyoming-whisper-bridge.py" 2>$null
        Write-Host "[OK] Wyoming STT Bridge detenido." -ForegroundColor Green
    }
    if ($wyomingTtsPid) {
        Write-Host "[cleanup] Deteniendo Wyoming TTS Bridge (PID: $wyomingTtsPid)..." -ForegroundColor Yellow
        try { Stop-Process -Id $wyomingTtsPid -Force -ErrorAction SilentlyContinue } catch {}
        wsl.exe -d Ubuntu -- pkill -f "wyoming-edge-tts-bridge.py" 2>$null
        Write-Host "[OK] Wyoming TTS Bridge detenido." -ForegroundColor Green
    }
    if ($openWebuiProcess -and -not $openWebuiProcess.HasExited) {
        Write-Host "[cleanup] Deteniendo Open WebUI (PID: $($openWebuiProcess.Id))..." -ForegroundColor Yellow
        Stop-Process -Id $openWebuiProcess.Id -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Open WebUI detenido." -ForegroundColor Green
    }
    # Limpiar port proxy LAN
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($isAdmin) {
        $null = netsh interface portproxy delete v4tov4 listenport=8787 listenaddress=0.0.0.0 2>$null
    } else {
        Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -Command `"netsh interface portproxy delete v4tov4 listenport=8787 listenaddress=0.0.0.0`"" -WindowStyle Hidden -Wait
    }
    Write-Host "[cleanup] Port proxy LAN eliminado." -ForegroundColor Gray
    Write-Host "[OK] Todo limpio. Hasta luego!" -ForegroundColor Cyan
    Start-Sleep -Seconds 2
    [Environment]::Exit(0)
}

# Hermes Agent Startup Script
# Uso:
#   .\start-hermes.ps1            -> arranca todo (llama-server + gateway + broker + ...)
#   .\start-hermes.ps1 -LlamaOnly -> SOLO llama-server con el perfil seleccionado
param([switch]$LlamaOnly)

# ---- CONFIGURACION ----
# Instalacion de llama.cpp: "stable" (mainline), "latest" (pruebas), "ik_llama" (fork con KV Q6_0 y MTP), "beellama" (DFlash + TurboQuant)
# ik_llama: KV Q6_0 (Hadamard rotations) para mas ctx, pero NO tiene --kv-unified asi que
# cada slot queda limitado a ctx/parallel tokens (vs mainline donde un slot puede usar todo el ctx).
# MTP tampoco funciona con multimodal. Volver a ik_llama cuando ambos problemas esten resueltos.
$useLlamaInstall = "stable"

# Modelo LLM: "qwen38_27b_unsloth_q6k_mtp", "qwen38_27b_nvfp4_q8attn_mtp", "qwen36_27b_bee_q5", "qwen36_27b_bee_q6", "qwen36_27b", "qwen36_27b_q6", "qwen36_27b_q4_mtp", "qwen36_27b_q5_mtp", "qwen36_27b_q6_mtp", "qwen36_27b_autoround_q6_mtp", "qwen36_27b_bartowski_q6kl_mtp", "qwen36", "qwen36q4", "qwen35", "gemma4"
$useModel = "qwen38_27b_nvfp4_q8attn_mtp"

# Herramienta browser: $true para activarla, $false para desactivarla
$useBrowserTool = $true

# Open WebUI: $true para arrancar la interfaz web en puerto 8080
$useOpenWebUI = $false

# Hermes WebUI: $true para arrancar hermes-webui en puerto 8787 (WSL)
$useHermesWebUI = $true

# Hermes Desktop backend: hermes serve en WSL, consumido por la app nativa Windows
$hermesDesktopPort = 9119

# Whisper + Wyoming bridges (Home Assistant): $true para arrancar whisper-server y bridges STT/TTS
# Discord y Telegram usan el STT interno de Hermes, no necesitan esto.
$useWhisper = $false
# -----------------------

# Auto-relaunch inside Windows Terminal so all services open as tabs
if (-not $env:WT_SESSION) {
    $wtExe = Get-Command wt.exe -ErrorAction SilentlyContinue
    if ($wtExe) {
        $scriptPath = $MyInvocation.MyCommand.Path
        $relaunchTitle = if ($LlamaOnly) { "Solo llama-server" } else { "Hermes Startup" }
        $extraArgs = @()
        if ($LlamaOnly) { $extraArgs = @("-LlamaOnly") }
        wt.exe new-tab --title $relaunchTitle -- powershell.exe -ExecutionPolicy Bypass -NoExit -File $scriptPath @extraArgs
        exit
    }
}

Write-Host "========================================" -ForegroundColor Magenta
$bannerTitle = if ($LlamaOnly) { "  Solo llama-server" } else { "  Hermes Agent Startup Script" }
Write-Host $bannerTitle -ForegroundColor Magenta
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
        $modelId = if ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp")) { "qwen3.8-27b" } else { "qwen3.6-27b" }
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
        "ik_llama" { return @{ Name = "ik_llama"; DirName = "ik_llama-cpp"; Label = "ik_llama.cpp" } }
        "beellama" { return @{ Name = "beellama"; DirName = "beellama\bin"; Label = "BeeLlama.cpp DFlash+TurboQuant" } }
        default { throw "Valor invalido para `$useLlamaInstall`: '$InstallName'. Usa 'stable', 'latest', 'ik_llama' o 'beellama'." }
    }
}

$llamaInstall = Get-LlamaInstallInfo -InstallName $useLlamaInstall
if ($useModel -in @("qwen36_27b_bee_q5","qwen36_27b_bee_q6") -and $useLlamaInstall -ne "beellama") {
    throw "Los modelos BeeLlama Qwen3.6-27B requieren `$useLlamaInstall = 'beellama'."
}

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
} elseif ($useModel -eq "qwen36_27b_bee_q5") {
    $modelLabel    = "Qwen3.6-27B-Q5_K_S + DFlash Q4_K_M"
    $modelSize     = "17.6 GB target + DFlash draft, vision+thinking, dense 27B, TurboQuant KV, ctx max"
    $ctxSize       = "262144"
} elseif ($useModel -eq "qwen36_27b_bee_q6") {
    $modelLabel    = "Qwen3.6-27B-Q6_K + DFlash Q4_K_M"
    $modelSize     = "21.0 GB target + DFlash draft, vision+thinking, dense 27B, TurboQuant KV, ctx 191k"
    $ctxSize       = "191608"
} elseif ($useModel -eq "qwen36_27b") {
    $modelLabel    = "Qwen3.6-27B-UD-Q4_K_XL"
    $modelSize     = "17.6 GB, vision+thinking, dense 27B, Unsloth Dynamic 2.0, KV Q8_0+rot"
    $ctxSize       = "200000"
} elseif ($useModel -eq "qwen36_27b_q6") {
    if ($useLlamaInstall -eq "ik_llama") {
        $modelLabel    = "Qwen3.6-27B-Q6_K"
        $modelSize     = "22.5 GB, vision+thinking, dense 27B, Q6_K, KV Q6_0+Hadamard (ik_llama unifies KV across 4 slots)"
        $ctxSize       = "196608"
    } else {
        $modelLabel    = "Qwen3.6-27B-Q6_K"
        $modelSize     = "22.5 GB, vision+thinking, dense 27B, Q6_K, KV Q8_0+rot"
        $ctxSize       = "131072"
    }
} elseif ($useModel -eq "qwen36_27b_q4_mtp") {
    $modelLabel    = "Qwen3.6-27B-UD-Q4_K_XL MTP"
    $modelSize     = "17.9 GB + MTP/NextN heads, vision+thinking, dense 27B, Unsloth Dynamic 2.0, mainline llama.cpp MTP, KV Q8_0, ctx 150k"
    $ctxSize       = "150000"
} elseif ($useModel -eq "qwen36_27b_q5_mtp") {
    $modelLabel    = "Qwen3.6-27B-UD-Q5_K_XL MTP"
    $modelSize     = "20.4 GB + MTP/NextN heads, vision+thinking, dense 27B, mainline llama.cpp MTP, KV Q8_0, ctx 130k"
    $ctxSize       = "130000"
} elseif ($useModel -eq "qwen36_27b_q6_mtp") {
    $modelLabel    = "Qwen3.6-27B-Q6_K MTP"
    $modelSize     = "22.9 GB + MTP/NextN heads, vision+thinking, dense 27B, mainline llama.cpp MTP, KV K Q5_1 / V Q4_0 + draft KV F16, ctx 170k, encoder en GPU"
    $ctxSize       = "170000"
} elseif ($useModel -eq "qwen36_27b_autoround_q6_mtp") {
    $modelLabel    = "Qwen3.6-27B-AutoRound-Q6_K MTP"
    $modelSize     = "21 GB + MTP/NextN heads, vision+thinking, dense 27B, Intel AutoRound Q6_K (sphaela, virtually indistinguishable from F16), KV K Q8_0 / V Q5_1 + draft KV F16, ctx 150k, encoder en GPU"
    $ctxSize       = "150000"
} elseif ($useModel -eq "qwen36_27b_bartowski_q6kl_mtp") {
    $modelLabel    = "Qwen3.6-27B Bartowski Q6_K_L MTP"
    $modelSize     = "22.6 GiB, MTP/NextN integrado Q8_0, vision+thinking, KV K Q8_0 / V Q5_1 + draft KV F16, ctx 115k"
    $ctxSize       = "115000"
} elseif ($useModel -eq "qwen38_27b_unsloth_q6k_mtp") {
    $modelLabel    = "Qwen3.8-27B Unsloth Q6_K MTP"
    $modelSize     = "21.3 GiB, MTP integrado, vision+thinking xhigh, KV K Q8_0 / V Q5_1 + draft KV F16, ctx 140k"
    $ctxSize       = "140000"
} elseif ($useModel -eq "qwen38_27b_nvfp4_q8attn_mtp") {
    $modelLabel    = "Qwen3.8-27B NVFP4-MTP-Q8attn (utautako)"
    $modelSize     = "17.8 GiB, MTP integrado, FFN NVFP4 + atencion/DeltaNet Q8_0, vision+thinking xhigh, KV K Q8_0 / V Q5_1 + draft KV F16, ctx 230k (margen VRAM)"
    $ctxSize       = "230000"
} elseif ($useModel -eq "gemma4") {
    $modelLabel    = "Gemma 4 31B-it UD-Q4_K_XL"
    $modelSize     = "17.5 GB, vision+thinking"
    $ctxSize       = "100000"
} else {
    $modelLabel    = "Qwen3.5-27B-UD-Q4_K_XL"
    $modelSize     = "17.6 GB, vision"
    $ctxSize       = "131072"
}

# Sampling params — single source of truth for both llama-server and broker restarts
# 2026-08-15: qwen38 = 1.0 (recomendación oficial Unsloth para 3.8 thinking-only;
# se probó 0.8 y se volvió al punto sintonizado oficial). Resto de perfiles: 0.6.
$env:OPENCLAW_LLAMA_TEMP = if ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp")) { "1.0" } else { "0.6" }
$env:OPENCLAW_LLAMA_TOP_P = "0.95"
$env:OPENCLAW_LLAMA_TOP_K = "20"
$env:OPENCLAW_LLAMA_MIN_P = "0"
$env:OPENCLAW_LLAMA_PREDICT = "81920"
if ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp","qwen36_27b_bee_q5","qwen36_27b_bee_q6","qwen36_27b","qwen36_27b_q6","qwen36_27b_q4_mtp","qwen36_27b_q5_mtp","qwen36_27b_q6_mtp","qwen36_27b_autoround_q6_mtp","qwen36_27b_bartowski_q6kl_mtp")) {
    $env:OPENCLAW_LLAMA_PRESENCE_PENALTY = "0"
} else {
    $env:OPENCLAW_LLAMA_PRESENCE_PENALTY = "1.5"
}

# MTP (Multi-Token Prediction) — upstream llama.cpp mainline uses --spec-type draft-mtp.
# Requires a GGUF that includes MTP/NextN heads. Keep this isolated in qwen36_27b_*_mtp
# so BeeLlama/DFlash remains one edit away if MTP is not stable enough for Hermes.
$env:OPENCLAW_LLAMA_MTP_ENABLED = if ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp","qwen36_27b_q4_mtp","qwen36_27b_q5_mtp","qwen36_27b_q6_mtp","qwen36_27b_autoround_q6_mtp","qwen36_27b_bartowski_q6kl_mtp")) { "1" } else { "0" }
# 2026-08-15: 3 (default llama.cpp) para qwen38 — con 65% acceptance y meanlen 2.5
# el 3er token draftado casi siempre se acepta (+5-12% TG). Resto de perfiles: 2.
$env:OPENCLAW_LLAMA_MTP_DRAFT_N_MAX = if ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp")) { "3" } else { "2" }
$env:OPENCLAW_LLAMA_MTP_DRAFT_P_MIN = "0"

Write-Host "[1/6] Comprobando llama-server ($modelLabel)..." -ForegroundColor Yellow

$llamaRoot       = Join-Path $openclawRoot $llamaInstall.DirName
$llamaServerExe  = Join-Path $llamaRoot "llama-server.exe"
if ($useModel -eq "qwen36") {
    $modelFile    = Join-Path $openclawRoot "models\qwen36-35b\Qwen3.6-35B-A3B-Q5_K_M.gguf"
    $mmProjFile   = Join-Path $openclawRoot "models\qwen36-35b\mmproj-BF16.gguf"
} elseif ($useModel -eq "qwen36q4") {
    $modelFile    = Join-Path $openclawRoot "models\qwen36-35b\Qwen3.6-35B-A3B-Q4_K_L.gguf"
    $mmProjFile   = Join-Path $openclawRoot "models\qwen36-35b\mmproj-BF16.gguf"
} elseif ($useModel -eq "qwen36_27b_bee_q5") {
    $modelFile    = Join-Path $openclawRoot "beellama\models\Qwen3.6-27B-Q5_K_S.gguf"
    $mmProjFile   = Join-Path $openclawRoot "beellama\models\mmproj-BF16.gguf"
    $draftModelFile = Join-Path $openclawRoot "beellama\models\dflash-draft-3.6-q4_k_m.gguf"
} elseif ($useModel -eq "qwen36_27b_bee_q6") {
    $modelFile    = Join-Path $openclawRoot "models\qwen36-27b\Qwen3.6-27B-Q6_K.gguf"
    $mmProjFile   = Join-Path $openclawRoot "models\qwen36-27b\mmproj-BF16.gguf"
    $draftModelFile = Join-Path $openclawRoot "beellama\models\dflash-draft-3.6-q4_k_m.gguf"
} elseif ($useModel -eq "qwen36_27b") {
    $modelFile    = Join-Path $openclawRoot "models\qwen36-27b\Qwen3.6-27B-UD-Q4_K_XL.gguf"
    $mmProjFile   = Join-Path $openclawRoot "models\qwen36-27b\mmproj-BF16.gguf"
} elseif ($useModel -eq "qwen36_27b_q6") {
    # Use MTP gguf only when MTP esta activado; con MTP off el gguf MTP carga ~400 MiB extra inutiles.
    if ($useLlamaInstall -eq "ik_llama" -and $env:OPENCLAW_LLAMA_MTP_ENABLED -eq "1") {
        $modelFile = Join-Path $openclawRoot "models\qwen36-27b\Qwen3.6-27B-Q6_K-mtp.gguf"
    } else {
        $modelFile = Join-Path $openclawRoot "models\qwen36-27b\Qwen3.6-27B-Q6_K.gguf"
    }
    $mmProjFile   = Join-Path $openclawRoot "models\qwen36-27b\mmproj-BF16.gguf"
} elseif ($useModel -eq "qwen36_27b_q4_mtp") {
    # Same file as qwen36_27b profile: Unsloth's UD-Q4_K_XL gguf already includes MTP heads
    $modelFile    = Join-Path $openclawRoot "models\qwen36-27b\Qwen3.6-27B-UD-Q4_K_XL.gguf"
    $mmProjFile   = Join-Path $openclawRoot "models\qwen36-27b\mmproj-F16.gguf"
} elseif ($useModel -eq "qwen36_27b_q5_mtp") {
    $modelFile    = Join-Path $openclawRoot "models\qwen36-27b\Qwen3.6-27B-UD-Q5_K_XL.gguf"
    $mmProjFile   = Join-Path $openclawRoot "models\qwen36-27b\mmproj-F16.gguf"
} elseif ($useModel -eq "qwen36_27b_q6_mtp") {
    $modelFile    = Join-Path $openclawRoot "models\qwen36-27b\Qwen3.6-27B-Q6_K-mtp.gguf"
    $mmProjFile   = Join-Path $openclawRoot "models\qwen36-27b\mmproj-BF16.gguf"
} elseif ($useModel -eq "qwen36_27b_autoround_q6_mtp") {
    $modelFile    = Join-Path $openclawRoot "models\qwen36-27b\Qwen3.6-27B-AutoRound-Q6_K.gguf"
    $mmProjFile   = Join-Path $openclawRoot "models\qwen36-27b\mmproj-BF16.gguf"
} elseif ($useModel -eq "qwen36_27b_bartowski_q6kl_mtp") {
    $modelFile    = Join-Path $openclawRoot "models\qwen36-27b\Qwen_Qwen3.6-27B-Q6_K_L.gguf"
    $mmProjFile   = Join-Path $openclawRoot "models\qwen36-27b\mmproj-BF16.gguf"
} elseif ($useModel -eq "qwen38_27b_unsloth_q6k_mtp") {
    $modelFile    = Join-Path $openclawRoot "models\qwen38-27b\Qwen3.8-27B-Q6_K.gguf"
    $mmProjFile   = Join-Path $openclawRoot "models\qwen38-27b\mmproj-BF16.gguf"
} elseif ($useModel -eq "qwen38_27b_nvfp4_q8attn_mtp") {
    $modelFile    = Join-Path $openclawRoot "models\qwen38-27b\Qwen3.8-27B-NVFP4-MTP-Q8attn.gguf"
    $mmProjFile   = Join-Path $openclawRoot "models\qwen38-27b\mmproj-BF16.gguf"
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
elseif ($useModel -in @("qwen36_27b_bee_q5","qwen36_27b_bee_q6") -and -not (Test-Path $draftModelFile)) {
    Write-Host "[!] No se encuentra el draft DFlash GGUF en $draftModelFile" -ForegroundColor Red
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
        $llamaLaunchEnv = @{}
        $llamaArgs = @(
            "--model",               $modelFile,
            "--alias",               $(if ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp")) { "qwen3.8-27b,$useModel" } else { "qwen3.6-27b,$useModel" }),
            "--mmproj",              $mmProjFile,
            "--ctx-size",            $ctxSize,
            "--slot-save-path",      $slotCachePath,
            "--n-gpu-layers",        "99",
            "--flash-attn",          "on",
            "--batch-size",          "2048",
            "--host",                "0.0.0.0",
            "--port",                $llamaPort,
            "--cont-batching",
            "--log-file",            $llamaLogFile
        )
        # Model-specific flags
        if ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp","qwen36","qwen36q4","qwen36_27b_bee_q5","qwen36_27b_bee_q6","qwen36_27b","qwen36_27b_q6","qwen36_27b_q4_mtp","qwen36_27b_q5_mtp","qwen36_27b_q6_mtp","qwen36_27b_autoround_q6_mtp","qwen36_27b_bartowski_q6kl_mtp")) {
            $chatTemplateFile = if ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp")) { $null } else { Join-Path $openclawRoot "models\qwen36-27b\qwen3.6-enhanced.jinja" }
            $ubatchSize = if ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp","qwen36_27b_q6_mtp","qwen36_27b_autoround_q6_mtp","qwen36_27b_bartowski_q6kl_mtp")) { "1024" } else { "2048" }
            $llamaArgs += @("--ubatch-size", $ubatchSize)
            $llamaArgs += @("--jinja")
            if ($chatTemplateFile) { $llamaArgs += @("--chat-template-file", $chatTemplateFile) }
            $llamaArgs += @("--reasoning", "on")
            if ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp")) { $llamaArgs += @("--reasoning-preserve") }
            $llamaArgs += @("--image-min-tokens", "1024")
            $llamaArgs += @("--image-max-tokens", "1024")
            $llamaArgs += @("--presence-penalty", $env:OPENCLAW_LLAMA_PRESENCE_PENALTY)
            $llamaArgs += @("--min-p", $env:OPENCLAW_LLAMA_MIN_P)
            $llamaArgs += @("--predict", $env:OPENCLAW_LLAMA_PREDICT)
            $llamaArgs += @("--temp", $env:OPENCLAW_LLAMA_TEMP, "--top-p", $env:OPENCLAW_LLAMA_TOP_P, "--top-k", $env:OPENCLAW_LLAMA_TOP_K)
            $chatTemplateKwargs = if ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp")) { '{"enable_thinking":true,"preserve_thinking":true,"reasoning_effort":"xhigh"}' } else { '{"preserve_thinking":true,"tool_call_format":"xml"}' }
            $env:LLAMA_CHAT_TEMPLATE_KWARGS = $chatTemplateKwargs
            $llamaLaunchEnv["LLAMA_CHAT_TEMPLATE_KWARGS"] = $chatTemplateKwargs
            $llamaArgs += @("--no-prefill-assistant")
            # MTP keeps draft state per slot, breaking ik_llama's KV unification.
            # Force parallel=1 when MTP active on ik_llama to avoid KV exhaustion.
            $useMtp = ($env:OPENCLAW_LLAMA_MTP_ENABLED -eq "1")
            if ($useModel -in @("qwen36_27b_bee_q5","qwen36_27b_bee_q6")) {
                $llamaArgs += @("--parallel", "1")
            } elseif ($useMtp) {
                $llamaArgs += @("--parallel", "1")
            } else {
                $llamaArgs += @("--parallel", "2")
            }
            if ($useLlamaInstall -eq "ik_llama") {
                # ik_llama unifies KV across slots by default (n_ctx is total, not per-slot).
                # Lacks --kv-unified / --no-cache-idle-slots; checkpoint flag is renamed.
                $llamaArgs += @("--ctx-checkpoints", "32", "--ctx-checkpoints-interval", "1024", "--cache-ram", "16384", "--no-context-shift")
            } elseif ($useModel -in @("qwen36_27b_bee_q5","qwen36_27b_bee_q6")) {
                $llamaArgs += @("--kv-unified", "--ctx-checkpoints", "32", "--checkpoint-min-step", "8192", "--cache-ram", "32768", "--no-context-shift", "--no-cache-idle-slots")
            } elseif ($useMtp) {
                # Mainline MTP: keep checkpoints dense enough for rollback while retaining
                # a broader span of long agentic histories within the 32-checkpoint limit.
                # --cache-ram bounds the secondary prompt cache; live slot checkpoints use process RAM.
                # --kv-unified is mainline-only and compatible with MTP (single shared KV pool).
                $promptCacheRam = if ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp","qwen36_27b_autoround_q6_mtp","qwen36_27b_bartowski_q6kl_mtp")) { "32768" } else { "16384" }
                $llamaArgs += @("--kv-unified", "--ctx-checkpoints", "32", "--checkpoint-min-step", "2048", "--cache-ram", $promptCacheRam, "--no-context-shift")
            } else {
                $llamaArgs += @("--kv-unified", "--ctx-checkpoints", "32", "--checkpoint-min-step", "1024", "--cache-ram", "16384", "--no-context-shift")
            }
            if ($useModel -in @("qwen36_27b_bee_q5","qwen36_27b_bee_q6")) {
                $llamaArgs += @("--spec-type", "dflash")
                $llamaArgs += @("--spec-draft-model", $draftModelFile)
                $llamaArgs += @("--spec-draft-ngl", "all")
                $llamaArgs += @("--spec-dflash-cross-ctx", "1024")
                $llamaArgs += @("--spec-draft-n-max", "16", "--spec-dm-controller", "profit")
                $llamaArgs += @("--cache-type-k", "turbo4", "--cache-type-v", "turbo3_tcq")
                $llamaArgs += @("--no-mmproj-offload")
                $llamaArgs += @("--log-verbosity", "2", "--perf", "--metrics", "--log-timestamps", "--log-prefix")
                $beeDflashLogEnv = @{
                    GGML_DFLASH_PROFILE = "summary"
                }
                foreach ($kv in $beeDflashLogEnv.GetEnumerator()) {
                    [Environment]::SetEnvironmentVariable($kv.Key, $kv.Value, "Process")
                    $llamaLaunchEnv[$kv.Key] = $kv.Value
                }
                Write-Host "  BeeLlama DFlash activado (draft Q4_K_M, KV turbo4/turbo3_tcq, parallel=1, logs resumen)" -ForegroundColor Cyan
            } elseif ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp","qwen36_27b","qwen36_27b_q6","qwen36_27b_q4_mtp","qwen36_27b_q5_mtp","qwen36_27b_q6_mtp","qwen36_27b_autoround_q6_mtp","qwen36_27b_bartowski_q6kl_mtp")) {
                if ($useLlamaInstall -eq "ik_llama" -and $useModel -eq "qwen36_27b_q6") {
                    # Q6_0 KV cache (ik_llama exclusive low-perp variant) — leaves headroom for MTP draft
                    $llamaArgs += @("-ctk", "q6_0", "-ctv", "q6_0")
                } elseif ($useModel -in @("qwen36_27b_q4_mtp","qwen36_27b_q5_mtp")) {
                    $llamaArgs += @("-ctk", "q8_0", "-ctv", "q8_0")
                } elseif ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp","qwen36_27b_autoround_q6_mtp","qwen36_27b_bartowski_q6kl_mtp")) {
                    # AutoRound pesa ~1.9 GB menos -> usamos ese margen para subir el KV a
                    # K q8_0 / V q5_1 (mejor recall fino).
                    $llamaArgs += @("-ctk", "q8_0", "-ctv", "q5_1")
                } elseif ($useModel -eq "qwen36_27b_q6_mtp") {
                    # K/V invertidos vs q4_0/q5_1: mismos bytes pero la mayor precision (q5_1) va a K, que es mas sensible
                    $llamaArgs += @("-ctk", "q5_1", "-ctv", "q4_0")
                } else {
                    $llamaArgs += @("-ctk", "q8_0", "-ctv", "q8_0")
                }
            }
            # Estos perfiles mantienen el encoder de vision en CPU para reservar VRAM al KV.
            if ($useModel -in @("qwen36_27b_q6","qwen36_27b_q4_mtp","qwen36_27b_q5_mtp") -and $useLlamaInstall -ne "ik_llama") {
                # --no-mmproj-offload doesn't exist in ik_llama
                $llamaArgs += @("--no-mmproj-offload")
            }
            # MTP (Multi-Token Prediction) — upstream llama.cpp mainline draft-mtp mode.
            if ($env:OPENCLAW_LLAMA_MTP_ENABLED -eq "1") {
                if ($useLlamaInstall -eq "ik_llama") {
                    $llamaArgs += @("-mtp", "--draft-max", $env:OPENCLAW_LLAMA_MTP_DRAFT_N_MAX)
                    Write-Host "  MTP activado (-mtp --draft-max $($env:OPENCLAW_LLAMA_MTP_DRAFT_N_MAX))" -ForegroundColor Cyan
                } else {
                    $llamaArgs += @("--spec-type", "draft-mtp,ngram-mod", "--spec-draft-n-max", $env:OPENCLAW_LLAMA_MTP_DRAFT_N_MAX)
                    if ($env:OPENCLAW_LLAMA_MTP_DRAFT_P_MIN -ne "0") {
                        $llamaArgs += @("--spec-draft-p-min", $env:OPENCLAW_LLAMA_MTP_DRAFT_P_MIN)
                    }
                    $llamaArgs += @("--cache-type-k-draft", "f16", "--cache-type-v-draft", "f16")
                    $llamaArgs += @("--spec-default")
                    Write-Host "  MTP + ngram-mod activados (--spec-type draft-mtp,ngram-mod --spec-draft-n-max $($env:OPENCLAW_LLAMA_MTP_DRAFT_N_MAX), p-min $($env:OPENCLAW_LLAMA_MTP_DRAFT_P_MIN), draft KV F16 + --spec-default)" -ForegroundColor Cyan
                }
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
            foreach ($kv in $llamaLaunchEnv.GetEnumerator()) {
                $launchLines += "set $($kv.Key)=$($kv.Value)"
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

# -LlamaOnly: detenernos aqui. El resto (gateway, desktop backend, broker,
# WebUI, port proxies...) no se toca.
if ($LlamaOnly) {
    if ($llamaNeedsWarmup) {
        Write-Host "  Esperando a que llama-server cargue el modelo..." -ForegroundColor Yellow
        $maxWait = 300
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
        if (-not $llamaReady) {
            Write-Host "[!] llama-server no ha respondido en $maxWait s; revisa el log: $llamaLogFile" -ForegroundColor Yellow
        }
        else {
            Invoke-LlamaWarmup -Port $llamaPort
        }
    }
    else {
        # Server ya corria antes de lanzar: verificar que sea del perfil seleccionado.
        # /v1/models devuelve id=alias principal; el perfil va en .aliases.
        $mismatch = $false
        $runningIds = @()
        try {
            $models = Invoke-RestMethod -Uri "http://localhost:${llamaPort}/v1/models" -Method Get -TimeoutSec 10
            $runningIds = @($models.data | ForEach-Object { @($_.id); @($_.aliases) } | Where-Object { $_ })
            $mismatch = -not ($useModel -in $runningIds)
        } catch {
            Write-Host "  [!] No se pudo consultar /v1/models para verificar el perfil" -ForegroundColor Yellow
        }
        if ($mismatch) {
            Write-Host "[!] El llama-server corriendo en :$llamaPort NO es el perfil seleccionado" -ForegroundColor Yellow
            Write-Host "    Corriendo: $($runningIds -join ', ')" -ForegroundColor Yellow
            Write-Host "    Pedido:   $useModel" -ForegroundColor Yellow
            Write-Host "    Para usar el perfil correcto: Stop-Process -Name llama-server -Force" -ForegroundColor Yellow
            Write-Host "    y reejecuta este acceso directo." -ForegroundColor Yellow
        }
        else {
            Write-Host "[OK] El llama-server corriendo ya es el perfil seleccionado ($useModel)" -ForegroundColor Green
        }
    }
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Magenta
    Write-Host "  Solo llama-server" -ForegroundColor Magenta
    Write-Host "  http://localhost:$llamaPort  ($modelLabel)" -ForegroundColor Gray
    Write-Host "  Para detenerlo: Stop-Process -Name llama-server -Force" -ForegroundColor Gray
    Write-Host "========================================" -ForegroundColor Magenta
    Write-Host ""
    [Environment]::Exit(0)
}

# Auto-patch: fix preflight token estimation for images (base64 over-count bug)
$patchFile = "/root/.hermes/hermes-agent/agent/model_metadata.py"
$patchCheck = wsl.exe -d Ubuntu -- grep -c '_estimate_messages_chars' $patchFile 2>$null
if ($patchCheck -eq "0" -or -not $patchCheck) {
    $patchScript = @'
import sys
filepath = "/root/.hermes/hermes-agent/agent/model_metadata.py"
with open(filepath, "r") as f:
    content = f.read()
old = "    if messages:\n        total_chars += sum(len(str(msg)) for msg in messages)"
new = """    if messages:
        total_chars += _estimate_messages_chars(messages)"""
if old in content:
    # Also inject the helper function after the closing of estimate_request_tokens_rough
    helper = '''

def _estimate_messages_chars(messages):
    """Estimate char count for messages, treating images as ~6400 chars (~1600 tokens).

    Avoids counting raw base64 image data which massively over-estimates token usage.
    """
    _IMAGE_CHARS = 6400
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, str):
                    total += len(part)
                elif isinstance(part, dict):
                    ptype = part.get("type", "")
                    if ptype in ("image_url", "input_image", "image"):
                        total += _IMAGE_CHARS
                    elif "text" in part:
                        total += len(part["text"])
                    else:
                        total += len(str(part))
        else:
            total += len(str(content))
        total += 20
    return total'''
    content = content.replace(old, new)
    # Insert helper after the function
    marker = "    return (total_chars + 3) // 4"
    idx = content.find(marker, content.find("estimate_request_tokens_rough"))
    if idx > 0:
        end = idx + len(marker)
        content = content[:end] + helper + content[end:]
    with open(filepath, "w") as f:
        f.write(content)
    print("OK")
else:
    print("SKIP")
'@
    $result = $patchScript | wsl.exe -d Ubuntu -- python3
    if ($result -eq "OK") {
        Write-Host "[PATCH] Fix preflight image token estimation aplicado" -ForegroundColor Cyan
    }
}

# Gateway WSL: launch Hermes gateway in a WSL tab
if ($useWTTabs) {
    $driveLetter = $PSScriptRoot.Substring(0,1).ToLower()
    $wslDir = "/mnt/$driveLetter" + ($PSScriptRoot.Substring(2) -replace '\\','/')
    Write-Host "  Lanzando Hermes gateway en pestana WSL..." -ForegroundColor DarkCyan
    $browserFlag = if ($useBrowserTool) { 'on' } else { 'off' }
    $tailscaleFlag = if ($useOpenWebUI -or $useHermesWebUI) { 'on' } else { 'off' }
    wt.exe -w 0 new-tab --title "Hermes Gateway (WSL)" -- wsl.exe -d Ubuntu -- bash -lc "cd '$wslDir' && USE_MODEL='$useModel' USE_BROWSER_TOOL='$browserFlag' USE_TAILSCALE='$tailscaleFlag' ./start-hermes-wsl.sh"
    Write-Host "[OK] Hermes gateway lanzado en pestana WSL" -ForegroundColor Green

    # Hermes Desktop backend: pestana propia con su propio ciclo de reinicio
    # (independiente del gateway; el update de la app Desktop puede matar este
    # proceso sin tocar el gateway, y viceversa).
    Write-Host "  Lanzando Hermes Desktop backend en pestana WSL..." -ForegroundColor DarkCyan
    wt.exe -w 0 new-tab --title "Hermes Desktop Backend (WSL)" -- wsl.exe -d Ubuntu -- bash -lc "cd '$wslDir' && DESKTOP_SERVE_PORT='$hermesDesktopPort' ./start-hermes-desktop-backend.sh"
    Write-Host "[OK] Hermes Desktop backend lanzado en pestana WSL" -ForegroundColor Green

    # Port proxy para Hermes Desktop (Windows app -> WSL hermes serve)
    $wslIp = (wsl.exe -d Ubuntu -- hostname -I).Trim().Split()[0]
    if ($wslIp) {
        Write-Host "  Configurando port proxy Hermes Desktop (WSL2 IP: $wslIp)..." -ForegroundColor DarkCyan
        $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        $netshSetup = @"
netsh interface portproxy delete v4tov4 listenport=$hermesDesktopPort listenaddress=0.0.0.0 2>`$null
netsh interface portproxy add v4tov4 listenport=$hermesDesktopPort listenaddress=0.0.0.0 connectport=$hermesDesktopPort connectaddress=$wslIp
`$fw = netsh advfirewall firewall show rule name="Hermes Desktop Backend" 2>`$null
if (`$fw -notmatch 'Hermes Desktop Backend') { netsh advfirewall firewall add rule name="Hermes Desktop Backend" dir=in action=allow protocol=tcp localport=$hermesDesktopPort }
"@
        if ($isAdmin) {
            Invoke-Expression $netshSetup
        } else {
            $tmpScript = Join-Path ([System.IO.Path]::GetTempPath()) "hermes-desktop-portproxy-setup.ps1"
            $netshSetup | Set-Content $tmpScript -Encoding UTF8
            Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$tmpScript`"" -WindowStyle Hidden -Wait
            try { Remove-Item $tmpScript -Force } catch {}
        }
        Write-Host "  [OK] Hermes Desktop backend accesible en http://localhost:$hermesDesktopPort" -ForegroundColor Green
    } else {
        Write-Host "  [!] No se pudo obtener la IP de WSL2, Hermes Desktop no tendra port proxy" -ForegroundColor Yellow
    }

    # Chat tab: opens hermes TUI after llama-server is ready
    # Desactivado: no se usa. Descomentar estas 3 lineas para reactivarlo.
    # Write-Host "  Lanzando pestana de chat con Hermes..." -ForegroundColor DarkCyan
    # wt.exe -w 0 new-tab --title "Hermes Chat" -- wsl.exe -d Ubuntu -- bash -l "$wslDir/start-hermes-chat.sh"
    # Write-Host "[OK] Pestana de chat lanzada (esperara a llama-server)" -ForegroundColor Green
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
$expectedBrokerComfyAppDir = "E:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI"

if ($brokerScript) {
    $brokerRunning = $false
    $brokerHealth = $null
    try {
        $brokerHealth = Invoke-RestMethod -Uri "http://localhost:${brokerPort}/health" -Method Get -TimeoutSec 2 -ErrorAction Stop
        $brokerRunning = (
            $brokerHealth.llama_profile -eq $useModel -and
            $brokerHealth.comfy_app_dir -eq $expectedBrokerComfyAppDir
        )
        if (-not $brokerRunning) {
            Write-Host "  Broker desactualizado: perfil=$($brokerHealth.llama_profile), ComfyUI=$($brokerHealth.comfy_app_dir)" -ForegroundColor Yellow
        }
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
            $env:OPENCLAW_COMFYUI_APP_DIR = $expectedBrokerComfyAppDir
            if ($brokerModelPathsConfig -and (Test-Path $brokerModelPathsConfig)) { $env:OPENCLAW_COMFYUI_EXTRA_MODEL_PATHS_CONFIG = $brokerModelPathsConfig }
            $env:OPENCLAW_COMFYUI_HOST = "127.0.0.1"
            $env:OPENCLAW_COMFYUI_PORT = "8000"
            $env:OPENCLAW_USE_BACKEND = "llama-server"

            $env:OPENCLAW_LLAMA_SLOT_SAVE_PATH = Join-Path $openclawRoot "slot-cache"
            $env:OPENCLAW_BROKER_LOG_FILE = Join-Path $openclawRoot "broker.log"
            if ($llamaServerExe) { $env:OPENCLAW_LLAMA_SERVER_EXE = $llamaServerExe }
            if ($modelFile) { $env:OPENCLAW_LLAMA_MODEL = $modelFile }
            if ($mmProjFile) { $env:OPENCLAW_LLAMA_MMPROJ = $mmProjFile }
            if ($draftModelFile) { $env:OPENCLAW_LLAMA_DRAFT_MODEL = $draftModelFile }
            if ($llamaLogFile) { $env:OPENCLAW_LLAMA_LOG_FILE = $llamaLogFile }
            $env:OPENCLAW_LLAMA_PORT = [string]$llamaPort
            $env:OPENCLAW_LLAMA_CTX_SIZE = $ctxSize
            $env:OPENCLAW_LLAMA_PARALLEL = if ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp","qwen36_27b_bee_q5","qwen36_27b_bee_q6","qwen36_27b_q4_mtp","qwen36_27b_q5_mtp","qwen36_27b_q6_mtp","qwen36_27b_autoround_q6_mtp","qwen36_27b_bartowski_q6kl_mtp")) { "1" } else { "2" }
            $env:OPENCLAW_LLAMA_N_GPU_LAYERS = "99"
            $env:OPENCLAW_LLAMA_BATCH_SIZE = "2048"
            $env:OPENCLAW_LLAMA_PROFILE = $useModel
            if ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp","qwen36","qwen36q4","qwen36_27b_bee_q5","qwen36_27b_bee_q6","qwen36_27b","qwen36_27b_q6","qwen36_27b_q4_mtp","qwen36_27b_q5_mtp","qwen36_27b_q6_mtp","qwen36_27b_autoround_q6_mtp","qwen36_27b_bartowski_q6kl_mtp")) {
                $env:OPENCLAW_LLAMA_UBATCH_SIZE = if ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp","qwen36_27b_q6_mtp","qwen36_27b_autoround_q6_mtp","qwen36_27b_bartowski_q6kl_mtp")) { "1024" } else { "2048" }
                $env:OPENCLAW_LLAMA_CTX_CHECKPOINTS = "32"
                $env:OPENCLAW_LLAMA_CHAT_TEMPLATE = if ($useModel -in @("qwen38_27b_unsloth_q6k_mtp","qwen38_27b_nvfp4_q8attn_mtp")) { "" } else { Join-Path $openclawRoot "models\qwen36-27b\qwen3.6-enhanced.jinja" }
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
Write-Host "  Hermes Desktop backend: http://localhost:$hermesDesktopPort" -ForegroundColor Gray
if ($useHermesWebUI) { Write-Host "  Hermes WebUI: https://localhost:8787" -ForegroundColor Gray }
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

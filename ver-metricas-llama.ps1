param(
    [string]$LlamaUrl = "http://localhost:30000",
    [string]$LlamaLog = "E:\Workspace\Openclaw\llama-server.log",
    [int]$TailLines = 2500
)

$ErrorActionPreference = "SilentlyContinue"

Write-Host ""
Write-Host "+==========================================================+"
Write-Host "|              METRICAS LLAMA / BEELLAMA                  |"
Write-Host "+==========================================================+"
Write-Host ""
Write-Host "Endpoint : $LlamaUrl/metrics"
Write-Host "Log      : $LlamaLog"
Write-Host ""

try {
    $metrics = (Invoke-WebRequest -UseBasicParsing -Uri "$LlamaUrl/metrics" -TimeoutSec 5).Content
} catch {
    Write-Host "[ERROR] No se pudo consultar /metrics. Esta llama-server arrancado con --metrics?" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}

function Get-MetricValue([string]$Name) {
    $line = ($metrics -split "`n" | Where-Object { $_ -match ("^" + [regex]::Escape($Name) + "\s+") } | Select-Object -First 1)
    if (-not $line) { return $null }
    $parts = $line.Trim() -split "\s+"
    if ($parts.Count -lt 2) { return $null }
    return [double]::Parse($parts[1], [Globalization.CultureInfo]::InvariantCulture)
}

$promptTps = Get-MetricValue "llamacpp:prompt_tokens_seconds"
$genTps = Get-MetricValue "llamacpp:predicted_tokens_seconds"
$promptTotal = Get-MetricValue "llamacpp:prompt_tokens_total"
$genTotal = Get-MetricValue "llamacpp:tokens_predicted_total"
$promptSec = Get-MetricValue "llamacpp:prompt_seconds_total"
$genSec = Get-MetricValue "llamacpp:tokens_predicted_seconds_total"
$nMax = Get-MetricValue "llamacpp:n_tokens_max"

Write-Host "[LLAMA METRICS]" -ForegroundColor Cyan
if ($null -ne $promptTps) { Write-Host ("  Prompt processing : {0:N2} tok/s" -f $promptTps) }
if ($null -ne $genTps) { Write-Host ("  Generacion        : {0:N2} tok/s" -f $genTps) }
if ($null -ne $promptTotal -and $null -ne $promptSec) { Write-Host ("  Prompt total      : {0:N0} tokens en {1:N2} s" -f $promptTotal, $promptSec) }
if ($null -ne $genTotal -and $null -ne $genSec) { Write-Host ("  Generacion total  : {0:N0} tokens en {1:N2} s" -f $genTotal, $genSec) }
if ($null -ne $nMax) { Write-Host ("  Mayor contexto obs: {0:N0} tokens" -f $nMax) }
Write-Host ""

Write-Host "[DFLASH]" -ForegroundColor Cyan
if (-not (Test-Path $LlamaLog)) {
    Write-Host "  No existe el log todavia." -ForegroundColor Yellow
    exit 0
}

$lines = Get-Content -Path $LlamaLog -Tail $TailLines
$clean = $lines | ForEach-Object { $_ -replace "\x1b\[[0-9;]*m", "" }
$accept = $clean | Where-Object { $_ -match "draft acceptance rate|statistics dflash|spec cycle" } | Select-Object -Last 20
$suppressed = @($clean | Where-Object { $_ -match "suppressing DFlash" })

if ($accept) {
    $accept | ForEach-Object { Write-Host ("  " + $_) }
} else {
    Write-Host "  No hay lineas recientes de acceptance/spec cycle." -ForegroundColor Yellow
}

if ($suppressed.Count -gt 0) {
    Write-Host ("  DFlash suprimido por tool/lazy grammar en las ultimas {0} lineas: {1} veces" -f $TailLines, $suppressed.Count) -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Consejo: ejecutalo antes y despues de una respuesta larga para comparar los contadores acumulados." -ForegroundColor DarkGray

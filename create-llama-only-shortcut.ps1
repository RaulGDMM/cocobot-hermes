# Crea el acceso directo "Solo llama-server" en el escritorio
$ErrorActionPreference = "Stop"
$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "Solo llama-server.lnk"

$ws = New-Object -ComObject WScript.Shell
if (Test-Path $lnkPath) {
    $sc = $ws.CreateShortcut($lnkPath)  # actualizar si existe
    Write-Host "Actualizando acceso directo existente en $lnkPath"
} else {
    $sc = $ws.CreateShortcut($lnkPath)
}
$sc.TargetPath = "E:\Workspace\Hermes\start-hermes.bat"
$sc.Arguments = "-LlamaOnly"
$sc.WorkingDirectory = "E:\Workspace\Hermes"
$sc.Description = "Arranca solo llama-server con el perfil de start-hermes.ps1 (sin gateway/broker/WebUI)"
$llamaExe = "E:\Openclaw\llama-cpp\llama-server.exe"
if (Test-Path $llamaExe) { $sc.IconLocation = "$llamaExe, 0" }
$sc.Save()

Write-Host "[OK] Acceso directo creado en: $lnkPath"
Write-Host "     Target: $($sc.TargetPath) $($sc.Arguments)"

import os
import shutil

os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

from huggingface_hub import hf_hub_download

DEST_DIR = "/mnt/e/Workspace/Openclaw/models/qwen36-27b"
STAGING_DIR = os.path.join(DEST_DIR, "_autoround_dl")
REPO_FILE = "Qwen3.6-27B-Q6_K.gguf"             # nombre en el repo (colisiona con el Q6_K estandar)
FINAL_NAME = "Qwen3.6-27B-AutoRound-Q6_K.gguf"  # nombre final esperado por start-hermes.ps1

final_path = os.path.join(DEST_DIR, FINAL_NAME)

# Limpiar restos de intentos previos
if os.path.exists(final_path):
    print(f"Borrando archivo final previo: {final_path} ({os.path.getsize(final_path)/1e9:.2f} GB)")
    os.remove(final_path)
os.makedirs(STAGING_DIR, exist_ok=True)

print("Descargando con hf_transfer (paralelo) en subcarpeta aislada...")
downloaded = hf_hub_download(
    repo_id="sphaela/Qwen3.6-27B-AutoRound-GGUF",
    filename=REPO_FILE,
    local_dir=STAGING_DIR,
)
print(f"Descarga completa: {downloaded} ({os.path.getsize(downloaded)/1e9:.2f} GB)")

# Mover al destino final con el nombre correcto
shutil.move(downloaded, final_path)
print(f"Movido a: {final_path}")

# Limpiar staging
shutil.rmtree(STAGING_DIR, ignore_errors=True)
print(f"OK: {final_path} ({os.path.getsize(final_path)/1e9:.2f} GB)")

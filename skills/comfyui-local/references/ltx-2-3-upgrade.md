# LTX 2.3 Distilled Model Upgrade — Session Notes (2026-05-01)

## Upgrade v1.0 → v1.1 — What Changed

**2 files only** (base checkpoint stays the same):

| Constant | v1.0 | v1.1 | ComfyUI folder | Size |
|---|---|---|---|---|
| `MODEL_LORA` | `ltx-2.3-22b-distilled-lora-384.safetensors` | `ltx-2.3-22b-distilled-lora-384-1.1.safetensors` | `loras/` | ~7.1GB |
| `MODEL_UPSCALER` | `ltx-2.3-spatial-upscaler-x2-1.0.safetensors` | `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` | `latent_upscale_models/` | ~950MB |

## Upgrade Procedure (tested, working)

1. **Download new files via huggingface_hub** (parallel downloads):
```python
from huggingface_hub import hf_hub_download

# LoRA v1.1 (~7.6GB)
hf_hub_download(
    repo_id='Lightricks/LTX-2.3',
    filename='ltx-2.3-22b-distilled-lora-384-1.1.safetensors',
    local_dir='/mnt/f/ComfyUIModels/loras'
)

# Upscaler v1.1 (~996MB)
hf_hub_download(
    repo_id='Lightricks/LTX-2.3',
    filename='ltx-2.3-spatial-upscaler-x2-1.1.safetensors',
    local_dir='/mnt/f/ComfyUIModels/latent_upscale_models'
)
```

2. **Update 2 constants** in `scripts/generate_video.py`:
- `MODEL_LORA = "ltx-2.3-22b-distilled-lora-384-1.1.safetensors"`
- `MODEL_UPSCALER = "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"`

3. **Keep v1.0 files** as fallback — reverting is just restoring the 2 constants.

4. **Test with a short video** (5s 720p t2v) to verify broker recognizes the new models.

## v1.1 Improvements (from HuggingFace + community testing)

- **Audio**: significantly cleaner, more natural, less digital artifacting
- **Visual aesthetics**: "different aesthetic experience" — more refined micro-textures
- **Face consistency**: better with `mxfp8_block32` quantization
- **Known issue**: stiffness/frozen frames in First-Last Frame workflows when reference strength ≥1.0 — lower to ~0.7

## Pitfalls

- **fp8_scaled v1.1 not updated yet** — Kijai's `fp8_input_scaled` version lagged. The `fp8_scaled` v1.1 uses many fp8 matmuls and is fast on supported hardware.
- **Non-32-divisible image dimensions** cause generation failures — generate at 640x640 then upscale.
- **Mixed versions break results** — v1.1 LoRA must pair with v1.1 upscaler.
- **Third-party LoRAs may need updates** for v1.1 compatibility.

## Broker Connectivity Troubleshooting

If `generate_video.py` hangs silently (no output, timeout):

1. Broker at `$OPENCLAW_COMFYUI_LOCAL_BROKER_URL` is unreachable
2. Common causes after ComfyUI updates: broker not started, port changed, Windows firewall blocking, or broker listening on `127.0.0.1` instead of `0.0.0.0`
3. Verify from Windows first: `curl http://localhost:8791` or open browser to `http://localhost:8791`
4. In this session, the issue was the broker bind address — changing from localhost to `0.0.0.0` (or the container-reachable IP) resolved it.

## Windows Model Path

- `F:\ComfyUIModels\` (accessible from WSL at `/mnt/f/ComfyUIModels/`)
- Subfolders: `checkpoints/`, `loras/`, `latent_upscale_models/`, `text_encoders/`, `vae/`

## Hermes Workspace — File Browser UI

The file explorer is accessed via the **folder icon at the bottom of the sidebar** (the icon rail), NOT the "Spaces" section. The "Spaces" section shows workspace configuration; the folder icon opens the actual file browser with Monaco editor + terminal.

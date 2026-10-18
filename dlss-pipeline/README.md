# Pipeline DLSS v2 — post-producción de vídeo IA a 4K HDR10 60fps

Cadena de mejora de calidad usada en el corto **"Perros vs Gatos"** (vídeo generado
con MiniMax H3 y mejorado con los nodos NVIDIA DLSS para ComfyUI). Probado y
aprobado en producción: máster de 274 s (6574 f @24) → 4K HDR10 60fps en ~6 h
en una RTX 5090.

```
SRC 1344×768 @24
 └─1─ DLSS SR 3× (Ultra Performance) + NR preset M      → 4K @24   (~12 min)
 └─2─ split por planos (SSIM cuts ∪ fronteras del edit)  → 59 clips @24
 └─3─ DLSS Frame Generation 24→60 POR PLANO              → 4K @60   (~5 h, domina)
 └─4─ concat + recorte 16:9 + rejilla global 60fps       → master SDR60 intermedio
 └─5─ RTX Video True HDR (PQ, 1500 nits) por chunks≤120f → chunks HDR
 └─6─ concat + encode H.264 10-bit bt2020/smpte2084      → FINAL HDR10 + audio maestro
```

Todo el trabajo GPU va por un broker que garantiza acceso exclusivo a la GPU
(para nosotros) y los pasos son **retomables**: `pvsg44_state.json` guarda el
progreso por paso y por ítem (plano FG / chunk HDR); relanzar reanuda.

## Archivos

| Archivo | Qué hace |
|---|---|
| `pvsg44_pipeline.py` | Runner completo del master (pasos cuts/up/split/fg/m60/hdr/final), retomable vía `pvsg44_state.json`. Requiere python con torch+numpy (calibración de cortes en CPU). |
| `m60_fix.py` | **Fix del lip-sync drift**: el FG redondea cada plano impar +0.5 frames; si no se corrige, el vídeo acumula ~+200 ms de adelanto. Recorta cada plano a la rejilla global 60fps (`len_i = R(b_{i+1})−R(b_i)`), deriva ≤8 ms y total exacto. |
| `dlss_ab_send.py` | Orquestador del broker + constructores de workflows API (`upscale_wf`, `fg_wf`, `run_job`). |
| `pvsg30_pipeline_v2.py` | Plantilla A/B de 30 s (misma receta, trozo pequeño) — útil para re-validar la cadena tras actualizar nodos. |
| `ssim_cuts_pvsg30.py` | Calibración de cortes por dip de SSIM a 32×32 (el detector interno del FG NO es fiable en cortes duros: produce frames "derretidos" atravesándolos). |
| `hdr1500_run.py` | Variante de mastering HDR a 1500 nits (vs 1000), la aprobada. |
| `yt_hdr10_upload.sh` | **Entrega para YouTube**: re-encode HEVC main10 con metadata de mastering HDR10 (ST 2086) + MaxCLL, y verificación. Uso: `yt_hdr10_upload.sh master.mp4 salida.mp4 [nits=1500]`. |

## Requisitos

- GPU RTX 40/50 (nodos usando el runtime NGX real; NR = feature 18).
- ComfyUI con `ComfyUI-NVIDIA-DLSS-Frame-Interpolation` (SR+FG+NR) y
  `ComfyUI_Nvidia_VFX_Nodes` (`RTXTrueHDR`).
- Nodos de vídeo: `SaveVideo` requiere `format` y `codec` explícitos; codec
  `"H.264 (NVIDIA NVENC)"` para velocidad.
- ffmpeg accesible a los nodos (en nuestro caso vía `sitecustomize.py` con
  `DLSS_FFMPEG_PATH`).
- `pvsg44_pipeline.py` usa el ejecutable de ComfyUI solo en remoto; localmente
  solo ffmpeg + ffprobe + torch.

## Uso

1. Ajusta `SRC` (máster 24fps) y `FINAL` en `pvsg44_pipeline.py`.
2. Ejecuta con un python que tenga torch+numpy: `python3 pvsg44_pipeline.py`.
   Pasos individuales: `python3 pvsg44_pipeline.py fg hdr` etc.
3. Si el máster es un montaje con cortes, **pre-split obligatorio** (paso split):
   la lista de cortes es la unión de los detectados por SSIM y las fronteras
   reales de edición (±2 frames de tolerancia por redondeo).

## Lecciones que costaron sangre (por si reutilizas esto)

- **Deriva labial por redondeo de FG por plano**: ver `m60_fix.py`. SIEMPRE en
  masters multiplano.
- **Re-runs con el mismo `filename_prefix`**: ComfyUI renumera (`_00002_`); el
  picker de outputs debe elegir el número más alto o el paso "exitoso" muere.
- **HDR por chunks es seguro**: `RTXTrueHDR` es stateless por frame (verificado);
  chunks ≤120 frames @4K60 sin costuras visibles (≤3 LSB de dithering).
- **Entregar HDR10**: un `-c copy` no escribe las etiquetas VUI (el vídeo sale
  como bt709). Reencodear con `-pix_fmt yuv420p10le -color_primaries bt2020
  -color_trc smpte2084 -colorspace bt2020nc` y verificar `color_transfer`.
- **Verificar CFR**: `ffprobe -show_packets pts_time` lista en orden DTS
  (B-frames): ORDENA los pts antes de comprobar que todos los deltas valen 1/60.
- **24→60 directo**: es el caso nativo de DLSSG (cascade+decimación); un
  24→120→60 daría la misma rejilla a ~2.7× el coste.
- **Entregar a YouTube en HDR da un paso extra**: las etiquetas de color
  (bt2020/smpte2084) en un H.264 NO bastan — YouTube clasifica HDR mirando el
  metadata de mastering **SMPTE ST 2086 (MDCV) + MaxCLL**, y prefiere HEVC/VP9.
  Sin ello sube el vídeo como SDR y su tone-map genérico "lava" los colores.
  El envase es `yt_hdr10_upload.sh` (HEVC main10 hvc1 + SEI ST2086/CLL, al
  estilo de las cámaras). Trampa de sintaxis: en x265 `max-cll` lleva COMA
  (`max-cll=1500,0`); con `:` se descarta dejando solo un warning. Tras subir,
  la insignia HDR aparece solo cuando YouTube termina la variante VP9/AV1 HDR
  (20 min–2 h).

## Entrega a YouTube (HDR10)

```bash
./yt_hdr10_upload.sh "montaje/Perros vs Gatos.mp4" "montaje/Perros vs Gatos_HDR10.mp4" 1500
```

El script re-utiliza el máster del paso 6 tal cual (no re-mira el grano: el
encode es CRF 18, visualmente lossless a 4K y YouTube re-codifica igualmente),
incrusta el mastering display de nuestros 1500 nits y **verifica** que el
`side data` del resultado trae MDCV y MaxCLL antes de dar el OK.

## Ritmos medidos (RTX 5090, máster 274 s)

| Paso | Coste |
|---|---|
| Upscale 3×+NR (6574 f → 4K) | ~12 min |
| FG 24→60 por plano (59 planos, 4K) | ~5 h |
| HDR 1500 nits (137 chunks) | ~57 min |
| Encode final HDR10 | ~13 min |

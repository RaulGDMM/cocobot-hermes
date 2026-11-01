# Open-H3-Regenerate-2K — weights, recipe, run notes

Open replacement (NVlabs SoL/Sana + MIT HAN Lab) for the closed MiniMax H3-Regenerate-2K API. Frozen H3
transformer + video VAE + one merged refiner LoRA; project-reported wins vs the official API on UniPercept
(all axes), VBench aesthetic/imaging/subject consistency, 87% in a blind study. License: MiniMax H3
Community License (territory/use terms — check before any commercial use; the bundle has no single blanket license).

## What we need on the ComfyUI path (broker, int8 convrot H3 base)
- **Merged full LoRA** (refiner r384 + LightX2V FL2VA Turbo v1.2 + LMS Sharp = rank 576): HF
  `DrakenZA/Open-H3-Regenerate-2K-ComfyUI` → `open_h3_regenerate_2k_comfy_swiglu_fixed.safetensors` (8.8 GB).
  **Use the `swiglu_fixed` file**: naive diffusers→comfy conversions reproduce WRONG weights (the Diffusers
  layout needs a SwiGLU transformation) and output looks broken. The merge already includes the few-step
distills, so use it ALONE — do not stack the PDD Acc / Turbo LoRAs on top.
- **Standalone refiner** (rank 384 bf16, 5.87 GB) at HF `Kijai/MiniMax-H3-experimental` — only if mixing with
different distills; LMS Sharp's AdaLN curve branches have no ComfyUI equivalent, so the merged DrakenZA file is the faithful route.
- **Latent upscaler node pack**: `github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler` (2D + 3D nodes,
category `video/MinimaxH3`; modes: scale 1.0–4.0× / target dimensions / megapixels; temporal chunking for long
clips; fp32/fp16/bf16; auto CPU-offload after run). Weights: HF
  `Efficient-Large-Model/Open-H3-Regenerate-2K` → `latent_upsampler/minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors` (0.69 GB) → `models/latent_upscale_models/`.
- Reference CLI (NOT used here): `NVlabs/Sana` branch `sol-engine` (Linux/diffusers, wants the 65 GB BF16 base) — only if a future test needs the fast 24-layer VAE decoder or SoL-Engine kernels.
- Our env: H3 runs as `minimax_h3_fl2va_pruned_int8_convrot.safetensors` (21 GB) + `minimax_h3_video_vae_int8_convrot` via the broker ComfyUI; text encoder qwen3vl_32b nvfp4-awq. Node packs for H3 live in the E: install `custom_nodes` (same place as PDD-Acc/Veda/DLSS).

## Sampling recipe (reference-exact)
1. Encode the draft once with the H3 video VAE (drafts 384P–768P accepted; H3 24 fps grid 17k+5 frames; 5–15 s per pass).
2. Latent upscaler → target grid (768P→2K = 36×64→90×160, 2.5× per side within trained range; for 4K apply it TWICE, each within range).
3. Initial latent: `(1−0.909375)·upscaled + 0.909375·noise`.
4. **3 Euler steps, sigmas [0.909375, 0.857143, 0.666667, 0], CFG 1** (no negative pass), model time = 1−sigma.
5. VAE decode.
Upscaling alone adds no detail — the 3 steps redraw surfaces; layout/motion/color are fixed by the draft (subject consistency high, but treat it as REGENERATION: identity QA always applies, same gates as the closed V2V route).

## Install layout (DONE — validated on the 5090)
- Weights live under the legacy `C:\ComfyUI\models` tree (`loras/`, `latent_upscale_models/`) — the broker's E: install sees them via its extra-model-paths yaml; node packs install to the E: `custom_nodes/`. Downloads staged in `E:\Open-H3-Regen\` (+ `SHA256SUMS`).
- Custom node `Cocobot-H3-Refine-Init` (in E: custom_nodes): takes the clean upscaled LATENT, outputs H3 AV latent (zero audio sized via official `temporal_shape`). **Run it at `sigma: 0`** — `SamplerCustomAdvanced`+`RandomNoise` already mixes at sigmas[0]; pre-mixing double-noises and hallucinates a new scene.
- API wiring: `MiniMaxH3LatentUpscaler3D` is a v3 io.Schema node → DynamicCombo option fields as DOTTED keys: `"mode": "target dimensions", "mode.width": 2560, "mode.height": 1440, "align": 32` (flat keys → HTTP 500 `required_input_missing: mode.width`).
- Test harness / workflow builder: `/root/workspace/openh3-ab/openh3_test.py` (reuses `generate_video.py` upload/request helpers; `wf(src, w, h, prefix, sigmas=...)`).
- Strip non-ASCII prints from the LBH node pack before first job (cp1252 zombie — see comfyui-local); backups `.bak-cocobot` left in place.

## Measured on RTX 5090 (int8 convrot base + merged LoRA)
- 5 s @1920×1088: 178–187 s. 5 s @2560×1440: 290–297 s.
- **Sage attention patch breaks long clips**: `MiniMaxH3MemoryEfficientSageAttentionPatch` (fp8 V + fp16 accumulation on sm89+) is fine at 5 s but turns 9.4 s into garbage everywhere (sharpness ~40). Wire `BasicGuider.model` straight to the LoRA loader for clips >124f. Isolation that proved it, on the same 226f clip: upscaler only, with and without temporal chunking, clean (~780); full refine without chunking, broken (42); full refine without Sage, clean (1218-1889).
- Without Sage: 9.4 s @2K ~15 min, clean. 15 s @2K OOMs: `convrot64 fused kernel shared memory request failed` (with Sage it OOMed in `int8_linear`). Forcing Sage to fp32 accumulation was TESTED: still garbage (43…376) — the int8/fp8 quantisation itself is the problem; patch reverted. Untested next options: FFN chunking (port LTXVffnChunkPatch), 15 s @1080p plus DLSS 2×, or ~7.5 s pieces split at camera motion. The VRAM readout says nothing about headroom (dynamic weight staging fills it to ~99%); only a real run shows whether a length fits.
- **H3 temporal grid (use the official helpers, never hand-roll):** frames must be 17k+5 (124, 226, 362…); `latent_t = ((frames-5)//17)*5+2` (124f→37, 226f→67, 362f→107); audio length = `temporal_shape(frames)[2]` from `comfy_extras.nodes_minimax_h3`. Trim drafts to the grid before upload. (Correct audio length is hygiene; fixing it alone did NOT repair long clips.)
- The LBH 3D node's internal temporal chunking (T>32 latents) also runs on healthy 5 s jobs (T=37) — it is NOT a length limit; do not blame it without an A/B (`enable_temporal_chunking` false vs true on the same clip).
- 4K native stays off the table. 4K delivery = refine @2K → DLSS 1.5×+NR → 4K.
- B200 reference (for context only): 5 s @2K 22 s (SoL-Engine) / 87 s (dense BF16).

## Identity drift: sigma tuning + chroma anchor (A/B, husky intro frame, same seed)
Face-crop sharpness (Laplacian var) and nose color (r−b on nose crop; draft +7.7 = pink snow-nose):
| arm | sharpness | nose r−b |
|---|---|---|
| draft Lanczos | 12.7 | +7.7 |
| σ0.909 official schedule | 132.8 | −1.5 (nose→black, eye dulled, toes reinterpreted) |
| σ0.667 | 52.9 | +4.5 (identity preserved) |
| σ0.50 | 47.8 | +5.9 (no gain over 0.667 — 0.667 is the lower bound of usefulness) |
| σ0.667 + chroma anchor | 54.1 | +7.5 (≈draft) |
| σ0.75 | 60.2 | +3.1 (pink OK; sharp 60 at t2.5) |
| σ0.80 | 66.9 | +1.3 borderline |
| σ0.857 | 87.9 | −0.5 black |
| σ0.909 + chroma anchor | 133.9 | **+7.6 ≈ draft, max texture** |
- Multi-frame nose grid (t=0.5/2.5/4.5): raw pink is only robust ≤σ0.75 (σ0.667 has borderline frames too). Texture-vs-nose are mutually exclusive in raw sigma space → **anchor chroma instead of lowering sigma**: σ0.909 + chroma gives both (vision-verified natural pink nose, no bleeding; nostril SHAPE reinterprets survive — luma is the refiner's).
- σ0.909 + chroma was only validated on a single-subject close-up. **On multi-character / wide shots σ0.909 rewrites SPECIES and anatomy** (black cat → dog face, bulldog drummer → human, paws → human hands) — chroma cannot fix shape. Raúl's decision: lower sigma, accepting less new detail. Before any full run, A/B σ0.909/0.80/0.75 on a wide band shot (scaled official curve: `s0*(1, 0.942563, 0.733104), 0`) and pick the highest σ where every character stays an animal; QA crops must cover EVERY character, background musicians and hands, not just the lead face.
- **Refine prompt = short per-shot scene description** (who is visible, species traits, "no humans, animal paws not human hands"), never the generation prompt: long i2v prompts carry timelines and "Picture N" refs that do not apply, and a husky-heavy prompt drags other subjects toward dog at high σ. σ0.667 (`"0.666667, 0.45, 0.25, 0"`) stays as fallback for identity-obsessive shots.
- Chroma anchor ffmpeg (verified ≡ PIL blend, nose +7.7): `[0:v]scale=WxH:flags=lanczos,format=yuv420p[r];[1:v]scale=WxH:flags=lanczos,format=yuv420p[d];[r][d]mergeplanes=0x001112:format=yuv420p` (draft scaled to the SAME grid and frame count).
- **Chroma anchor (always, free):** YCbCr composite = Y from refined + Cb/Cr from the lanczos-upscaled draft (`out[:,:,0]=ref.Y; out[:,:,1:]=draft.CbCr`). Fixes color drift deterministically, zero GPU, touches no geometry; structural reinterprets (toe shapes, head yaw) survive it → identity QA gates stay mandatory.
- **QA every refined output with a full-clip curve, not face crops**: per-frame Laplacian variance of the whole frame at 320×180 vs the draft (healthy refine ≫ draft across ALL deciles; a broken run sits far BELOW the draft). A 'job OK' from the broker proves nothing.
- **v3 recipe (σ under re-evaluation, see identity drift above)**: draft 768P → refine @2K (σ chosen by the band A/B, short per-shot prompt) WITHOUT the Sage patch, one job per camera shot up to ~9.5 s (fewer seams; cuts hide joins) → chroma anchor → DLSS 1.5×+NR → 4K → FG 60 → tonemap; mux master audio. Full-video runbook: `perros vs gatos/HANDOFF-OPENH3-V3.md` (budget 291 s ≈ 59-65 chunks: 9.5-11 h total; pilot intro-15 s first to check chunk-seam flicker).

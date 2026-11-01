---
name: comfyui-local
description: Generate images and videos locally through the Windows ComfyUI broker using FLUX, LTX 2.3, LTX 2.5, MiniMax H3, MOSS-Image.
metadata:
  {
    "openclaw":
      {
        "emoji": "🖼️",
        "requires": { "bins": ["uv"], "env": ["OPENCLAW_COMFYUI_LOCAL_BROKER_URL"] },
        "primaryEnv": "OPENCLAW_COMFYUI_LOCAL_BROKER_URL",
        "install":
          [
            {
              "id": "uv-brew",
              "kind": "brew",
              "formula": "uv",
              "bins": ["uv"],
              "label": "Install uv (brew)",
            },
          ],
      },
  }
---

# ComfyUI Local

Use the bundled script to generate images locally through the broker on the Windows host.

## Model Selection

Use `--model` to choose the image generation model. **Default is `z-image-turbo`** (fast + good text). A/B-validated decision (2026-09-19, blind test, same prompt+seed):

| Model | Flag | Role |
|-------|------|------|
| FLUX 3 Image Klein | `--model flux3-klein` / `flux3-klein-base` | Fast all-rounder + editing (installed 2026-10-25): distilled 16 steps ~6-8s/1MP (fastest quality arm), text ES perfect, clean product shots; skin realism below MOSS (use base+upsampler for faces). Editing wired and A/B-validated (2026-10-25 round 2): ties Qwen on identity swaps at ~4-8x the speed, BEATS Qwen on 2-ref position adherence; not pixel-preserving when the prompt contradicts the photo. Comm. OK <5M€ revenue. |
| MOSS-Image SFT | `--model moss-image` | **Photorealism specialist** (installed 2026-10-25): best skin realism (won the portrait A/B vs Qwen 2.1), documentary scenes, ES text (tie with Qwen, perfect Ñ). t2i ONLY (script rejects `--image`). Apache-2.0 → commercial-safe (unlike Qwen 2.1 / Ideogram 4). |
| Qwen-Image 2.1 | `--model qwen-image-2.1` | **DEFAULT** (since 2026-09-21, after the hard-prompt A/B battery): best overall t2i, the ONLY multi-reference editor (up to 16 refs, identity-preserving), native RGBA/transparent output. Qwen Research License: **non-commercial only** (same as Ideogram 4). |
| Z-Image-Turbo | `--model z-image-turbo` | Fast + renders text well in most cases. Best legibility (bold high-contrast text) and speed; no editing. |
| Ideogram 4.0 | `--model ideogram4` | Use when **exact text matters** (posters, banners, infographics). 0 text errors in A/B; most reliable for Spanish text with accents. Slower (~4x) and heavier (~29GB). Auto-runs the magic prompt through the local LLM. |
| FLUX.2 Klein 9B | `--model flux2-klein-9b` | **For image editing** (`--image`) when Qwen's edit is not enough; best anatomy/instrument detail (won the cello test). Make exact-text work: in A/B it mangled "DEL"→"DE" and "ESPECIALIDAD"→"ESPECIALDAD". |
| FLUX.1 Dev | `--model flux1-dev` | Character consistency / i2i via Kontext. |

| Model | Flag | Quality | Speed (RTX 5090) | VRAM | Text | Best for |
|-------|------|---------|-------------------|------|------|----------|
| FLUX.1 Dev | `--model flux1-dev` | High | ~8-12s | ~16GB | Good | Character consistency and detailed recurring subjects |
| FLUX.2 Klein 9B | `--model flux2-klein-9b` | Higher | ~3-5s | ~12GB | Excellent | Speed, text rendering, landscapes and iteration |
| Z-Image-Turbo | `--model z-image-turbo` | High | ~1-2s | ~10GB | Excellent, including Spanish | Ultra-fast generation, portraits, HDR-like lighting and text |
| Ideogram 4.0 | `--model ideogram4` | State-of-the-art (AA #1 open-weights) | ~70s end-to-end (incl. model load) | ~29GB (dual DiT fp8 + Qwen3-VL-8B encoder) | **Best-in-class**, incl. Spanish, with exact layout control | Posters, banners, covers, infographics, any image with in-frame text; 2K native; hex color palettes |
| Qwen-Image 2.1 | `--model qwen-image-2.1` | High (2K native; **A/B winner overall 2026-09-21**) | ~40-60s at 720p+ int8 | ~17.5GB (DiT int8 + Qwen3VL-8B encoder int8 + VAE) | Best overall: 2K quality, multi-reference editing (16 refs, no identity crossing), transparent/RGBA assets, concept/double-exposure, local mask edits | **DEFAULT**: general generation, editing, product cutouts |

### Qwen-Image 2.1 (7B, 2026-09-20)

**Prompting:** before writing any Qwen 2.1 prompt (text-to-image, text in image, editing, multi-ref, RGBA), read [`references/qwen-image-2-1-prompt-guide.md`](references/qwen-image-2-1-prompt-guide.md) — 5-slot structure, quoted+placed text strings, RGBA prompt format, multi-ref define-each-reference pattern, ready templates.

Unified t2i + image editing in one checkpoint, 2K native, **native RGBA/transparent** output, up to 16 reference images, local-region edits (masks). Weights on `F:\ComfyUIModels` (Comfy-Org packaging): `diffusion_models/qwen_image_2.1_int8_convrot.safetensors` (7.3GB), `text_encoders/qwen3vl_8b_int8_convrot.safetensors` (9.4GB), `vae/qwen_image_2.1_vae_bf16.safetensors`.

Pitfalls (learned 2026-09-20 during first setup):
- **The encoder is `qwen3vl_8b_int8_convrot.safetensors`** (Qwen3VL-8B, CLIPLoader `type: "qwen_image"`). The repo's `qwen3.5_9b_qwen_image_2.1_pe_{t2i,i2i}.int8_convrot` files are prompt-enhancer variants, NOT the generator's encoder — do not download/use them for generation. Also NOT compatible with Ideogram 4's `qwen3vl_8b_fp8_scaled` (different weight-key prefixes).
- **`TextEncodeQwenImage21` requires `resolution` in the API workflow** even though the UI has a default — API validation fails with "Required input is missing: resolution" otherwise. In t2i mode (no `image_N` refs) the value only sizes the unused square latent the node returns; the KSampler uses EmptyLatentImage.
- Edit/multi-ref mode: reference images plug into `TextEncodeQwenImage21` as autogrow inputs `image_1`…`image_16`, and the node also outputs a latent at the first ref's size (use it, not EmptyLatentImage).
- **License: Qwen Research License — non-commercial only** (same restriction as Ideogram 4). Personal use OK; commercial needs a separate license.
- VRAM: int8 config ≈ 17.5GB weights, bf16 DiT config ≈ 23.1GB weights — both fit the 5090 with room to spare. bf16 encoder (17.5GB) does NOT fit with the DiT. **Measured (2026-09-20): sampling is ~18s for 1024²/20 steps in BOTH int8 and bf16** (RTX 5090 bandwidth makes int8 no faster); the ~55-58s wall time per image is mostly model load + broker overhead, not sampling.
- **A/B int8 vs bf16 (same seed/prompt, DiT only differs): BF16 IS THE DEFAULT and wins side-by-side.** The 2026-09-20 "pixel diff mean 1.2/255, imperceptible" verdict was WRONG — the mean metric hides what humans actually see: in a same-seed side-by-side (2026-09-21, serenoide test) bf16 has visibly finer bioluminescent veins, cleaner skin (int8 shows subtle grain in glow zones), sharper hands/fin and tighter glow. Lesson: for perceptual A/B of quantizations, judge side-by-side with vision, never mean-pixel-diff alone. Speed on the 5090: sampling equally fast (bandwidth-bound); bf16 batch costs ~19s extra per batch for the 14.2GB model load vs 7.3GB int8 — negligible in multi-image batches. **Int8 weights DELETED 2026-09-21** and the `--qwen21-dit` flag REMOVED from `generate_image.py` (the script hardcodes `qwen_image_2.1_bf16.safetensors` — do not pass the flag, it no longer exists). Re-add the flag + map + download int8 weights only if a future A/B ever justifies it.
- Sampling: euler / simple / cfg=1.0 per the official Comfy-Org t2i template (`image_qwen_image_2_1_t2i.json`); default 25 steps in the template, 20 works fine.

A/B 2026-09-20 (same prompts/seeds as the 2026-09-19 `ab_ig4` battery, `imagenes/ab_q21/`): poster ES 0 errors, apple 9/10 photoreal, banner ES 0 errors (tildes + "ESPECIALIDAD" correct, where FLUX.2 Klein had mangled it).

**Hard-prompt A/B 2026-09-21** (18 generations, 4 models, same prompt+seed per test, `imagenes/ab_q21/hard/`):
- **P1 long Spanish text (poster "FERIA DEL LIBRO" + ñ):** all four spelled everything correctly (incl. ñ, dates); Z-Image best *legibility* (uniform bold), Qwen most *editorial*, FLUX worst (grunge texture mutes the small line). No text inversions anywhere.
- **P2 hands + small text:** IDEOGRAM won (most realistic hands); Qwen correct on all three criteria (3rd); FLUX had one "glove" hand.
- **P3 5 objects + 5 price tags "3,50 €"…:** Qwen 5/5 objects + 5/5 tags *correctly mapped*; **IDEOGRAM got "Image blocked by safety filter" twice (P3, P4)** — even with magic-prompt JSON it false-positives on benign prompts; Z-Image swapped a price and dropped one tag. FLUX also 5/5 but bigger/sharper (narrow win on fidelity).
- **P4 concept double-exposure (fox+forest):** **QWEN WON** — the only model that actually fused the silhouette with the forest (FLUX partial, Z-Image "two things pasted", Ideogram blocked).
- **P5 2K cello portrait:** FLUX.2 KLEIN won clearly (correct cello anatomy + both hands; Qwen failed the instrument — volute glued to the head, missing left hand).
- **Edit/multi-ref (Qwen-only, no competitor):** identity background swap 8.5/10 (recognizable same person); **2 distinct people in one scene: 8/10, zero identity crossing** (balding vs beard+glasses stayed on the right man); cat re-composed to sunny windowsill 8/10 with clean scene removal + rim-light/shadow integration; **RGBA cutout: real alpha (21.9% fully transparent), clean edge, semi-transparent contact shadow inside the alpha channel** — no other installed model can do this.
- **Verdict → Qwen-Image 2.1 is the DEFAULT** for both t2i and editing (set 2026-09-21): only multi-ref editor + only RGBA model + wins concept + text tie. Keep Ideogram 4 for layout-heavy text (but beware its safety filter), FLUX.2 Klein for musical instruments/fine anatomy, Z-Image for speed.

**Prompt enhancer (since 2026-09-22):** `--prompt-enhance` is an OPT-IN flag for `--model qwen-image-2.1` (t2i AND edit). It expands the user's short brief (any language) into a detailed 5-slot layout brief via the local llama-server (same mechanism as Ideogram 4's magic prompt), using the system prompt `scripts/qwen_image_2.1_enhance_v1.txt` (5-slot order, verbatim quoted text with original language/accents, RGBA rules, multi-ref Figure-N pattern). Fails open to the raw prompt if the LLM is down. Verified 2026-09-22 on 3 briefs (poster ES, RGBA sticker, edit): correct structure, Spanish text preserved verbatim with quotes, RGBA prefix/suffix exact, edit prompt defines Figure 1 + preservation + do-not list. Rule of thumb: use it for SHORT briefs; skip it when the prompt already follows the 5-slot guide (re-expanding an already-structured prompt wastes tokens and can add invented detail). To iterate on the enhancer, edit `qwen_image_2.1_enhance_v1.txt` only — do not touch the script's plumbing.

**Negative prompt A/B recipe (NOT default):** our Qwen 2.1 workflow is pinned to the official Comfy-Org template (cfg=1.0), so any negative prompt is INERT as wired — the negative branch only computes when cfg>1. Do not change the default. If a specific failure mode appears (deformed hands, blurry text, oversaturation), run a controlled A/B: same prompt+seed, one image at cfg=1.0 (baseline) vs one at `--guidance 2.0` with a negative targeting ONLY the failure mode ("deformed hands, blurry text"), judge side-by-side. If the CFG>1 win is clear for that task class, note it here with the tested value; never raise the global default without a validated A/B.

**Multi-ref wiring pitfall (2026-09-21):** the reference images of `TextEncodeQwenImage21` are an `Autogrow` input with id `images` (TemplateNames `image_1`…`image_16`). In the **API workflow they must be TOP-LEVEL dotted keys** `"images.image_N": [loadNodeId, 0]` — NOT top-level `"image_N"` (the validator auto-expands the schema and passes validation, but `execute()` then dies with `unexpected keyword argument 'image_1'`) and NOT a nested `"images": {}` dict (Python workflow JSON can't express it). The runtime re-groups the dotted keys into the `images` dict via `dynamic_paths` before `execute()`.

### FLUX 3 Image Klein (BFL, 5.6B, 2026-10-15)

**Weights** (FLUX Kommunity License; HF repo `black-forest-labs/flux-3-image-klein-comfy` is GATED — agree on web as the token user, or download from the ungated mirror `ml-resources/flux-3-image-klein-comfy`, same files). Installed in `F:\ComfyUIModels`: `flux3-image-klein-bf16.safetensors` + `flux3-image-klein-base-bf16.safetensors` (distilled + base, 11 GB each), `qwen3vl_4b_bf16.safetensors` (CLIPLoader `type: "flux3"`), VAE = existing `flux2-vae.safetensors`.

**Recipe (from official BFL workflow JSONs, mirrored in generate_image.py):** UNETLoader + CLIPLoader(flux3) + **ModelSamplingFlux(max_shift=base_shift=2.77259, width, height)** + EmptyFlux2LatentImage + KSampler euler/simple. Distilled: 16 steps CFG 1.0; base: 50 steps CFG 4.0. Prompt upsampler (qwen3.5_9b_flux3_prompt_upsampler_w4a8, NOT installed) is part of the UI template and BFL says don't skip it — wired as opt-in `--upsample` (t2i only): CLIPLoader(type flux3) `qwen3.5_9b_flux3_prompt_upsampler_int8_convrot.safetensors` (9.75 GB, F:) -> `TextGenerate` (template sampling: temp 1, top_k 1, top_p 0.95, presence 1.5, max 3584, mtp off; DynamicCombo sub-inputs as dotted `sampling_mode.*`; system prompt = official BFL caption prompt in `scripts/flux3_upsampler_system.txt`, user msg `ORIGINAL PROMPT:\n<prompt>`) -> CLIPTextEncode text. The script refuses to send if `--upsample` is set but no TextGenerate is in the graph (guard added after a silent no-op bug: the param was never forwarded from main(), so the first ON battery was pixel-identical to OFF, mean|diff| 0.0 — ALWAYS check `'811' in png.info['prompt']` or a pixel diff before judging an A/B). Editing IS wired (`--image`/`--image2` + `--model flux3-klein[-base]`, verified 2026-10-25): LoadImage→ImageScaleToTotalPixels(1 MP)→`ReferenceMultiLatent`→KSampler, **guidance 1.0 on BOTH checkpoints in edit mode** (template; the t2i defaults are wrong for edits). v3-node API pitfalls that cost 3 debug cycles: DynamicCombo goes as `"resolution": "resize"` + DOTTED `"resolution.megapixels": 1.0` (flat or nested keys fail: "Required input is missing: resolution.megapixels"), refs go as dotted `"images.imageN"` (Autogrow), and `ImageScaleToTotalPixels` param is `resolution_steps` (NOT `resolution_round`).

**A/B 3-way vs Qwen-2.1 + MOSS (2026-10-25, seed 20261025, raw prompts, `imagenes/ab_flux3/cmp3_*`):** no model swept. Skin portrait: MOSS 1st, Klein 2nd (distilled over-sharpened pores; base visibly more photographic), Qwen 3rd. Product: Qwen 1st (brief adherence), Klein 2nd (text perfect, NO gibberish micro-text — beat MOSS there). ES poster: three-way tie, all 3 texts perfect incl. Ñ. Hands simple grip: all pass. Tea-stall documentary: Klein≈MOSS 1st, Qwen 3rd. Matches AA Elo (Klein 1043 ≈ Qwen 1042 t2i). Community lore held: anatomy-scare is mostly complex poses; editing is Klein's real pitch (pixel-exact preservation). **Round 2 DONE (2026-10-25, `imagenes/ab_flux3/edit/cmp_e*`, same seed 20261025 vs Qwen 2.1):** identity background-swap = TIE at parity with Qwen's 2026-10-16 8.5 (both preserved face/hair/shirt pattern; Klein in 16 steps ~4-8x faster). Two-people pub scene = **Klein WON**: honored left/right placement of the two refs and rendered believable hands on the table, while Qwen swapped who sits where. Preservation test (toast→pancakes, intentionally lying prompt: "same wooden table" on a white-speckled surface): NEITHER model is truly pixel-preserving — both invented the wooden table the text asked for; Qwen kept the top-down angle, Klein made the more appetizing edit. Rule: Klein = co-default for editing with Qwen (speed + multi-ref position adherence); Qwen keeps RGBA and product-brief edits; prompt text beats pixels in both, so never contradict the source photo in edit prompts. **

**Upsampler ON vs OFF (2026-10-25, same seed/prompts, `imagenes/ab_flux3/cmp_up_*`):** ON wins 4 clear + 1 narrow on DETAILED briefs because raw Klein drifts from the brief and the upsampler pins it: portrait (natural skin irregularities, real harbour context vs OFF's over-carved uniform spots), product (OFF wandered to a lifestyle kitchen, ON = clean studio as asked), full-body hands (OFF cropped to waist-up ignoring 'full-body'), tea stall (ON actually pours from height into a kulhad, rickshaw/rain; but invents a garbled newspaper), ES poster (text 3/3 perfect BOTH, ON narrow win on layout). BUT on a SHORT vague prompt ('A red fox in fresh snow at sunrise') OFF won clearly: ON built a richer landscape but stilt legs, weird smile, cut-out lighting. Rule: use `--upsample` for full briefs with constraints (studio bg, framing, actions); skip it for short mood prompts and when exact text legibility matters more than layout. Upsampler can invent pseudo-text props (newspapers/signs).

### MOSS-Image SFT (OpenMOSS, 2026-10-25)

**Requirements:** ComfyUI ≥ 0.42 (native support: `CLIPLoader type: "moss_image"`, Flux2 latent format — `EmptyFlux2LatentImage`). Weights in `F:\ComfyUIModels`: `diffusion_models/moss_image_sft_bf16.safetensors` (10.2 GB, Kijai int8 also available), `text_encoders/qwen3.5_9b_int8_convrot.safetensors` (9.75 GB; bf16 19.3 GB does NOT fit alongside the bf16 DiT), VAE = existing `flux2-vae.safetensors`. No custom nodes needed for t2i. ~20 GB total weights, fits the 5090.

**Recipe (validated):** er_sde / simple / 30 steps / CFG 2.5, negative `plastic skin, waxy skin` (inert at cfg≤1). Script defaults: steps 30, guidance 2.5; pass `--moss-negative`. Base model exists for LoRA training; CharRef/pose LoRAs + edit node (`ComfyUI-MOSS-Image-Ostris-Edit`) NOT installed.

**A/B vs Qwen-Image 2.1 (2026-10-25, seed 20261025, `imagenes/ab_moss/`, 5 tests):** MOSS 2 – Qwen 1 – 2 ties. MOSS WON skin realism (sun spots, pores, knit texture vs Qwen's too-clean skin) and documentary scene obedience (chai stream into the requested cup); TIED on ES poster text (both perfect incl. ñ) and simple hands (MOSS did full-body with correct fingers); LOST product brief (wandered to lifestyle scene + invented gibberish micro-text under the correct brand label). Verdict: opt-in specialist for photoreal portraits/documentary + commercial-safe (Apache-2.0); Qwen 2.1 remains DEFAULT (editing, RGBA, brief adherence).

### FLUX 3 Image Klein (BFL 5.6B, installed 2026-10-25)

Flags: `--model flux3-klein` (distilled, default 16 steps cfg 1) and `--model flux3-klein-base` (50 steps cfg 4, also the LoRA-training variant). Wiring mirrors the official BFL ComfyUI workflows (UNETLoader + CLIPLoader type `flux3` Qwen3VL-4B + ModelSamplingFlux max_shift=base_shift=2.77259 + EmptyFlux2Latent + euler/simple); the Qwen3.5-9B prompt upsampler is intentionally OFF for raw-prompt A/B fairness. Editing (Set Reference Multi Latent, `<ref_image_N>`, up to 10 refs) NOT wired yet — script rejects `--image`. Edit-prompt rule when wired: describe the FINAL frame, not the change. Community caveats: BFL says Klein was trained with long LLM-written captions (raw short prompts weaker); anatomy (hands/eyes) is its reported weakness.

Weights in `F:\ComfyUIModels`: `diffusion_models/flux3-image-klein-bf16.safetensors`, `flux3-image-klein-base-bf16.safetensors`, `text_encoders/qwen3vl_4b_bf16.safetensors`; VAE = existing `flux2-vae.safetensors`. **HF gotcha:** `black-forest-labs/flux-3-image-klein-comfy` is gated (Kommunity License) — 403 even with a valid token until accepted in the web UI; the **`ml-resources/flux-3-image-klein-comfy`** mirror is ungated with byte-identical sizes, and hosts the official `workflows/*.json` (t2i/i2i/mi2i reference wiring; UI-format, core nodes live under `definitions.subgraphs`). License: FLUX Kommunity (commercial OK <5M USD/yr). A/B vs Qwen-Image 2.1 + MOSS (seed 20261025, `imagenes/ab_flux3/run_battery_klein.py`): pending verdict.

### Ideogram 4.0

Ideogram 4 (9.3B single-stream DiT, trained from scratch, June 2026) is the #1 open-weights model on the Artificial Analysis image leaderboard (Elo ~1012). It uses a Qwen3-VL-8B vision-language model as text encoder and **dual-branch CFG**: a conditional and an unconditional DiT (both fp8, `ideogram4_fp8_scaled.safetensors` + `ideogram4_unconditional_fp8_scaled.safetensors`), asymmetric `DualModelGuider` cfg=7, `CFGOverride` cfg=3 from 70% of the schedule, and an `Ideogram4Scheduler` (flow matching, mu/std per preset).

**⚠️ SAFETY FILTER — THE CRITICAL PITFALL.** Ideogram 4 has a built-in safety filter trained into the weights. Plain-text (natural-language) prompts trigger it at a HIGH false-positive rate: instead of an image you get a gray placeholder saying `Image blocked by safety filter`. This is NOT the broker, NOT ComfyUI, and NOT a content-moderation service — it is inside the model, and there is no flag to disable it. The fix is the model's own training format: **structured JSON captions**. The script handles this automatically: for `--model ideogram4` with a natural-language prompt, it calls the local LLM (`magic_prompt_expansion()`, official open-source system prompt `ideogram4_magic_prompt_v1.txt` next to the script, via llama-server at `http://172.23.176.1:30000`, override with `--llama-url` or `OPENCLAW_LLAMA_URL`) to expand the prompt into the JSON caption schema, then sends that to ComfyUI. If the LLM is down it falls back to the raw prompt — expect blocks in that case. If the user's prompt is already a structured JSON object (contains `compositional_deconstruction`), it is passed through untouched.

**JSON caption schema** (what the magic prompt emits; also accepted directly in `--prompt`): `{high_level_description, style_description{aesthetics,lighting,photo|art_style,medium,color_palette[#RRGGBB upper]}, compositional_deconstruction{background, elements[{type:"obj"|"text", bbox:[y1,x1,y2,x2] 0-1000, desc|text}]}}` — key order matters (the model was trained on a consistent order). In-image text goes in `text` elements with verbatim characters; bbox gives explicit placement; `color_palette` hexes steer the palette. Full guide: https://github.com/ideogram-oss/ideogram4/blob/main/docs/prompting.md

**Presets** (`--preset`): `quality` (48 steps, mu 0.0, std 1.5 — best for final posters), `default` (20 steps), `turbo` (12 steps, mu 0.5). `--steps` overrides the preset's step count. Resolutions: any multiple of 16 from 256 to 2048, aspect up to 6:1. 1280x720 default preset measured ~70s end-to-end on the broker (including ~29GB model load — the broker swaps the LLM out first, per the standing GPU rule).

**Limitations:** text-to-image only (no `--image` editing — the script rejects it; mask inpainting exists via community LoRA but is not wired in). Non-commercial license (Ideogram 4 Non-Commercial Model Agreement, accepted 2026-09-19): fine for personal use, not for commercial deliverables. For i2i keep using FLUX.1 Dev / FLUX.2 Klein.

**Required model files** (in `F:\ComfyUIModels`, downloaded from the public `Comfy-Org/Ideogram-4` repo — do NOT use the gated `ideogram-ai/ideogram-4-fp8` diffusers repo, its key prefixes are incompatible with the ComfyUI loaders):

| File | Folder | Size |
|------|--------|------|
| `ideogram4_fp8_scaled.safetensors` | `diffusion_models/` | 9.3 GB |
| `ideogram4_unconditional_fp8_scaled.safetensors` | `diffusion_models/` | 9.3 GB |
| `qwen3vl_8b_fp8_scaled.safetensors` | `text_encoders/` | 10.6 GB |
| `flux2-vae.safetensors` | `vae/` (shared with FLUX.2) | 321 MB |

### MOSS-Image (OpenMOSS SFT, Apache-2.0, installed 2026-10-25)

`--model moss-image` — text-to-image only (the script rejects `--image`: MOSS has no image input without the experimental edit node/LoRA). Script defaults follow the official recipe: `er_sde` / `simple` / 30 steps / CFG 2.5; pass `--moss-negative "plastic skin, waxy skin"` for realistic skin. `--dit` also swaps the MOSS DiT (Base is the LoRA-training variant).

Native support in ComfyUI ≥0.42 (verify via `comfyui_version.py` of the live install): UNETLoader + CLIPLoader `type: "moss_image"` + `EmptyFlux2LatentImage` + FLUX.2 VAE (shared `flux2-vae.safetensors` — already installed, zero VAE download). No custom node needed for t2i.

Weights on `F:\ComfyUIModels`: `diffusion_models/moss_image_sft_bf16.safetensors` (10.2GB) + `text_encoders/qwen3.5_9b_int8_convrot.safetensors` (9.75GB) ≈ 20GB, fits the 5090 with headroom (same bf16-DiT + int8-encoder pattern as Qwen 2.1 — the bf16 19.3GB encoder does not fit alongside the DiT). int8 DiT (5.4GB) and w4a8 encoder (7.3GB) variants exist in `Comfy-Org/MOSS-Image` if VRAM ever tightens; the 4-step model/LoRA (`akhaliq/MOSS-Image-SFT-4-steps`, CFG 1 + 4 steps) is NOT installed.

**License: Apache-2.0 — commercial use OK.** This is the differentiator: Qwen 2.1 and Ideogram 4 are non-commercial, so MOSS is the candidate for commercial-realistic deliverables.

- **Rule for wiring any new model by hand:** grep its class in the live install's `comfy/supported_models.py` first — `latent_format` dictates the empty-latent node (MOSS → `latent_formats.Flux2` → `EmptyFlux2LatentImage`; wrong node = shape/validation error) and `sampling_settings` shift/multiplier are applied at model load, so no `ModelSampling*` node is needed.
- **Claims to verify, not facts:** the launch video reports skin realism beating Qwen 2.1 and FLUX 3, but failing hard hand poses and inpainting. Until the local same-seed side-by-side (battery runner `imagenes/ab_moss/run_battery.py`: both arms' jobs launched in parallel inside the 5 s batch window — first arm first, second arm ~2 s later — same `--seed` per test for seed alignment) has run, keep Qwen 2.1 as DEFAULT and never quote MOSS wins as established.

FLUX.2 Klein 9B is a distillation of FLUX.2 Dev (32B) into a compact 9B model. It inherits FLUX.2's architecture: better prompt adherence, superior text rendering, improved anatomy, and higher native resolution (4MP vs 1MP). Despite being smaller than FLUX.1 Dev (12B), it outperforms it due to the FLUX.2 architecture.

Z-Image-Turbo is Alibaba Tongyi Lab's distilled 6B S3-DiT model. It uses a Qwen3-4B text encoder, AuraFlow sampling, and 8-step generation. It is the fastest installed option and performed better than FLUX.2 Klein in our Spanish text-rendering comparison.

For video series with recurring characters, prefer FLUX.1 Dev for character reference frames and FLUX.2 Klein for backgrounds, landscapes, text-heavy shots, and rapid iteration.

## Before calling the script

**THE BROKER PAUSES THE AGENT ITSELF.** The broker stops the llama.cpp/Strata server that serves the agent's own LLM before a GPU job, then restores it after. While a job runs the agent is frozen — it CANNOT do parallel work, poll, or "use the time" for other tasks. Correct pattern: send a short confirmation message, launch the job (background=true + notify for long jobs, or just foreground with a generous timeout), END YOUR TURN, and resume when the completion notification arrives — the outputs are already on disk by then. Never interpret the silence as failure, and never schedule independent work expecting to do it during generation. (2026-10-07: Raúl had to correct this — "el broker para llama.cpp o strata, donde corres, y por tanto no puedes hacer nada mientras corre".)

Always send a short confirmation message to the user. Example: `Ok, voy a generar 3 imagenes en formato 16:9 de Cocobot persiguiendo un raton. Tardara un poco.`

## Generate one image

```bash
uv run {baseDir}/scripts/generate_image.py --prompt "your image description" --filename "output.png"
```

With FLUX.2 Klein 9B:

```bash
uv run {baseDir}/scripts/generate_image.py --prompt "your image description" --filename "output.png" --model flux2-klein-9b
```

## Generate multiple images in one broker batch — MANDATORY for any multi-image request

```bash
uv run {baseDir}/scripts/generate_image.py --prompt "your image description" --filename "output.png" --count 3 --aspect 16:9
```

This creates `output-1.png`, `output-2.png`, `output-3.png` and keeps all requests inside the same broker batch. **NEVER call the script multiple times for a multi-image request — each separate call triggers a full GPU swap cycle** (stop llama.cpp + warmup + restore ≈ 45-55s overhead per call on this setup). The broker's `_collect_batch()` groups all jobs queued within `OPENCLAW_BATCH_WAIT_SECONDS` (5s, max 20) into ONE swap: single llama stop → all jobs run with the model kept in VRAM → single restart. Verified 2026-09-21: 3 images batched = 69s wall; 3 separate calls ≈ 3.5 min.

Batched-seed rule: with `--seed N` the batch uses seeds N, N+1, N+2 (base_seed + index). Same width/height/steps/guidance for the whole batch — for different sizes or models, run separate batches (one swap each), and still batch the items inside each. `--prompts-json` + `--count N` mixes prompts; same model/size constraints apply.

## Generate multiple images with different prompts

```bash
uv run {baseDir}/scripts/generate_image.py \
  --prompts-json '["prompt one", "prompt two", "prompt three"]' \
  --filename "output.png" \
  --aspect 16:9
```

## Optional quality controls

```bash
uv run {baseDir}/scripts/generate_image.py \
  --prompt "your image description" \
  --filename "output.png" \
  --steps 24 \
  --guidance 3.5 \
  --aspect 16:9
```

Aspect ratio guide

- `--aspect 1:1` => `1024x1024`
- `--aspect 16:9` => `1280x720` (standard wide format, preferred over extra-wide cinematic sizes like `1920x512`)
- `--aspect 21:9` => `1536x640` (ultrawide / cinematic)
- `--aspect 3:2` => `1216x832`
- `--aspect 4:3` => `1152x896`
- `--aspect 5:4` => `1120x896`
- `--aspect 2:3` => `832x1216`
- `--aspect 4:5` => `896x1120`
- `--aspect 9:16` => `768x1344`

If the user asks for panoramic in the normal sense, use `--aspect 16:9`.
Use `--aspect 21:9` only when the user clearly asks for ultrawide or cinematic.
If the user asks for some other format or exact dimensions, use explicit `--width` and `--height`.

Examples:

```bash
uv run {baseDir}/scripts/generate_image.py --prompt "scene" --filename "output.png" --aspect 4:3
```

```bash
uv run {baseDir}/scripts/generate_image.py --prompt "scene" --filename "output.png" --width 1408 --height 1024
```

Broker configuration

- `OPENCLAW_COMFYUI_LOCAL_BROKER_URL` env var
- Optional timeout via `OPENCLAW_COMFYUI_LOCAL_TIMEOUT_SECONDS`
- Or set `skills."comfyui-local".env.*` in `~/.openclaw/openclaw.json`
- **Find the LIVE ComfyUI install before inspecting or installing anything:** `curl http://172.23.176.1:8791/health` returns `comfy_app_dir` = the install the broker actually runs (`E:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI`; version in its `comfyui_version.py`, custom nodes in its `custom_nodes/`). Model weights live in `F:\ComfyUIModels` (the install's own `models/` dirs are mostly empty stubs); `C:\ComfyUI` is a second, legacy install — never assume paths from one when the health output names the other.
- **PITFALL (2026-10-03, cost 3 lost batch runs): both scripts fall back to `DEFAULT_BROKER_URL = http://host.docker.internal:8791` when the env var is missing — and on this WSL box `host.docker.internal` resolves to `<YOUR_LAN_IP>`, which is NOT the broker (it lives on the Docker gateway `172.23.176.1:8791`). Result: every job dies with `[Errno 113] No route to host` on the first upload, while `curl`/health from a shell that HAS the env var works fine — a confusing false "network flap". The Hermes `execute_code` kernel does NOT inherit `OPENCLAW_COMFYUI_LOCAL_BROKER_URL` (it's set in the terminal shell only), so any batch launched via the kernel's `subprocess.Popen` hits the bad fallback. **Fix: always pass `--broker-url http://172.23.176.1:8791` explicitly** in every `generate_video.py`/`generate_image.py`/`generate_song.py` call from a build script or the kernel, or export the env var in the launched process's env. Verify a launch is reaching the real broker by checking the echoed command line in the log contains the correct `--broker-url`.

### Installing third-party custom nodes / hand-built workflows via the broker

- **Strip non-ASCII from `print()` in any new custom node before the first job.** The broker's ComfyUI console is cp1252: an emoji print raises UnicodeEncodeError, kills the execution thread, and leaves ComfyUI a zombie (GPU idle ~10%, a few GB) while the broker waits its full job timeout with Strata stopped. Fix: `perl -i.bak-cocobot -pe 's/[^\x00-\x7F]//g if /print\(/'` on the pack's .py files. If a job seems stuck: grep `Traceback|UnicodeEncodeError|OutOfMemory` in `E:\Workspace\Hermes\comfyui-process.log`, then kill the ComfyUI python (Windows `taskkill /F /PID`) so the broker closes the batch and restores Strata.
- **Every launch/command gets an explicit timeout** (`timeout N` wrapper + background notify for jobs) and never run broad `find`/`grep` over `/mnt/c` `/mnt/e` — they hang the session for many minutes (Raúl's standing correction). Search known dirs only.
- v3/io.Schema nodes with DynamicCombo need DOTTED keys in API JSON (`"mode": "x", "mode.width": ..`) — HTTP 500 at validation otherwise.
- **Partial-denoise refiners (flow models):** with `SamplerCustomAdvanced` + `RandomNoise`, the sampler already mixes `x=(1-σ0)·latent+σ0·noise`. Do NOT pre-noise the latent in a custom node too — double noising leaves ~1% of the source signal and the "refine" hallucinates a new scene. Feed the clean (upscaled) latent and let sigmas[0] set strength.
- Smoke-test new video pipelines on 5 s at 1080p before long/2K runs; 15 s at 2K of an H3-sized model can OOM the 32 GB 5090 mid-run.

Edit an existing image (Flux Kontext)

```bash
uv run {baseDir}/scripts/generate_image.py --image "./input.png" --prompt "Change the background to a sunset beach" --filename "./edited.png"
```

Edit with a second reference image

```bash
uv run {baseDir}/scripts/generate_image.py --image "./photo.png" --image2 "./style-ref.png" --prompt "Apply the style from the second image to the first" --filename "./styled.png"
```

In edit mode, `--aspect`/`--width`/`--height` are ignored (dimensions come from the input image). Default guidance is 2.5 (vs 3.5 for generation). You can override with `--guidance`.

Before image-to-image edits, check the input image dimensions. If the image is larger than about 2MP or its longest side is above 1536px, downscale a temporary copy first and pass that resized file to `--image`. Phone photos such as 3072x4096 will make FLUX.2 Klein sample the full latent and can turn a 3-5s job into many minutes. Prefer a longest side of 1536px for fast edits, 2048px when the user explicitly prioritizes detail, and only keep original size when the user explicitly asks for full-resolution editing.

Prompt tips for editing:
- Be specific: "Change the car color to red" instead of "make it red"
- Preserve explicitly: "Change the background to a beach while keeping the person in the same position"
- For style transfer: "Transform to oil painting with visible brushstrokes while maintaining the original composition"

Notes (images)

- This skill is local-only and uses the Windows broker plus ComfyUI.
- **Model selection**: default is `--model z-image-turbo` (fast + good text). Use `--model ideogram4` when exact in-frame text matters (posters/banners); use `--model flux2-klein-9b` for image editing. See the "Model Selection" table above for the A/B-validated reasoning.
- **Image editing**: Both models support image editing via `--image`. FLUX.1 uses Kontext architecture, FLUX.2 Klein uses a completely different native i2i workflow. Edit with FLUX.2 Klein: `--image "input.png" --model flux2-klein-9b --prompt "your edit"`.

### FLUX.2 Klein i2i — CRITICAL SETTINGS

FLUX.2 Klein's i2i workflow uses **ReferenceLatent chaining** per the official ComfyUI documentation. Each reference image is independently VAE-encoded and its visual features are injected into conditioning tensors through `ReferenceLatent` nodes that chain sequentially.

**Input size rule:** In i2i mode, the script does not resize with `--width`/`--height`; the encoded latent comes directly from the input image size. Always inspect and downscale oversized input images before running FLUX.2 Klein i2i. Target ~1-2MP / longest side 1536px by default. This preserves the expected fast path and avoids dynamic VRAM/offload behavior that can make each sampler step take tens of seconds.

**Single-image edit workflow:**
- `LoadImage` → `VAEEncode` → `ReferenceLatent(conditioning, latent)` → `FluxGuidance` → `KSampler`
- `ConditioningZeroOut` of the same prompt as negative conditioning
- CFG: **4.0** | Denoise: **0.75** | CLIP: `type: "flux2"` with `qwen_3_8b_fp8mixed.safetensors`

**Dual reference images (`--image` + `--image2`):** Uses `ReferenceLatent` chaining — NOT `ImageStitch`.
- Each image: `LoadImage` → `VAEEncode` → independent `ReferenceLatent` node
- First `ReferenceLatent` takes prompt conditioning as base
- Second `ReferenceLatent` chains from the first `ReferenceLatent` output
- Final `ReferenceLatent` → `FluxGuidance` → `KSampler`
- The first encoded latent is used as the base latent in `KSampler`
- Prompt should describe what to combine from each reference

**Denoise guide for Klein i2i:**
- 0.75 (default) — Balanced: preserves composition, allows meaningful style/subject changes
- 0.60 — Subtle changes: color tweaks, minor detail edits, keeps original composition
- 0.90 — Heavy changes: significant reimagining, less structure preserved

**⚠️ ComfyUI Node Compatibility:** The following nodes may NOT be available in all ComfyUI versions:
- ❌ `SamplerCustomAdvanced`, `Flux2Scheduler`, `CFGGuider`, `RandomNoise`, `KSamplerSelect`, `ImageScaleToTotalPixels`, `GetImageSize`
- The script uses only **verified available nodes**: `UNETLoader`, `VAELoader`, `CLIPLoader`, `CLIPTextEncode`, `ConditioningZeroOut`, `FluxGuidance`, `LoadImage`, `VAEEncode`, `ReferenceLatent`, `KSampler`, `VAEDecode`, `SaveImage`
- If you get HTTP 500 from the broker, check which node caused the error and replace it with a compatible alternative

- **Denoise in edit mode**: FLUX.2 Klein i2i uses `denoise=0.75` by default. For subtle edits, use lower denoise (~0.6). For heavy structural changes, use higher (~0.9).
- Historical broker download failures in prior chat turns may be stale. For a new text-to-image request, try this skill once in the current turn before concluding it is unavailable.
- The script saves the final PNG into the current workspace path you pass in `--filename`.
- For multi-image requests, prefer `--count` and optionally `--prompts-json` rather than multiple separate exec calls.
- After generation, send each image with the `message` tool using both `message` and `media`. Example: `{ "action": "send", "message": "Imagen 1 de 3", "media": "./output-1.png" }`.
- The `message` text field is required. Never call `message` without it.
- Do not read the image back; report the saved path only.

### Required model files

| Model | Diffusion model | VAE | Text encoder |
|-------|----------------|-----|--------------|
| FLUX.1 Dev | `diffusion_models/flux1-dev.safetensors` (23G) | `vae/ae.safetensors` (320M) | `clip/clip_l.safetensors` + `clip/t5xxl_fp16.safetensors` |
| FLUX.2 Klein 9B | `diffusion_models/flux-2-klein-9b-fp8.safetensors` (8.8G) | `vae/flux2-vae.safetensors` (321M) | `clip/qwen_3_8b_fp8mixed.safetensors` (8.1G) |

---

# ComfyUI Local — Video Generation (MiniMax H3 by default; LTX 2.5 and LTX 2.3 optional)

Use the bundled script to generate videos locally through the broker on the Windows host.

Before calling the script, always send a short confirmation message to the user with the `message` tool. Example: `Ok, voy a generar un video de 5 segundos en 720p de un gato jugando. Tardará unos minutos.`

## MiniMax H3

> **Detailed reference:** Before planning non-trivial H3 work—Ref2VA, continuation, editing, multiple references, dialogue, or performance tuning—read [`references/minimax-h3-guide.md`](references/minimax-h3-guide.md). It contains the official MiniMax/ComfyUI sources, mode-selection rules, prompt structures, continuation recipes, performance findings, and verification checklist.
>
> **Exact-audio music videos** (song-window lip-sync, keyframe gates, stem-based timing measurement, intercutting, cross-shot continuity/clothing audit, build verification): read [`references/music-video-workflow.md`](references/music-video-workflow.md) — the "H3 exact-audio" section has the measurement recipes (melisma ends via vocals-stem envelope, drum onsets via no_vocals, motion profiles, fade luma ramps, scene-detection cut checks).

MiniMax H3 is the default engine because it provides substantially higher visual and audiovisual quality. `--engine minimax-h3` remains accepted when an explicit command is clearer. H3 generates native stereo audio jointly with the video and runs at a fixed 24 fps.

**PDD 8-step is the default sampler (since 2026-08-31).** The script builds the workflow with the official Alibaba PAI PDD Acc LoRAs (`MiniMax-H3-{FL2VA,Ref2VA}-Acc-8Step.safetensors` in `models/pdd_acc/`, node pack `ComfyUI-MiniMax-H3-PDD-Acc`): `MiniMaxH3SigmaShift` (video 12 / audio 3) → `MiniMaxH3PDDAccApply` (nfe 8, lora 1.0, on_off_grid=error) → guider on the patched model, sampler `euler`, sigmas from the Apply node. A/B-validated on this machine: 5s FL2VA 480p 1.63×, 15s Ref2VA 1344×768 3 refs **2.23×** (914s → 410s), no visible degradation, dialogue present. **Only use the classic 20-step `res_multistep` mode when Raúl explicitly asks for it** (`--no-pdd`; keep `--steps 20`). The PDD recipe is fail-closed — the script rejects any `--steps` other than 4/6/8 while PDD is on.

**Explicit-scene iteration learnings (2026-10-09, Judy rabbit series, closed by Raúl):** (1) `--reference-video` continuation cost scales with ref length: a full 15s ref video = ~160 s/step (20 steps ≈ 54 min, exceeds the broker's default 1800s timeout → HTTP 500 with misleading `last_seen=None`); trim the ref to the last ~5s and pass `--timeout-seconds 3600`. (2) Ref2VA preserves the reference composition over the prompt — posing corrections stated only in the prompt (e.g. "press pelvises together") are ignored; the pose must be fixed in the reference image itself. (3) Image-edit attempts to fix adult poses fail elsewhere too: Nano Banana/Gemini blocks the whole scene with `PROHIBITED_CONTENT` (even a neutral edit instruction on the same input), and Qwen-Image edit stretches the character's body instead of moving the partner. (4) Single-image refs with a static action photo tend to render frozen video (mean scene_score <0.002) — for motion-heavy explicit scenes use first-frame mode (`--image`, exclusive with references) or video continuation, not a far-from-action reference.

H3 uses the KJNodes `MiniMaxH3MemoryEfficientSageAttentionPatch` by default. This patches only MiniMax H3 transformer blocks; it does not enable SageAttention globally or change LTX workflows. Use `--no-sage-attention` only for troubleshooting or reproducible A/B comparisons against PyTorch attention.

Validated RTX 5090 stack (2026-08-04):

- ComfyUI Python 3.12, PyTorch `2.10.0+cu130`, CUDA 13.0
- `sageattention==2.2.0+cu130torch2.10.0andhigher.post6` (`cp310-abi3-win_amd64`)
- `triton-windows==3.6.0.post26` (Torch 2.10 maps to Triton 3.6; keep it below 3.7)
- KJNodes commit `195d312a251efdc484c3d9c4570914ab2da9da54`
- SageAttention wheel SHA-256: `8a8df597c0c0a874c70b0ce915dedf6ab4a1254d577375939f79b8d2dcb0b195`

A same-prompt, same-seed H3 benchmark at 1344x768, 362 frames, and 20 steps completed in 14m44s with SageAttention versus 30m21s with PyTorch attention (2.06x end-to-end, 51.45% less wall time), with no clear visual degradation. Do not use ComfyUI's global `--use-sage-attention` flag for this setup.

Text-to-video:

```bash
uv run {baseDir}/scripts/generate_video.py --engine minimax-h3 \
  --prompt 'A cinematic storm over a futuristic city. Stereo audio: rain and distant thunder.' \
  --filename h3-t2v.mp4
```

Image-to-video supports an initial frame, a final frame, or both:

```bash
# Initial frame
uv run {baseDir}/scripts/generate_video.py --engine minimax-h3 \
  --image first.png --prompt 'The subject turns toward the camera' --filename h3-first.mp4

# Final frame only
uv run {baseDir}/scripts/generate_video.py --engine minimax-h3 \
  --end-image last.png --prompt 'The scene evolves naturally into the supplied final frame' --filename h3-last.mp4

# Initial and final frames
uv run {baseDir}/scripts/generate_video.py --engine minimax-h3 \
  --image first.png --end-image last.png --prompt 'A smooth transition between both frames' --filename h3-both.mp4
```

Reference-to-video accepts up to nine images, three videos, and three standalone audio clips, with at most twelve mixed files. Image order defines `<Picture 1>`, `<Picture 2>`, etc.; video order independently defines `<Video 1>`, `<Video 2>`, etc. Audio numbering includes video soundtracks first, followed by standalone `--reference-audio` values. Reference inputs cannot be combined with first/last-frame conditioning.

```bash
uv run {baseDir}/scripts/generate_video.py --engine minimax-h3 \
  --reference-image character.png \
  --reference-video camera-motion.mp4 \
  --prompt 'Use <Picture 1> for character identity and <Video 1> for camera movement and timing. Generate the character walking through a rainy street.' \
  --filename h3-reference.mp4
```

- `--ref-image-size match` is the default and fastest. Use `max` only when stronger identity fidelity justifies much higher compute cost.
- Repeat `--reference-video` up to three times. Each clip must be 2–15 seconds at 23.976–60 fps, and their combined duration cannot exceed 15 seconds.
- Reference videos are normalized locally to 24 fps H.264/AAC before upload so their timing matches H3's local Ref2VA node. Supported inputs: MP4, MOV, WebM, MKV, and AVI.

### H3 Reference Audio & Dialogue

H3 generates native stereo audio including dialogue, SFX, music, and ambience. **Spanish is fully supported** as one of 11 stable dialogue languages (Arabic, Chinese, English, French, German, Italian, Japanese, Korean, Portuguese, Russian, Spanish).

**Dialogue in prompts:** Use speaker labels `(S1)`, `(S2)`, language tags, and `<d>` tags for exact text:
```text
The man (S1) looks at her and says, <d>[Spanish] ¿Estás bien?</d>
She smiles and replies, <d>[Spanish] ¡Ahora sí!</d>
```
For simpler prompts, quotes work too: `speaking in Spanish, saying: "¿Estás bien?"`

**Voice cloning with audio reference:** H3 accepts up to 3 standalone audio clips (2-15s each, 15s total combined) for voice identity transfer. The model clones the voice timbre and cadence from the reference and generates new speech with that voice.

Semantic mode (default): H3 uses the audio for voice identity, words, cadence, timing, music, or sound design, then jointly generates a new AAC stereo soundtrack.
```bash
uv run {baseDir}/scripts/generate_video.py \
  --reference-image portrait.png \
  --reference-audio speech.wav \
  --prompt 'Use <Picture 1> as the speaker and <Audio 1> for voice, words, timing, and lip movement.' \
  --filename h3-semantic-audio.mp4
```

Exact mode adds `--preserve-reference-audio`: H3 still conditions mouth and motion on `<Audio 1>`, then the script replaces the generated soundtrack with the complete original recording encoded as 16-bit ALAC lossless. The output duration follows the reference audio automatically; any explicit `--duration` is ignored. Exact mode accepts exactly one standalone audio reference.

```bash
uv run {baseDir}/scripts/generate_video.py \
  --reference-image portrait.png \
  --reference-audio speech.wav \
  --preserve-reference-audio \
  --prompt 'Use <Picture 1> as the speaker. Match mouth and jaw movement to every syllable and timestamp in <Audio 1>.' \
  --filename h3-exact-audio.mp4
```

- Exact mode preserves the decoded PCM16 samples and original sample rate/channel count; it does not merely re-encode to AAC.
- H3 produces visible speaking motion and joint audiovisual timing, but phoneme-perfect lip sync is not guaranteed. Inspect the result temporally for production use.
- When reference videos contain audio, their soundtracks consume the first `<Audio N>` tags. The CLI prints the actual tag assigned to each standalone audio.
- H3 supports 1–15 seconds; frame counts are automatically aligned to the model's 17k+5 temporal grid.
- H3 presets are multiples of 32. Its `720p` preset maps to the native 1344×768 canvas.
- Do not combine H3 with LTX-only flags such as `--audio`, `--lipsync`, or `--id-lora`.
- The broker prepares prompts and uploads while Qwen is active, unloads llama.cpp for the GPU job, and restores the exact Qwen profile afterward.

### H3 long videos — motion-context chain (`--h3-chain`)

`--h3-chain N` renders N segments as ONE continuous take via the installed `ComfyUI-H3-Motion-Context` pack: each segment continues the previous one's sampler latent (picture + sound), so motion, lip state and ambience genuinely CONTINUE across joins — no cuts, no semantic reinterpretation. Use it for sustained notes/phrases >15 s, one-takes, and any commission where parts must be re-rollable independently.

```bash
uv run {baseDir}/scripts/generate_video.py --engine minimax-h3 --h3-chain 2 \
  --prompt "<fallback prompt for every segment>" \
  --chain-prompts-json '["prompt seg 1", "prompt seg 2"]' \
  --duration 7.3 --resolution 720p --filename take.mp4 --seed 4242 \
  --reference-image character.png [--reference-audio song.mp3 --preserve-reference-audio --chain-audio-start 86.38]
```

- **Lengths**: `--duration` snaps to the pack's grid-aligned sampled lengths (124/175/226/277/328 f). Segment 1 delivers the full sampled length; every later segment delivers sampled −22 frames (the pinned 0.917 s head comes off automatically, with audio matched). `--dry-run` prints the exact slot/delivery/window plan — run it before expensive chains.
- **Slots & re-rolls**: segment k saves `output/h3_context/<chain-id>/clip_000kk.safetensors` on the server. Re-roll a bad tail WITHOUT touching approved video: same `--chain-id`, `--chain-start <slot>` (it loads that slot-1 latent). Changing an earlier slot invalidates later ones (natural chain dependency). Final file = `<filename>`; per-slot files `<filename>_slotK.mp4` are kept for review.
- **Exact-audio chain**: `--reference-audio <MASTER> --preserve-reference-audio --chain-audio-start T0` — the script slices each segment's conditioning window (covering the SAMPLED length including the pinned 0.917 s before its delivered start — validated: mouth already correct at delivered frame 0) and muxes the final file with the master slice. Do NOT pre-slice windows yourself in this mode.
- Prompts must follow the pack's chain rules (airlock: each segment opens on the previous closing framing with the action already running; contradictions render as unions; no first_frame except slot 1; `--end-image` applies to the LAST slot). Full rules and wiring: `references/minimax-h3-guide.md`.
- Fixed: `context_length 22`, `audio_context_length 18`, one resolution for the whole chain, PDD default. Co-generated audio muffles slightly after ~4-5 links (irrelevant when muxing a master).
- **Pitfall — repo/venv drift breaks ComfyUI startup (seen 2026-08-21):** ComfyUI Desktop auto-updated the repo which now imports `ColorPrimaries`/`ColorTrc` from `av.video.reformatter` (needs PyAV ≥ 17, PR #2175) while `C:\ComfyUI\.venv` still had `av 16.1.0` → broker logs `RuntimeError: ComfyUI exited during startup` and every job fails with HTTP 500. **Diagnose via the last traceback in `E:\Workspace\Hermes\comfyui-process.log`.** RESOLVED 2026-08-21:
  1. `uv pip install --python 'C:\ComfyUI\.venv\Scripts\python.exe' --upgrade 'av>=17'` → installed av 18.1.0. (cmd.exe mangles `"` quotes for uv — use PowerShell single-quotes, e.g. `powershell -NoProfile -Command "& uv pip install --python 'C:\ComfyUI\.venv\Scripts\python.exe' --upgrade 'av>=17'"`.)
  2. Bump the repo pin `E:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\requirements.txt`: `av>=16.0.0` → `av>=17.0.0` (the old pin let the stale venv pass checks on future upgrades).
  3. Verify: `C:\ComfyUI\.venv\Scripts\python.exe -c "from av.video.reformatter import ColorPrimaries, ColorRange, ColorTrc"` → IMPORT_OK.
  Note: a 404 on broker `GET /v1/health` is NORMAL for this broker build — no health route; the broker is fine when the ComfyUI subprocess crashes.

## LTX 2.5

LTX 2.5 (Lightricks, 2026) is the newest LTX generation: a 22B distilled transformer that jointly generates **video + stereo audio** with fixed sigma schedules. It must be selected explicitly with `--engine ltx25`.

Quality sits between H3 and LTX 2.3; it is faster than H3 and has better prompt adherence and audio than 2.3. Use it when you want native audio generation with LTX-style speed, or as an A/B alternative to H3.

Text-to-video:

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx25 \
  --prompt "A red fox leaping across a snowy forest at golden hour, cinematic" \
  --filename output-t2v.mp4
```

Image-to-video (first frame):

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx25 \
  --image first.png --prompt "The scene comes alive, camera slowly pushes in" \
  --filename output-i2v.mp4
```

First+last-to-video (interpolate between two frames):

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx25 \
  --image first.png --end-image last.png --prompt "A smooth transition between both frames" \
  --filename output-flf.mp4
```

- Pipeline (mirrors the official Comfy-Org `video_ltx2_5_t2v/i2v/flf2v` templates): t2v/i2v run **two stages** — stage 1 at half resolution (8-sigma distilled schedule) → `LTXVLatentUpsampler` x2 → stage 2 refinement (4-sigma schedule). flf2v runs a **single full-resolution pass** (12-sigma schedule) with `LTXVAddGuide` on frame 0 and frame -1 (strength 0.7) plus `LTXVCropGuides`.
- Sampling: `SamplerCustomAdvanced` + `euler_ancestral`, `LTXVDualCFGGuider` cfg 1/1, `ManualSigmas` — the distilled model ignores `--steps`; it prints 20 but the schedule is fixed. `--fps` is fixed at 24.
- Audio is generated natively (no `--audio` conditioning in 2.5). Frame grid: 8k+1 (73 frames for 3s).
- Models (in `F:\ComfyUIModels`): `diffusion_models/ltx-2.5-22b-distilled-int8-convrot.safetensors`, `clip/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` (`CLIPLoader type="ltxv"`), `vae/ltx-2.5-vae.safetensors`, `vae/ltx-2.5-vae-encoder.safetensors`, `loras/ltx-2.5-32x-upscale.safetensors` (latent upscaler via `LatentUpscaleModelLoader`).
- Not available in 2.5 (script rejects): `--audio`, `--lipsync`, `--id-lora`, `--reference-audio`, `--preserve-reference-audio`, `--reference-image/-video`.
- 720p 3s measured on RTX 5090 (2026-08-27): t2v 45 s, i2v 44 s, flf2v 61 s. 1080p works but is ~2x slower; prefer 720p for iteration.

## LTX 2.3

LTX 2.3 is the faster fallback and must be selected explicitly with `--engine ltx23`. Use it when speed, supplied-audio conditioning, lip-sync, or ID-LoRA matters more than H3's higher generation quality.

Text-to-Video (basic)

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --prompt "A cat chasing a laser pointer across a living room" --filename "output.mp4"
```

Image-to-Video (animate a first frame)

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --image "./first-frame.png" --prompt "The camera slowly zooms in while flowers sway in the wind" --filename "output.mp4"
```

Audio-conditioned video (the video follows the audio)

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --audio "./music.mp3" --prompt "A DJ mixing tracks in a neon club" --filename "output.mp4"
```

Image + Audio (first frame + audio conditioning)

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --image "./scene.png" --audio "./narration.wav" --prompt "The narrator describes the scene" --filename "output.mp4"
```

Lip-sync mode (best for talking heads / singing)

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --lipsync --image "./portrait.png" --audio "./speech.wav" --prompt "A woman speaking directly to camera" --filename "lipsync_output.mp4"
```

- Requires both `--image` (face/portrait) and `--audio` (speech/singing audio).
- Internally uses MelBand RoFormer to isolate vocals from the audio, then conditions video generation on the clean vocal track via a dedicated Audio VAE.
- Produces significantly better lip synchronisation than regular `--image --audio` (which treats audio as ambient conditioning).
- **The output video keeps the original audio track** — the script automatically replaces the model-generated audio with the input audio via ffmpeg after generation.
- Best results with: clear frontal face, clean speech audio, 3-8 second clips.

**Lip-sync prompt rules:**
- Include the exact spoken text in quotes and identify the language/accent so the mouth motion has matching phonetic guidance.
- Analyze the source image before writing the prompt, especially for panels, ornamental frames, or multi-subject compositions.
- Default to a static camera for structured source images; zooms and pans can deform their layout.

Custom duration, resolution, and aspect ratio

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --prompt "A drone shot over a mountain range at sunset" --filename "output.mp4" --duration 10 --resolution 1080p --aspect 16:9
```

**🚫 Avoid editing `generate_video.py` unless you are explicitly asked to update the workflow itself. It already encodes the official LTX 2.3 ID-LoRA template (two-stage distilled pipeline). Just call it with `--engine ltx23 --id-lora`.**

ID-LoRA mode (consistent voice identity from a 5-second reference)

ID-LoRA transfers the voice identity from a ~5-second audio reference to generate new speech with the same voice. The model generates both video and audio jointly — no separate TTS step needed. Lip-sync is built-in.

**⚠️ IMPORTANT: Always use the script below. Do NOT construct the ComfyUI workflow JSON manually — the ID-LoRA pipeline mirrors the official `video_ltx2_3_id_lora` ComfyUI template (BF16 checkpoint `ltx-2.3-22b-dev.safetensors` + distilled LoRA + ID-LoRA stacked, two-stage low/high-res with `LTXVLatentUpsampler`, `CFGGuider` cfg=1.0, `euler_ancestral_cfg_pp` / `euler_cfg_pp`, `ManualSigmas`). All the node wiring is handled internally by `generate_video.py --engine ltx23 --id-lora`.**

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --id-lora \
  --image "./portrait.png" \
  --reference-audio "./voice_sample.wav" \
  --identity-guidance-scale 1.5 \
  --prompt "[VISUAL]: A person speaks to camera in a cozy room. The character opens its mouth wide to speak clearly, its jaw moving with each word [SPEECH]: Hello, this is what I want to say [SOUNDS]: warm indoor ambience, soft echo" \
  --filename "output.mp4"
```

- Requires `--image` (first frame, ideally a face/portrait) and `--reference-audio` (5-second voice sample for identity).
- The reference audio defines WHO speaks (voice timbre, pitch, cadence). The `[SPEECH]` tag in the prompt defines WHAT they say.
- The model generates the actual spoken words with the reference voice identity — unlike regular `--audio` mode which only generates ambient sounds.
- **Prompt format for ID-LoRA** — use structured tags:
  - `[VISUAL]:` — Scene description (what the camera sees)
  - `[SPEECH]:` — Exact words the character says (the model will synthesize these)
  - `[SOUNDS]:` — Vocal quality descriptors + ambient sounds (e.g. "deep male voice, room reverb, rain outside")
- `--identity-guidance-scale N` (default 3.0) — Controls how strongly the voice identity is preserved. Higher = more faithful to reference but less natural. Range 0-10, sweet spot is 2.0-5.0. **For lip-sync: use 1.5** — lower guidance allows more facial movement while preserving voice identity. Tested and confirmed working on RTX 5090 with full BF16 model.
- **Language note**: ID-LoRA was trained primarily on English (CelebV-HQ + TalkVid datasets). Spanish works but quality may vary — the voice identity transfers well, but pronunciation/prosody may be less natural than English. Try it and iterate.
- Best results with: clear 5s voice sample (no background noise), frontal face image, short clips (3-8s).
- Can be combined with `--duration`, `--resolution`, `--aspect`, `--steps`, `--seed`.
- **Do NOT combine** with `--lipsync` or `--audio` — ID-LoRA handles voice generation internally.
- **Do NOT build the workflow JSON manually** — always call `generate_video.py --engine ltx23 --id-lora` which handles all the complex node wiring internally.

**💡 ID-LoRA — Lip-sync & quality tips (tested on RTX 5090):**
1. **Use `--identity-guidance-scale 1.5`** (not the default 3.0) — lower guidance = more facial movement while keeping voice identity
2. Add mouth movement to `[SPEECH]`: "The character opens its mouth wide to speak clearly, their jaw moving with each syllable"
3. Use the BF16 checkpoint (`ltx-2.3-22b-dev.safetensors`) — the full model works fine with memory swapping and produces better visuals/lip-sync than FP8. The script's `MODEL_IDLORA_CHECKPOINT` is set to BF16.
4. Voice LoRA: only `ltx-2.3-id-lora-talkvid-3k` is installed (CelebVHQ alternative was deleted 2026-09-21 as part of the disk cleanup; re-download from Comfy-Org if better motion is ever needed).
4. **Audio glitches at the start**: If you hear artifacts before the main speech, regenerate with a different seed — it's random and usually clears on the second try
5. **Model location**: User models are in `F:\ComfyUIModels` (not the default ComfyUI path)
6. **Text length**: Keep `[SPEECH]` to ~10s of spoken text. Longer text (>15s) causes truncation and garbled output. Split into multiple clips if needed.

**⚠️ ID-LoRA rigidity problem (KNOWN):**
At `strength_model: 1.0` the video is **extremely static/rigid** — barely any motion. Fixes: lower `--identity-guidance-scale` to **1.5** or switch to **CelebVHQ checkpoint** (better motion than TalkVid).

ID-LoRA examples:

Same character, different lines (voice stays consistent across videos):

```bash
# First video
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --id-lora \
  --image "./gato.png" --reference-audio "./gato_voice.wav" \
  --identity-guidance-scale 1.5 \
  --prompt "[VISUAL]: A black cat speaks to camera. The character opens its mouth wide to speak clearly, its jaw moving with each word [SPEECH]: Yo soy el guardian de los secretos [SOUNDS]: deep mysterious male voice, echo" \
  --filename "scene1.mp4"

# Second video — same voice reference, different text
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --id-lora \
  --image "./gato.png" --reference-audio "./gato_voice.wav" \
  --identity-guidance-scale 1.5 \
  --prompt "[VISUAL]: The same black cat turns to look at something off-screen. Opens its mouth wide to speak clearly [SPEECH]: Los humanos no comprenden nuestro poder [SOUNDS]: deep mysterious male voice, wind" \
  --filename "scene2.mp4"
```

### Visual character consistency across clips

- Generate the initial reference set with FLUX.1 Dev when identity consistency matters most.
- For stronger persistence, train an LTX 2.3 Character LoRA from 10–20 varied frames; use IC-LoRA when pose or structural control is the priority.
- Character LoRA and ID-LoRA can be combined to keep visual and voice identity consistent. See `references/ltx-2-3-lora-training.md` and `references/id-lora-voice.md`.

Optional quality controls

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --prompt "description" --filename "output.mp4" --steps 24 --seed 42
```

Resolution presets

- `--resolution 480p` — Fast previews; good for testing prompts
- `--resolution 720p` — Default; good balance of quality and speed
- `--resolution 1080p` — Full HD; slower but best quality

Aspect ratio guide

- `--aspect 16:9` — Standard widescreen (default)
- `--aspect 4:3` — Classic TV / photo
- `--aspect 1:1` — Square (social media)
- `--aspect 9:16` — Vertical / mobile / stories
- `--aspect 3:4` — Vertical photo

Duration

- `--duration N` where N is 1–20 seconds (default 5)
- Internally converted to a valid LTX frame count (8k+1 formula)
- Longer videos use proportionally more VRAM and time

Prompt tips for video
Prompt tips for video
- Describe **motion** explicitly: "A bird takes flight from a branch", "The camera pans left slowly"
- Include environment details: "in a sunlit forest", "during heavy rain at night"
- For image-to-video, describe what should **change** from the static image: "The water begins to flow", "Clouds drift across the sky"
- Prompts are auto-enhanced by Gemma 3 12B for better results — keep your prompt natural and descriptive
- **Speech/Lip-sync**: LTX 2.3 can generate real spoken dialogue natively. Specify the language/accent and put the exact line in quotes, for example: `speaking in Spanish with a Spanish accent, saying: "Hola"`.
- The negative prompt is built-in: blurry, watermark, subtitles, etc. Use `--negative-prompt "extra terms"` to **append** to the defaults, or prefix with `--negative-prompt "!only these terms"` to replace entirely.

Notes (video)
Notes (video)
- Uses LTX 2.3 with a two-pass pipeline: first pass at half-resolution for structure, then latent upscale + refinement for detail.
- Audio is generated automatically alongside the video (ambient sounds, effects). No separate audio step needed.
- **Voice generation**: LTX 2.3 generates real voices and spoken words jointly with video. State the language explicitly and quote the exact dialogue. ID-LoRA adds consistent voice identity from a reference sample; `--lipsync` is for matching a supplied audio recording.
- **`--audio`**: optionally provide a local audio file (wav/mp3/ogg/flac/m4a) as a conditioning reference. The model uses it to synchronize video motion to the rhythm, speech, or effects in the audio. The output audio is **regenerated by the model** (not the original file). If the user wants the exact original audio track on the video, replace it afterward with ffmpeg. Can be combined with `--image`.
- Output format is MP4 (auto codec). Compatible with Telegram and most players.
- For image-to-video, `--image` accepts a local path. The script uploads it to the broker automatically.
- `--aspect` and `--resolution` are ignored in i2v mode if the image already defines dimensions (the image is resized to the closest preset).
- Video generation is significantly slower than image generation. A 5s 720p video may take several minutes.
- **CRITICAL**: Always use `exec timeout=1800` for video generation. The default exec timeout (300s) is NOT enough. LTX example: `exec timeout=1800 uv run {baseDir}/scripts/generate_video.py --engine ltx23 ...`
- After generation, send the video with the `message` tool: `{ "action": "send", "message": "Aquí va el video", "media": "./output.mp4" }`.
- One video per invocation. Do not batch video requests.
- **PITFALL — existing output blocks the rename (seen 2026-10-14):** if `<filename>.mp4` ALREADY exists, `generate_video.py` saves the new render as `<filename>` WITHOUT the extension (it does not overwrite) and the `mv` guard in wrapper scripts (`[ -f X ] && [ ! -f X.mp4 ]`) silently skips — so QA can end up inspecting the OLD .mp4 while the new render rots extensionless. Always delete/rename the previous output before re-running the same `--filename`, and verify the delivered file's mtime/size matches the fresh render before judging it.

---

# ComfyUI Local — H3 Still (imágenes fijas con MiniMax H3, Fizgig nodes)

Instalado 2026-10-16: nodo `ComfyUI-Fizgig-H3-Still` (clonado en custom_nodes del install del broker) + `loras/minimax/minimax_h3_turbo_v4_step600_ema.safetensors` (780 MB, larryvrh repo). Reutiliza los pesos H3 de vídeo ya instalados (fl2va int8 + qwen3vl_32b nvfp4 + video VAE) — cero descargas extra.

**Wiring API (probado, `imagenes/ab-h3still/battery.py` es el reference):**
- t2i: `MiniMaxH3ImageToVideo` (clip type `minimax`, `length: 5`, LATENT sin conectar) + `FizgigH3StillLatent` (w/h múltiplos de 32) → `SamplerCustomAdvanced` con `er_sde` + `BasicScheduler simple` 20 pasos + BasicGuider cfg implícita → `FizgigH3StillDecode` → SaveImage. Turbo LoRA vía `LoraLoaderModelOnly` strength **0.38**.
- edit: `MiniMaxH3ReferenceToVideo` con refs como clave punteada **`ref_images.ref_image_N`** en el dict de inputs (clave pelada `ref_image_1` → TypeError execute(), mismo fallo que el autogrow de Qwen). `ref_image_size: match`. Canvas edit ~2.5MP de la ratio de la foto.
- **PITFALL validación**: `lora_name` debe llevar barra invertida Windows exacta como la lista ComfyUI: `minimax\minimax_h3_turbo_v4_step600_ema.safetensors` (con `/` falla la validación con 500).
- Rendimiento 5090 (turbo 20 pasos): 1.3MP ~110-118 s, 2.5MP ~128-134 s imagen (warm).
- **Edits multi-ref con animales antropomórficos**: copia muy bien pelaje/identidad (mejor que Qwen en pelaje denso), pero NO obedece cláusulas de expresión canina negativas — "jaws CLOSED, teeth NOT showing, tongue NOT visible" y "paws NOT touching" fallaron 2/2 tandas (sonrisa de jadeo + zarpa al hombro persisten). Si la expresión del keyframe debe cambiar, asumir re-rulo o aceptarla: un hocico abierto en el keyframe contamina ~1.5 s del clip hijo (H3 lip-sincroniza cualquier boca abierta en clips exact-audio).
- **PITFALL broker (Raúl 16/10)**: lanzar los `/v1/generate` en SECUESTRA bloqueante uno-detras-de-otro → el broker para y REARRANCA Strata entre imagen e imagen (recarga enorme). Hay que lanzar todos los POSTs en paralelo dentro de la ventana de batch de 5 s (hilos/threads) para que corran en UN solo swap.

**A/B vs Qwen-Image 2.1 (2026-10-16, seed 20261016, `imagenes/ab-h3still/cmp_T*.png`):** edits: H3 gana/empata (identidad T3 con pattern de camiseta casi idéntico; T4 dos identidades sin cruzar + escena de pub más rica y risas naturales). Texto ES: EMPATE perfecto (H3 escribió "FERIA DEL LIBRO / CIUDAD REAL • 23 DE AÑIL" sin un error, Ñ incluida — sorpresa). t2i fino: Qwen ligeramente delante (poros de piel, fidelidad de escena) pero H3 estaba en desventaja: solo 1.3MP y Fizgig dice que H3 rinde de 3MP arriba — retest t2i a 2.5MP pendiente. Veredicto: no es el "otra dimensión" del hype de Reddit, pero es un segundo editor serio; útil como `--model h3-still` para identidad/multi-ref/escenas si el retest grande lo confirma.

## ComfyUI Local — Song Generation (ACE Step 1.5)

Use the bundled script to generate songs locally through the broker on the Windows host.

Before calling the script, always send a short confirmation message to the user with the `message` tool. Example: `Ok, voy a generar una canción de 2 minutos de rock épico. Tardará un poco.`

Generate a song (basic)

```bash
uv run {baseDir}/scripts/generate_song.py --tags "rock, epic, female vocals" --filename "output.mp3"
```

Generate a song with lyrics

```bash
uv run {baseDir}/scripts/generate_song.py --tags "pop, ballad, male vocals" --lyrics "Verse 1\nHere are my lyrics...\n\nChorus\nThis is the chorus..." --filename "output.mp3"
```

Generate with custom BPM, key, and duration

```bash
uv run {baseDir}/scripts/generate_song.py --tags "electronic, ambient" --filename "output.mp3" --duration 240 --bpm 90 --key "A minor" --language en
```

Use a reference audio for style/timbre transfer

```bash
uv run {baseDir}/scripts/generate_song.py --tags "rock, guitar" --reference-audio "./media/inbound/reference.mp3" --filename "output.mp3"
```

Tag guide

- Tags describe the genre, style, instruments, and mood: `rock, epic, guitar solo, cinematic, female vocals`
- Multiple tags separated by commas
- Be specific: `hard rock, electric guitar, power ballad` produces better results than just `rock`
- Include vocal type if relevant: `male vocals`, `female vocals`, `duet`, `choir`

Key options

- Format: `<root> <quality>` — e.g. `C major`, `E minor`, `F# minor`, `Bb major`
- All standard roots supported: C, C#, Db, D, D#, Eb, E, F, F#, Gb, G, G#, Ab, A, A#, Bb, B
- Default: `C major`

Language codes

- `es` (Spanish, default), `en` (English), `ja` (Japanese), `zh` (Chinese), `de` (German), `fr` (French), `pt` (Portuguese), `ru` (Russian), `it` (Italian), `ko` (Korean), and more.

Notes (songs)

- Uses ACE Step 1.5 XL Turbo with the 4B decoder and 4B text encoder by default (`--quality xl-turbo`, 8 steps, CFG 1.0). Fast generation with great quality.
- `--quality xl-merge` uses the SFT+Turbo merged model (task arithmetic α=0.5). Same 8 steps as turbo but with blended SFT weights — less artifacts, fewer wrong notes, better structure. Experimental — community feedback is on the 2B version, XL merge is very new.
- `--quality high` uses the original 2B base turbo model with 4B encoder split (8 steps).
- `--quality standard` uses the AIO checkpoint with the smaller encoder (faster, lower quality). Only use as fallback.
- Output format is MP3 at 320kbps. Compatible with Telegram and all players.
- **Lyrics**: Write lyrics in the language matching `--language`. Cocobot should compose the lyrics creatively and pass them via `--lyrics`.
- **Reference audio**: `--reference-audio` sets the timbre/style from another song. The script uploads it to the broker automatically.
- `--quality standard` uses the AIO checkpoint with the smaller encoder (faster, lower quality). Only use as fallback.
- `--format flac` outputs lossless FLAC instead of the default MP3 (320kbps). Use FLAC when audio fidelity matters (master copies, further processing). Default is `mp3` for compatibility.
- Song generation is fast: a 2-minute song typically takes 30-60 seconds.
- After generation, send the song with the `message` tool: `{ "action": "send", "message": "Aquí va la canción", "media": "./output.mp3" }`.
- Use `--count N` (or `-n N`) to generate multiple variations in a single batch. Files are named `output-1.mp3`, `output-2.mp3`, etc. Each gets a different seed automatically.
- **Always use `--count N`** instead of calling the script multiple times — this keeps all requests in the same broker batch and avoids repeated model loading/unloading.

### Edit mode (inpainting a section of a song)

Re-render a specific time range of an existing song (fix vocal quality, change instrumentation, etc.). The rest of the song remains untouched.

Edit a section (fix vocal clarity):

```bash
uv run {baseDir}/scripts/generate_song.py --edit "./original.mp3" --start 45 --end 50 --tags "rock, epic, female vocals" --lyrics "Same lyrics as original..." --filename "./edited.mp3"
```

Edit with stronger denoise (change melody/feel):

```bash
uv run {baseDir}/scripts/generate_song.py --edit "./original.mp3" --start 30 --end 50 --tags "pop, ballad" --lyrics "Same lyrics as original..." --filename "./edited.mp3" --denoise 0.5
```

Edit-specific flags:

| Flag          | Default | Description |
|---------------|---------|-------------|
| `--edit`      | —       | Path to original MP3 (activates edit mode) |
| `--start`     | —       | Start of edit region in seconds (required) |
| `--end`       | —       | End of edit region in seconds (required) |
| `--denoise`   | 0.25    | Regeneration strength (0.05 = subtle, 1.0 = full) |
| `--crossfade` | 0.5     | Crossfade at edit boundaries in seconds |

How it works: the script VAE-encodes the original, runs KSampler with partial denoise on the full latent (preserving structure), then uses ffmpeg to splice only the edit region back into the original with smooth crossfade.

Denoise guide:

| Range       | Use case |
|-------------|----------|
| 0.15 – 0.30 | Fix vocal clarity, clean small artifacts. Preserves temporal structure and lyrics placement. |
| 0.30 – 0.50 | Moderate change: adjust timbre, slight melodic variation. |
| 0.50 – 0.80 | Heavy change: new melody/instrumentation. Lyrics may shift position. |

Notes (edit mode):

- **MUST pass the same `--tags`, `--lyrics`, `--bpm`, `--key`** as the original song — without matching conditioning the edit will sound incoherent.
- **Always include `--lyrics`** even for small edits — without lyrics conditioning the model may generate instrumental-only content in the edit region.
- Duration is auto-detected from the original file (no `--duration` needed).
- `--count` is not supported in edit mode (one edit per invocation).
---

## Sound Effects (SFX) Generation

Model: **Stable Audio Open 1.0** (stabilityai/stable-audio-open-1.0) — 1.2B params, 44.1 kHz stereo output.
VRAM: ~4 GB (FP16). Max duration: ~47 seconds.
Auto-downloads on first run (~5 GB from HuggingFace).

### Direct (WSL, with GPU)

```bash
uv run {baseDir}/scripts/generate_sfx.py --prompt "cat hissing aggressively" --filename ./sfx.wav
uv run {baseDir}/scripts/generate_sfx.py --prompt "thunder rolling in the distance" --duration 10 --filename ./thunder.wav
uv run {baseDir}/scripts/generate_sfx.py --prompt "glass shattering" --count 3 --filename ./glass.wav
```

### Via Broker (from sandbox container)

```bash
python3 {baseDir}/scripts/generate_sfx_broker.py --prompt "rain on a tin roof" --filename /workspace/temp/rain.wav
```

### Options

| Flag                | Default                          | Description |
|---------------------|----------------------------------|-------------|
| `--prompt`          | (required)                       | Text description of the sound effect |
| `--filename`        | (required)                       | Output WAV path |
| `--duration`        | 10.0                             | Duration in seconds (max ~47) |
| `--steps`           | 100                              | Diffusion steps |
| `--guidance`        | 7.0                              | CFG scale |
| `--count`           | 1                                | Number of variations (different seeds) |
| `--negative-prompt` | "Low quality, distorted, noise." | What to avoid |

### Notes

- Output is always 44.1 kHz stereo 16-bit WAV (high quality).
- HuggingFace token required (gated model). Auto-read from `~/.cache/huggingface/token`.
- Multiple prompts + filenames supported: `--prompt "A" "B" --filename a.wav b.wav`
- Broker wrapper uses gpu-exec endpoint (stops llama → runs SFX → restarts llama).

---

## Text-to-Speech (TTS)

Model: **Qwen3-TTS** (1.7B default, 0.6B with `--fast`). Multilingual (Spanish, English, Chinese, etc.).
VRAM: ~6 GB (FP16). Falls back to CPU when insufficient VRAM.

### Via Broker (from sandbox container — preferred)

```bash
python3 {baseDir}/scripts/generate_speech_broker.py --text "¡Miau! Hola Raúl" --filename /workspace/temp/cocobot.wav
python3 {baseDir}/scripts/generate_speech_broker.py --text "Hello world" --ref-audio /workspace/skills/comfyui-local/scripts/assets/ref.wav --ref-text "transcript" --filename /workspace/temp/clone.wav
```

### Direct (WSL, with GPU)

```bash
uv run {baseDir}/scripts/generate_speech.py --text "Hello" --filename ./speech.wav
uv run {baseDir}/scripts/generate_speech.py --text "Hola" --ref-audio ./ref.wav --ref-text "Reference transcript" --filename ./clone.wav
uv run {baseDir}/scripts/generate_speech.py --text "Hi there" --speaker Mochi --instruct "Speak playfully" --filename ./mochi.wav
```

### Modes

1. **Voice clone** (default for Cocobot): `--ref-audio` + `--ref-text` — clones the voice from a reference sample.
2. **Preset speaker**: `--speaker Mochi` + `--instruct "Speak playfully"` — uses built-in voices.
3. **Voice design**: `--design "A warm female voice with a slight accent"` — creates a new character voice from a natural-language description.

### Options

| Flag            | Default | Description |
|-----------------|---------|-------------|
| `--text`        | (required) | Text to synthesize |
| `--filename`    | (required) | Output WAV path |
| `--language`    | auto    | Language override (Spanish/English/Chinese/...) |
| `--fast`        | off     | Use 0.6B model (~3x faster, lower quality) |
| `--ref-audio`   | —       | Reference audio for voice cloning |
| `--ref-text`    | —       | Transcript of the reference audio |
| `--speaker`     | —       | Preset speaker name (Vivian/Mochi/Ryan/...) |
| `--instruct`    | —       | Voice style instruction |
| `--design`      | —       | Natural-language voice description |
| `--max-duration` | 300    | Max output duration in seconds |

### Notes (TTS)

- **CRITICAL: ALWAYS use `generate_speech_broker.py` for TTS.** This is the ONLY correct way to generate speech from the sandbox. It handles the broker gpu-exec swap automatically (stops llama-server → runs TTS on GPU → restarts llama-server). NEVER try to call llama-server's API directly for TTS — llama-server runs the Qwen3.5-27B chat model, NOT a TTS model.
- **NEVER write your own TTS script or try alternative approaches.** The infrastructure is already built and tested. Just call `generate_speech_broker.py` with the right arguments.
- For long texts, split into fragments and call `generate_speech_broker.py` once per fragment. Each call goes through the broker (stop llama → TTS → restart llama), so minimize the number of fragments.
- The `--timeout` flag controls how long the broker waits for the TTS to finish. Default is 900s (15 min). For very long texts, increase it.
- First run may be slow: the TTS model (~3.4 GB) downloads from HuggingFace on first use. Subsequent runs use the cached model.
- Output is always WAV (24 kHz mono). Convert to other formats with ffmpeg if needed.
- English, Spanish, Chinese, and other languages are all supported. Use `--language English` to force English if auto-detection fails.
- If no `--ref-audio` and no `--speaker` and no `--design` are given, the script uses the default Cocobot voice (from `assets/cocobot-voice-ref.wav`).
- Use `exec timeout=900` when calling from sandbox to match the broker timeout.
- For production clips, add 0.3s trailing silence and verify the spoken content with Whisper before using it in video. The complete generate/download/pad/verify procedure is in `references/tts-workflow.md`.

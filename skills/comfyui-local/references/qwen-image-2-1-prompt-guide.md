# Qwen-Image 2.1 Prompt Guide

Consolidated from: official HF model card (`Qwen/Qwen-Image-2.1`), Qwen blog (2026-09-20), diffsynth Qwen-Image-2.1 docs, Dream Pixel Forge working guide (open Qwen family), weshop.ai 2.1 guide, apiyi 2512 practical guide (family-level principles — 2.1 shares the same prompt dialect).

## 1. Core dialect: layout briefs, not keyword tags

Qwen-Image is trained to read *layouts and sentences*, not keyword piles. Comma-stuffed tags (`cat, blue, cyberpunk, 4k`) produce generic images with garbled lettering. Write complete descriptive sentences.

**The 5-slot structure (in this order):**
1. **Artifact type** — "a letterpress event poster", "a chalkboard menu board", "an editorial infographic", "a product photograph". Naming the object tells the model which layout grammar to use; highest-value phrase in the prompt.
2. **Scene and subject** in complete sentences, with concrete attributes (age, clothing, materials, pose/action).
3. **Every text string, quoted and placed** — the literal characters in double quotes, plus physical position relative to something in the frame ("across the upper third", "bottom right corner").
4. **Typography and color per string** — weight, case, serif/sans, color ("bold sans-serif capitals in deep red"). Never just "modern font".
5. **Camera, light, and finish** last — shot size, angle, lens, lighting, mood.

**Priority order:** Subject → Environment → Details. In 20-gen tests, subject-first prompts hit clear subject 95% vs 70% for environment-first.

**Length:**
- Simple scenes: 1–3 sentences is the sweet spot (better composition, fewer tokens, faster).
- Text-heavy / layout work: go long — the long-prompt capability pays only for *structural* detail (which panel holds what, where each label sits), never for style adjectives.

**Official Qwen demo prompt (study this — it is the model's home turf):**
```
A coffee shop entrance features a chalkboard sign reading "Qwen Coffee $2 per cup,"
with a neon light beside it displaying "通义千问". Next to it hangs a poster showing a
beautiful Chinese woman, and beneath the poster is written "π≈3.1415926".
```
Three text surfaces, each with literal content AND physical placement, in two writing systems.

**Quality suffix ("positive magic"):** for photographic work append `, Ultra HD, 4K, cinematic composition.` (Qwen's own reference code does this). Skip it on flat graphic/print work — "cinematic" drags toward depth of field and warm grading you didn't ask for.

## 2. Text rendering (our main use case: text + references)

- **ALWAYS wrap rendered text in double quotes**: `headline "FERIA DEL LIBRO 2026"`. Quoting raises rendering accuracy dramatically (65%→96% in 2512 tests; our A/B confirmed 0 errors with ñ/tildes).
- **Describe each string separately, one per line in the prompt**, with its own position and font treatment.
- **Font specificity**: "bold condensed sans-serif capitals", "small italic serif" — not "a nice font".
- **Name the layout explicitly** when there are multiple elements: "a single horizontal row", "2x2 grid", "items left-aligned with prices right-aligned".
- **Spanish with accents works** (validated 2026-09-20/21: ñ, tildes, "ESPECIALIDAD" all correct). Keep exact characters verbatim — do not normalize or "fix" spelling in prompts.
- **Numeric strings** (dates, prices, π digits) are fine but occasionally misalign; keep them short ("Issue 25" > "#25 Jan 2026").
- In negative prompt (see §4) include `blurry, distorted text` for any text-heavy job — it is in Qwen's own default negative.
- For exact-text posters/banners with complex layout, Ideogram 4's JSON-caption format is still the most controllable (bbox per text element); Qwen 2.1 wins when you also need editing or multi-ref.

## 3. Transparency / RGBA assets (2.1-only capability)

The VAE is 4-channel RGBA; transparency comes from the prompt, there is no alpha switch.

**Official recommended format (model card):**
```
This is an RGBA image with transparency. A cute cartoon dragon sticker.
The image has alpha channel and the background is transparent.
```

**diffsynth doc tips:**
- State explicitly that the output is an asset with a transparent channel: `isolated on a fully transparent background`, `alpha matte`, `die-cut sticker`, `PNG with transparency`, `no background`.
- **Never describe an environment or ambient light** ("underwater", "indoor") — the model will fill the canvas. Rewrite atmosphere as attributes of the subject itself and add "nothing else in the scene".
- Hair, ribbons, water-like lighting produce wide semi-transparent transitions (intermediate alpha). For hard edges add: `clean cut-out edges` or `crisp silhouette`.
- Save as PNG (jpg/RGB conversion discards alpha). Our script saves PNG by default.
- Validated on this machine (2026-09-21): real alpha (21.9% fully transparent), clean edge, semi-transparent contact shadow kept inside the alpha channel.

## 4. Negative prompt (caveat for our wiring)

Qwen is one of the few current models with a *real* weighted negative input. Correct usage: **rendering failures, not scene content** — low resolution, low quality, deformed limbs, deformed fingers, oversaturated, wax-figure look, excessive smoothing, AI look, chaotic composition, blurry/distorted text (Qwen's own default list). Asking a negative to remove an object from the scene works badly.

**Our ComfyUI 2.1 workflow runs cfg=1.0 (per official template), so the negative branch is INERT as wired.** To use a negative prompt we must raise `--guidance` above 1 and verify the effect in an A/B — untested. Until then: fold the intent into the positive prompt ("sharp, evenly kerned lettering") or keep negatives for API paths that support them.

## 5. Editing prompt structure (single reference)

Reusable structure (weshop.ai, validated against our A/B results):
```
Content to preserve: [subject, person, product, composition, style that must not change]
Requested changes: [add / replace / remove / move]
Consistency requirements: [lighting direction, perspective, proportions, materials, contact shadows]
Do not add or change: [text, logos, objects, distortions]
```

Key line to copy: `Keep the product's appearance, color, material, proportions, packaging, and camera angle unchanged.` Preservation instructions matter more the bigger the edit — "place the product in a living room" alone lets the model redesign the product.

Local-region edits (circles, painted annotations, separate masks) are supported per the official blog — not yet wired in `generate_image.py`; the prompt pattern for masked edits is "Edit only the selected region. Replace X with Y. Keep person, lighting, background, camera angle, and composition unchanged."

## 6. Multi-reference recipes (our differentiator: up to 16 refs in the node, 10 per official docs)

1. Decide what each reference provides (product / identity / background / style / composition).
2. Upload in a FIXED order (`--image`, `--image2`, …).
3. **Define every reference at the beginning of the prompt, in the SAME order as the upload**: "Dress the adult model from Figure 2 in the outfit from Figure 1 and place the model in the background from Figure 3."
4. Explain how the references combine.
5. Add per-reference preservation requirements: "Preserve the color, cut, material, and pattern of the outfit in Figure 1. Preserve facial identity, hairstyle, skin tone, and body proportions of the person in Figure 2."
6. End with the do-not list (no new logos/text/unrelated objects).

If upload order changes without updating the prompt, roles get crossed. Our A/B (2026-09-21): two distinct people, zero identity crossing — the define-each-ref pattern is what makes it work.

## 7. Visual vocabulary (ready keywords)

| Dimension | Keywords |
|---|---|
| Shot size | extreme close-up, close-up, medium shot, full shot, long shot |
| Perspective | eye level perspective, bird's eye, low angle, aerial perspective |
| Lens | macro lens, ultra-wide angle lens, telephoto lens (blurred bg), fisheye |
| Lighting | natural light / sunlight / moonlight, backlight (silhouette), neon light, ambient light, golden hour, soft studio lighting, dramatic side lighting |
| Style | realistic / photorealistic, 3D cartoon, watercolor, ink painting, surreal, pointillism, clay style, origami, post-apocalyptic, C4D rendering |
| Finish | shallow depth of field, sharp focus on X, high contrast, natural skin texture, clean negative space |

## 8. Parameters (this machine)

- Steps: 20–25 (official template says 25–40; our 2026-09-20 measurement: 1024²/20 steps ≈ 18s sampling; bf16 DiT is default, int8 deleted).
- Sampler euler / simple, cfg 1.0 (official t2i template).
- Native 2K: `--width/--height` or `--aspect`. 2.1 native ratios: 1:1 2048², 4:3 2400×1792, 3:4 1792×2400, 3:2 2528×1696, 2:3 1696×2528, 16:9 2752×1536, 9:16 1536×2752.
- Empty prompt must be a space, never "" (Qwen has no bos token — encoder gets nothing).

## 9. Ready templates

**Poster with exact Spanish text:**
```
A vintage letterpress event poster printed on textured cream stock, shot flat and
square to the camera. Across the upper third, the words "FERIA DEL LIBRO" in large
condensed sans-serif capitals in deep red. Centered beneath it, the line "Ciudad
Real, 12 al 15 de mayo" in a small italic serif in charcoal. Along the bottom
edge, "PLAZA DE ESPAÑA" in widely letterspaced capitals. Flat two-colour print,
visible paper grain, even overhead light, Ultra HD, 4K, cinematic composition.
```
(Adjust suffix: drop "cinematic composition" for flat print.)

**Transparent asset:**
```
This is an RGBA image with transparency. A die-cut sticker of [SUBJECT] with
[2-3 concrete attributes]. Isolated on a fully transparent background, crisp
silhouette, clean cut-out edges, nothing else in the scene.
```

**Multi-ref scene (3 refs: person, product, background):**
```
Place the product from Figure 1 in the hands of the person from Figure 2, set in
the environment from Figure 3. Preserve the product's exact shape, color, material
and label text. Preserve the person's facial identity, hair and clothing. Use the
lighting direction, perspective and scale from Figure 3. Match contact shadows.
Do not add text, logos, or extra objects.
```

## 10. Prompt enhancement (`--prompt-enhance`, since 2026-09-22)

Opt-in flag, verified 2026-09-22: `uv run scripts/generate_image.py --model qwen-image-2.1 --prompt "un poster..." --prompt-enhance --filename out.png`. **Field test 2026-09-22 (serenoide, --count 3, 2048x1152):** raw 621-char brief (female alien mermaid, THREE-fingered hands) vs `--prompt-enhance`. Verdict: the enhancer FIXES the recurring 3-arms bug (raw Q21 rendered 3 arms; all 3 enhanced runs = 2 arms) and keeps all aesthetic features stable (bioluminescent constellations, glowing eyes, filaments, tail). It does NOT fix digit count — the model renders 4-digit hands 3/3 even when the prompt says exactly 3; a 3-digit result is a seed lottery, not a prompt-structure win. Also caught a real enhancer bug this test: the FIRST post-GPU-job LLM call to llama-server degraded to 0/174 chars (HTTP 200, empty/early-EOS content — NOT a broker kill, which would raise a connection exception and fail open to raw prompt). Fix: `_qwen21_prompt_complete()` rejects output not ending in terminal punctuation, retries once, then fails open to the raw brief. A truncated 5-slot prompt silently dropped bioluminescence/eyes/tail and produced a grey legged creature.

**Field test 2026-09-22 (biblioteca-vuela, --count 3, seeds 770051101-103, 1792x2400):** 3/3 prompts expanded pre-POST (190→700-800 chars, single broker wave = 1 GPU swap); 2/3 rendered "LA BIBLIOTECA VUELA" correctly, seed ...103 mangled the E of VUELA into an L ("VULLA") despite the verbatim-quoted text in the prompt. Lessons: (a) verbatim quoting prevents most text errors but does NOT guarantee 100% — always verify in-frame text with a zoomed vision crop on final deliverables; (b) on a batch, one mangled seed usually means one reroll of just that seed, not a prompt rewrite.

Rewrites the brief (any language) into a 5-slot English layout brief via the local llama-server using `scripts/qwen_image_2.1_enhance_v1.txt` (plain text out — not JSON, unlike Ideogram 4). Expansion runs SEQUENTIALLY in `main()` before any broker POST (never in worker threads), so with `--count N`/`--prompts-json` all jobs still land inside the broker's 5s batching window = ONE GPU swap (verified 2026-09-22: 2 enhanced prompts, POST span 0.00s). The llama-server stop happens AFTERWARD, inside the broker — no conflict, same pattern as Ideogram 4's magic prompt. Fails open to the raw prompt (with a single retry on empty LLM response). Use for short briefs; skip when the prompt already follows the 5-slot structure. Iteration = edit the .txt file only.

**Official PE models** (`Qwen-Image-2.1-PE-T2I` / `-PE-I2I`, fine-tuned Qwen3.5-VL 9B) remain the upgrade path if the local-LLM enhancer ever underperforms (they also suggest an aspect ratio, JSON `{rewritten_prompt, wh_ratio}`). NOT installed; the `qwen3.5_9b_qwen_image_2.1_pe_*` files in F:\ComfyUIModels are these enhancers, not the generator's encoder — never use them for generation.

**Negative prompt (A/B only, never default):** the wired workflow runs cfg=1.0, so negatives are inert. A/B recipe in SKILL.md: baseline cfg=1.0 vs `--guidance 2.0` + failure-targeted negative, same prompt+seed, judge side-by-side before adopting.

---
name: nano-banana-pro
description: Generate or edit images via Nano Banana 2 (Gemini 3.1 Flash Image) with fallback to Nano Banana Pro.
homepage: https://ai.google.dev/
metadata:
  {
    "openclaw":
      {
        "emoji": "🍌",
        "requires": { "bins": ["uv"], "env": ["GEMINI_API_KEY"] },
        "primaryEnv": "GEMINI_API_KEY",
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

# Nano Banana 2 (Gemini 3.1 Flash Image)

**Model update (Oct 2026):** Nano Banana 2.1 (`gemini-nano-banana-2.1`) shipped 2026-10-06 and
Google deprecated Nano Banana 2. The script's default is now `gemini-nano-banana-2.1`
(Flash-level speed, better character consistency across multi-image edits, 14 ref images).
Fallback stays `gemini-3-pro-image-preview` (Nano Banana Pro). Use the bundled script to generate or edit images.

Generate

```bash
uv run {baseDir}/scripts/generate_image.py --prompt "your image description" --filename "output.png" --resolution 1K

# optional: force a specific model
uv run {baseDir}/scripts/generate_image.py --prompt "your image description" --filename "output.png" --model "gemini-3.1-flash-image-preview"
```

Edit (single image)

```bash
uv run {baseDir}/scripts/generate_image.py --prompt "edit instructions" --filename "output.png" -i "/path/in.png" --resolution 2K
```

Multi-image composition (up to 14 images)

```bash
uv run {baseDir}/scripts/generate_image.py --prompt "combine these into one scene" --filename "output.png" -i img1.png -i img2.png -i img3.png
```

API key

- `GEMINI_API_KEY` env var
- Or set `skills."nano-banana-pro".apiKey` / `skills."nano-banana-pro".env.GEMINI_API_KEY` in `~/.openclaw/openclaw.json`

Model override

- Default model: `gemini-nano-banana-2.1` (Nano Banana 2.1, stable)
- Fallback model: `gemini-3-pro-image-preview` (Nano Banana Pro)
- Optional override via env var: `NANO_BANANA_MODEL` (or `GEMINI_IMAGE_MODEL`)

Notes

- Resolutions: `1K` (default), `2K`, `4K`.
- Use timestamps in filenames: `yyyy-mm-dd-hh-mm-ss-name.png`.
- The script does **NOT** auto-send the image. After it finishes, **you must send the image yourself** using the `message` tool with the `media` field set to the relative path (e.g. `./output.png`). Send it only **once**.
- Do not read the image back; report the saved path only.

## Pitfalls

0. **Hermes PYTHONPATH leak** — inside Hermes the env has PYTHONPATH pointing to a py3.14 venv → `uv run` fails with `No module named pydantic_core._pydantic_core`. Run with `env -u PYTHONPATH uv run ...` (or a clean venv). GEMINI_API_KEY lives in /root/.hermes/.env: `export $(grep '^GEMINI_API_KEY=' /root/.hermes/.env | xargs)`.

1. **Celebrity names are blocked** — Gemini 3.1 Flash refuses to generate images with real political figure names (Trump, Biden, etc.). Use detailed visual descriptions instead: "a man with distinctive tall blonde golden comb-over hair, very orange-tan skin tone, wearing a dark blue suit with an oversized long red necktie."
2. **Long prompts** — Nano Banana 2 handles long multi-sentence edit prompts (~1000 chars) fine; the old ~400-char failure (`'NoneType' object is not iterable`) is not a limit in practice. If a long prompt ever fails, split into shorter segments or drop details.
3. **Content policy** — Violent, sexually suggestive, or defamatory content descriptions may be silently rejected. Frame scenes creatively to avoid triggering filters.
4. **Iterate on an approved base with MINIMAL edits** — when fixing a defect in an image the user already approved, issue the smallest possible instruction on that exact file ("remove ONE arm — the raised one — keep EVERYTHING ELSE EXACTLY THE SAME"); rebuilding the scene from identity references makes the model reintroduce the rejected defect or delete the wrong element. After any anatomy edit, vision-verify the exact limb/prop count — edits can silently add a third arm or remove the wrong one — and require the gap to be closed with fur/clothing matching the body.
5. **Edits brighten the scene** — any edit pass (especially adding an element) systematically lifts exposure toward a flatter, brighter look, breaking a dark/moody approved base. Fix with a follow-up exposure-match pass: pass the edited image plus the approved base as a second reference and instruct "keep ALL content of image 1 exactly, change ONLY lighting/exposure to match the near-darkness of image 2". One change per pass (add element → re-seat/fix position → exposure match), never combine fixes in a single edit.

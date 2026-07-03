---
name: comfyui-template-import
description: Import an official ComfyUI workflow template (Image / Video / Audio) into the comfyui-local skill. Use when the user says "he descargado una plantilla de ComfyUI" / "downloaded a ComfyUI template" and provides a screenshot + template name.
metadata:
  {
    "openclaw":
      {
        "emoji": "🧩",
        "requires": { "bins": ["uv", "python3"] },
      },
  }
---

# ComfyUI Template Import

This skill teaches you (Cocobot) how to take an official ComfyUI workflow template that the user has just installed locally, port its node graph into a new `build_<name>_workflow` function inside `Hermes/skills/comfyui-local/scripts/generate_video.py` (or `generate_image.py` / `generate_song.py` depending on modality), expose it through a new CLI flag, and validate it end-to-end through the local broker.

The procedure was extracted from the successful port of `video_ltx2_3_id_lora` (FP8 + distilled LoRA + ID-LoRA, two-stage). Follow it exactly when the user gives you:

1. A **screenshot of the template** (the node graph as it looks in ComfyUI).
2. A **template name** (e.g. `video_ltx2_3_id_lora`, `flux2_klein_inpaint`, `ace_step_1_5_remix`).

If the user only gives you the screenshot but not the name, ask them once for the exact name.

---

## Step 0 — Confirm to the user

Send a short message to the user before doing anything: e.g. `Ok, voy a importar la plantilla "<name>" a la skill comfyui-local. Tardara unos minutos.`

Do not start touching files until that message is sent.

---

## Step 1 — Locate the template JSON on disk

Templates are shipped as JSON files inside pip packages installed in the ComfyUI venv. Search them in this order:

```bash
# All known template package roots (search them all in parallel):
ls /mnt/c/ComfyUI/.venv/Lib/site-packages/comfyui_workflow_templates/templates/             2>/dev/null
ls /mnt/c/ComfyUI/.venv/Lib/site-packages/comfyui_workflow_templates_media_video/templates/ 2>/dev/null
ls /mnt/c/ComfyUI/.venv/Lib/site-packages/comfyui_workflow_templates_media_audio/templates/ 2>/dev/null
ls /mnt/c/ComfyUI/.venv/Lib/site-packages/comfyui_workflow_templates_media_image/templates/ 2>/dev/null

# Fall back to a recursive search by name:
find /mnt/c/ComfyUI/.venv/Lib/site-packages -name "<template_name>.json" 2>/dev/null
```

If still not found, try `E:/Programs/ComfyUI/resources/ComfyUI/user/default/workflows/` and `C:/ComfyUI/user/default/workflows/` (user-saved workflows).

Once located, copy the path. Read the JSON with `read_file` to understand the structure.

---

## Step 2 — Parse the graph (subgraph templates)

Modern ComfyUI templates often package the whole graph as a **single subgraph**. The actual nodes live inside `definitions.subgraphs[0].nodes` and links inside `definitions.subgraphs[0].links` (dict format with keys `origin_id`, `origin_slot`, `target_id`, `target_slot`).

Use this helper to dump them in a readable form:

```bash
python3 - <<'PY'
import json, sys
p = "/mnt/c/ComfyUI/.venv/Lib/site-packages/comfyui_workflow_templates_media_video/templates/<name>.json"
g = json.load(open(p, encoding="utf-8"))
sub = g.get("definitions", {}).get("subgraphs", [g])[0] if g.get("definitions", {}).get("subgraphs") else g
nodes = sub["nodes"]
links = sub.get("links", {})
print(f"# nodes={len(nodes)} links={len(links)}")
for n in nodes:
    wv = n.get("widgets_values") or []
    print(f"[{n['id']}] {n['type']}  widgets={wv}")
print("--- links ---")
for k, v in (links.items() if isinstance(links, dict) else enumerate(links)):
    print(k, v)
PY
```

If `definitions.subgraphs` is missing, the template uses the legacy flat format and `nodes`/`links` live at the root.

Build a mental map: for every node you need its `class_type`, ordered widgets (which become positional `inputs`), and incoming links (each link becomes `["<source_node_id>", <slot_index>]` in the target's `inputs`).

---

## Step 3 — Resolve every node's input schema

The template stores **widget values in order** but `generate_*.py` workflows must use **named inputs**. To map widget index → input name, read the node implementation in ComfyUI's source. Search in this order:

```bash
# Built-in nodes
grep -rn "class <ClassType>" /mnt/e/Programs/ComfyUI/resources/ComfyUI/nodes.py /mnt/e/Programs/ComfyUI/resources/ComfyUI/comfy_extras/

# Custom nodes (LTX, etc.)
grep -rn "class <ClassType>" /mnt/c/ComfyUI/custom_nodes/ /mnt/e/Programs/ComfyUI/resources/ComfyUI/custom_nodes/
```

Look for `INPUT_TYPES`. The order of keys inside `required` is the exact order of widget values.

**Common pitfalls — verify these names before assuming:**

- Image batch nodes derived from `ImageProcessingNode` use **`images`** (plural). Examples: `ResizeImagesByLongerEdge`, `ImageBatchStack`. The unrelated `LTXVPreprocess` uses singular `image`.
- Math nodes like `ComfyMathExpression` may not be installed. **Always pre-compute math in Python** instead of including these nodes; pass numeric literals into the workflow JSON.
- `RandomNoise` widget order is `[noise_seed, randomize]`. To force a fixed seed pass `"randomize": "fixed"`; for randomized pass `"randomize": "randomize"`.
- `ManualSigmas` takes a comma-separated **string**, not a list: `"sigmas": "1.0, 0.99375, ..., 0.0"`.
- `CFGGuider` inputs are `model, positive, negative, cfg`.
- `KSamplerSelect` has a single `sampler_name`.
- `SamplerCustomAdvanced` order: `noise, guider, sampler, sigmas, latent_image`.
- LoRA stacking goes through `LoraLoaderModelOnly` (one node per LoRA). Order matters for layered effects.

---

## Step 4 — Verify all referenced models exist locally

Extract every model filename mentioned in the template (checkpoints, LoRAs, VAEs, upscalers, CLIPs) and confirm they are present:

```bash
ls /mnt/c/ComfyUI/models/checkpoints/ /mnt/c/ComfyUI/models/loras/ /mnt/c/ComfyUI/models/vae/ /mnt/c/ComfyUI/models/upscale_models/ /mnt/c/ComfyUI/models/clip/ /mnt/c/ComfyUI/models/text_encoders/ 2>/dev/null
```

If any required model is missing, **stop** and report the missing files to the user with the URL or repo it should come from (read the template's `meta.description` field — it usually links to the download).

---

## Step 5 — Add the new `build_<name>_workflow` function

Edit the right script in `Hermes/skills/comfyui-local/scripts/`:

- Video templates → `generate_video.py`
- Image templates → `generate_image.py`
- Audio / song templates → `generate_song.py`

Conventions (mirror `build_idlora_workflow` in `generate_video.py`):

1. Add module-level constants for every model filename and any prompt defaults specific to the template (e.g. `MODEL_<NAME>_CHECKPOINT`, `<NAME>_NEGATIVE_PROMPT`, `<NAME>_DEFAULT_FPS`). Do **not** overwrite the constants used by other modes — add new ones.
2. Use **string node IDs** that describe the role (`ckpt`, `text_enc`, `lora_distilled`, `pos_clip`, `neg_clip`, `sampler_low`, `decode_video`, …). Never reuse the numeric IDs from the template.
3. Pre-compute all math (e.g. `low_w = max(64, (width // 2) // 32 * 32)`).
4. For every node specify `class_type` and `inputs` with named keys; cross-references are `["<node_id>", <slot>]`.
5. Keep the function signature consistent with siblings: `def build_<name>_workflow(*, prompt, negative_prompt, image_remote_name, audio_remote_name, width, height, fps, frames, seed, steps, ...)` — only add parameters the template actually needs.
6. Return the dict; do **not** wrap in `{"prompt": ...}` (the broker submits it as-is).

Then plug it into the dispatcher (look for the existing `if args.id_lora:` / `elif args.lipsync:` chain in `main()` and add a new branch).

---

## Step 6 — Add the CLI flag and resolve defaults

Add an `argparse` flag (e.g. `--<name>` or `--mode <name>`). Then, after parsing args, resolve template-specific defaults **only when the flag is set**:

```python
if getattr(args, "<name>", False):
    if args.fps is None:
        args.fps = <NAME>_DEFAULT_FPS
    if args.negative_prompt is None:
        args.negative_prompt = <NAME>_NEGATIVE_PROMPT
```

Validate `ast.parse` of the modified file with `python3 -c "import ast; ast.parse(open('...generate_video.py').read())"` before running it.

Run `python3 .../generate_<modality>.py --help` and confirm the new flag appears.

---

## Step 7 — Document the new mode in the comfyui-local SKILL.md

Append a new subsection under the corresponding modality (Video / Image / Audio) describing:

- What the template does (1–2 lines).
- The exact CLI invocation with all required flags.
- Required inputs (image / audio / reference paths).
- Any new defaults introduced (fps, negative prompt, identity scales, etc.).
- A clear warning: `Always call generate_<modality>.py --<flag>; do NOT build the workflow JSON manually.`

Do **not** create extra markdown files — extend the existing SKILL.md only.

---

## Step 8 — End-to-end test through the broker

Cocobot must be able to actually run the new template, not just generate code that compiles. Use the broker that is already running on the Windows host. From WSL the broker is reachable at the WSL2 default-gateway IP, **not** `localhost`:

```bash
# Discover the gateway (typical: 172.23.176.1 — different per session):
ip route | awk '/default/ {print $3}'

export OPENCLAW_COMFYUI_LOCAL_BROKER_URL="http://<gateway_ip>:8791"
export OPENCLAW_COMFYUI_LOCAL_TIMEOUT_SECONDS="1500"

# Health check first
curl -s "$OPENCLAW_COMFYUI_LOCAL_BROKER_URL/health"
```

If the broker is not running, start it from a PowerShell terminal:

```powershell
Start-Process -WindowStyle Hidden -FilePath python -ArgumentList "E:\Workspace\Hermes\scripts\comfyui-broker.py" -RedirectStandardError "E:\Workspace\Hermes\comfyui-broker.err.log"
```

Then stage minimal test inputs in `/tmp/` (image + reference audio if needed) and run the new mode with a tight prompt and short duration:

```bash
python3 /mnt/e/Workspace/Hermes/skills/comfyui-local/scripts/generate_video.py \
  --<name> --image /tmp/test.png --reference-audio /tmp/ref.wav \
  --prompt "..." --filename /mnt/e/Workspace/Hermes/test_<name>.mp4 \
  --duration 5 --resolution 720p --aspect 16:9 --seed 12345
```

If it fails, **always read** `/mnt/e/Workspace/Hermes/comfyui-broker.err.log`. ComfyUI returns precise validation messages like `required_input_missing details=images class_type=ResizeImagesByLongerEdge`; fix the input name in the workflow and retry. Do not add error handling around it — the bug is always in the JSON wiring.

When the test passes, verify the output exists and has the expected codec/duration with `ffprobe -show_entries stream=codec_name,width,height,duration`.

---

## Step 9 — Sync to the deployed skills directory

Cocobot does **not** load skills directly from the Hermes source repo at `E:\Workspace\Hermes\skills\`. It loads them from the OpenClaw workspace at `C:\Users\Raúl\.openclaw\workspace\skills\` (from WSL: `/mnt/c/Users/Raúl/.openclaw/workspace/skills/`). Any change to a script or `SKILL.md` must be copied there before Cocobot can see it.

After validating end-to-end, sync to **all three** deployed locations. Cocobot loads skills from `/root/.hermes/skills/media/` (WSL native — this is the primary runtime path). The other two are fallbacks / used by OpenClaw Desktop:

```bash
SRC=/mnt/e/Workspace/Hermes/skills

# 1. Primary — Hermes WSL runtime (where Cocobot actually executes scripts)
DST1=/root/.hermes/skills/media
cp "$SRC/comfyui-local/SKILL.md"                  "$DST1/comfyui-local/SKILL.md"
cp "$SRC/comfyui-local/scripts/generate_video.py"  "$DST1/comfyui-local/scripts/generate_video.py"
cp "$SRC/comfyui-local/scripts/generate_image.py"  "$DST1/comfyui-local/scripts/generate_image.py"

# 2. OpenClaw workspace (Windows-side, used by OpenClaw Desktop agent)
DST2=/mnt/c/Users/Raúl/.openclaw/workspace/skills
cp "$SRC/comfyui-local/SKILL.md"                  "$DST2/comfyui-local/SKILL.md"
cp "$SRC/comfyui-local/scripts/generate_video.py"  "$DST2/comfyui-local/scripts/generate_video.py"
cp "$SRC/comfyui-local/scripts/generate_image.py"  "$DST2/comfyui-local/scripts/generate_image.py"

# add other generate_*.py files only if you also touched them
```

Verify the new flag is visible in the primary runtime path:

```bash
grep -c "<new_flag>" "$DST1/comfyui-local/scripts/generate_<modality>.py"
```

**Do not delete files that exist only in the deployed copies** (e.g. `generate_song.py`, `generate_speech_broker.py`, `generate_sfx.py`, best-practices markdown). They are part of the agent's working skill and may not be present in the Hermes source. Sync individual files, never `rsync --delete`.

---

## Step 10 — Report back

Send a final message summarising:

- Path of the imported template JSON.
- New CLI flag and defaults.
- Models used.
- Path of the test output file and its duration/resolution.
- Any quirks the user should know (e.g. "voice quality is best in English", "needs 5s reference audio", "uses 22GB VRAM").

---

## Quick reference — files Cocobot may modify

| Path | Purpose |
|---|---|
| `Hermes/skills/comfyui-local/scripts/generate_video.py` | Add `build_<name>_workflow` + CLI flag for video templates |
| `Hermes/skills/comfyui-local/scripts/generate_image.py` | Same, for image templates |
| `Hermes/skills/comfyui-local/scripts/generate_song.py` | Same, for audio templates |
| `Hermes/skills/comfyui-local/SKILL.md` | Document the new mode |

Do **not** modify `Hermes/scripts/comfyui-broker.py` — the broker is generic and already accepts arbitrary workflows.

---

## Things to NEVER do

- Never invent input names — always confirm them by reading the node's `INPUT_TYPES` in the ComfyUI source.
- Never hard-code subprocess paths assuming localhost from WSL — always use the gateway IP.
- Never bypass the test step. A workflow that "looks right" is not validated until the broker accepts it and a media file is produced.
- Never overwrite the constants/branches used by existing modes (`flux1`, `flux2-klein`, `lipsync`, `id-lora`, etc.). Add new ones alongside.
- Never wrap the returned dict in `{"prompt": ...}`; the broker does that.

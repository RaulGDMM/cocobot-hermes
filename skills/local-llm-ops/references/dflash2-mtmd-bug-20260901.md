# DFlash2 + multimodal (mtmd) bug — status 2026-09-01

Session question: "¿Se arregló el bug de DFlash2 con imágenes? ¿Actualizar llama.cpp y cambiar de perfil?" Answer: **no — keep the MTP profile.** Everything below verified via GitHub API on 2026-09-01 (latest release b10740).

## Verified status
- Issue [ggml-org/llama.cpp#27408](https://github.com/ggml-org/llama.cpp/issues/27408): **OPEN**, no assignee/labels, created 2026-08-19. Title: "spec: mtmd image chunks leave positional holes in the draft KV cache -> llama_decode(ctx_dft) rc=-1 -> HTTP 500 with draft-dflash (CUDA); zero-fill patch crash-eliminating but no speculative benefit on images".
- PR [#27914](https://github.com/ggml-org/llama.cpp/pulls/27914) (fishlikeX, complete fix, 3 changes in `common/speculative.cpp`): **closed UNMERGED** 2026-08-28. Maintainer ngxson's only comment: "already fixed, reconvert your GGUF" — wrong. 2026-08-30 HermiG confirmed the bug persists on a recent build (0.0 dflash2 draft acceptance with images in context) and that the fork patch fixes it, including restoring speculation on image requests.
- Commit log of `common/speculative.cpp` since the DFlash2 merge (b10f9ca, 2026-08-27): `ca3d5a3` DSpark (#27804), `662a0b0` DFlash encoder fusion into KV injection (#27310, perf refactor only). **Nothing touches the mtmd positional hole.**
- Root cause (measured by fishlikeX, not inferred): every image row arrives at the SAME 1-D position (spatial structure lives in the target's M-RoPE); 752 rows span only ~47 positions, so text resumes at image_pos+47, not +n_rows. The 1-D draft KV cache cannot represent either shape → hole → non-consecutive position → decode rc=-1.
- Platform symptom variants: CUDA (RTX 3090 Ti): ~500 s stall then HTTP 500. Vulkan (RDNA4 gfx1201): fails fast in ~3 s with "non-consecutive token position ... failed to process mtmd chunk". Text-only unaffected on both.

## Fix options
| Option | Crash on images | Speculation on images | Base | Fit for sm_120 (5090) |
|---|---|---|---|---|
| Upstream b10658…b10740 | Yes | No | current master | yes (but broken) |
| `z-lab/llama.cpp-fork#1` (zero-fill, +74/−5) | No | **No** (acceptance 0; ~35 tok/s ≈ no-spec baseline) | unclear maintenance | maybe |
| `fishlikeX/sm70-attn` (3-point fix, verified) | No | Yes | **Volta (sm_70)-oriented** | no — do not base a Blackwell build on it |

## Consequences for this setup (Qwen3.8-27B, RTX 5090, 140K ctx)
- DFlash2 > MTP on text-only: 2.26× real coding (153.9 tok/s), 3.55× at 36k ctx vs MTP 2.57×; n_max optimal 5 (hard cap 7); +2720 MiB VRAM for the draft (incoai DFlash2 GGUF Q4_K_M).
- With images: DFlash2 degrades to baseline-or-worse (our earlier measurement on the b10658-era build: acceptance ~1.8%, 27–43 tok/s after images). The MTP profile is NOT affected by this bug.
- Decision: keep `qwen38_27b_unsloth_q6k_mtp` as default. Revisit only when (a) an upstream PR referencing #27408 merges into a tagged release, or (b) fishlikeX's 3-point patch is re-ported onto current master and validated on sm_120 with a real image request (check: image request → 200 OK, `draft acceptance` > 0, correct visual answer).

## Monitor recipe (cheap, no LLM)
```bash
curl -s "https://api.github.com/repos/ggml-org/llama.cpp/issues/27408" | python3 -c "import json,sys; i=json.load(sys.stdin); print(i['state'], i.get('comments'), i.get('closed_at'))"
curl -s "https://api.github.com/search/issues?q=repo:ggml-org/llama.cpp+27408" | python3 -c "import json,sys; [print(i['number'], i['state'], i['title'][:80]) for i in json.load(sys.stdin).get('items',[])]"
```
Deterministic output for a cron `monitor` job — it changes when the issue closes or a PR references it.

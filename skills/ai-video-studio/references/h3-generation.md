# H3 generation — prompt structure, field-verified pitfalls, recipes

The defect-aware prompting + iteration layer for MiniMax H3 (`--engine minimax-h3`). For the full API (ref2va modes, audio flags, official prompting guide) load the `comfyui-local` skill → `references/minimax-h3-guide.md`; this file is the field-tested gotchas the generic docs don't cover.

## Base command

```bash
uv run /root/.hermes/skills/media/comfyui-local/scripts/generate_video.py --engine minimax-h3 \
  --prompt "$(cat prompt.txt)" --negative-prompt "..." \
  --reference-image main.png --reference-image identity.png \
  --duration 10 --resolution 720p --aspect 16:9 --filename "videos/shot_v1" --seed 42
```

720p (1344×768) + `--aspect 16:9` for local generation; `21:9` is invalid for H3. Assign every `--reference-image` an explicit job; never let two refs have contradictory jobs.

## Ref2VA prompt structure (every H3 clip)

```
subject_definitions:   <- each subject + which <Picture N> it comes from
retention_analysis:    <- per <Picture N>: fully_preserved / partially_preserved / weak_reference
detailed_description:  <- "Single continuous shot, no camera cuts"; chronological; camera type + AMPLITUDE + SPEED; the motion
overall_soundscape:    <- non-dialog clips: "ABSOLUTELY NO SPEECH, NO VOCALS, NO MUSIC"
non_diegetic_music: no music
```

## Recipe A — fixed in-scene screen (camera moves, screen content must NOT change)

Without this, H3 reverts the screen to the anchor image's original content toward the end of the camera move.

```
subject_definitions:
- <screen>: the <display> shows <content from Picture 1> ...
retention_analysis:
- Picture 2 (scene/anchor): FULLY PRESERVED for EVERYTHING. The ONLY change: its <display>
  now shows the <Picture 1> content. Picture 1 is ONLY the content to display; it is NOT the scene.
detailed_description:
  ... THE SCREEN shows the <Picture 1> content in EVERY single frame, INCLUDING THE FINAL
  FRAME — it never changes, morphs or switches. There is NO <unwanted content> on the screen
  at any point. <the moving element inside the screen at "natural brisk speed, ABSOLUTELY
  NO slow motion">.
overall_soundscape: <ambient only, no speech/music>
non_diegetic_music: no music
```
Negative MUST include: `<unwanted> on screen, screen content changing, morphing, text watermark on screen`.

If the screen must show TEXT (banner, news ticker): do NOT rely on H3 to render+hold it in ref-only mode — the banner flickers frame to frame. Pre-bake the text into the anchor with Nano Banana 2 (one edit: "add a news lower-third bar with '<TEXT>' in white caps on a red block at the bottom of the screen") and animate that single image; model-added flourishes (an invented "LIVE" block) are usually a feature, not a bug.

## Recipe B — crowd / audience

- Picture 1 = approved crowd image, FULLY PRESERVED. Hands/phones: "arms locked in the same position, phones stay up, no one lowers their phone, statue-still".
- A crowd action (clasp hands, raise arms) must be a STATIC POSTURE already in the anchor image, not an action H3 invents.
- Hand-in-hand chains: NB2 gets only "islands" of clasped hands, and H3 re-animates/roboticizes the arms no matter how hard "frozen/statue" is stated. Two validated fixes: (1) anchor the gesture in the NB2 image — "EVERY person, INCLUDING THE CHILDREN, holds at least one hand; an unbroken chain; natural chest/shoulder height, NOT raised high" — iterate NB2 passes until the chain reads, then hand the frozen image to H3; (2) freeze with Recipe C keyframes so the arms literally cannot move.
- Preference: organic per-person motion beats a full statue-freeze unless asked — never a synchronized/robotic wave.
- DAYTIME crowds in front of dense backgrounds get dragged by the camera parallax (a rigid unison left→right "dance") even with a freeze block. Fix (all three parts): prompt "THE CROWD IS FROZEN PIXEL-FOR-PIXEL IN THE FRAME ... does NOT slide, shift, translate, drift or parallax across the frame, not even a little"; negative `crowd sliding across frame, crowd drifting, parallax crowd, crowd bouncing, people swaying, synchronized crowd motion`; declare anything that must look alive the ONLY other living thing allowed to move, with explicit minimal micro-motion (ear twitch, tail flick; "its body, legs and position NEVER change"). Verify with a numeric crowd-band diff vs frame 0 (people region, mean abs diff per frame) + vision on a 3-panel strip.

## Recipe C — first/last keyframe freeze (`--image` + `--end-image`)

- **Scene keyframes must be IDENTITY-ANCHORED, never text-to-image from scratch.** A keyframe generated from text alone (or edited repeatedly from such a draft) silently drifts the character's face (round plush muzzle, generic eyes, wrong fur/tail color) even while lighting/framing get fixed — the user always catches the identity drift before you do. Build scene keyframes as a Nano-Banana EDIT with TWO inputs: canonical character sheet as identity source + the scene/lighting draft as composition target ("Image 1 is the canonical character — copy her IDENTITY EXACTLY; Image 2 is the target scene; place Image 1's character into Image 2 with its framing/pose"). QA the keyframe against the character sheet (muzzle, eye shape, fur sheen, tail color, outfit) BEFORE spending a GPU clip on it — a drifted keyframe dooms the clip regardless of identity refs in the video prompt. NB edits can also RELOCATE edge props (mic stand pushed to the border): re-verify edge geography after each edit; if a deterministic ffmpeg crop cuts a prop out, shift the crop window instead of re-editing.

The reliable way to lock composition (pose, camera, screen) while animating the in-between. Reference inputs CANNOT be combined with first/last conditioning — this mode takes keyframes only.

1. `first.png` = the approved opening frame (NB2).
2. `last.png` = a second NB2 image identical except the ONE thing that changes. Everything that must NOT move stays pixel-identical between the two. NB2 does not reliably apply a requested camera shift between two images — treat `last.png` as "same composition, different in-screen content".
3. Run with `--image first.png --end-image last.png`, NO `--reference-image` at all.
4. Result: both endpoints pin the frozen elements, the screen animates between states, camera ~static.

If the keyframes are identical, H3 gives no pan — add a controlled slide in post (sliding crop window, screen centered):

```bash
ffmpeg -i in.mp4 -vf "crop=1209:768:'135*(1-n/123)':0,fps=24" -an \
  -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p out_pan.mp4
```

(1209 = 1280−135 pan; 123 = frame count; 135 = total px of drift. Tune to taste.) This gives a perfectly smooth, direction-exact pan the model can't do on its own.

## Distilled field pitfalls (A/B-tested across ~40-clip series)

- **End-of-clip identity morph from variant refs** — main individual's ref only + "must remain the same individual throughout" + negative `morphing, identity change, transformation` (see SKILL.md).
- **Bioluminescence / eye state** — generic "pulsing" produced an on/off EYE flicker; the over-fix ("always lit") produced permanently glowing eyes when the ref had dark ones. Inspect the ref with vision and describe the actual state: "small natural DARK eyes, exactly as in the reference — NOT glowing, NOT illuminated." Keep biolum on the body, not tied to the eyes; drop "pulsing" near eyes. Negative: `glowing eyes, bright white eyes, eyes lighting up, blinking`.
- **Slow-motion drift** — H3 trends dreamy even when told "natural". State speed for BOTH camera and action: "constant speed — not fast, not slow", "ABSOLUTELY NO slow motion, NO dreamy slowed drift". Negative: `slow motion, dreamy motion`.
- **`--image` + `--reference-image` cannot combine** (broker rejects). Fallback when framing isn't critical: pass the still as the FIRST `--reference-image` (FULLY PRESERVED) — but that does NOT anchor the opening framing; framing-critical → `--image` alone (i2v).
- **r2v does NOT anchor the opening framing** — the model invents camera choreography (verified case: a WIDE ref + "slow left drift" came out as a close-up dolliing OUT to the wide framing; two prompt rewrites with the same seed failed identically; measured objectively: screen-core pixel width shrank ~60% across the clip = dolly-out, not a lateral track). Framing-critical → i2v. Reserve the r2v still-first-ref pattern for shots where framing is not critical or the motion is toward/away from the ref subject.
- **r2v reference image OUTRANKS the text prompt on gesture presence** — if the named gesture (paw on shoulder, hand on waist...) is not actually present in the supplied reference image, the clip will not have it no matter how explicit the prompt and negatives are (pvsg: two rolls failed twice demanding the cat's paw on the husky's shoulder while the ref frame at t=237.0 had her paws down; the third roll passed the moment the ref frame from t=233.0 contained the gesture). Before any GPU roll, extract the intended ref frame and verify the gesture with vision; when the gesture lives at another moment of the same take, sweep the take with 2-4 fps contact grids to find it, and crop the frame to the desired framing (the ref also sets composition).
- **Two-person r2v shots collapse into a group "selfive"/selfie pose** — expect pose-freeze + GoPro-fisheye framing with 2+ humans in one r2v shot (requested side-by-side tracking walk came out as arms-linked posing); fine details of the SECONDARY character are the first lost (stubble texture vs salient glasses). Counter: "NOT posing, NOT facing the camera, NOT standing still — a visible stride, legs alternating mid-step, bodies in profile" + name the tracking camera explicitly; if the motion still doesn't happen, plan two solo shots and composite.
- **Front-camera selfie refs ship with MIRRORED brand text** (in the saved file, not just the preview); H3 reproduces the mirrored logo and can extend the mirroring to scene text. If readable brand text matters, flip the image horizontally before passing it.
- **Secondary characters default to the rest position** — a character who must ENTER the scene mid-clip gets placed already waiting in his natural resting position (r2v composes a plausible static cast; it does not stage entries you didn't ask for). Give every character a start position and a timed entry in `detailed_description` ("at second X he appears in the doorway and steps out behind him — he was INSIDE the cabin until that moment") + negative against the rest position. Give the entry a PHYSICALLY PLAUSIBLE PATH along the scene geography too ("enters walking along the STAGE from the left edge, staying at the same depth as <character>, never crossing between the camera and the stage") — without it the model walks the entrant through impossible space (over the crowd, in front of camera).
- **A character on a platform renders as standing IN FRONT of it** — image models happily draw a performer on a stage so she reads as on the audience side of the stage edge. Pin the platform geography in the keyframe prompt: boots planted ON the platform's boards, the spotlight pool on the floor at her feet, low audience-level camera tilted slightly UP, the platform edge and a floor monitor visible in the lower foreground, background instruments clearly farther back behind her, and her face the brightest thing in frame (not a silhouette in the cone's edge). Vision-verify with the explicit question "is she ON the platform or in front of it?" before sending for approval.
- **Hand-pushed heavy vehicles default to a static "posing with it" pose** — H3 treats a hand-pushed 70-ton vehicle as physically implausible and snaps it to "parked" no matter how hard the push is scripted. Rolling reads as plausible ONLY when the whole vehicle stays in frame AND the camera does NOT follow the pushers (far-back wide shot, nose→tail both visible; background objects sliding past prove motion — camera-tracking shots kill the roll because tracking implies the camera, not the plane, is moving). "Accelerate / pick up speed" from a hand push does not happen (degrades to static pose again). Anchor the initial backward drift explicitly ("completely still, does NOT roll or drift backward during the first N seconds") + negative `plane moving backward, plane rolling back, plane drifting backward`. Push-from-BEHIND: "from BEHIND the plane, hands on the REAR fuselage" per beat (front pushes default to nose-side framing). When physical implausibility is the ceiling, sell the ACTION beats instead of fighting for the physics (the approved deliverable kept a static plane with sprint → tail push → door-leap beats).
- **Character refs drag their own room into the shot** (hard cut to the ref's location the moment that character appears) — three-part fix in SKILL.md; verify with a strip: every indoor frame must share the SAME table/wall fixtures.
- **One-off character gags don't need a character ref** — i2v with the real scene photo as frame 0 (padded to the aspect, e.g. 9:16 768×1344 from a 960×1280 source) + a rich identity description (skin, hair, figure, smile) + an explicitly timed entry + anti-morph and anti-speech negatives works first try. r2v identity refs are only needed when a specific face matters or across multiple shots.
- **Sustained intensity decays** — a gale/expression described at EVERY timestamp still settles to neutral (still hair/clothes, calm face) in the final 2–3 s of 10–15 s clips. Treat the tail as dead by default: verify the LAST frame; cut the shot shorter (8–10 s), plan an edit that keeps the energetic middle, or end before the decay. Do not promise "constant/continuous" force.
- **H3 generates usable SFX when prompted** — "Add sound effects: applause, cheers, clapping. No music, only natural sound effects" yields mixable audio.
- **Recurring entity drift** — H3 changes a recurring entity's appearance mid-video (e.g. Jupiter); re-emphasize its defining features ("gas giant, swirling atmospheric bands, deep space, no rings") in every prompt.
- **Underwater objects default to the ocean floor** — keep them floating: "suspended and floating freely in the water column, not resting on any surface or floor. There is no ground beneath it. The dark ocean surrounds it on all sides."
- **White/studio background at the end** — H3 tends to transition to white in the last seconds: "The entire scene remains dark and underwater throughout - no white backgrounds, no studio lighting, no surface or floor visible beneath [subject]."
- **Reveal shots (pre-compose the FINAL frame)** — for a reveal (fireworks spelling a phrase, drone silhouettes forming, an approach): pre-compose the final frame with Nano Banana, pass it as a single r2v ref, prompt the motion chronologically with the physics (climb → EXPLODES → flash → expanding cloud → sparks cool, separate, settle), keep one subject FROZEN PIXEL-FOR-PIXEL, and accept the model's slow push-in when the read still works. For spelled-phrase fireworks, r2v with BOTH keyframes as refs (neither anchored) beats i2v first+last — the latter reads as a crossfade of the letters in mid-frames; negative `text fading in, letters materializing, letters appearing from nothing`. Pre-compose both keyframes (frame 0: ascending trails with EMPTY upper sky; final: phrase in the top quarter, subject not touching the letters). Verify formation with per-color-region pixel counts per frame: each region stays ~0 px until the final ~1.5–2 s and then ramps >3k px — formation earlier than that is a fade-in fake.
- **NB character preservation: edit the character ref as the single BASE image** (`-i`) and prompt "edit ONLY background + pose; keep the character pixel-identical" — describing the character in a multi-ref NB prompt makes NB reinterpret it (humanized head, wrong fin, feminine torso). Add a dedicated BACK ref when orientation matters (back of head = plain dome, no visor/eyes/screen).
- **Multi-frame comparison grids: build in PIL, not ffmpeg filter_complex** (a 6-input ffmpeg grid aborted with `malloc(): invalid size`).

## Real public figures — stable portrait recipe (standing rule)

Whenever the script names a real person, the clip must show a RECOGNIZABLE caricature, the SAME person across all generations. Never let the model invent a generic "president" — it defaults to an unrecognizable suited man.

1. Find a recognizable source crop (an old frame/still of the person from a previous project; crop the face region with ffmpeg).
2. Generate a FIXED portrait bust with Qwen-Image 2.1: `--image <face crop> --image2 <project style ref>`, prompt = "Portrait bust of a caricature of <NAME>, <hair/face/costume details>, rendered in the exact same visual style as the second reference... Plain dark background. No text." Save to `refs/<name>_retrato.png` with a fixed seed. Verify recognizability + style match with vision BEFORE any scene work.
3. In every scene image that includes the person: Qwen-Image 2.1 with `--image <scene ref> --image2 refs/<name>_retrato.png`, the prompt assigns the ref its identity job ("Figure 2 shows <NAME> — USE his exact identity... his exact hair, suit, tie") + "He is a silent background figure" (or scripted speech) when he must not talk.
4. In H3 r2v: pass the SAME portrait as a `--reference-image` with an explicit job line ("Picture N: identity reference for <NAME> — preserve his exact blond hair, frown, dark suit and red tie in EVERY frame") + negative `wrong hair, inconsistent face, generic president`.

## Qwen-Image 2.1 — duplicate-character fix

Passing a character identity ref (`--image2`) makes Qwen-Image 2.1 draw the character TWICE (foreground + background). State the count explicitly in the scene description ("EXACTLY ONE sleek jet-black cat in the whole image: it sits in the background... Do not draw any other cat") and repeat it in the style block; regenerate with the next seed until vision confirms a single instance.

## Triage for "new H3" claims (tutorials, videos, news)

1. Extract the concrete claims (which node/model, benchmarked on which hardware).
2. Separate official (MiniMaxAI HF org, platform.minimax.io) from community forks; benchmarks from other hardware don't count against this machine's validated A/Bs.
3. Check the local baseline first: PDD 8-step + SageAttention already own speed on the 5090, and PDD accepts 4/6/8 steps via `--steps` — community "turbo 4-step" or sparse-attention gains are usually marginal (learned sparse predictors that stack ON TOP of Sage — Veda-class — are the exception; see Status of record in video-model-ecosystem.md).
4. Estimate the real e2e gain before installing: `speedup = 1/((1−f) + a·f)`, where `a` = attention-ratio from the candidate's own per-step measurements (attention time with/without it) and `f` = attention's share of a step in the baseline. `f` GROWS with clip length (attention ~tokens², MLP ~tokens linear), so short-clip vendor headlines understate long clips and vice versa — quote the measured row matching our clip length, never the vendor max. Anchor: the Veda repo's docs/hardware.md logs per-step breakdowns per GPU (RTX PRO 6000 96 GB ≈ bandwidth proxy for the 5090; 12 GB cards pay extra weight-movement that inflates their f and deflates their speedup).
5. If a candidate survives: real A/B with same prompt/seed/refs, timing + frame-diff + Whisper + vision.

Headline-number traps: "runs in N GB VRAM" = smallest quantization on a memory-CAPPED card, check the model card's per-format table; "N× faster" is usually vs dense attention without Sage on a different GPU — recompute against the local baseline with the formula above.

Status of record (re-verify before relying; it changes fast):
- **H3-Regenerate-2K** (native 2K): NOT open-sourced, API-only (platform.minimax.io; the official flow = iterate locally at 768p, send the keeper through the API for the 2K master). It re-regenerates the 768p result in-context with the original multimodal context — it is NOT an upscaler. Sparse-attention reference code still pending ("future update"). Re-verify points: `MiniMaxAI/MiniMax-H3` README H3-Regenerate-2K section + Discussions, `github.com/MiniMax-AI/MiniMax-H3/releases`, minimax.io/news. User policy: cloud is too expensive → 2K only becomes practical once the weights are released.
- **H3-Context-IR**: not part of the open weights; compensated with structured/explicit prompts (the Ref2VA structure above).
- **Latent upscalers** (3D-CNN on H3's 24ch VAE latents, ~700MB each; the actively maintained fork is `xmarre/Comfyui_Minimax_h3_latent_Upscaler-Plus`): value = SPEED (fewer tokens in the main pass) + resolution headroom past 768p (~0.8MP), NOT 2K. Generative — can invent detail and shift identity (the #1 defect class for series); A/B on an identity-critical clip (frame diff + vision) before trusting.
- **Turbo-LoRA 4-step packs**: test `--steps 4` with the official PDD LoRA FIRST (its own benchmark table ranks PDD highest on quality and notes community turbos degrade audio).
- **Sparse/attention nodes**: marginal on top of validated SageAttention + PDD; only adopt on a measured large jump, never as a default change. Learned sparse predictors (Veda-class) stack on Sage with no new quantization cost when their kernel arithmetic equals Sage's — but their predictors are trained on T2VA/FL2VA, so R2VA quality REQUIRES a human A/B (frame-diff + Whisper + vision) before default; a dedicated per-modality fine-tune release is the signal to revisit.
- **Veda A/B RESULT (2026-10-11, husky pilot seed 4242, 8 s R2VA exact-audio, PDD baseline): NOT adopted.** Infra installed: node `veda-sparse-attention` 0.3.1 in the broker's E: install, both predictors in `E:...\models\veda` (must be the broker install's models dir, not C:), `generate_video.py --veda` flag (node 31 after PDD Apply, before Guider; predictor auto-picks R2VA ckpt when refs present; budget 32/32; triton-windows 3.6.0 runs the sm120 INT8 kernel fine). Speed: 177 s → 131 s = **1.35× at 8 s** — node logged only 71.6% attention skipped (fixed 32-tile plan under-skips on small grids; 13% padding at 1344×768/192f; node suggests 1536×768/209f divides evenly). Audio: final clips bit-identical (remux) — but that check is CIRCULAR for exact-audio: lips follow the model's NATIVE co-generated audio, which the remux overwrites. Compared the RAW pre-remux outputs (C:\\ComfyUI\\output\\openclaw-local-output_*): Veda's native audio diverged from the song (Whisper: baseline co-gen "esto no es un juego" sustained through the sung vowel 6.06→7.66 matching the song's 6.2→7.28; Veda mangled phrase 1 into garbage and cut "juego" at 6.2 — no vowel sustain; envelope-corr vs song @lag0: baseline 0.84, Veda 0.76, optimal lag 0 for both = internal timing wrong, not an offset). Joint video+audio denoising means the diverged video trajectory corrupts the co-gen audio even though Veda keeps audio attention dense → mouth desyncs against the remuxed song (Raúl saw it). **Lesson: for exact-audio lip-sync clips, ALWAYS evaluate the native co-gen audio from the raw ComfyUI output (or extract it before replacement) — the remuxed final hides everything.** Video: identity + singing survive, but R2VA-preview defects are absolute: **mic stand + cable vanish (floating mic — breaks the MICRO rule)**, framing drifts to close-up, paw deformation, fur softening, bg truss flicker; PSNR 16.6/SSIM 0.74 vs baseline (diverges like a different seed). Deterministic: cold==warm bit-identical. Revisit ONLY when the dedicated R2VA fine-tune lands (announced) or for long ref-less drafts.
- **Full fine-tunes** (HDR, distant faces, expressiveness, VFX): A/B candidate for specific shot types, never a default — swapping the base checkpoint invalidates the whole validated pipeline, and the recommended pairing is its own 4-step turbo, not PDD; audio behavior of fusions unverified.

Decision rule: speed → PDD `--steps` first (free). Resolution → wait for official 2K; latent upscaler is the stopgap. Quality → fine-tune A/B per shot type. Cloud/2K → not adopted.

## Sampler

res_multistep vs euler A/B (same prompt/seed, 5 s 720p 16:9, 20 steps, SageAttention): no measurable difference — audio within 0.7 dB (sub-audible), clean frames, stable identity. Keep res_multistep (production default). Do not re-run this experiment. Note: same seed + different sampler → different look (seed does not guarantee identical output across samplers). Third-party "sampler improves audio/sharpness" claims transfer from full distilled pipelines (8-step LoRA + two-stage upscaling), not from a sampler swap on the standard graph.

## Ops notes

- ComfyUI auto-updates move the repo code but NOT the venv — a `video_types.py` import crash after an auto-update (PyAV ≥17 needed for `av.video.reformatter`) is that drift: `uv pip install --python 'C:\ComfyUI\.venv\Scripts\python.exe' --upgrade 'av>=17'` + bump the repo requirements pin. Watch for this class of drift on every auto-update.
- PowerShell mangles `cmd.exe /c "uv ... 'av>=17'"` (the `>`): use `& uv pip install --python <exe> --upgrade 'av>=17'` and verify success via a direct import check, not exit code.
- The broker freezes during generation (llama-server torn down, ~5–10 min per run) — run generations sequentially and don't schedule dependent LLM work in the window.
- Broker upload flaps with `urlopen error [Errno 113] No route to host` on `/v1/upload` while `/health` still returns 200 (host in interactive use) — probe with a REAL tiny-PNG upload to `/v1/upload` in a `wait_broker()` loop before spending a quality attempt; retry infra errors with backoff WITHOUT consuming the attempt.

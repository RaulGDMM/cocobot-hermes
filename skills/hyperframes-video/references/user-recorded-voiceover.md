# Replacing provisional TTS with sectioned user voice

Use this workflow when a HyperFrames project already has provisional TTS and the user supplies one real recording per scene or section.

## 1. Inventory before changing the timeline

- Match recordings to scenes by an explicit numeric prefix.
- Preserve Unicode filenames during discovery.
- Require a complete one-to-one scene/audio mapping before timing edits.
- Copy each original recording into a project-owned `source/` directory. Never modify message attachments destructively.
- Back up the provisional TTS separately so rollback remains simple.

## 2. Transcribe the source recordings

- Use a multilingual ASR model and specify the language explicitly.
- Capture segment and word timestamps, not only plain text.
- Compare against the approved script, but treat the recording as authoritative when the speaker intentionally changes wording.
- Normalize obvious ASR substitutions for known product/brand names only when context is unambiguous.
- Detect hallucinated tails by timestamp plausibility. A complete sentence assigned to a fraction of a second is not credible; use the last credible word timestamp for trimming.

## 3. Create deterministic production audio

For spoken video narration, a reliable default is:

- PCM WAV, 48 kHz, mono
- moderate normalization around -16 LUFS
- peak at or below -1.5 dBFS
- 150–200 ms safety before the first spoken word
- about 250 ms after the last spoken word
- very short fades at both boundaries to prevent clicks

Trim exterior silence only. Preserve the speaker's pauses and cadence inside the recording.

Keep a machine-readable manifest containing, per section:

- original and staged source paths
- source duration
- trim start/end
- processed duration
- derived scene duration
- verified spoken text
- ASR text and any anomaly notes

## 4. Verify the processed WAVs again

Re-transcribe the final WAV files before timeline work. This catches:

- clipped first or last words
- an over-aggressive silence trim
- an ASR hallucination that was accidentally retained
- wrong scene/file association

Measure final duration, loudness, and peak from the processed files. Do not reuse source-container durations.

## 5. Rebuild timing from final audio

Derive each scene duration from its own WAV plus deliberate lead-in and tail room. A useful starting point is:

- audio starts 250 ms after scene entry
- scene ends 550 ms after audio ends

Then recalculate cumulatively:

- scene starts and durations
- audio starts and durations
- root composition duration
- transition boundaries
- sub-composition `data-duration` values
- motion sidecars
- `SCRIPT.md` and `STORYBOARD.md`

Never force the speaker back into provisional TTS timings.

If the real narration is longer, stretch the scene choreography proportionally instead of letting the visuals finish early and hold statically. For an existing GSAP scene, setting the completed paused timeline's duration before registering it is a compact proportional retime. Validate seek behavior afterward because timeline adapters may differ.

## 6. Verify the assembled timeline

Add a deterministic timing assertion that checks:

- scene count equals audio count
- scene starts are cumulative
- every audio begins inside its owning scene
- no audio overflows its scene
- root duration equals the sum of scene durations

Then:

1. Run `npx hyperframes check`.
2. Capture at least two frames per scene: middle and close to the end.
3. Inspect for empty holds, resets, clipped elements, incorrect final states, and transition overlap.
4. Open Studio and select the root composition.
5. Confirm Studio displays the expected total duration and enables playback/audio controls.
6. Start real playback and verify the playhead advances.
7. Confirm every WAV loaded as a browser resource and check the console for runtime errors.

A moving visual playhead alone does **not** prove narration loaded.

## Approval gate

When the user requested review before final delivery, keep the MP4 render blocked after voice integration. Provide the updated preview and render only after explicit approval.

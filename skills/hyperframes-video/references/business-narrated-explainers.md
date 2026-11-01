# Business-facing narrated technology explainers

Use this workflow when a technical product, library, internal platform, or QA/developer tool must be explained to a non-technical business audience in a narrated video.

## Message translation

Translate implementation details into outcomes before scripting:

| Technical fact | Business-facing formulation |
|---|---|
| Tests run on pull requests | Problems are detected before the developer integrates the code |
| Shared CLI/core | One comparison engine and one consistent criterion across platforms |
| Pixel/block/displacement pipeline | Several analysis layers reduce noise and false alarms |
| LLM/failsafe | AI provides a contextual second opinion only after normal comparison fails |
| Baseline/diff artifacts | Approved reference, current result, and highlighted differences |

Keep important product and repository names on screen even when they are awkward or unnecessary in narration.

## Script approval before production

For a new narrated presentation:

1. Inspect the source material and verify product claims.
2. Draft the complete narration, organized by scene, with rough timings.
3. Present the narration for approval before generating TTS or building frames.
4. Apply wording corrections without defending the original phrasing.
5. Lock the approved version in `SCRIPT.md`; only then generate audio and visuals.

When the audience is business-facing:

- Avoid unexplained terms such as pull request, CLI, LLM, baseline, pixel diff, adapter, artifact, or framework.
- Prefer “one of its best virtues” over declaring a single “greatest virtue” when several differentiators matter.
- Lead with customer risk, prevention, time saved, operating cost, and adoption friction.
- Do not invent percentages, incident counts, time savings, or competitor prices. Qualitative evidence such as “a significant reduction” is acceptable only when the user supplied it.
- Competitor comparisons may name relevant products and pricing models, but should omit exact prices unless verified from current primary sources.
- If a capability relies on a shared internal service, distinguish “no additional project cost” from “free in every possible deployment.” Preserve the user's chosen claim after surfacing the nuance once.

## Spanish TTS verification

Spanish TTS often mispronounces English product names even when the sentence is otherwise correct. Keep two layers:

- `SCRIPT.md`: canonical user-approved wording and spelling.
- TTS input: pronunciation-only aliases, with no change to the message or on-screen text.

Typical phonetic adaptations include names such as Screenshot, Playwright, Cypress, Failsafe, iOS, and English product names. Generate scene-by-scene audio so only affected lines need regeneration.

Verification loop:

1. Generate one audio file per scene.
2. Measure each file with `ffprobe`; do not use estimated timings after audio exists.
3. Concatenate a review copy with short silence between scenes.
4. Transcribe the review copy with Whisper or `faster-whisper` in the target language.
5. Compare the transcript with the canonical script, paying special attention to product names, negations, numbers, and the final claim.
6. Regenerate only problematic scenes with phonetic aliases.
7. Re-transcribe until the complete meaning and names are recognizable.
8. Set scene durations from real audio duration plus a small visual hold (normally 0.5–1.0 seconds).

Do not treat punctuation differences in ASR as narration defects. Do treat missing words, reversed meaning, mangled names, and wrong numbers as defects.

## Visual direction for internal corporate audiences

A useful midpoint between corporate and dynamic is:

- warm off-white or restrained dark canvas;
- near-black typography and one strong accent color;
- asymmetric editorial layouts with edge anchors;
- real screenshots as evidence rather than decorative mockups;
- large outcome statements plus smaller monospace technical labels;
- controlled transitions and kinetic emphasis on the AI, cost, and prevention beats.

Avoid generic blue-purple AI gradients, glassmorphism, dense code, and dashboards that require technical interpretation.

## Final gate

Before rendering:

- confirm every approved narration line is present in the audio;
- inspect scene midpoint snapshots, especially real screenshots and competitor labels;
- check that technical terminology shown on screen does not leak into unexplained narration;
- open HyperFrames Studio for final user review;
- render only after explicit approval.

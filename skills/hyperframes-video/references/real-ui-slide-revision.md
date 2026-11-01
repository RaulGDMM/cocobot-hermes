# Real-UI slide revision (HyperFrames)

Topic: revising a HyperFrames slide that renders a realistic UI (app/dashboard/OS window) so the interface reads as real, not mockup.

## Goal

A slide showing a UI should look like a real product screenshot — correct density, real control states, plausible data, no placeholder lorem blocks — while staying a static, seek-safe HyperFrames frame (no live DOM, no JS interactivity).

## Rules

- Build the UI with pure HTML/CSS in the composition (no JS, no real DOM components). It must be a flat, deterministic render — the same pixels on every seek.
- Use real-looking content: actual column headers, plausible values, correct alignment. No `lorem ipsum`, no `xxxx` blocks, no empty gray boxes standing in for data.
- Reproduce real control states: buttons have hover/pressed/active distinctions where the shot implies them; toggles are clearly on or off; focus rings appear on exactly one element at most.
- Match the platform's visual language (spacing, corner radius, typography, elevation/shadows) — a macOS window is not a Windows window. Copy the metric, don't approximate it.
- Density matters: real UIs are tight. Avoid excessive padding that makes the mockup look like a poster.
- Text: use real strings at real sizes. If a long string would overflow, truncate it the way the real product would (ellipsis / wrap), never let it blow out the layout.

## Seek-safety

- The slide must render identically at any timestamp — no animation-driven layout, no scroll position, no time-varying content unless it is a pure CSS transform/opacity that still resolves to a valid frame.
- Verify by seeking to 0 s, mid, and end and diffing the UI region — it must be stable.

## Verification

- Render the frame and inspect: does it read as a real product at a glance? Check alignment, control states, data plausibility, overflow.
- If it reads as "mockup" (uniform gray blocks, fake data, wrong platform), fix the content/metrics — not the rendering tech.

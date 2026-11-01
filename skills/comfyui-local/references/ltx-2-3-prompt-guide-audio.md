# LTX 2.3 — Official Prompt Guide (Voice & Audio Section)

Source: [ltx.io/model/model-blog/ltx-2-3-prompt-guide](https://ltx.io/model/model-blog/ltx-2-3-prompt-guide)

## Key Principles for Audio/Voice

- **Detail drives quality**: LTX 2.3 responds best to long, highly specific prompts covering subject, action, lighting, camera movement, AND audio.
- **Enhanced audio impact**: Improved audio quality in 2.3 means prompts should explicitly describe acoustic environments, voice qualities, and ambient sounds.
- **For endpoints that generate synchronized audio**, include audio descriptions in your prompt: "the sound of rain on pavement," "soft ambient music," "a crowd cheering in the distance."

## Dialogue & Acting

- Break dialogue into **short phrases** with acting directions between lines
- Use **physical cues** instead of emotional labels (e.g., "His eyes widen momentarily" instead of "He looks scared")
- Example:
  > A middle-aged man with greying hair speaks in a sad, slow-paced voice, "I remember after you kids came along..." He pauses and looks to the side, then continues, "your mom..." His eyes widen momentarily. He finishes with a cracking voice, "said something to me I never quite understood." The camera slowly zooms into his face. The audio is crisp with faint room tone.

## Formatting Rules

- Write as a **single flowing paragraph** — NOT bullet points
- Use **present tense verbs** for action/movement
- Place dialogue in **quotes**
- Specify **language/accent** if non-default

## 6 Essential Prompt Elements

1. Establish the Shot (cinematography terms, shot scale)
2. Set the Scene (lighting, color palette, textures, atmosphere)
3. Describe the Action (natural sequence, start to finish)
4. Define Character(s) (appearance, emotion via physical cues)
5. Identify Camera Movement(s) (how/when, relative to subject)
6. Describe the Audio (ambient sound, music, speech/singing)

## What Works vs What to Avoid

### ✅ Strengths
- Cinematic compositions (wide/medium/close-up, thoughtful lighting)
- Emotive moments (subtle gestures, facial nuance)
- Atmosphere & setting (fog, mist, golden hour, rain)
- Clear camera language ("slow dolly in", "handheld tracking")
- Stylized aesthetics (painterly, noir, analog film)
- **Voice capabilities** (talking/singing characters, multi-language)

### 🚫 Avoid
- Internal emotional states without visual cues
- Over-constrained numerical specifications
- Complex physics (chaotic motion → artifacts)
- Overloaded scenes (too many characters/actions)

## Community Notes

- [r/StableDiffusion](https://www.reddit.com/r/StableDiffusion/comments/1rnij3k/): "The new vocoder improves reliability and alignment. If you want sound, describe it: Environmental audio. Tone and intensity. Dialogue clarity."
- Voice consistency WITHOUT ID-LoRA is achievable but limited — expect variation between generations even with identical prompts.
- Voice descriptor specificity matters: "deep gravelly baritone" >> "deep voice" >> "male voice"

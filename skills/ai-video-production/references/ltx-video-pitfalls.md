# LTX 2.3 Video Generation — Session Learnings

## Biblic-Cocobot Project (2026-05-05)

### Vision Analysis is Mandatory
- User correction: "antes de generar, analizaras con visión la imagen para entenderla y así adaptar el prompt no solo al texto sino a la imagen en si"
- Without vision analysis, prompts describe generic scenes → camera movements destroy structured compositions (tríptics, panels, ornate frames)
- Example failure: clip1b had a 3-panel tríptico layout. Initial prompt with zoom/pan destroyed all three panels.

### Lipsync Text in Quotes
- Without `saying: 'exact text'`, mouth movement is generic and doesn't match audio rhythm
- Format: `Speaking in Spanish with clear Spanish accent as [voice type] voice, saying: 'exact dialogue text'`
- This MUST match the TTS audio content exactly

### Static Camera Default
- Camera movement (zoom, pan, orbit) should ONLY be used when explicitly requested
- Most images have structured compositions that camera movement distorts
- Use `STATIC CAMERA` as the prompt prefix by default
- When orbit IS wanted: `SLOW circular camera orbit` not aggressive movement

### Grain/Noise
- Inherent to LTX 2.3 model output
- NOT controllable via prompt (no negative prompt support)
- NOT a workflow bug
- Accept or use post-production denoising

### Erratic Limb Movement
- Fix: add "His arms and paws stay relaxed at his sides without erratic movement"
- Particularly affects characters with prominent hands/paws

### Static Falling Objects
- LTX may render bombs, rain, debris as floating still images
- Fix: emphasize verbs in CAPS: "bombs RAINING DOWN, CRASHING into buildings with bright EXPLOSIONS"
- Add lighting effects: "explosions and lightning casts dynamic orange and blue light reflections INTO THE ROOM"

### Timing Actions Within Clips
- Use: "About two-thirds into the scene, [character] suddenly [action]"
- Helps LTX place timed events correctly within video duration
- Example: cat spinning and fleeing from cucumber at 2/3 mark

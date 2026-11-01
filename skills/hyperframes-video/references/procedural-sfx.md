# Procedural Sound Effects for HyperFrames

Generate SFX (whooshes, booms, chimes, clicks, ambient pads) using Python's `wave` module. No external audio libraries needed.

## Quick generator script

Run via `execute_code`:

```python
import struct, math, wave, os

def generate_wav(filename, sample_rate, duration, waveform_fn):
    num_samples = int(sample_rate * duration)
    with wave.open(filename, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(num_samples):
            t = i / sample_rate
            val = waveform_fn(t, sample_rate)
            val = max(-32768, min(32767, int(val * 32767)))
            wf.writeframes(struct.pack('<h', val))

sr = 44100
out = "assets"

# Whoosh (rising sweep)
generate_wav(f"{out}/whoosh.wav", sr, 0.3, lambda t, sr: (
    min(1.0, t/0.05) if t < 0.05 else (1.0 if t < 0.15 else max(0, 1-(t-0.15)/0.15))
) * math.sin(2*math.pi*(200+800*(t/0.3))*t) * 0.5)

# Boom (deep impact)
generate_wav(f"{out}/boom.wav", sr, 0.6, lambda t, sr: (
    min(1.0, t/0.02) * math.exp(-(t-0.02)*5) if t > 0.02 else 0
) * math.sin(2*math.pi*(80+40*math.exp(-t*30))*t) * 0.5)

# Chime (A5 bell)
generate_wav(f"{out}/chime.wav", sr, 0.4, lambda t, sr: (
    math.exp(-t*8) if t > 0.005 else 0
) * (math.sin(2*math.pi*880*t) + math.sin(2*math.pi*1760*t)*0.3) * 0.25)

# Click
generate_wav(f"{out}/click.wav", sr, 0.1, lambda t, sr: (
    math.exp(-t*80)
) * math.sin(2*math.pi*(1200+800*math.exp(-t*200))*t) * 0.6)

# Ambient pad (30s loopable)
generate_wav(f"{out}/bg_pad.wav", sr, 30, lambda t, sr: (
    min(1.0, t/0.5) * min(1.0, (30-t)/0.5)
) * (math.sin(2*math.pi*220*t)*0.08 + math.sin(2*math.pi*330*t)*0.06 + math.sin(2*math.pi*440*t)*0.04))
```

## Tips

- Generate all SFX in `execute_code` — it's fast (< 10s for 6 effects)
- Place output in `assets/` directory of your HyperFrames project
- Use `data-volume` on `<audio>` elements to control SFX levels (0.3-0.7 typical)
- For longer ambient pads, increase the duration parameter — the pad function fades in/out automatically

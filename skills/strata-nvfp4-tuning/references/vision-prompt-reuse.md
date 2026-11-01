# Vision pipeline & prompt-reuse diagnosis

How the image path works and how to measure prefix reuse against the live server.

## Pipeline (serve/server.py + engine)

- Request with `image_url` parts → `Vision.encode()`: normalize (Pillow converts WebP/TIFF/AVIF; JPEG/PNG/BMP/GIF pass through), key = sha256[:32], LRU cache of 64 `.sve` embedding files in the encoder's `%TEMP%\strata-vision-XXXX\` dir. Cache hit = no re-encode.
- Per request the images are concatenated into one `req-*.sve` (`combined_embeddings_path`, deleted after the request; on Windows opened `O_SHORT_LIVED` so it usually never hits the disk) and passed to the engine as `GENI <max_new> <keys> <file>` instead of `GEN`.
- Engine side: embeddings are spliced at `<|image_pad|>` positions (M-RoPE); on checkpoint restore it validates `checkpoint image identity differs` / `checkpoint image prefix differs` — a mismatch discards the checkpoint from the first differing image, so a client that re-encodes/re-compresses an old image (different bytes) forces a reread from there. Hermes resends images byte-identical, so this rarely fires.
- Encoder process: `strata-vision.exe --mmproj … --model …` (CPU-only build, hides the GPU, 8 threads, no warm-up). 1.8 s invoice-size / 6.2 s 4K photo; the engine is idle meanwhile (costs no decode t/s). `--max-tokens`/`--min-tokens` come from the config's `vision.max_tokens`/`vision.min_tokens`.
- Engine knobs relevant to reuse (from `strata.exe --help`): `--prompt-cache N` (default 6 checkpoints, ~118 MB RAM each, shared across conversations), `--prompt-cache-every N` (16384), `--prompt-cache-tail`, `--conversation-cache-mib N` (parked-conversation RAM, default 0 = off), `--conversation-cache-slots N` (4), `--short-read N`.
- Per-request sampling keys that change checkpointing: `strata_checkpoint: false` → `ckpt=0` (no checkpoint for this turn, prefix reuse kept), `strata_prefix: {"tokens":N}` → `pin=N` (pinned shared prefix; **ignored when the request has images** — `resolve_prefix` logs `strata_prefix ignored: the request has images`).

## Measuring prefix reuse against the live server

Log lines `strata serve: prompt N tokens = R reused + M read in X ms` have no timestamps. To attribute a probe request to its log line:

1. `before=$(grep -c 'strata serve: prompt ' strata.log)` before the API call.
2. POST to `http://172.23.176.1:8097/v1/chat/completions` (bearer key `~/.hermes/secrets/strata-api-key`, model `qwen3.8-flash-next-nvfp4`; `enable_thinking:false` keeps probes short).
3. `grep -a 'strata serve: prompt ' strata.log | tail -n +$((before+1))` after it.

Probe shape that reproduces the question: build a ~4K-token system prompt, then run (a) text-only turn, (b) turn+1 → expect high `reused`; (c) first image turn on the same base → expect only the image tokens as `read`; (d) text turn after the image → expect high `reused`; (e) resend the same image in a new turn → expect no re-encode (check the `.sve` mtime did not change) and reuse kept. A synthetic PNG works without Pillow (zlib+struct, truecolor, noisy gradient) — a real photo stresses the encoder more.

Beware: any probe conversation of its own consumes `--prompt-cache` slots, so a 4K-token probe can evict Raúl's main-session checkpoints and show him a `0 reused + 50K` turn mid-measurement. Note it when it happens; it is the same eviction mechanism under study, not a probe bug.

## Decisive eviction test (main → one-shot → main)

To separate "one-shots fill the cache" from "interleaving breaks the chain", run: main conversation (~45K tokens) T1 cold → T2 warm (must show high `reused`) → **exactly one** small one-shot (62–1250 tokens, optionally with `strata_checkpoint:false`) → T3 on the main conversation. If T3 shows `0 reused` even with a single tiny `ckpt=0` one-shot, interleaving itself is the killer and per-request checkpoint flags are the wrong lever.

Probe sizing pitfall: `"t"+random 9-digit number` strings tokenize at ~9 tokens each, not 1 — a 42000-word filler blew past `--max-context 262144` and the server answered **400** (`request exceeds the context window`, message carries the true token count). Size fillers from the token math, not word counts; ~4600 such words ≈ 45K tokens.

## Correlating image turns in historical logs

`prompt` lines lack timestamps, but each encode writes `<sha256>.sve` whose mtime is the encode moment:

```bash
find "/mnt/c/Users/Raúl/AppData/Local/Temp/" -maxdepth 2 -iname '*.sve' -newermt <date> -printf '%T@ %p\n' | sort -n
```

Same hash in several `strata-vision-*` dirs = the same image re-encoded across server lifetimes: the encode cache dict is memory-only and each server process gets a fresh temp dir, so after a restart the same image IS re-encoded (new mtime, new dir). One dir per server process lifetime; counting dirs near an incident tells you how many server lifetimes spanned it.

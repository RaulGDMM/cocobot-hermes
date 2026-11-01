# Strata NVFP4 — read-only performance audit

Auditing "is Qwen3.8-Flash-Next on Strata running as fast as it can on this box?" without changing anything. Strata (Niko1221/Strata; sergqwer/strata-nvfp4 fork) is NOT llama.cpp: experts live in RAM/SSD tiers and only a cache of them sits in VRAM, so the bottleneck analysis differs and llama.cpp flags do not apply.

## Install layout (PC Gaming)

`E:\Workspace\Openclaw\strata-nvfp4\strata-nvfp4\` — `config/*.json` (engine flags), `strata.log`, `engine/strata.exe`, `docs/NVFP4.md`, `README.md`, `enable-large-pages.cmd`, `mtp-orca/rt`.

## Procedure

1. **Live state, unauthenticated first.** `curl http://<host>:8097/health` is open (model, max_context, loaded). `/props` and `/v1/models` need `-H "Authorization: Bearer $(cat ~/.hermes/secrets/strata-api-key)"`. There is no `/stats`. `/props` yields `build_info` (engine version), `default_generation_settings.n_ctx`, `model_path`, `total_slots` — nothing about memory tiers.

2. **Confirm which config the LIVE process uses — never trust the file on disk.** Several near-identical configs sit in `config/`; the process command line is the truth (`--max-context`, `--kv`, `--spec`, `--spec-min-p`, `--mtp`, `--expert-cache`):
   ```
   /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command \
     "Get-CimInstance Win32_Process -Filter \"Name like 'strata%'\" | Select-Object Name,CommandLine | Format-List"
   ```

3. **`strata.log` is ground truth for speed** (the engine's equivalent of `slot print_timing`). Per-request line:
   `prompt N tokens = X reused + Y read in Z ms (PP t/s), M generated in W ms (TG t/s), drafts accepted A of B`
   plus `decode expert cache hit rate: NN%`, `resident RAM: N GiB of experts in RAM`, and `expert tiers: GPU … RAM … files … blobs … MB read`.

4. **Bucket decode t/s by context size; never report a flat median.** Regex the request lines, keep only generations ≥100 tokens, report median/p25/p90 per bucket (<8K, 20–40K, 40–60K, >80K). A flat median mixes cold short-context runs with warm long ones and manufactures a fake variance story.

5. **Identify which memory mode the engine chose** from its startup lines — this decides which knobs exist at all:
   - `low RAM (below 96 GB installed; N GiB installed)` → `experts via mmap (--mmap-experts)` + `FileExpertSource: allocating N GiB page-locked cache complement` → `mapped pinned cache complement ready: page-locked and mapped`. Some experts still read from the SSD tier (watch `blob reads from the file` / `MB read`).
   - ≥96 GB → the resident **expert arena** path — the only path that uses large pages.
   Also read: `expert cache N slots, X GiB of VRAM`, `pre-filled N of N slots`, `N expert-pool workers + the host thread`, `PCIe probe: N GB/s → pcie_frac`.

6. **Harvest the engine's own warnings — they name the fix:**
   - `N MiB of VRAM free with everything loaded - LOW: requests may stall; add --vram-reserve-mib NNN to the config's args (or lower --max-context)`
   - `only N MiB free once the slots are written; shrinking the expert cache` (repeated) = the expert cache is squeezed by KV; lowering `--max-context` buys slots back (~+25% going 262K→131K on a 32 GB card).

7. **Compare against the right reference row, not the headline number.** `README.md` tabulates decode by VRAM and names its reference rig (5090 + 9950X3D + 128 GB DDR5-5600). `docs/NVFP4.md` has a 64 GB-emulated row (ballast process + `STRATA_EMULATE_RAM_GIB=64`) — judge a 64 GB box against that, not the 128 GB headline.

8. **Check the CPU/RAM side — the expert pool is CPU- and bandwidth-bound.** `Win32_Processor` (core count vs the engine's `expert-pool workers + host thread`), `Win32_PhysicalMemory` (`ConfiguredClockSpeed`, DIMM count = channels). On an 8-core CPU the pool is the ceiling and no KV/page knob moves it.

## Knobs (only after step 7 shows a real gap)

- `--vram-reserve-mib N` — stability against stalls, not speed.
- `--max-context` lower → more expert-cache slots → higher hit rate.
- `STRATA_PREFILL_NVFP4=w4a4` — faster prompt read, less accurate; affects only the first cold prompt.
- `--spec 3` vs `4` — A/B the `drafts accepted A of B` ratio; higher acceptance is not a guaranteed net gain.
- `--pcie-frac` — default 0.25 is auto-probed from measured GB/s; only worth touching if PCIe is unusual.

## Pitfalls

- **Read `docs/NVFP4.md`'s "Tried and dropped" section before proposing any knob** — the author already measured `--pcie-mode dma`, `--spec 5/6`, `--spec-min-p 0.3/0.7`, and extra pool workers as no-gain or worse. Re-proposing them costs the user time and your credibility.
- **That same doc discounts large pages for decode**: the CPU pool steadies from 7.4–11 ms to ~7.5 ms per round, but "decode itself is GPU-bound, so the rate barely moves". Do not sell large pages as a throughput win.
- **The `large pages (2097152 B)` log line only exists on the expert-arena path.** On a low-RAM (mmap + page-locked complement) box it never prints even when `SeLockMemoryPrivilege` is granted. Check with `enable-large-pages.cmd -Check` (read-only) before claiming the privilege is missing.
- **From WSL, `powershell.exe` and `cmd.exe` are not on PATH** — use absolute paths (`/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe`, `/mnt/c/Windows/System32/cmd.exe`).
- **Vision runs on the CPU** (`strata-vision.exe`, 8 threads) by design so the GPU keeps all its VRAM for the model — not a misconfiguration.
- Prefix reuse is excellent on this engine (90K-token prompts re-reading a few hundred tokens). If `reused` is near zero on a follow-up turn, that is the anomaly worth investigating, not raw decode speed.

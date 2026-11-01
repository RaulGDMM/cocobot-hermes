# Preparing a large MoE checkpoint for an alternative engine (Strata / strata-nvfp4)

Use when a model is too big for VRAM+RAM in llama.cpp mainline and a specialised fork (experts in RAM/NVMe, attention in VRAM) is the candidate. Example class: 100B+ MoE on a 32GB GPU + 64GB RAM host.

## Decide the engine
- Prefer a fork that ships a **Windows release bundle** (portable exe + CUDA DLLs) over one that must be compiled; check `api.github.com/repos/<owner>/<repo>/releases` first.
- Check whether a **pre-built pack already exists on HF** (`huggingface.co/api/models?search=<engine>+<quant>`) before converting; pre-packs often exist only for lower-bit GGUF quants, not for NVFP4.
- Check the expert footprint vs RAM: if experts ≈ total RAM, the engine needs a low-RAM/NVMe-streaming mode and a fixed pagefile (verify with `Get-CimInstance Win32_PageFileUsage` before touching it — it may already be set).
- Note the checkpoint provenance (official vs abliterated fine-tune) and tell the user before downloading.

## Placement
- Run the engine on **Windows native** when its fast paths (unbuffered NVMe reads) are Windows-only; WSL is only for download/conversion.
- Put model artifacts in the user's existing Windows models folder (`E:\Workspace\Openclaw\models\`), engine in its own folder beside it; write a custom engine config with absolute paths instead of moving files into the bundle layout.

## Conversion (one-time, lossless repack)
- Use the bundle's own `prepare-model` order; wrap it in a resumable script that skips outputs that exist **and are complete**.
- **Delete partial outputs before resuming**: an interrupted writer leaves a truncated `.gguf` that a size>0 skip test treats as done.
- **Pass `--use-temp-file` to llama.cpp's `convert_hf_to_gguf`** for 70GB+ outputs: by default it holds every tensor in RAM until the final write and will reach the WSL memory cap; with the flag RAM stays at a few GB.
- Run long conversions as tracked background processes (`terminal background=true, notify=true`), never `nohup/setsid`. Warn the user that **stopping the Hermes turn kills them** — they must not press stop to switch models mid-conversion.
- Verify downloads by shard count + no tiny shards; `snapshot_download` returns a `str`, wrap in `Path` before `rglob`.
- **Strata NVFP4 specific (sergqwer/strata-nvfp4 v0.1.38-nvfp4.2)**: the conversion order is `ple_fp8_pack.py` (51.2 GB PLE table), `embd_bf16_pack.py` (1.3 GB embeddings — must come from the OrcaRouter checkpoint because the abliteration modified `embed_tokens`), `nvfp4_convert.py` with `--use-temp-file` (73.9 GB native GGUF, 47 layers, attention + shared experts + output in Q8_0, MoE experts as NVFP4 with per-expert F32 scales), `iq_pack.py --experts-bin` (63 GiB `experts.bin` + tokenizer), `mtp_extract.py` → `mtp_pack.py --experts q2_0` → `mtp_rt.py` (draft head, q2_0 for the runtime). Vision encoder via `convert_hf_to_gguf --mmproj --outtype f32` (1.8 GB).

## Actualizar la build Strata instalada (updater de escritorio)

`C:\Users\Raúl\Desktop\actualizar-strata-nvfp4.bat` (creado 2026-10-04, clon de `actualizar-llama-cpp.bat`). Fork correcto = **`sergqwer/strata-nvfp4`** (el que consta en `engine\BUILD.json` → campo `"fork"`; chimpera/strata-nvfp4 es la misma línea pero sin releases Windows). Instalación: `E:\Workspace\Openclaw\strata-nvfp4\strata-nvfp4`.

- Release API `repos/sergqwer/strata-nvfp4/releases/latest`, asset `strata-nvfp4-*-windows-x64.zip` (~400 MB, publica digest sha256 → el script lo verifica). El bundle se **despliega encima** (robocopy /E de la raíz del zip, localizada vía `engine\BUILD.json`): `.venv-serve\`, `pack\`, `mtp-orca\`, `config\cocobot.json` y `start-cocobot.cmd` no están en el zip y se conservan (confirmado por el changelog del mantenedor: "Unzip over the previous folder").
- **Parche local que el updater reaplica**: `tools\nvfp4_convert.py` lleva `--use-temp-file` en el argv de convert_hf_to_gguf. El zip lo trae sin parchear; es el ÚNICO fichero local divergente del zip 0.1.38-nvfp4.2 (verificado byte a byte). El script lo reinyecta con PowerShell (patrón `"--outfile", str(out)]`).
- Backup previo en `E:\Workspace\Openclaw\strata-nvfp4-backup-<fecha>` EXCLUYENDO `pack\ mtp-orca\ models\ .venv-serve\` y `strata.log` (si no, ~72 GB por backup). Kill: `taskkill strata.exe` + solo el python cuyo CommandLine matchee `serve\.server` (no cualquier python.exe).
- Verificación post-install: `BUILD.json.version` + `strata.exe` sin args imprime ayuda con `--pack` (no tiene `--version`).
- Trampas bat ya resueltas: fichero **CRLF** obligatorio (LF → cmd rompe líneas), `setlocal EnableDelayedExpansion` necesario para `!VAR!`, y recortar el `\` final de la ruta robocopy (escapa la comilla → errorlevel ≥8; mismo problema que documentó actualizar-llama-cpp.bat).
- 2026-10-04: updater ejecutado con exito por Raúl → instalada `v0.1.39-nvfp4.1` (7% decode más rápido, mismo output; `parallel: N` y Responses API opt-in). El updater paso backup `strata-nvfp4-backup-<fecha>` con la version anterior.
- Trampa bat adicional ya corregida: `echo` con `(` o `)` sin escapar dentro de un bloque `if (...)` rompe el parseo de cmd y cierra la ventana sin mensaje (el `)` del texto cierra el bloque). Escapar siempre como `^(` `^)`. Y el patron de pausa fiable: el bat se re-lanza a si mismo (`if not "%~1"=="__inner" ( cmd /c ""%~f0" __inner" & pause )`) para que la pausa final sobreviva incluso a errores de sintaxis del cuerpo.

## Test before profile
- User frees VRAM/RAM (stops llama-server, switches agent to cloud). Then: start engine, measure TTFT + decode (short, agentic ~1.5K, 32K), A/B quality vs current default on the same prompts.
- Only after it passes: back up `start-hermes.ps1`, add the profile, make it default, update Hermes `model.base_url`, parse-validate the .ps1.

## Benchmarks (Strata NVFP4, OrcaRouter uncensored, 64 GB RAM, RTX 5090 32 GB, ctx 262K)
| Prompt | Tokens in | Tokens out | TTFT | Decode |
|---|---:|---:|---:|---:|
| Short (greeting) | 59 | 64 | 1.7 s | 42 t/s |
| Agentic (cold) | 178 | 1024 | 1.3 s | **62 t/s** |
| Agentic (warm, cached) | 178 | 1024 | 0.1 s | **63 t/s** |
| ~32 K | 39 K | 300 | 15 s | 46 t/s |

**Low-RAM mode**: 37 GiB page-locked experts in RAM, 17.7 GiB VRAM expert cache (6868 slots). MTP: 1.1 GB VRAM, q2_0, 3-token draft. Vision in CPU.

**Provenance note**: the checkpoint is `jpezzulli/OrcaRouter-Qwen3.8-Flash-Next-Uncensored-ModelOpt-NVFP4` — a third-party abliterated fine-tune on top of a PTQ NVFP4 without QAT. Not the official Qwen 3.8 Flash-Next. Quality is coherent but may differ from the base model on strict reasoning tasks.

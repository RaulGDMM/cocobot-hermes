# Actas de rendimiento — Mavenchi (Strata NVFP4)

Ledger vivo de velocidad para comparar **versiones de Strata** (y, cuando toque, **Qwen4**) en la caja de Raúl: RTX 5090 32 GB · 64 GB DDR5 · 7800X3D (8c/16t) · NVMe Gen5 · Win11.

## Condiciones fijas del banco (no cambiar sin anotar el delta como columna)

- Pack `qwen-nvfp4-gptq` + uncensor cvec (project/per-layer 8-33), mmproj BF16 CPU.
- Args: `--ram-budget 42 --vram-reserve-mib 1024 --host-core last --prefill auto --spec 4 --spec-min-p 0.5 --lookup-chain 2 --max-context 262144 --kv int8 --conversation-cache-mib 8192 --conversation-cache-min-free-mib 512 --conversation-disk-*` (persist) · env headroom 2, PARK_REWIND_MAX 8192, EMB_REUSE_ACCOUNT 1.
- Sampling T 1.0 / top_p 0.95 / top_k 20 (oficial thinking).
- Estado **cálido** (motor ≥1 h de uso, sin ComfyUI/juegos), broker sin GPU.

## Protocolo A — tráfico pasivo (gratis, siempre)

Con ≥30 requests o ≥2 días de tráfico real Hermes desde el `engine started` de interés:
```bash
python ~/.hermes/skills/strata-nvfp4-tuning/scripts/baseline_ab.py --from <arranque>
```
Anota medianas por banda (<8K / 8-32K / 32-80K / 80-140K / ≥140K), aceptación drafts y hit rate. Cortes del log, no de benchy.

## Protocolo B — activo (5 min, GPU libre)

```bash
uvx llama-benchy==0.4.0 --base-url http://172.23.176.1:8097/v1 --api-key $(cat ~/.hermes/secrets/strata-api-key) \
  --model qwen3.8-flash-next-nvfp4 --tokenizer /mnt/e/Workspace/Openclaw/strata-nvfp4/strata-nvfp4/models/qwen-nvfp4-gptq/pack/tokenizer \
  --pp 1024 4096 16384 --tg 32 128 --runs 3 --no-cache
```
- **TG fiable = tg128** (benchy ↔ log run a run; tg32 ruidoso). El PP de benchy es basura (estima por TTFR): anotar el PP **del log**, líneas `prompt N tokens` con `0 reused` de los propios runs (tolerancia ±12% sobre 1024/4096/16384), mediana. TTFT = columna `e2e_ttft`.
- Ojo: benchy desaloja los checkpoints de la sesión viva → el siguiente turno de Hermes relee (conv-disk lo re-estaciona en ~1-2 s).
- Extra opcional: guardar sesión larga y medir `disk hit:` (restaura de 135-165K) tras reinicio limpio.

## Reglas del acta

1. Cada versión nueva de fork/upstream (o pack): fila A + fila B en las 48 h posteriores al primer arranque limpio, en cálido.
2. **No cruzar packs/modelos en una comparación de velocidad** — Qwen4 u otro pack = fila/columna nueva (otra geometría y otro tamaño de expertos).
3. Si una fila se mide con condiciones distintas (residency, reserve, flags), se escribe en la columna desviaciones; si no, compararla es mentir.
4. `STRATA_ROUTE_TAIL_SKIP` y demás knobs calidad↔velocidad: solo con OK explícito de Raúl, anotado como desviación.

## Historial

| Fecha | Motor / pack | Pinned | Decode mediana por banda (t/s) | TG128 seco | PP frío 1K/4K/16K | Drafts | Notas |
|---|---|---|---|---|---|---|---|
| 2026-10-10/13 · 0.1.41–0.1.42 · orca | 44,2 (completa) | 95-122 <32K · ~90 @32K · 82,9→96,3 @104K (post host-core last) | — | 1700@3,6K / 2970@15K / 3623@52K | 75-76% (T1,0: 72,8%) | referencia histórica |
| 2026-10-17/18 · **0.1.44.1-nvfp4.1** · gptq | 41,3 | A: total 64,8 · 32-80K 66,2 · 80-140K 64,7 · ≥140K 64,2 | — | — | 66,8% | primer acta gptq en cálido (A/B lookup-chain) |
| 2026-10-19 21:18→20 18:18 · **0.1.44.1-nvfp4.2** + lookup-chain 2 · gptq | 42,0 | A (n=739): <8K 72,2 · 8-32K 71,2 · 32-80K 68,5 · 80-140K 67,3 · ≥140K 68,1 | — | ≥8K frío: 1330-1577 | ~65-67% | baseline oficial pre-0.2.0 |
| 2026-10-20 18:18 · **0.2.0-beta-nvfp4.3** (0.1.45.3) · headroom 4 | 39,53 | A (n=7, 1ª hora): 89,5 (86-90) | — | 20K frío 855 (tier fichero gordo) | — | arranque con poca RAM (43,8); conv-disk rechazó diálogos viejos (esperado) |
| 2026-10-20 20:15 · **0.2.0-beta-nvfp4.3** (0.1.45.3) · headroom 2 · **BASELINE 0.2.0** | 42,00 | A (n=5): 80-140K 91,5 · reuso 99%+ @136K · re-read 135K 25,3 s | **101,3 / 103,5 / 103,1** (log 78-111, med 97) | **714 / 1406 / 3000** | **69,2%** (hit 82-92%) | TTFT e2e 1,35/2,75/4,99 s · #2065 ×3 (525/393/180 MiB) → candidato reserve 1536 |
| 2026-10-21 · **0.2.0-beta-nvfp4.3** · headroom 2 · **banda A refrescada** (anclas 20/10 22:40 n=48 + 21/10 07:56 n=16) | 42,00 | A: 8-32K 80,0 · 32-80K 77,5 · 80-140K 69,6 · TOTAL 76,0 | — | — | 66,7% | la mediana 91,5 @80-140K (n=5) no se sostiene: con n=16 queda 69,6; fila B del acta anterior sigue vigente como TG/PP de referencia |

## Pendientes de acta

- (Hecho 21/10: banda A refrescada con n=64; ver fila 2026-10-21.)
- Próxima release del fork (rebase sobre upstream 0.2.x): fila A+B al instalarla.
- Qwen4 (QN4): cuando salga el pack comunitario — columna pack nueva; el gate real será 128 GB si el tier sube de tamaño.

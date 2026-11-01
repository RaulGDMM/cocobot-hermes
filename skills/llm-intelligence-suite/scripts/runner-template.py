#!/usr/bin/env python3
"""Plantilla de runner de la suite de inteligencia (GSM8K/ARC/HellaSwag/PIQA/PPL/HumanEval).
Reasoning xhigh. Orden: razonamiento primero, HumanEval al final (el mas largo).
Guarda JSON incremental tras cada benchmark (no pierdes progreso si cae a mitad).

USO:
  1. Copiar a /root/workspace/scripts/benchmarks/run-<model>-intelligence.py
  2. Editar BASE, MODEL y OUT (OUT con fecha)
  3. Lanzar en background de Hermes con notify_on_complete=true:
       python3 -u run-<model>-intelligence.py > <model>-intelligence-<YYYYMMDD>.log 2>&1
  (NO usar nohup: falla en este entorno con exit -1)
"""
import importlib.util, json, time
from datetime import datetime

# ===== EDITAR ESTAS TRES LINEAS POR MODELO =====
BASE  = "http://172.23.176.1:30000"
MODEL = "qwen3.8-27b"                      # el nombre exacto que devuelve /v1/models
OUT   = "/root/workspace/scripts/benchmarks/qwen38-intelligence-YYYYMMDD.json"
# ===============================================

# Importar el motor de la suite (NO modificar el motor salvo max_tokens/datasets)
MOTOR = "/root/workspace/llm-intelligence-benchmark.py"
spec = importlib.util.spec_from_file_location("bench", MOTOR)
mod  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

QUAD = ["gsm8k", "arc_easy", "hellaswag", "piqa"]

def log(m, *a, **k):
    # **k acepta flush=True y otros args opcionales de print
    print(m, *a, **k)

def save(acc, elapsed):
    data = {"model": MODEL, "server": BASE, "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(elapsed, 1), "scores": {}, "details": acc}
    for k in QUAD:
        if k in acc:
            data["scores"][k] = acc[k]["score"]
    if "humaneval" in acc:
        data["scores"]["humaneval"] = acc["humaneval"]["score"]
    if "perplexity" in acc:
        data["perplexity"] = acc["perplexity"]
    # Ojo: average = media de 4 (razonamiento). Los JSONs de versiones antiguas usaban
    # media de 5. NO comparar el campo 'average' entre versiones sin reconstruir.
    if all(k in data["scores"] for k in QUAD):
        data["scores"]["average"] = round(sum(data["scores"][k] for k in QUAD) / 4, 1)
    with open(OUT, "w") as f:
        json.dump(data, f, indent=2)
    log(f"   [💾 guardado parcial {OUT}]", flush=True)

log(f"🚀 {MODEL} — inteligencia COMPLETA — reasoning xhigh", flush=True)
log(f"   server={BASE}  model={MODEL}  {datetime.now().isoformat()}", flush=True)
log(f"   OUT={OUT}", flush=True)
log("=" * 60, flush=True)

t0 = time.time()
acc = {}

log("\n📐 [1/6] GSM8K — razonamiento matemático ...", flush=True)
s, r = mod.evaluate_gsm8k(BASE, MODEL)
acc["gsm8k"] = {"score": round(s, 1), "details": r}; save(acc, time.time() - t0)
log(f"   ✅ GSM8K: {s:.1f}%   ({time.time()-t0:.0f}s transcurridos)", flush=True)

log("\n🔬 [2/6] ARC Easy — razonamiento científico ...", flush=True)
s, r = mod.evaluate_arc_easy(BASE, MODEL)
acc["arc_easy"] = {"score": round(s, 1), "details": r}; save(acc, time.time() - t0)
log(f"   ✅ ARC Easy: {s:.1f}%   ({time.time()-t0:.0f}s transcurridos)", flush=True)

log("\n🧩 [3/6] HellaSwag — sentido común ...", flush=True)
s, r = mod.evaluate_hellaswag(BASE, MODEL)
acc["hellaswag"] = {"score": round(s, 1), "details": r}; save(acc, time.time() - t0)
log(f"   ✅ HellaSwag: {s:.1f}%   ({time.time()-t0:.0f}s transcurridos)", flush=True)

log("\n🔧 [4/6] PIQA — razonamiento físico ...", flush=True)
s, r = mod.evaluate_piqa(BASE, MODEL)
acc["piqa"] = {"score": round(s, 1), "details": r}; save(acc, time.time() - t0)
log(f"   ✅ PIQA: {s:.1f}%   ({time.time()-t0:.0f}s transcurridos)", flush=True)

log("\n📉 [5/6] Perplexity — WikiText-2 (NO comparable: 1 token/chunk) ...", flush=True)
pg, pa, pt = mod.evaluate_perplexity(BASE, MODEL)
acc["perplexity"] = {"geometric_mean_ppl": round(pg, 4) if pg else None,
                     "arithmetic_mean_ppl": round(pa, 4) if pa else None,
                     "total_tokens": pt}
save(acc, time.time() - t0)
log(f"   ✅ PPL geo: {pg:.4f}  arith: {pa:.4f}" if pg else "   ⚠️ PPL: sin logprobs", flush=True)

log("\n💻 [6/6] HumanEval — código Python (164) — EL MAS LARGO, va al final ...", flush=True)
s, r = mod.evaluate_humaneval(BASE, MODEL)
acc["humaneval"] = {"score": round(s, 1), "details": r}; save(acc, time.time() - t0)
log(f"   ✅ HumanEval: {s:.1f}% pass@1", flush=True)

elapsed = time.time() - t0
avg = (acc["gsm8k"]["score"] + acc["arc_easy"]["score"] + acc["hellaswag"]["score"] + acc["piqa"]["score"]) / 4
log("\n" + "=" * 60, flush=True)
log(f"📊 {MODEL.upper()} — RESULTADOS FINALES (reasoning xhigh)", flush=True)
log("=" * 60, flush=True)
for k, label in [("gsm8k","GSM8K"),("arc_easy","ARC Easy"),("hellaswag","HellaSwag"),("piqa","PIQA")]:
    log(f"{label:10} {acc[k]['score']:.1f}%", flush=True)
log(f"{'AVERAGE(4)':10} {avg:.1f}%", flush=True)
log(f"{'HumanEval':10} {acc['humaneval']['score']:.1f}% pass@1", flush=True)
if pg:
    log(f"{'PPL geo':10} {pg:.4f}", flush=True)
log(f"⏱️  Tiempo total: {elapsed:.0f}s ({elapsed/60:.1f} min)", flush=True)
log(f"💾 {OUT}", flush=True)

#!/usr/bin/env python3
"""Suite DURA de contexto largo — multi-hop, distractores y 200k.

Complementa long_context_test.py (aguja simple + suma de 5 puntos) con:
  1. Needle-in-a-haystack a 200k tokens (20/50/80%) — el límite práctico del ctx 230k
  2. Multi-hop 3-sum a 140k: 3 importes REGISTRO-H dispersos (10/50/90%), hay que sumar los 3
  3. Multi-hop 4-sum a 200k: 4 importes en posiciones 8/35/62/89% — el más difícil
  4. Carga de distractores a 140k y 200k: 18 "PUNTO-DECIM: <número>" con formato
     idéntico esparcidos + 1 "REGISTRO FINALE: <código>" en el 50% — el modelo debe
     discriminar la etiqueta correcta entre 19 registros parecidos

Salida: results/long-context-hard-YYYYMMDD-HHMMSS.json
IMPORTANTE: ejecutar desde el mismo directorio que long_context_test.py (import).
"""
import json, random, datetime, pathlib
from long_context_test import (chat, medir_chars_por_token, construir_contexto,
                               BASE, MODEL, OUTDIR, NEEDLE, NEEDLE_ANSWER, PREG_NAGLE, log)

OUT = OUTDIR / f"long-context-hard-{datetime.datetime.now():%Y%m%d-%H%M%S}.json"

def main():
    log(f"Salida: {OUT}")
    cpl = medir_chars_por_token()
    resultados = {"fecha": datetime.datetime.now().isoformat(),
                  "modelo": MODEL, "base": BASE, "cpl_calibrado": round(cpl, 3),
                  "suite": "hard", "probes": []}

    def registrar(tag, contexto, tipo, pregunta, respuesta_ok, extra=None):
        content, reason, pt, fr, dt = chat([
            {"role": "system", "content": "Eres un asistente de extracción de información. Responde de forma exacta y concisa."},
            {"role": "user", "content": "Documento interno:\n" + contexto + "\n\n" + pregunta}],
            max_tokens=1024)
        rec = {"tipo": tipo, "tag": tag, "prompt_tokens": pt,
               "respuesta": (content or "").strip()[:300],
               "correcto": bool(respuesta_ok(content or "")),
               "finish_reason": fr, "segundos": round(dt, 1), "len_reasoning": len(reason or "")}
        if extra:
            rec.update(extra)
        resultados["probes"].append(rec)
        json.dump(resultados, open(OUT, "w"), ensure_ascii=False, indent=1)
        log(f"[{tag}] ctx={pt} tok | ok={rec['correcto']} | {fr} | {dt:.0f}s | {rec['respuesta'][:80]!r}")

    # ---------- 1. Aguja a 200k ----------
    for frac in [0.2, 0.5, 0.8]:
        rng = random.Random(5000 + int(frac * 100))
        ctx = construir_contexto(cpl, 204800, rng, [(frac, "\n" + NEEDLE + "\n")])
        registrar(f"nag200k-p{int(frac*100)}", ctx, "needle", PREG_NAGLE,
                  lambda c: NEEDLE_ANSWER in c, {"ctx_target": 204800, "profundidad": frac})

    # ---------- 2. Multi-hop 3-sum a 140k ----------
    target, rng = 143360, random.Random(7001)
    nums = [rng.randint(100, 999) for _ in range(3)]
    fracs = [0.10, 0.50, 0.90]
    insert = [(f, f"\nREGISTRO-H{i+1}: {n} (importe en euros, serie H)\n")
              for i, (f, n) in enumerate(zip(fracs, nums))]
    ctx = construir_contexto(cpl, target, rng, insert)
    p = ("El documento contiene 3 registros 'REGISTRO-H1', 'REGISTRO-H2' y 'REGISTRO-H3', cada uno "
         "con un importe en euros. Suma los 3 importes y responde únicamente con la suma, sin nada más.")
    registrar("multihop3-140k", ctx, "multi-hop", p,
              lambda c, s=sum(nums): str(s) in c, {"esperado": sum(nums), "numeros": nums})

    # ---------- 3. Multi-hop 4-sum a 200k ----------
    target, rng = 204800, random.Random(7101)
    nums = [rng.randint(100, 999) for _ in range(4)]
    fracs = [0.08, 0.35, 0.62, 0.89]
    insert = [(f, f"\nREGISTRO-H{i+1}: {n} (importe en euros, serie H)\n")
              for i, (f, n) in enumerate(zip(fracs, nums))]
    ctx = construir_contexto(cpl, target, rng, insert)
    p = ("El documento contiene 4 registros 'REGISTRO-H1' a 'REGISTRO-H4', cada uno con un importe "
         "en euros. Suma los 4 importes y responde únicamente con la suma, sin nada más.")
    registrar("multihop4-200k", ctx, "multi-hop", p,
              lambda c, s=sum(nums): str(s) in c, {"esperado": sum(nums), "numeros": nums})

    # ---------- 4. Carga de distractores ----------
    for target, seed in [(143360, 9001), (204800, 9101)]:
        rng = random.Random(seed)
        code = f"FINALE-{rng.randint(1000, 9999)}"
        decoys = [rng.randint(100, 999) for _ in range(18)]
        pos = sorted(rng.sample([round(x * 0.02, 2) for x in range(1, 50) if (x * 0.02) > 0.03 and (x * 0.02) < 0.97], 18))
        insert = [(f, f"\nPUNTO-DECIM: {d} (dado de control, serie decim)\n") for f, d in zip(pos, decoys)]
        insert.append((0.5, f"\nREGISTRO FINALE: {code} (código de cierre de ejercicio)\n"))
        ctx = construir_contexto(cpl, target, rng, insert)
        p = ("El documento contiene 18 registros 'PUNTO-DECIM' y 1 registro 'REGISTRO FINALE'. "
             "¿Cuál es el valor exacto del REGISTRO FINALE? Responde únicamente con el valor, sin nada más.")
        registrar(f"distractores-{target//1024}k", ctx, "distractores", p,
                  lambda c, k=code: k in c, {"esperado": code})

    # ---------- resumen ----------
    log("\n===== RESUMEN =====")
    log(f"{'tag':22s} {'ctx tok':>9s} {'ok':>4s} {'s':>6s}  respuesta")
    for p in resultados["probes"]:
        log(f"{p['tag']:22s} {str(p['prompt_tokens']):>9s} {str(p['correcto']):>4s} {str(p['segundos']):>6s}  {p['respuesta'][:60]}")
    ok = sum(1 for p in resultados["probes"] if p["correcto"])
    log(f"\n{ok}/{len(resultados['probes'])} correctos")
    json.dump(resultados, open(OUT, "w"), ensure_ascii=False, indent=1)
    log(f"Guardado: {OUT}")

if __name__ == "__main__":
    main()

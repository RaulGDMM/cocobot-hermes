#!/usr/bin/env python3
"""Prueba de degradación en contexto largo — llama-server OpenAI API.

Diseño:
  0. Calibración: medir chars/token del servidor real con usage.prompt_tokens
  1. Baseline: contexto corto (~4k) + aguja → sanity check del harness
  2. Needle-in-a-haystack: contextos 32k/64k/96k/140k/180k tokens × profundidad 20/50/80%
  3. Agregación: 5 números PUNTO dispersos en todo el contexto (64k, 140k) → el modelo
     debe leer TODO el contexto para sumar (no basta localizar un hecho)

Salida: results/long-context-YYYYMMDD-HHMMSS.json + tabla en consola.
"""
import json, random, time, urllib.request, datetime, pathlib, sys

BASE = "http://172.23.176.1:30000"
MODEL = "qwen3.8-27b"
OUTDIR = pathlib.Path("/mnt/e/Workspace/performance/results")
OUTDIR.mkdir(parents=True, exist_ok=True)
OUT = OUTDIR / f"long-context-{datetime.datetime.now():%Y%m%d-%H%M%S}.json"

NEEDLE = "CÓDIGO SECRETO: AZUL-DELFIN-42"
NEEDLE_ANSWER = "AZUL-DELFIN-42"

# ---------- filler determinista (apuntes de reuniones de una empresa ficticia) ----------
NOMBRES = ["Lucía", "Marcos", "Ana", "Pablo", "Carmen", "Diego", "Sofía", "Javier", "Elena", "Raúl"]
CIUDADES = ["Valencia", "Sevilla", "Bilbao", "Málaga", "Zaragoza", "Alicante", "Gijón", "Valladolid"]
PRODUCTOS = ["panel de inventario", "aplicación de pedidos", "portal de clientes", "servicio de notificaciones",
             "sistema de facturación", "módulo de logística", "app de catálogo", "sistema de reservas"]
METRICAS = ["tiempo de carga", "tasa de conversión", "error de sincronización", "latencia media",
            "consumo de memoria", "índice de satisfacción", "puntos de error", "cobertura de tests"]
AVERIGUA = [
    "En la reunión de {n1} se revisó la evolución del {p} en {c}. El equipo acordó priorizar {m1} y asignar a {n2} el seguimiento semanal de los datos. El informe mensual indicaba un comportamiento estable, sin desviaciones relevantes respecto al plan original. Se programó una revisión de requisitos para la próxima iteración, con participación del área de calidad y del equipo de soporte.",
    "El avance de {m1} en {c} se discutió con detalle: {n1} presentó las cifras del trimestre y concluyó que el objetivo global se mantiene, aunque hay margen de mejora en {m2}. Se decidió documentar el proceso completo y compartirlo con los equipos de {c2}. La siguiente sesión se dedicará a la revisión de dependencias y riesgos abiertos.",
    "Respecto al {p}, el equipo de {c} confirmó que las últimas versiones superan los criterios mínimos de calidad. {n2} propuso añadir una verificación automática de {m1} en el pipeline de despliegue, y el comité aceptó la propuesta con cambios menores. El seguimiento correspondiente quedará recogido en el tablero de planificación.",
    "La auditoría interna de {c} detectó dos incidencias menores en el {p}, ambas corregidas en la revisión siguiente. {n1} verificó el cierre de cada incidencia y archivó la evidencia en el repositorio de calidad. Se reforzó el protocolo de pruebas de {m1} para evitar que se repita el mismo tipo de fallo.",
    "El plan de formación de {c} incluye una sesión sobre buenas prácticas de {m2}, impartida por {n1}. El material quedó disponible en el wiki interno y la asistencia fue del noventa por ciento del equipo. Se valoró organizar un taller complementario centrado en {m1}, pendiente de confirmar fechas con los responsables de cada área.",
    "El comité de dirección revisó el estado del proyecto {p}: el hito de integración está en plazo y los recursos son suficientes. {n2} presentó el análisis de riesgos y propuesto un indicador adicional de {m1} para el panel de seguimiento. La decisión final sobre el alcance queda pendiente de la próxima reunión de partes interesadas.",
    "Las métricas de {m1} en {c} mostraron una mejora sostenida durante el último mes, dentro de lo previsto en el plan. {n1} compartió el desglose por módulo y se identificaron tres puntos de oportunidad en {m2}. Se acordó una experimentación controlada antes de generalizar los cambios al resto de {c2}.",
    "El análisis de la base de usuarios de {c} reveló patrones de uso estables en el {p}. {n2} preparó un resumen ejecutivo con las conclusiones principales y las propuso como base para la planificación del próximo trimestre. El equipo de datos validó las cifras con la fuente primaria antes de su publicación.",
]

def filler_parrafos(rng, n):
    out = []
    for _ in range(n):
        t = rng.choice(AVERIGUA)
        out.append(t.format(
            n1=rng.choice(NOMBRES), n2=rng.choice(NOMBRES),
            c=rng.choice(CIUDADES), c2=rng.choice(CIUDADES),
            p=rng.choice(PRODUCTOS), m1=rng.choice(METRICAS), m2=rng.choice(METRICAS)))
    return "\n\n" + "\n\n".join(out) + "\n\n"

# ---------- API ----------
def chat(messages, max_tokens=1024):
    body = json.dumps({"model": MODEL, "messages": messages,
                       "max_tokens": max_tokens, "temperature": 0}).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=1200) as r:
        data = json.loads(r.read())
    dt = time.time() - t0
    usage = data.get("usage") or {}
    msg = data["choices"][0]["message"]
    return (msg.get("content") or "", msg.get("reasoning_content") or "",
            usage.get("prompt_tokens"), data["choices"][0].get("finish_reason"), dt)

def log(msg):
    print(msg, flush=True)

# ---------- calibración chars/token ----------
def medir_chars_por_token():
    rng = random.Random(7)
    texto = filler_parrafos(rng, 8)  # ~5.6k chars
    _, _, pt, _, _ = chat([{"role": "user", "content": "Responde solo 'ok' a esta nota interna:\n" + texto}], 16)
    cpl = len(texto) / max(pt - 12, 1)  # resta cabeceras de plantilla ~12 tok
    log(f"Calibración: {pt} prompt_tokens / {len(texto)} chars -> {cpl:.2f} chars/token")
    return cpl

# ---------- construir contexto ----------
def construir_contexto(cpl, target_tokens, rng, insert):
    """insert: list de (frac_posicion, lineas_texto) insertadas en el contexto."""
    bloques = []
    acum = 0.0
    while acum < target_tokens * 1.02:
        b = filler_parrafos(rng, 3)
        bloques.append(b)
        acum += len(b) / cpl
    # concatenar todo e insertar (de atrás hacia adelante para no invalidar índices)
    todo = "".join(bloques)
    insert.sort(key=lambda x: x[0], reverse=True)
    for frac, texto in insert:
        idx = int(len(todo) * frac)
        todo = todo[:idx] + texto + todo[idx:]
    return todo

# ---------- probes ----------
def probe_needle(tag, contexto, pregunta):
    msgs = [{"role": "system", "content": "Eres un asistente de extracción de información. Responde de forma exacta y concisa."},
            {"role": "user", "content": "Documento interno:\n" + contexto + "\n\n" + pregunta}]
    return chat(msgs, max_tokens=1024)

PREG_NAGLE = "¿Cuál es el código secreto mencionado en el documento anterior? Responde únicamente con el código, sin nada más."

def main():
    log(f"Salida: {OUT}")
    cpl = medir_chars_por_token()
    resultados = {"fecha": datetime.datetime.now().isoformat(),
                  "modelo": MODEL, "base": BASE, "cpl_calibrado": round(cpl, 3), "probes": []}

    def registrar(tag, contexto, tipo, pregunta, respuesta_ok, extra=None):
        content, reason, pt, fr, dt = probe_needle(tag, contexto, pregunta)
        ok = respuesta_ok(content)
        rec = {"tipo": tipo, "tag": tag, "prompt_tokens": pt, "respuesta": content.strip()[:300],
               "correcto": bool(ok), "finish_reason": fr, "segundos": round(dt, 1),
               "len_reasoning": len(reason)}
        if extra:
            rec.update(extra)
        resultados["probes"].append(rec)
        json.dump(resultados, open(OUT, "w"), ensure_ascii=False, indent=1)
        log(f"[{tag}] ctx={pt} tok | ok={rec['correcto']} | {fr} | {dt:.0f}s | {content.strip()[:80]!r}")

    # 1. Baseline
    rng = random.Random(101)
    ctx = construir_contexto(cpl, 4096, rng, [(0.5, "\n" + NEEDLE + "\n")])
    registrar("base-4k", ctx, "needle", PREG_NAGLE, lambda c: NEEDLE_ANSWER in c)

    # 2. Needle-in-a-haystack
    for target in [32768, 65536, 98304, 143360, 184320]:
        for frac in [0.2, 0.5, 0.8]:
            rng = random.Random(hash((target, frac)) & 0xFFFF)
            ctx = construir_contexto(cpl, target, rng, [(frac, "\n" + NEEDLE + "\n")])
            registrar(f"nag-{target//1024}k-p{int(frac*100)}", ctx, "needle", PREG_NAGLE,
                      lambda c: NEEDLE_ANSWER in c, {"ctx_target": target, "profundidad": frac})

    # 3. Agregación: 5 números PUNTO dispersos, sumar todos
    for target in [65536, 143360]:
        rng = random.Random(2000 + target)
        nums = [rng.randint(100, 999) for _ in range(5)]
        fracs = sorted(rng.sample([0.08, 0.22, 0.37, 0.55, 0.71, 0.89, 0.95], 5))
        insert = [(f, f"\nPUNTO-{i+1}: {n} (registro contable, no es el código secreto)\n")
                  for i, (f, n) in enumerate(zip(fracs, nums))]
        ctx = construir_contexto(cpl, target, rng, insert)
        pregunta = ("El documento contiene 5 registros 'PUNTO-i: <número>'. Suma los 5 números y "
                    "responde únicamente con la suma, sin nada más.")
        registrar(f"suma-{target//1024}k", ctx, "agregacion", pregunta,
                  lambda c, s=sum(nums): str(s) in c, {"esperado": sum(nums), "numeros": nums})

    # resumen
    log("\n===== RESUMEN =====")
    log(f"{'tag':22s} {'ctx tok':>9s} {'ok':>4s} {'s':>6s}  respuesta")
    for p in resultados["probes"]:
        log(f"{p['tag']:22s} {str(p['prompt_tokens']):>9s} {str(p['correcto']):>4s} {str(p['segundos']):>6s}  {p['respuesta'][:60]}")
    json.dump(resultados, open(OUT, "w"), ensure_ascii=False, indent=1)
    log(f"\nGuardado: {OUT}")

if __name__ == "__main__":
    main()

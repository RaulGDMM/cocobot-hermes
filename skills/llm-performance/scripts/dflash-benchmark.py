#!/usr/bin/env python3
"""
Benchmark script for llama-server
Measures prompt processing speed and token generation speed
with short, medium, and long prompts.

Uses SERVER-REPORTED timings exclusively (no client wall-clock).
Includes:
  • Plain text generation (speculative decoding active)
  • Auto-wait when server is busy (Hermes agent using it)

Usage:
    python dflash-benchmark.py
    python dflash-benchmark.py --host localhost --port 8080
    python dflash-benchmark.py --runs 1 --max-tokens 256
    python dflash-benchmark.py --json-output results.json
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

# ─── Prompt templates ───────────────────────────────────────────────

SHORT_PROMPT = """Escribe un resumen de 3 líneas sobre la inteligencia artificial."""

# Medium: ~500-800 tokens
MEDIUM_PROMPT_TEMPLATE = """Analiza las siguientes noticias tecnológicas y proporciona un resumen estructurado con puntos clave, tendencias identificadas y predicciones a corto plazo:

{news_items}

Considera el impacto en el mercado, las implicaciones técnicas y las oportunidades para desarrolladores.
"""

# Long: ~5000-10000 tokens
LONG_PROMPT_TEMPLATE = """Eres un asistente de investigación especializada. Analiza el siguiente documento técnico extenso y proporciona:
1. Resumen ejecutivo
2. Puntos clave técnicos
3. Análisis de viabilidad
4. Comparativa con alternativas existentes
5. Recomendaciones

DOCUMENTO:
{technical_doc}

---

Además, genera un plan de implementación detallado con fases, estimaciones de tiempo y recursos necesarios.
"""


def generate_news_items(count: int) -> str:
    topics = [
        "OpenAI anuncia GPT-5 con capacidades multimodales mejoradas y razonamiento avanzado",
        "Google Gemini 2.5 supera benchmarks de razonamiento matemático con 94% de precisión",
        "Anthropic lanza Claude Opus 4 con ventana de contexto de 2 millones de tokens",
        "Meta open-source Llama 5 405B con licenciamiento comercial completo",
        "NVIDIA revela la arquitectura Blackwell 2 con 200GB HBM3e por GPU",
        "Apple integra modelo de 70B nativo en iOS 22 con inferencia on-device",
        "Microsoft Copilot++ obtiene acceso directo al sistema de archivos y ejecución de código",
        "Mistral AI presenta Mixtral 8x256B MoE con eficiencia energética récord",
        "xAI Grok-3 integra búsqueda web en tiempo real con verificación de fuentes",
        "Qwen 3.0 de Alibaba alcanza paridad con GPT-5 en benchmarks multilingües",
    ]
    items = []
    for i in range(count):
        topic = topics[i % len(topics)]
        items.append(
            f"Noticia {i+1}: {topic}\n"
            f"  Fecha: 15 de mayo de 2026\n"
            f"  Categoría: IA/ML\n"
            f"  Impacto: Alto\n"
            f"  Detalles: Esta noticia representa un avance significativo en el campo. "
            f"Los expertos señalan que las implicaciones son profundas y afectarán "
            f"a múltiples sectores industriales. Se espera que los próximos trimestres "
            f"vean una adopción masiva de estas tecnologías por parte de empresas "
            f"tanto grandes como pequeñas. Los analistas predicen un crecimiento del "
            f"mercado estimado en billones de dólares para 2027.\n\n"
        )
    return "\n".join(items)


def generate_technical_doc(chapters: int) -> str:
    sections = []
    for ch in range(chapters):
        sections.append(
            f"## Capítulo {ch+1}: Arquitectura del Sistema\n\n"
            f"Este capítulo describe la arquitectura del módulo {ch+1} del sistema. "
            f"El diseño sigue patrones de microservicios con comunicación asíncrona "
            f"basada en eventos. Cada componente está containerizado y desplegado en "
            f"Kubernetes con auto-scaling configurado.\n\n"
            f"### Componentes principales\n\n"
            f"1. **API Gateway**: Maneja la autenticación, rate limiting y routing de requests.\n"
            f"2. **Service Mesh**: Implementa mTLS entre servicios con Istio.\n"
            f"3. **Message Queue**: Apache Kafka con 12 partitions y replication factor 3.\n"
            f"4. **Database**: PostgreSQL 16 con partitioning por rango de fecha.\n"
            f"5. **Cache Layer**: Redis Cluster con 6 nodos y sentinel configuration.\n"
            f"6. **Object Storage**: S3-compatible bucket para artifacts y modelos.\n\n"
            f"### Especificaciones técnicas\n\n"
            f"- Latencia p99: < 50ms para operaciones de lectura\n"
            f"- Throughput: 10,000 requests/second por instancia\n"
            f"- Availability: 99.99% SLA con multi-AZ deployment\n"
            f"- Data retention: 90 días para logs, 1 año para métricas\n"
            f"- Backup strategy: Incremental daily + full weekly con cross-region replication\n\n"
            f"### Consideraciones de seguridad\n\n"
            f"Todos los datos sensibles están encriptados en tránsito (TLS 1.3) y en reposo "
            f"(AES-256). Las credenciales se gestionan mediante HashiCorp Vault con rotation "
            f"automática cada 24 horas. El acceso sigue el principio de mínimo privilegio con "
            f"RBAC granular y audit logging completo.\n\n"
        )
    return "\n".join(sections)


# ─── Data structures ────────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    label: str
    prompt_tokens: int
    generated_tokens: int
    prompt_ms: float
    predicted_ms: float
    prompt_tps: float
    predicted_tps: float
    total_time_ms: float
    # Speculative decoding stats (from server response)
    spec_accepted: Optional[int] = None
    spec_attempted: Optional[int] = None
    spec_acceptance_rate: Optional[float] = None
    # Per-token timing data
    timings_per_token: list = field(default_factory=list)

    @property
    def spec_str(self) -> str:
        if self.spec_accepted is None or self.spec_attempted is None:
            return "N/A"
        return f"{self.spec_accepted}/{self.spec_attempted} ({self.spec_acceptance_rate:.1f}%)"


# ─── Server idle detection ──────────────────────────────────────────

def check_server_queue(base_url: str) -> dict:
    """Check if server has pending tasks in queue."""
    try:
        req = urllib.request.Request(f"{base_url}/queue")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


def wait_for_server_idle(base_url: str, max_wait: int = 300, poll_interval: float = 3.0) -> bool:
    """Wait until server queue is empty. Returns True if idle, False if timeout."""
    deadline = time.time() + max_wait

    while time.time() < deadline:
        queue = check_server_queue(base_url)
        if isinstance(queue, dict):
            size = queue.get("size", 0) or queue.get("n_tasks", 0) or 0
        elif isinstance(queue, list):
            size = len(queue)
        else:
            size = 0

        if size == 0:
            return True

        remaining = int(deadline - time.time())
        print(f"   ⏳ Servidor ocupado ({size} tareas en cola). "
              f"Esperando... ({remaining}s restantes)", end="\r", flush=True)

        time.sleep(poll_interval)

    print(f"\n   ⚠️ Timeout esperando servidor idle después de {max_wait}s")
    return False


# ─── Core benchmark logic ───────────────────────────────────────────

def make_completion_request(base_url: str, prompt: str, max_tokens: int,
                            temperature: float = 0.0) -> dict:
    """Send /completion request to llama-server."""
    payload = {
        "prompt": prompt,
        "n_predict": max_tokens,
        "temperature": temperature,
        "top_k": 1,          # deterministic for benchmarking
        "stream": False,
        "cache_prompt": False,  # cold cache for fair comparison
        "timings_per_token": True,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/completion",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"\n  ❌ Error de conexión: {e}", file=sys.stderr)
        raise


def parse_result(response: dict, label: str) -> BenchmarkResult:
    """Parse /completion response into BenchmarkResult using SERVER timings."""
    timings = response.get("timings", {})

    prompt_n = timings.get("prompt_n", 0)
    prompt_ms = timings.get("prompt_ms", 0.0)
    predicted_n = timings.get("predicted_n", 0)
    predicted_ms = timings.get("predicted_ms", 0.0)

    prompt_tps = (prompt_n / (prompt_ms / 1000)) if prompt_ms > 0 else 0
    predicted_tps = (predicted_n / (predicted_ms / 1000)) if predicted_ms > 0 else 0
    total_ms = prompt_ms + predicted_ms

    # Speculative decoding stats
    # New llama.cpp: draft_n / draft_n_accepted directly in timings
    # Old llama.cpp: per-token speculative field in timings_per_token
    tpt_list = response.get("timings_per_token", [])
    spec_accepted = timings.get("draft_n_accepted", 0)
    spec_attempted = timings.get("draft_n", 0)

    # Fallback: old format from timings_per_token
    if spec_attempted == 0:
        for t in tpt_list:
            spec = t.get("speculative", {})
            if spec:
                spec_accepted += spec.get("accepted", 0)
                spec_attempted += spec.get("attempted", 0)

    acceptance_rate = (spec_accepted / spec_attempted * 100) if spec_attempted > 0 else None

    return BenchmarkResult(
        label=label,
        prompt_tokens=prompt_n,
        generated_tokens=predicted_n,
        prompt_ms=prompt_ms,
        predicted_ms=predicted_ms,
        prompt_tps=prompt_tps,
        predicted_tps=predicted_tps,
        total_time_ms=total_ms,
        spec_accepted=spec_accepted if spec_attempted > 0 else None,
        spec_attempted=spec_attempted if spec_attempted > 0 else None,
        spec_acceptance_rate=acceptance_rate,
        timings_per_token=tpt_list,
    )


def run_benchmark(base_url: str, prompt: str, label: str,
                  max_tokens: int, runs: int,
                  wait_idle: bool = True) -> list[BenchmarkResult]:
    """Run completion benchmark using server-reported timings."""
    results = []
    estimated_tokens = len(prompt.split()) * 1.3

    print(f"\n{'='*70}")
    print(f"  🧪 {label}")
    print(f"     Prompt: ~{estimated_tokens:.0f} tokens | Gen: {max_tokens} tokens | Runs: {runs}")
    print(f"{'='*70}")

    for run in range(1, runs + 1):
        # Wait for server idle before each run
        if wait_idle and run > 1:
            print(f"  ⏳ Esperando servidor idle... ", end="", flush=True)
            if wait_for_server_idle(base_url, max_wait=120):
                print("✅ Libre")
            else:
                print("⚠️ Sigue ocupado, intentando de todas formas")

        print(f"  Run {run}/{runs}... ", end="", flush=True)

        try:
            resp = make_completion_request(base_url, prompt, max_tokens)
            result = parse_result(resp, f"{label} (run {run})")
            results.append(result)

            # Print ONLY server-reported data
            spec_info = f" | spec: {result.spec_str}" if result.spec_accepted else ""
            print(f"✅ {result.predicted_tps:.1f} tok/s "
                  f"(prompt: {result.prompt_tps:.0f} tok/s, "
                  f"gen: {result.generated_tokens} tokens, "
                  f"server: {result.total_time_ms:.0f} ms{spec_info})")
        except Exception as e:
            print(f"❌ Failed: {e}")

    return results


# ─── Table output ───────────────────────────────────────────────────

def print_results_table(all_results: list[BenchmarkResult]):
    """Print a clean summary table with server-reported timings."""
    print(f"\n{'='*80}")
    print("  📊 RESULTADOS (timings reportados por el servidor)")
    print(f"{'='*80}")
    print(f"{'Test':<25} {'Prompt':>8} {'Gen':>6} {'Prompt TPS':>11} {'Gen TPS':>9} {'Spec':>12} {'Total ms':>10}")
    print(f"{'─'*80}")

    for r in all_results:
        label = r.label.replace(" (run 1)", "").replace(" (run 2)", "").replace(" (run 3)", "")
        if "run" in r.label:
            label = r.label
        print(f"{label:<25} {r.prompt_tokens:>8} {r.generated_tokens:>6} "
              f"{r.prompt_tps:>10.1f} {r.predicted_tps:>8.1f} "
              f"{r.spec_str:>12} {r.total_time_ms:>9.0f}")

    print(f"{'─'*80}")
    print("  Nota: Todos los valores son timings internos del servidor (sin overhead de red/serialización)")
    print(f"{'='*80}\n")


def save_json(results: list[BenchmarkResult], path: str):
    """Save results to JSON."""
    data = []
    for r in results:
        data.append({
            "label": r.label,
            "prompt_tokens": r.prompt_tokens,
            "generated_tokens": r.generated_tokens,
            "prompt_ms": r.prompt_ms,
            "predicted_ms": r.predicted_ms,
            "prompt_tps": r.prompt_tps,
            "predicted_tps": r.predicted_tps,
            "total_time_ms": r.total_time_ms,
            "spec_accepted": r.spec_accepted,
            "spec_attempted": r.spec_attempted,
            "spec_acceptance_rate": r.spec_acceptance_rate,
        })
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"💾 Resultados guardados en {path}")


# ─── Main ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Benchmark llama-server")
    parser.add_argument("--host", default="172.23.176.1", help="Server host")
    parser.add_argument("--port", type=int, default=30000, help="Server port")
    parser.add_argument("--runs", type=int, default=1, help="Runs per test (default: 1)")
    parser.add_argument("--max-tokens", type=int, default=256, help="Max tokens to generate")
    parser.add_argument("--json-output", help="Save results to JSON file")
    parser.add_argument("--no-wait", action="store_true", help="Don't wait for server idle")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    # Health check
    try:
        req = urllib.request.Request(f"{base_url}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            health = json.loads(resp.read().decode("utf-8"))
        print(f"🟢 Servidor OK: {health.get('status', 'unknown')}")
    except Exception as e:
        print(f"❌ No se puede conectar al servidor: {e}")
        sys.exit(1)

    all_results = []

    # Short prompt
    results = run_benchmark(
        base_url, SHORT_PROMPT, "Texto corto",
        args.max_tokens, args.runs, wait_idle=not args.no_wait
    )
    all_results.extend(results)

    # Medium prompt
    medium_prompt = MEDIUM_PROMPT_TEMPLATE.format(news_items=generate_news_items(5))
    results = run_benchmark(
        base_url, medium_prompt, "Texto medio",
        args.max_tokens, args.runs, wait_idle=not args.no_wait
    )
    all_results.extend(results)

    # Long prompt
    long_prompt = LONG_PROMPT_TEMPLATE.format(technical_doc=generate_technical_doc(3))
    results = run_benchmark(
        base_url, long_prompt, "Texto largo",
        args.max_tokens, args.runs, wait_idle=not args.no_wait
    )
    all_results.extend(results)

    # Summary table
    print_results_table(all_results)

    # Save JSON
    if args.json_output:
        save_json(all_results, args.json_output)


if __name__ == "__main__":
    main()

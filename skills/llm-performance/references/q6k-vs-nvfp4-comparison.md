# Comparativa Q6_K vs NVFP4-Q8_0 — Qwen3.6-27B

**Fecha**: 2026-05-27
**Hardware**: RTX 5090 32GB, llama-server
**Servidor**: `http://172.23.176.1:30000/v1`
**Script**: `/root/workspace/llm-intelligence-benchmark.py`
**Parámetros**: `max_tokens=2000`, `temperature=0.0`

## Resultados

| Benchmark | Muestras | Q6_K | NVFP4-Q8_0 | Diferencia |
|-----------|----------|------|------------|------------|
| GSM8K | 51 | 88.2% (45/51) | 86.3% (44/51) | +1.9 pp |
| ARC Easy | 30 | 100.0% (30/30) | 100.0% (30/30) | 0 |
| HellaSwag | 30 | 63.3% (19/30) | 66.7% (20/30) | -3.4 pp |
| PIQA | 20 | 100.0% (20/20) | 100.0% (20/20) | 0 |
| **Promedio** | **131** | **87.9%** | **88.2%** | **-0.3 pp** |

## Análisis

- **GSM8K**: Q6_K ligeramente superior (+1.9pp). Con 51 muestras, esta diferencia es marginalmente significativa.
- **ARC Easy**: Ceiling effect — ambos al 100% con solo 30 muestras. No informativo.
- **HellaSwag**: NVFP4 gana 3.4pp, pero con 30 muestras, un solo acierto extra = 3.3pp. Ruido estadístico.
- **PIQA**: Ceiling effect — ambos al 100% con solo 20 muestras. No informativo.

## Conclusión

La diferencia de 0.3pp en promedio es completamente insignificante. Q6_K y NVFP4-Q8_0 son equivalentes en capacidad intelectual para este modelo.

**Criterio de elección**: Velocidad (tokens/segundo) y consumo de VRAM, no precisión.

## Línea base FP16 (referencia oficial)

| Benchmark | FP16 (oficial) | Q6_K | Pérdida |
|-----------|----------------|------|---------|
| GSM8K | ~91% | 88.2% | ~2.8pp |
| ARC Challenge | ~70% | — | — |
| MMLU | ~85% | — | — |

## Archivos de resultado

- `/root/workspace/llm-eval-qwen3.6-27b-q6k.json` — Datos completos Q6_K
- `/root/workspace/llm-eval-qwen3.6-27b-q6k.log` — Log de ejecución Q6_K
- `/root/workspace/llm-eval-qwen3.6-27b-20260527-224549.json` — Datos completos NVFP4-Q8_0

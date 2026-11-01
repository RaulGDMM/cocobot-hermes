# HumanEval Integration Notes

## Qué mide
HumanEval evalúa **capacidad de generación de código Python**. 164 problemas hand-crafted con assertions de test. Métrica: **pass@1** — ¿cuántas funciones pasan todas las assertions a la primera?

## Dataset
- Fuente: OpenAI, `openai/human-eval` en GitHub
- Formato: JSONL con campos `task_id`, `prompt`, `canonical_solution`, `test`, `entry_point`
- Descargar: `curl -sL "https://github.com/openai/human-eval/raw/master/data/HumanEval.jsonl.gz" | gunzip > HumanEval.jsonl`
- Copiar a `references/HumanEval.jsonl` dentro de esta skill

## ⚠️ Pitfall: Extracción de código del modelo

Los modelos con thinking (Qwen3.5/3.6, DeepSeek) generan explicaciones extensas ANTES del código. El prompt "Return ONLY the code" NO es suficiente — el modelo sigue explicando.

### Estrategia de extracción (orden de prioridad):

1. **Bloques ```python**: Buscar con `re.findall(r'```(?:python|py)?\s*\n(.*?)```', code, re.DOTALL)`
2. **Definición de función**: Si no hay bloques, buscar `def entry_point(` en la respuesta y extraer desde ahí
3. **Fallback**: Strip markdown wrappers si ninguno de los anteriores funciona

### Código de extracción:
```python
code = response.strip()
# Strategy 1: Find ```python code blocks
code_blocks = re.findall(r'```(?:python|py)?\s*\n(.*?)```', code, re.DOTALL)
if code_blocks:
    code = code_blocks[0].strip()
else:
    # Strategy 2: Find the function definition
    func_pattern = rf'def\s+{re.escape(entry_point)}\s*\('
    match = re.search(func_pattern, code)
    if match:
        code = code[match.start():]
    else:
        # Strategy 3: Strip markdown wrappers
        code = re.sub(r'^```(?:python|py)?\s*\n?', '', code, flags=re.IGNORECASE)
        code = re.sub(r'\n?```\s*$', '', code)
        code = code.strip()
```

## Ejecución de código
- Usar `subprocess.run(["python3", "-c", full_code], capture_output=True, timeout=30)`
- **NUNCA** usar `eval()` — seguridad y aislamiento
- Timeout de 30s por problema (algunos pueden entrar en bucle infinito)
- Verificar `proc.returncode == 0` para pass/fail

## Línea base FP16
- Qwen3.6-27B: ~82-85% pass@1 (referencia del paper/leaderboard)
- Modelos 7B: ~50-60%
- Modelos 70B+: ~90%

## Benchmark relacionado
- **MBPP**: 300 problemas Python más simples (alternativa más fácil)
- **HumanEval+**: Versión con tests adicionales más estrictos
- **SWE-bench**: Resolver issues reales de GitHub (mucho más complejo, requiere sandbox)

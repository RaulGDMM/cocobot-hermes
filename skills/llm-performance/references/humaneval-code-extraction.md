# HumanEval Code Extraction — Debugging Workflow

## Problem

When evaluating code generation with HumanEval, the model's raw response is **not** clean Python code. It contains:
- Explanations and reasoning before the code
- Markdown code blocks (```python ... ```)
- Sometimes multiple code blocks
- Sometimes NO code blocks at all (just inline code)

## Three-Strategy Extraction (in order of priority)

### Strategy 1: Markdown code blocks
```python
code_blocks = re.findall(r'```(?:python|py)?\s*\n(.*?)```', code, re.DOTALL)
if code_blocks:
    code = code_blocks[0].strip()
```
**Works for**: Models that output clean ```python blocks (most models with `--format json` or explicit code-only prompts).

### Strategy 2: Function definition anchor
```python
func_pattern = rf'def\s+{re.escape(entry_point)}\s*\('
match = re.search(func_pattern, code)
if match:
    code = code[match.start():]
```
**Works for**: Models that output explanations before code (Qwen3.6, DeepSeek). This is the **most reliable** strategy because it finds the actual function definition regardless of surrounding text.

### Strategy 3: Markdown stripping (fallback)
```python
code = re.sub(r'^```(?:python|py)?\s*\n?', '', code, flags=re.IGNORECASE)
code = re.sub(r'\n?```\s*$', '', code)
code = code.strip()
```
**Works for**: Edge cases where code blocks are malformed or missing closing backticks.

## Key Finding: Qwen3.6 Models

Qwen3.6-27B with `reasoning_content` does NOT use ```python code blocks by default. It outputs:
1. Long reasoning/explanation (in `reasoning_content`)
2. Sometimes more explanation in `content`
3. Then the actual function definition

**Strategy 2 (function anchor) is essential** for these models. Strategy 1 alone fails ~20% of the time.

## Execution

After extraction, execute in isolated subprocess:
```python
full_code = f"""{prompt}{code}\n\n{test_code}\n\ncheck({entry_point})"""
proc = subprocess.run(
    ["python3", "-c", full_code],
    capture_output=True,
    text=True,
    timeout=30,
)
is_correct = proc.returncode == 0
```

## Pitfalls

- **`subprocess.run` timeout**: 30s is generous. If a model generates an infinite loop, the process hangs. Always use `timeout=30`.
- **`python3 -c` vs file**: `-c` is simpler but has no filename for error messages. Use a temp file if you need better error reporting.
- **Prompt duplication**: The `prompt` already contains the function signature. The model's response may repeat it. The function anchor strategy handles this correctly by finding the definition in the response.

## Result

With all three strategies, HumanEval extraction succeeds for ~100% of cases. Without Strategy 2, Qwen3.6 models fail ~20% of cases with SyntaxError from explanation text.

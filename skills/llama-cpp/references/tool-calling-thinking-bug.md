# Tool Calls Inside Thinking Blocks — Qwen3.5/3.6

**Session**: 2026-05-01  
**Model**: Qwen3.6-27B Q4_K_XL (Unsloth) + Qwen3.5 variants  
**Status**: Known upstream bug, partially addressed, not fully fixed

## Symptom

Model generates tool call XML (`<tool_call>...`) **inside** the `<think>` reasoning block instead of after `</think>`. The PEG parser receives the entire output including thinking text, fails to parse, and the model stops generating.

Visual: the tool call appears "printed" as text within the thinking block rather than executed as a structured tool call.

## Root Cause (two layers)

1. **Model behavior**: Qwen3.5/3.6 sometimes emits tool calls during reasoning phase — "preparing" a tool call while still thinking.

2. **llama.cpp parser**: The lazy grammar trigger detects `<tool_call>` and constrains generation, forcing `<eog>` (end of generation). The model cannot generate `</think>` to close the thinking block. The PEG parser then fails because it receives the full output (thinking text + tool call) but expects `root ::= tool-call`.

## Affected Models

- Qwen3.5-9B, 27B, 35B-A3B, 122B-A10B
- Qwen3.6-27B, 35B-A3B
- Also reported with GLM-4.7-Flash
- **Also happens in vLLM** — not exclusively llama.cpp; partially a model training behavior

## Open Issues

| Issue | Title | State |
|-------|-------|-------|
| [#20837](https://github.com/ggerganov/llama.cpp/issues/20837) | Qwen3.5 9B prints tool calls in XML and stops when thinking enabled | OPEN |
| [#20260](https://github.com/ggerganov/llama.cpp/issues/20260) | peg-native parser fails when model outputs text before `<![CDATA[<tool_call>]]>` | OPEN |
| [#22398](https://github.com/ggerganov/llama.cpp/issues/22398) | Qwen3.6 27B answers in think tags, strange stops in agentic workloads | OPEN |

## Closed/Partial Fixes

| PR/Issue | Build | What it does |
|----------|-------|--------------|
| PR [#20970](https://github.com/ggerganov/llama.cpp/pull/20970) | ~8560+ | Inhibits lazy grammar sampler while reasoning is active |
| #21158 | closed 2026-03-29 | Qwen3.5-27B specific fix (superseded by #20970) |

## Workarounds

| Workaround | Effect | Trade-off |
|------------|--------|-----------|
| `--reasoning-format none` | Keeps `<think>` tags but doesn't send as `reasoning_content`. Model receives its thinks as normal text in subsequent turns, reducing disorientation. | Tags visible in output; multi-turn reasoning_content handling changes |
| `--chat-template-kwargs '{"enable_thinking": false}'` | Eliminates thinking blocks entirely | **Loses all reasoning capability** — not recommended |
| Custom chat templates (e.g., qwen3-coder.jinja) | More explicit separation between thinking and tool_calls | Requires manual template management |
| `reasoning_effort: high` (Hermes config) | Reduces thinking budget → fewer chances for model to "get lost" | Less reasoning depth than `xhigh` |
| "Continúa" prompt | Unblocks stalled generation | Manual intervention required |

## Key Technical Finding (from #20837 discussion by @pwilkin, @aldehir)

> "The grammar trigger is independent from the reasoning parser and the grammar forces `<eog>` when it's done reading what it considers a tool call, so the model can't generate further (it should close the thinking block and redo the tool call properly within the normal content block)."

The fix requires either:
- Accepting tool calls within thinking blocks (like vLLM does)
- Preventing grammar triggers from activating inside reasoning blocks (PR #20970 approach)

## Client-Side Consideration

The problem worsens if the client (Hermes, Zed, etc.) doesn't return `reasoning_content` correctly in multi-turn agentic loops. When thinking content is dropped or merged into regular content, the model becomes disoriented about where it left off.

## Verification

To check if a llama.cpp build includes the fix:
```bash
llama-server --version
# Build 8560+ should include PR #20970
```

To check Hermes config:
```yaml
# ~/.hermes/config.yaml
agent:
  reasoning_effort: xhigh  # Consider lowering to "high" if issue persists
```

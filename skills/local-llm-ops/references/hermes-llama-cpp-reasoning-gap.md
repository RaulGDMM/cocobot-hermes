# Hermes ↔ llama.cpp reasoning_effort gap

Session findings, 2026-08-19 (Raúl's WSL + Windows llama-server, RTX 5090).

> **STATUS UPDATE 2026-09-01 (Hermes 0.20.6): the "dead config" below is OUTDATED.**
> The custom llama-server provider now carries `extra_body.chat_template_kwargs`
> (`{"reasoning_effort": ...}`) resolved through `resolve_runtime_provider()` →
> `request_overrides` on the gateway path. `agent.reasoning_effort` (global) and
> `/reasoning <level>` DO reach the server, verified empirically: after
> `/reasoning max` on Telegram, every request carried `max` and died in the
> template with the Jinja 500; setting global `agent.reasoning_effort: xhigh`
> (via `hermes config set`) changed the effort live. The old
> `_supports_reasoning_extra_body()` dead-config note applies to older versions
> only — re-verify against the installed source if behavior looks off again.
>
> **Valid levels, live-probed 2026-09-01 (qwen3.8-27b UD-Q6_K GGUF, current
> template):** `xhigh`, `high`, `medium`, `low` → 200 OK. `max`, `ultra`,
> `none`, anything else → 500 `Jinja Exception: Unexpected reasoning effort
> <X>. Supported types are xhigh (default), medium, and low.` The error message
> UNDER-REPORTS the accepted set (it omits `high`, which works) — always probe
> per level. Probe:
> ```bash
> for EFF in max xhigh high medium low none; do
>   curl -s -m 60 http://<host>:30000/v1/chat/completions -H 'Content-Type: application/json' \
>     -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"responde solo: OK"}],"max_tokens":6,"chat_template_kwargs":{"reasoning_effort":"'$EFF'"}}' \
>   | python3 -c "import json,sys; d=json.load(sys.stdin); print('ERROR' if 'error' in d else 'OK')"
> done
> ```
>
> **Session-scoped vs global `/reasoning`:** `/reasoning <level>` WITHOUT
> `--global` writes only the in-memory `SessionState.conversation.reasoning_override`
> (gateway process memory, NOT state.db) — a gateway restart clears it. That is
> also the cleanest recovery from a broken session effort: restart the gateway.
> `--global` persists to `config.yaml` (`agent.reasoning_effort`) and survives
> restarts — if the global is a bad level, fix it with
> `hermes config set agent.reasoning_effort xhigh`.
>
> **`show_reasoning` display on Telegram (gateway run.py, 0.20.6):** the
> reasoning block (💭 fenced, collapsed at 15 lines) is prepended to the FINAL
> message in the non-streamed path only. With `display.platforms.telegram.streaming: true`
> the body is delivered live (`already_sent=True`) and the prepend is silently
> dropped — the user sees no reasoning even though `show_reasoning: true` is set.
> To surface reasoning on Telegram: set that platform's `streaming: false`.
> Verify the model is actually thinking independent of display:
> `sqlite3 ~/.hermes/state.db "SELECT role, length(reasoning) FROM messages WHERE session_id='<id>' ORDER BY id DESC LIMIT 5;"`
> non-empty `reasoning` = it works.

## Key fact (verified in Hermes source, 2026-08-19)

Hermes `agent.reasoning_effort` (config.yaml) and the `/reasoning [level]` slash command only matter when the transport emits a reasoning field in the request. The gate is `run_agent.py::AIAgent._supports_reasoning_extra_body()`:

- OpenRouter (live catalog / known prefixes), GitHub Models, LM Studio (capability probe), Ollama Cloud (thinking capability probe) → reasoning IS emitted.
- **Custom OpenAI-compatible endpoints (`provider: custom:*`, e.g. local `llama-server`) → returns False; nothing is sent.** No error — silently ignored.

So `agent.reasoning_effort: xhigh` in config and `/reasoning medium` in the TUI are **dead config** for a local llama.cpp server. The real lever is llama.cpp-side: the Qwen3.8 chat template reads `reasoning_effort` from **chat_template_kwargs**.

## How to control it

1. **Server default (applies to ALL clients: Hermes, OpenWebUI, curl)**
   - `llama-server --chat-template-kwargs '{"enable_thinking":true,"reasoning_effort":"medium"}'` or env `LLAMA_CHAT_TEMPLATE_KWARGS`.
   - `--reasoning-effort medium` also reported as a server-wide default in newer builds (Qwen3.8 HF discussion).
   - Changing requires llama-server restart (model reload = minutes on a 5090). Not viable for live switching.
2. **Per-request override** (chat completions body):
   ```json
   {"messages": [...], "chat_template_kwargs": {"reasoning_effort": "low"}}
   ```
   Documented (Qwen HF discussion #113, llama.cpp discussion #20408): llama-server passes non-standard kwargs through `--chat-template-kwargs` to the template.
3. **Hard off**: `chat_template_kwargs: {"enable_thinking": false}` — more robust than `reasoning_effort: "off"`.

## Qwen3.8-27B: valid levels

Template accepts ONLY: `xhigh`, `medium`, `low`, `off`.
`minimal`, `high`, `max` make the template throw an error on every request (server starts fine, then all requests fail — confusing first hit).

Community measurements (HF discussion `Qwen/Qwen3.8-27B#113`):

| level | thinking tokens | wait before answer |
|---|---|---|
| xhigh (default) | 106 | 1.44 s |
| medium | 91 | 0.92 s (~1/3 less, no measured quality drop) |
| low | 78 | 1.21 s |
| off | 0 | 0.21 s (~10x) |

Shorter thinking is also faster per token (less for the MTP draft head to predict).

## Making Hermes's live toggle work (analyzed options, unimplemented)

Goal: `/reasoning off|low|medium|xhigh` works live against a local llama-server, default medium.

- **A. No code change**: server default `medium` in the launcher script + `providers.<name>.extra_body` in `config.yaml` for a static override. Limitation: `extra_body` is static — it cannot follow `/reasoning` changes; switching = config edit + process restart.
- **B. Small Hermes patch** (~10–15 lines in `agent/transports/chat_completions.py`): when `detect_local_server_type(base_url) == "llamacpp"` and `reasoning_config` is set, build `extra_body["chat_template_kwargs"]` with the FULL dict (`enable_thinking`, `preserve_thinking`, `reasoning_effort` — or `enable_thinking: false` for off, in case llama.cpp replaces rather than merges kwargs). Then `/reasoning` works per-session, per-request. **NOT yet implemented** — patch pending user approval. Re-apply needed after `hermes update` rewrites the file (or vendor it).
- **C. Restart llama-server per change**: impractical (model reload), rejected.

## Environment notes (Raúl's setup)

- Active launcher: `/mnt/e/Workspace/Hermes/start-hermes.ps1`. The `/root/workspace/cocobot-hermes/` copy is a STALE clone still targeting qwen36 — always use the E: copy.
- qwen38 profile currently: `--jinja`, no `--chat-template-file` (native template), `--reasoning on`, `--reasoning-preserve`, `LLAMA_CHAT_TEMPLATE_KWARGS='{"enable_thinking":true,"preserve_thinking":true,"reasoning_effort":"xhigh"}'` → this is where the "xhigh" actually comes from.
- OpenWebUI (port 8080) shares the same llama-server → any global default belongs server-side, not in Hermes config.

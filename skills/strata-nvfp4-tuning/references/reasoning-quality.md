# Reasoning quality: repeated / stereotyped thinking

Symptom: in long Hermes sessions the model's thinking collapses to a short stock phrase repeated across turns ("It's a pure logic question.", "I need to investigate this further. Let me check the details"), usually on trivial steps between tool calls.

## Diagnose before proposing a fix
1. Quantify in Hermes `state.db` (column is `reasoning_content`/`reasoning`, NOT `finish_reason`):
   ```python
   rows=c.execute("select m.session_id, coalesce(nullif(m.reasoning_content,''),m.reasoning) r from messages m where m.role='assistant' and r!='' order by m.id desc limit 600")
   collections.Counter(r.strip()[:70] for _,r in rows).most_common(10)
   ```
   Also compare across models (`join sessions s ... where s.model=?`) and find the turn index where the phrase first appears in the worst session.
2. Check `strata.log` for `repeated reasoning detected` (in-reply loop detector). Zero hits = cross-turn self-imitation, not a degenerate in-reply loop.
3. Check effective sampling: `config/cocobot.json` `sampling` block applies whenever the client sends none (Hermes sends no temperature for custom:strata). Request values override config.

## Findings that hold
- Strata's `serve/chat_template.jinja` is the official Qwen template (byte-identical to llama.cpp's); `preserve_thinking` undefined = ON, and Hermes replays `reasoning_content` to `custom` providers. The retired 27B on llama.cpp had the same setup and the same stock-phrase habit — so preserve_thinking is NOT what differs between engines.
- Official Qwen3.8-Flash-Next thinking sampling: temperature 1.0, top_p 0.95, top_k 20, presence 0. Our config ran 0.6; low temperature makes the model copy what dominates context. First lever = official temperature 1.0; second = presence_penalty 0.5-1.0 (community mitigation, deviates from official).
- Degradation grows past ~140K context / hundreds of turns: advise compaction or a new session per milestone.

## User preference
Do NOT propose disabling `preserve_thinking` as the fix: Raúl treats it as a model capability (agentic gain since Qwen3.6). Only consider it as a last resort, stating the capability loss. When he pushes back with "but on engine X it didn't happen", verify that claim against data (state.db per-model counts) and search online before defending the first hypothesis.

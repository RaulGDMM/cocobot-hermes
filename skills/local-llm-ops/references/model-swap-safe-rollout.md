# Swapping the model GGUF for a new version/quant (safe rollout)

Session: 2026-08-23 — Qwen3.8-27B Unsloth Q6_K → Dynamic 3.0 `UD-Q6_K` (repo restructured, MTP now also shipped as a separate file). General procedure + the traps hit.

## When
User wants to replace the running model GGUF with a newer quant/version (e.g. "descarga la nueva versión y sustitúyela, sin borrar la actual todavía").

## Workflow
1. **Re-query the repo — do NOT assume filenames survive an update.** The file list can change between visits (rename, re-quant, restructure). Always pull the tree/`siblings` API (`/api/models/<repo>?blobs=true`) at decision time. Unsloth's Qwen3.8-27B-GGUF went from `Qwen3.8-27B-Q6_K.gguf` → `Qwen3.8-27B-UD-Q6_K.gguf` (Dynamic 3.0, 2026-08-20) — a 1:1 path swap would have pointed at a file that no longer exists upstream, and the local old name is the OLD artifact, not the new one.
2. **Check whether MTP (or any spec-decode feature) is still embedded.** Don't trust the filename OR the README; check HF discussions (`/api/models/<repo>/discussions`) + verify the GGUF itself after download (tensor scan, method in the `llama-cpp` skill's `gguf-mtp-verification.md`). Unsloth kept MTP embedded in Dynamic 3.0 (org member confirmed in discussion #12) and shipped `MTP/mtp-Qwen3.8-27B-Q4_0.gguf` separately — the separate file is a fallback for `--model-draft`, not the primary path.
3. **Download WITHOUT deleting the current model** (user-requested safe rollout). `hf download <repo> <file1> <file2> --local-dir <dir>` in background (`terminal background=true, notify_on_complete=true`) — 20+ GB files do not fit a foreground timeout.
4. **Find EVERY reference to the model file before editing.** In the Hermes/Openclaw setup there are two:
   - `E:\Workspace\Openclaw\llama-launch.cmd` — `--model` path (live config; what the user restarts).
   - `E:\Workspace\Hermes\start-hermes.ps1` — `$modelFile` for the profile. **CRITICAL: this script REGENERATES `llama-launch.cmd` on every launch** (~line 446-448: it writes `$launchScript` from `$llamaArgs`). Editing only the `.cmd` gets silently overwritten on the next full startup. Edit both; the ps1 edit is the durable one.
   - `config/hermes.yaml` `model.path` is a stale `/app/...` Docker-style path that Hermes does NOT read (Hermes talks to the server over HTTP via alias) — leave it.
5. Update the human-facing label (e.g. `$modelSize` GiB string) in the same profile block so the banner stays truthful.
6. **Verify before hand-off**: sha256sum of the downloaded file vs the `lfs.sha256` from the siblings API; MTP tensor scan; only then tell the user to restart.
7. Rollback = revert the path back to the old filename (old file untouched) — no re-download needed.
8. **Audit model PINS after any model swap — cron jobs are invisible breakage.** `~/.hermes/cron/jobs.json` entries carry `model` + `provider`; a pinned job does NOT follow the main model and does NOT use `fallback_providers`. When the pinned model stops being served (retired profile, port moved, model renamed) every request dies and the job surfaces it only as `RuntimeError: Request timed out.` after burning its full timeout — the error text never names the model. Audit: list every job's `model`/`provider` and cross-check each against the live `/v1/models` of its provider's `base_url` (a dead endpoint = curl timeout, not a slow model). Fix with `hermes cron edit <id> --model <m> --provider <p> --pin`, then prove the endpoint answers a real completion before claiming it's fixed. Also check `auxiliary_models` / `auxiliary.*` in config.yaml for the same stale pins (the agent reads the `auxiliary:` section; `auxiliary_models:` feeds only the web UI). Failure-diagnosis playbook: `hermes-operations` skill → `references/cron-jobs.md`, "Model & provider pins".

## Pitfalls
- **Generated launchers beat hand-edited ones.** Any launcher that a bootstrap script regenerates must be edited at the generator, or the fix evaporates on next startup.
- **`hf` CLI download of a repo that was re-uploaded:** `hf download` resolves against the live `main` branch — if you recorded a filename from an earlier API snapshot and the repo moved on, it 404s. Re-verify the tree right before downloading.
- **Disk:** 20-25 GB GGUFs — confirm free space on the target drive before starting (E: had 1.8 TB free; trivial here, but check when stacking new+old).
- **The `MTP/` subdir files are NOT needed when MTP is embedded** — download them only as fallback, and remember they must be referenced with `--model-draft` (different flag than the embedded path, which needs nothing but `--spec-type draft-mtp`).
- **A retired model behind a cron pin looks like a timeout, not a missing model.** (2026-10-05: daily AI-news job pinned to `qwen3.6-27b` on `custom:llama-server` failed with `Request timed out` after 164 good runs — the 5090 profile had moved to `qwen3.8-flash-next-nvfp4` on `custom:strata` :8097 and the old llama-server port stopped answering entirely. Raising the timeout would have changed nothing; the fix was re-pinning the job.) Always rule out "endpoint dead" before "model too slow".
- **HF commits API quirk:** `/api/models/<repo>/commits?path=<file>` can return a 404/error dict instead of a list (observed 2026-08-23) — don't build workflows on it; the `?blobs=true` siblings endpoint and discussions are reliable.

## Environment snapshot (this rollout)
- New file: `Qwen3.8-27B-UD-Q6_K.gguf` = 21,983,677,344 B (20.4 GiB), sha256 `c9c206812fbe4ac7b76a729e25928b63f2ae89d37f69da7a71c20aec763cd436`.
- Fallback MTP: `MTP/mtp-Qwen3.8-27B-Q4_0.gguf` = 1,369,590,656 B, sha256 `50d9ce5a6da381bbcfb31061cf73df94a90e6faf8efeddee379a9cb8f1501c6e`.
- Old file kept: `Qwen3.8-27B-Q6_K.gguf` (21.3 GiB, Dynamic 2.0, MTP embedded).
- Launcher flags unchanged (MTP still embedded → same `--spec-type draft-mtp,ngram-mod --spec-draft-n-max 3 --cache-type-k-draft f16 --cache-type-v-draft f16 --spec-default`).

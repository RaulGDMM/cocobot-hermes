#!/usr/bin/env python3
"""Lightweight ComfyUI broker for GPU swap and batched image jobs.

The broker exposes a small HTTP API on Windows so OpenClaw-side tools can:
1. Queue one or more ComfyUI API prompt graphs.
2. Batch multiple requests over a short window.
3. Stop llama-server, start ComfyUI, execute prompts, then restore llama-server.

Request format:
  POST /v1/generate
  {
    "workflow": { ... ComfyUI API prompt graph ... }
  }

  Or:
  {
    "workflow_path": "E:/path/to/workflow_api.json"
  }

Optional fields:
  "copies": 4,
  "timeout_seconds": 1800,
  "batch_wait_seconds": 5,
  "client_id": "custom-client-id",
  "replacements": {"__PROMPT__": "...", "cat.png": "real_input.png"}

  POST /v1/gpu-exec        (run a command with GPU access — swaps llama-server)
  {
    "command": ["uv", "run", "generate_speech.py", "--text", "hello"],
    "timeout_seconds": 900,
    "cwd": "/some/dir",        (optional)
    "wsl": true,               (optional — wraps command with "wsl -d Ubuntu --")
    "async": false             (optional — if true, returns job_id immediately)
  }

The broker intentionally stays generic: it accepts ready-to-run ComfyUI API JSON.
Later skill wrappers can export API workflows and replace placeholders before calling it.
"""

from __future__ import annotations

import argparse
import copy
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)

# Detect Windows Terminal for tab-aware launches
_WT_SESSION = os.environ.get("WT_SESSION")
_WT_EXE = shutil.which("wt.exe") if _WT_SESSION else None

_log_lock = threading.Lock()
_log_file_handle = None  # type: Any


def _raw_log(message: str) -> None:
    """Thread-safe log to stderr + file using raw writes (no logging module)."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [comfy-broker] {message}\n"
    with _log_lock:
        try:
            sys.stderr.write(line)
            sys.stderr.flush()
        except Exception:
            pass
        fh = _log_file_handle
        if fh is not None:
            try:
                fh.write(line)
                fh.flush()
            except Exception:
                pass


def setup_logging(log_file: Path | None = None) -> None:
    """Open the persistent log file handle."""
    global _log_file_handle
    if log_file:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            _log_file_handle = open(str(log_file), "a", encoding="utf-8")
        except OSError as exc:
            _raw_log(f"Could not open log file {log_file}: {exc}")


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def request_json(method: str, url: str, payload: Any | None = None, timeout: float = 10.0) -> Any:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, headers=headers, method=method)
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urlerror.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:2000]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {exc.code} {exc.reason}: {body}") from exc


def url_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        request_json("GET", url, timeout=timeout)
        return True
    except Exception:
        return False


def read_json_file(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Workflow JSON must be an object")
    return data


def replace_placeholders(value: Any, replacements: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: replace_placeholders(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_placeholders(item, replacements) for item in value]
    if isinstance(value, str) and value in replacements:
        return replacements[value]
    return value


def detect_comfy_app_dir(root_dir: Path, user_dir: Path) -> Path | None:
    candidates: list[Path] = []

    for name in ("comfyui_8000.log", "comfyui.log", "comfyui_8000.prev.log", "comfyui_8000.prev2.log"):
        log_path = user_dir / name
        if not log_path.exists():
            continue
        try:
            content = log_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        match = re.search(r"\*\* ComfyUI Path: (.+)", content)
        if match:
            candidates.append(Path(match.group(1).strip()))

    candidates.extend(
        [
            root_dir,
            root_dir / "resources" / "ComfyUI",
            Path("E:/Comfy-Desktop/ComfyUI-Installs/ComfyUI/ComfyUI"),
            Path("E:/Programs/ComfyUI/resources/ComfyUI"),
        ]
    )

    for candidate in candidates:
        if candidate and (candidate / "main.py").exists():
            return candidate
    return None


class ExclusiveHTTPServer(ThreadingHTTPServer):
    """Prevent multiple processes from binding the same port on Windows."""
    allow_reuse_address = False
    request_queue_size = 64

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


@dataclass(slots=True)
class BrokerConfig:
    broker_host: str
    broker_port: int
    batch_wait_seconds: float
    batch_max: int
    default_timeout_seconds: int
    comfy_host: str
    comfy_port: int
    comfy_root_dir: Path
    comfy_user_dir: Path
    comfy_input_dir: Path
    comfy_output_dir: Path
    comfy_python: Path
    comfy_app_dir: Path | None
    comfy_extra_model_paths_config: Path | None
    keep_comfy_running: bool
    use_backend: str
    llama_port: int
    llama_server_exe: Path | None
    llama_model: Path | None
    llama_draft_model: Path | None
    llama_mmproj: Path | None
    llama_chat_template: Path | None
    llama_log_file: Path | None
    broker_log_file: Path | None
    llama_slot_save_path: Path
    llama_ctx_size: int
    llama_parallel: int
    llama_n_gpu_layers: int
    llama_batch_size: int
    llama_ubatch_size: int
    llama_ctx_checkpoints: int
    llama_slot_min_tokens: int
    llama_profile: str
    llama_temp: str
    llama_top_p: str
    llama_top_k: str
    llama_min_p: str
    llama_presence_penalty: str
    llama_predict: str
    llama_mtp_enabled: bool
    llama_mtp_draft_n_max: str
    llama_mtp_draft_p_min: str

    @classmethod
    def from_env(cls, broker_port_override: int | None = None) -> "BrokerConfig":
        comfy_root_dir = Path(os.environ.get("OPENCLAW_COMFYUI_ROOT", "C:/ComfyUI"))
        comfy_user_dir = Path(os.environ.get("OPENCLAW_COMFYUI_USER_DIR", str(comfy_root_dir / "user")))
        comfy_input_dir = Path(os.environ.get("OPENCLAW_COMFYUI_INPUT_DIR", str(comfy_root_dir / "input")))
        comfy_output_dir = Path(os.environ.get("OPENCLAW_COMFYUI_OUTPUT_DIR", str(comfy_root_dir / "output")))
        comfy_python = Path(os.environ.get("OPENCLAW_COMFYUI_PYTHON", str(comfy_root_dir / ".venv" / "Scripts" / "python.exe")))

        comfy_app_dir_env = os.environ.get("OPENCLAW_COMFYUI_APP_DIR")
        comfy_app_dir = Path(comfy_app_dir_env) if comfy_app_dir_env else detect_comfy_app_dir(comfy_root_dir, comfy_user_dir)
        comfy_extra_model_paths = os.environ.get("OPENCLAW_COMFYUI_EXTRA_MODEL_PATHS_CONFIG")

        def optional_path(name: str) -> Path | None:
            value = os.environ.get(name)
            return Path(value) if value else None

        script_dir = Path(__file__).resolve().parent
        slot_save_path = Path(os.environ.get("OPENCLAW_LLAMA_SLOT_SAVE_PATH", str(script_dir / "slot-cache")))

        return cls(
            broker_host=os.environ.get("OPENCLAW_BROKER_HOST", "127.0.0.1"),
            broker_port=broker_port_override or env_int("OPENCLAW_BROKER_PORT", 8791),
            batch_wait_seconds=env_float("OPENCLAW_BATCH_WAIT_SECONDS", 5.0),
            batch_max=env_int("OPENCLAW_BATCH_MAX", 20),
            default_timeout_seconds=env_int("OPENCLAW_DEFAULT_GENERATION_TIMEOUT", 1800),
            comfy_host=os.environ.get("OPENCLAW_COMFYUI_HOST", "127.0.0.1"),
            comfy_port=env_int("OPENCLAW_COMFYUI_PORT", 8000),
            comfy_root_dir=comfy_root_dir,
            comfy_user_dir=comfy_user_dir,
            comfy_input_dir=comfy_input_dir,
            comfy_output_dir=comfy_output_dir,
            comfy_python=comfy_python,
            comfy_app_dir=comfy_app_dir,
            comfy_extra_model_paths_config=Path(comfy_extra_model_paths) if comfy_extra_model_paths else None,
            keep_comfy_running=env_bool("OPENCLAW_KEEP_COMFY_RUNNING", False),
            use_backend=os.environ.get("OPENCLAW_USE_BACKEND", "llama-server"),
            llama_port=env_int("OPENCLAW_LLAMA_PORT", 30000),
            llama_server_exe=optional_path("OPENCLAW_LLAMA_SERVER_EXE"),
            llama_model=optional_path("OPENCLAW_LLAMA_MODEL"),
            llama_draft_model=optional_path("OPENCLAW_LLAMA_DRAFT_MODEL"),
            llama_mmproj=optional_path("OPENCLAW_LLAMA_MMPROJ"),
            llama_chat_template=optional_path("OPENCLAW_LLAMA_CHAT_TEMPLATE"),
            llama_log_file=optional_path("OPENCLAW_LLAMA_LOG_FILE"),
            broker_log_file=optional_path("OPENCLAW_BROKER_LOG_FILE"),
            llama_slot_save_path=slot_save_path,
            llama_ctx_size=env_int("OPENCLAW_LLAMA_CTX_SIZE", 131072),
            llama_parallel=env_int("OPENCLAW_LLAMA_PARALLEL", 1),
            llama_n_gpu_layers=env_int("OPENCLAW_LLAMA_N_GPU_LAYERS", 99),
            llama_batch_size=env_int("OPENCLAW_LLAMA_BATCH_SIZE", 4096),
            llama_ubatch_size=env_int("OPENCLAW_LLAMA_UBATCH_SIZE", 4096),
            llama_ctx_checkpoints=env_int("OPENCLAW_LLAMA_CTX_CHECKPOINTS", 32),
            llama_slot_min_tokens=env_int("OPENCLAW_LLAMA_SLOT_MIN_TOKENS", 200),
            llama_profile=os.environ.get("OPENCLAW_LLAMA_PROFILE", "qwen35").strip().lower(),
            llama_temp=os.environ.get("OPENCLAW_LLAMA_TEMP", "0.6"),
            llama_top_p=os.environ.get("OPENCLAW_LLAMA_TOP_P", "0.95"),
            llama_top_k=os.environ.get("OPENCLAW_LLAMA_TOP_K", "20"),
            llama_min_p=os.environ.get("OPENCLAW_LLAMA_MIN_P", "0"),
            llama_presence_penalty=os.environ.get("OPENCLAW_LLAMA_PRESENCE_PENALTY", "0"),
            llama_predict=os.environ.get("OPENCLAW_LLAMA_PREDICT", "81920"),
            llama_mtp_enabled=env_bool("OPENCLAW_LLAMA_MTP_ENABLED", False),
            llama_mtp_draft_n_max=os.environ.get("OPENCLAW_LLAMA_MTP_DRAFT_N_MAX", "2"),
            llama_mtp_draft_p_min=os.environ.get("OPENCLAW_LLAMA_MTP_DRAFT_P_MIN", "0"),
        )

    @property
    def comfy_base_url(self) -> str:
        return f"http://{self.comfy_host}:{self.comfy_port}"

    @property
    def llama_base_url(self) -> str:
        return f"http://127.0.0.1:{self.llama_port}"


@dataclass(slots=True)
class Job:
    workflow: dict[str, Any]
    timeout_seconds: int
    created_at: float = field(default_factory=time.time)
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event: threading.Event = field(default_factory=threading.Event)
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass(slots=True)
class GpuExecJob:
    command: list[str]
    timeout_seconds: int
    cwd: str | None = None
    needs_gpu: bool = True
    created_at: float = field(default_factory=time.time)
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event: threading.Event = field(default_factory=threading.Event)
    result: dict[str, Any] | None = None
    error: str | None = None


class BrokerState:
    def __init__(self, config: BrokerConfig) -> None:
        self.config = config
        self.queue: list[Job] = []
        self.queue_cond = threading.Condition()
        self.swap_lock = threading.Lock()
        self.worker = threading.Thread(target=self._worker_loop, name="comfy-broker-worker", daemon=True)
        self.started_at = time.time()
        self.last_batch_started_at = 0.0
        self.last_batch_size = 0
        self.last_error = ""
        self.total_jobs_processed = 0
        self.total_batches_processed = 0
        self.comfy_process: subprocess.Popen[str] | None = None
        self.comfy_started_by_broker = False
        self.gpu_exec_queue: list[GpuExecJob] = []
        self.gpu_exec_cond = threading.Condition()
        self.gpu_exec_worker = threading.Thread(target=self._gpu_exec_worker_loop, name="gpu-exec-worker", daemon=True)
        self.worker.start()
        self.gpu_exec_worker.start()

    def _log(self, message: str) -> None:
        _raw_log(message)

    def status(self) -> dict[str, Any]:
        with self.queue_cond:
            queue_size = len(self.queue)
        with self.gpu_exec_cond:
            gpu_exec_queue_size = len(self.gpu_exec_queue)
        return {
            "status": "ok",
            "uptime_seconds": round(time.time() - self.started_at, 1),
            "queue_size": queue_size,
            "gpu_exec_queue_size": gpu_exec_queue_size,
            "worker_alive": self.worker.is_alive(),
            "gpu_exec_worker_alive": self.gpu_exec_worker.is_alive(),
            "batch_wait_seconds": self.config.batch_wait_seconds,
            "batch_max": self.config.batch_max,
            "last_batch_size": self.last_batch_size,
            "total_jobs_processed": self.total_jobs_processed,
            "total_batches_processed": self.total_batches_processed,
            "last_error": self.last_error,
            "comfy_running": self.comfy_is_ready(),
            "llama_running": self.llama_is_ready(),
            "whisper_running": self.whisper_is_running(),
            "comfy_app_dir": str(self.config.comfy_app_dir) if self.config.comfy_app_dir else None,
            "llama_profile": self.config.llama_profile,
        }

    def enqueue(self, job: Job) -> None:
        with self.queue_cond:
            self.queue.append(job)
            self.queue_cond.notify()

    def enqueue_gpu_exec(self, job: GpuExecJob) -> None:
        with self.gpu_exec_cond:
            self.gpu_exec_queue.append(job)
            self.gpu_exec_cond.notify()

    def comfy_is_ready(self) -> bool:
        return url_ok(f"{self.config.comfy_base_url}/queue", timeout=2.0)

    def llama_is_ready(self) -> bool:
        return url_ok(f"{self.config.llama_base_url}/health", timeout=2.0)

    def _llama_slot_persistence_supported(self) -> bool:
        # ik_llama.cpp supports slot save/restore with multimodal models
        exe = self.config.llama_server_exe
        if exe and "ik_llama" in str(exe.parent):
            return True
        mmproj = self.config.llama_mmproj
        return not (mmproj and mmproj.exists())

    def _llama_slot_alias(self) -> str | None:
        if not self.config.llama_model:
            return None
        alias = re.sub(r"[^A-Za-z0-9._-]+", "-", self.config.llama_model.stem).strip("-._")
        return alias or None

    def _llama_slot_files(self) -> list[Path]:
        alias = self._llama_slot_alias()
        if not alias:
            return []
        slot_dir = self.config.llama_slot_save_path
        if not slot_dir.exists():
            return []
        return sorted(path for path in slot_dir.glob(f"slot_{alias}_*") if path.is_file() and path.stat().st_size > 0)

    @staticmethod
    def _slot_decoded_tokens(slot: dict[str, Any]) -> int:
        decoded = slot.get("n_decoded")
        if isinstance(decoded, int):
            return decoded
        next_token = slot.get("next_token")
        # ik_llama.cpp puts n_decoded inside next_token (as dict, not list)
        if isinstance(next_token, dict) and isinstance(next_token.get("n_decoded"), int):
            n = int(next_token["n_decoded"])
            if n > 0:
                return n
        if isinstance(next_token, list) and next_token:
            item = next_token[0]
            if isinstance(item, dict) and isinstance(item.get("n_decoded"), int):
                return int(item["n_decoded"])
        prompted = slot.get("n_prompt_tokens_processed")
        if isinstance(prompted, int):
            return prompted
        # ik_llama.cpp: if prompt field has content, the slot has cached tokens
        prompt = slot.get("prompt")
        if prompt and isinstance(prompt, str) and len(prompt) > 10:
            return max(len(prompt) // 4, 1000)  # estimate; enough to pass min threshold
        return 0
        return 0

    def _save_llama_slots(self) -> None:
        if not self._llama_slot_persistence_supported():
            self._log("Skipping KV slot save: llama.cpp slot save/restore is not supported for multimodal servers")
            return
        alias = self._llama_slot_alias()
        if not alias:
            self._log("Skipping KV slot save: no llama model alias available")
            return
        try:
            self.config.llama_slot_save_path.mkdir(parents=True, exist_ok=True)
            slots = request_json("GET", f"{self.config.llama_base_url}/slots", timeout=5)
        except Exception as exc:
            self._log(f"Skipping KV slot save: {exc}")
            return

        if not isinstance(slots, list):
            self._log(f"Skipping KV slot save: unexpected /slots response: {slots}")
            return

        saved = 0
        is_ik_llama = self.config.llama_server_exe and "ik_llama" in str(self.config.llama_server_exe.parent)
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            slot_id = slot.get("id")
            if not isinstance(slot_id, int):
                continue
            decoded = self._slot_decoded_tokens(slot)
            # ik_llama.cpp /slots doesn't expose total KV tokens reliably;
            # always attempt save and let the server report n_saved
            if not is_ik_llama and decoded < self.config.llama_slot_min_tokens:
                continue
            filename = f"slot_{alias}_{slot_id}"
            body = {"id_slot": slot_id, "filename": filename}
            try:
                resp = request_json(
                    "POST",
                    f"{self.config.llama_base_url}/slots/{slot_id}?action=save",
                    payload=body,
                    timeout=120,
                )
                size_mb = round(float(resp.get("n_read", 0)) / (1024 * 1024), 1)
                self._log(f"Saved KV slot {slot_id} ({decoded} tokens, {size_mb} MB, {filename})")
                saved += 1
            except Exception as exc:
                self._log(f"Failed to save KV slot {slot_id}: {exc}")
        if saved:
            self._log(f"Saved {saved} KV slot(s) to {self.config.llama_slot_save_path}")
        else:
            self._log("No eligible KV slots to save")

    def _restore_llama_slots(self) -> None:
        if not self._llama_slot_persistence_supported():
            self._log("Skipping KV slot restore: llama.cpp slot save/restore is not supported for multimodal servers")
            return
        alias = self._llama_slot_alias()
        if not alias:
            self._log("Skipping KV slot restore: no llama model alias available")
            return
        slot_files = self._llama_slot_files()
        if not slot_files:
            self._log(f"No saved KV slots found for {alias}")
            return

        restored = 0
        self._log(f"Restoring {len(slot_files)} KV slot(s) for {alias}")
        for file_path in slot_files:
            suffix = file_path.name.removeprefix(f"slot_{alias}_")
            try:
                slot_id = int(suffix)
            except ValueError:
                self._log(f"Skipping malformed KV slot filename: {file_path.name}")
                continue
            body = {"id_slot": slot_id, "filename": file_path.name}
            try:
                resp = request_json(
                    "POST",
                    f"{self.config.llama_base_url}/slots/{slot_id}?action=restore",
                    payload=body,
                    timeout=120,
                )
                restored_tokens = int(resp.get("n_restored", 0))
                timings = resp.get("timings") if isinstance(resp, dict) else {}
                restore_ms = timings.get("restore_ms") if isinstance(timings, dict) else None
                restore_label = f", {restore_ms} ms" if restore_ms is not None else ""
                self._log(f"Restored KV slot {slot_id} ({restored_tokens} tokens{restore_label})")
                restored += 1
            except Exception as exc:
                self._log(f"Failed to restore KV slot {slot_id}: {exc}")
        self._log(f"Restored {restored}/{len(slot_files)} KV slot(s) from {self.config.llama_slot_save_path}")

    def _worker_loop(self) -> None:
        self._log("Worker thread started")
        while True:
            batch = self._collect_batch()
            if not batch:
                continue
            try:
                self._process_batch(batch)
            except Exception as exc:  # pragma: no cover - defensive top-level guard
                self._log(f"Worker exception: {exc}")
                self._log(traceback.format_exc())
                self.last_error = str(exc)
                for job in batch:
                    job.error = str(exc)
                    job.event.set()

    def _collect_batch(self) -> list[Job]:
        with self.queue_cond:
            while not self.queue:
                self.queue_cond.wait()

            deadline = time.time() + self.config.batch_wait_seconds
            while len(self.queue) < self.config.batch_max:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self.queue_cond.wait(timeout=remaining)
                if not self.queue:
                    continue

            batch = self.queue[: self.config.batch_max]
            del self.queue[: len(batch)]
            return batch

    def _process_batch(self, batch: list[Job]) -> None:
        self.last_batch_started_at = time.time()
        self.last_batch_size = len(batch)
        self.total_batches_processed += 1
        restore_error: str | None = None

        with self.swap_lock:
            llama_was_running = self.llama_is_ready() or self._llama_process_exists()
            whisper_was_running = self.whisper_is_running()
            self._log(f"Starting batch of {len(batch)} job(s); llama_running={llama_was_running}, whisper_running={whisper_was_running}")
            if whisper_was_running:
                self._stop_whisper_server(blocking=False)
            # Always attempt to stop llama-server: health check may timeout
            # if the process is busy loading the model or processing a prompt.
            self._log("Stopping llama-server to free VRAM")
            self._stop_llama_server()

            started_comfy = self._ensure_comfy_running()

            try:
                for job in batch:
                    try:
                        self._log(f"Running job {job.job_id} (timeout={job.timeout_seconds}s)")
                        job.result = self._run_job(job)
                        self.total_jobs_processed += 1
                    except Exception as exc:
                        self.last_error = str(exc)
                        job.error = str(exc)
                        self._log(f"Job {job.job_id} FAILED: {exc}")
            finally:
                if started_comfy and not self.config.keep_comfy_running:
                    self._log("Stopping ComfyUI after batch")
                    self._stop_comfy()
                if llama_was_running:
                    try:
                        self._log("Restarting llama-server")
                        self._start_llama_server()
                        self._log("Warming up llama-server")
                        self._warmup_llama_server()
                        self._log("Restoring llama KV cache slots")
                        self._restore_llama_slots()
                        self._log("llama-server restored and ready")
                    except Exception as exc:
                        restore_error = f"Failed to restore llama-server: {exc}"
                        self.last_error = restore_error
                        self._log(restore_error)
                if whisper_was_running:
                    try:
                        self._start_whisper_server()
                    except Exception as exc:
                        self._log(f"Warning: failed to restart whisper-server: {exc}")

        if restore_error:
            for job in batch:
                if not job.error:
                    job.error = restore_error

        for job in batch:
            job.event.set()

        self._log(f"Finished batch of {len(batch)} job(s)")

    def _ensure_comfy_running(self) -> bool:
        if self.comfy_is_ready():
            self.comfy_started_by_broker = False
            self._log("ComfyUI already running")
            return False

        if not self.config.comfy_app_dir:
            raise RuntimeError("Could not detect ComfyUI app directory; set OPENCLAW_COMFYUI_APP_DIR")
        if not self.config.comfy_python.exists():
            raise RuntimeError(f"ComfyUI python not found: {self.config.comfy_python}")

        args = [
            str(self.config.comfy_python),
            str(self.config.comfy_app_dir / "main.py"),
            "--listen",
            self.config.comfy_host,
            "--port",
            str(self.config.comfy_port),
            "--output-directory",
            str(self.config.comfy_output_dir),
            "--input-directory",
            str(self.config.comfy_input_dir),
            "--user-directory",
            str(self.config.comfy_user_dir),
            "--disable-auto-launch",
            "--reserve-vram", "2.0",
            "--disable-smart-memory",
        ]

        if self.config.comfy_extra_model_paths_config and self.config.comfy_extra_model_paths_config.exists():
            args.extend([
                "--extra-model-paths-config",
                str(self.config.comfy_extra_model_paths_config),
            ])

        comfy_env = os.environ.copy()
        comfy_env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True,max_split_size_mb:512"

        comfy_log_path = self.config.broker_log_file.parent / "comfyui-process.log" if self.config.broker_log_file else None
        if comfy_log_path:
            self._comfy_log_fh = open(str(comfy_log_path), "w", encoding="utf-8")
            self._log(f"ComfyUI stdout/stderr -> {comfy_log_path}")
        else:
            self._comfy_log_fh = None
        self.comfy_process = subprocess.Popen(
            args,
            cwd=str(self.config.comfy_app_dir),
            env=comfy_env,
            creationflags=CREATE_NO_WINDOW,
            stdout=self._comfy_log_fh or subprocess.DEVNULL,
            stderr=subprocess.STDOUT if self._comfy_log_fh else subprocess.DEVNULL,
        )
        self.comfy_started_by_broker = True
        self._log(f"Started ComfyUI process (pid={self.comfy_process.pid})")

        deadline = time.time() + 90
        while time.time() < deadline:
            if self.comfy_is_ready():
                self._log("ComfyUI is ready")
                return True
            if self.comfy_process.poll() is not None:
                raise RuntimeError("ComfyUI exited during startup")
            time.sleep(1)

        raise RuntimeError("Timed out waiting for ComfyUI to become ready")

    def _stop_comfy(self) -> None:
        if self.comfy_process and self.comfy_process.poll() is None:
            self._log(f"Stopping ComfyUI process (pid={self.comfy_process.pid})")
            self.comfy_process.terminate()
            try:
                self.comfy_process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._log("ComfyUI did not exit after terminate; killing it")
                self.comfy_process.kill()
                self.comfy_process.wait(timeout=5)
        self.comfy_process = None
        self.comfy_started_by_broker = False
        if getattr(self, "_comfy_log_fh", None):
            try:
                self._comfy_log_fh.close()
            except Exception:
                pass
            self._comfy_log_fh = None

    # -- Whisper server lifecycle (free RAM during ComfyUI batches) ----------

    _WHISPER_PORT = 8787

    def whisper_is_running(self) -> bool:
        return url_ok(f"http://127.0.0.1:{self._WHISPER_PORT}/health", timeout=2.0)

    def _stop_whisper_server(self, blocking: bool = True) -> None:
        if not self.whisper_is_running():
            return
        self._log("Stopping whisper-server to free RAM")
        # Kill the Python process listening on the whisper port
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-NetTCPConnection -LocalPort {self._WHISPER_PORT} -ErrorAction SilentlyContinue "
             f"| Select-Object -ExpandProperty OwningProcess -Unique "
             f"| ForEach-Object {{ Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }}"],
            capture_output=True, text=True,
            creationflags=CREATE_NO_WINDOW, check=False,
        )
        if not blocking:
            self._log("whisper-server kill signal sent (non-blocking)")
            return
        deadline = time.time() + 20
        while time.time() < deadline:
            if not self.whisper_is_running():
                self._log("whisper-server stopped")
                return
            time.sleep(0.5)
        self._log("Warning: whisper-server did not stop in time")

    def _start_whisper_server(self) -> None:
        if self.whisper_is_running():
            return
        whisper_script = Path(__file__).resolve().parent / "whisper-server.py"
        if not whisper_script.exists():
            self._log(f"whisper-server.py not found at {whisper_script}, skipping")
            return
        self._log("Starting whisper-server")
        py_exe = shutil.which("py") or shutil.which("python")
        if not py_exe:
            self._log("Warning: python launcher not found, cannot start whisper-server")
            return
        args = [py_exe, "-3.12", str(whisper_script), "--model", "medium"]
        subprocess.Popen(
            args,
            creationflags=CREATE_NO_WINDOW,
        )
        # Don't wait for it — whisper loads lazily on first request
        self._log("whisper-server launch requested")

    # -- llama-server lifecycle -----------------------------------------------

    @staticmethod
    def _llama_process_exists() -> bool:
        """Check if any llama-server.exe process is alive (regardless of health check)."""
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq llama-server.exe", "/NH"],
            capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, check=False,
        )
        return "llama-server.exe" in result.stdout

    def _stop_llama_server(self) -> None:
        if self.llama_is_ready():
            self._log("Saving llama KV cache slots before shutdown")
            self._save_llama_slots()

        subprocess.run(
            ["taskkill", "/IM", "llama-server.exe", "/F"],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )

        deadline = time.time() + 20
        while time.time() < deadline:
            if not self._llama_process_exists():
                self._log("llama-server stopped")
                return
            time.sleep(1)
        raise RuntimeError("Timed out stopping llama-server")

    def _start_llama_server(self) -> None:
        if self.config.use_backend != "llama-server":
            return
        if not self.config.llama_server_exe or not self.config.llama_server_exe.exists():
            raise RuntimeError("llama-server executable not configured")
        if not self.config.llama_model or not self.config.llama_model.exists():
            raise RuntimeError("llama model path not configured")

        # Ensure slot-save-path directory exists
        self.config.llama_slot_save_path.mkdir(parents=True, exist_ok=True)

        profile = self.config.llama_profile
        if profile not in {"qwen35", "qwen36", "qwen36q4", "qwen36_27b_bee_q5", "qwen36_27b_bee_q6", "qwen36_27b", "qwen36_27b_q6", "qwen36_27b_q4_mtp", "qwen36_27b_q5_mtp", "qwen36_27b_q6_mtp", "qwen36_27b_autoround_q6_mtp", "qwen36_27b_bartowski_q6kl_mtp", "gemma4"}:
            profile = "qwen35"

        is_ik_llama = "ik_llama" in str(self.config.llama_server_exe.parent)

        args = [
            str(self.config.llama_server_exe),
            "--model",
            str(self.config.llama_model),
            "--alias",
            f"qwen3.6-27b,{profile}",
        ]

        if self.config.llama_mmproj and self.config.llama_mmproj.exists():
            args.extend(["--mmproj", str(self.config.llama_mmproj)])

        args.extend(
            [
                "--ctx-size",
                str(self.config.llama_ctx_size),
                "--slot-save-path",
                str(self.config.llama_slot_save_path),
                "--parallel",
                # MTP keeps draft state per slot, breaking ik_llama's KV unification.
                "1" if self.config.llama_mtp_enabled else str(self.config.llama_parallel),
                "--n-gpu-layers",
                str(self.config.llama_n_gpu_layers),
                "--flash-attn",
                "on",
                "--batch-size",
                str(self.config.llama_batch_size),
                "--host",
                "0.0.0.0",
                "--port",
                str(self.config.llama_port),
                "--cont-batching",
            ]
        )

        # Keep restart args aligned with start-hermes.ps1 profile branches.
        if profile == "qwen35":
            args.extend(["--ubatch-size", str(self.config.llama_ubatch_size)])
            if self.config.llama_chat_template and self.config.llama_chat_template.exists():
                args.extend(["--chat-template-file", str(self.config.llama_chat_template)])
            if is_ik_llama:
                args.extend(["--ctx-checkpoints", str(self.config.llama_ctx_checkpoints), "--swa-full"])
            else:
                args.extend(["--kv-unified", "--ctx-checkpoints", str(self.config.llama_ctx_checkpoints), "--swa-full"])
        elif profile in ("qwen36", "qwen36q4", "qwen36_27b_bee_q5", "qwen36_27b_bee_q6", "qwen36_27b", "qwen36_27b_q6", "qwen36_27b_q4_mtp", "qwen36_27b_q5_mtp", "qwen36_27b_q6_mtp", "qwen36_27b_autoround_q6_mtp", "qwen36_27b_bartowski_q6kl_mtp"):
            # Qwen3.6 family: jinja, reasoning on, thinking enabled, self-healing template
            args.extend(["--ubatch-size", str(self.config.llama_ubatch_size)])
            args.extend(["--jinja", "--reasoning", "on"])
            if self.config.llama_chat_template and self.config.llama_chat_template.exists():
                args.extend(["--chat-template-file", str(self.config.llama_chat_template)])
            args.extend(["--image-min-tokens", "1024"])
            args.extend(["--image-max-tokens", "1024"])
            if profile in ("qwen36_27b", "qwen36_27b_q6", "qwen36_27b_q4_mtp", "qwen36_27b_q5_mtp", "qwen36_27b_q6_mtp", "qwen36_27b_autoround_q6_mtp", "qwen36_27b_bartowski_q6kl_mtp"):
                # Q6_0 KV (ik_llama low-perp) when MTP is on q6 model — fits 131k ctx with parallel 4 + MTP
                if self.config.llama_mtp_enabled and profile == "qwen36_27b_q6":
                    args.extend(["-ctk", "q6_0", "-ctv", "q6_0"])
                elif profile in ("qwen36_27b_q4_mtp", "qwen36_27b_q5_mtp"):
                    args.extend(["-ctk", "q8_0", "-ctv", "q8_0"])
                elif profile in ("qwen36_27b_autoround_q6_mtp", "qwen36_27b_bartowski_q6kl_mtp"):
                    # High-quality Q6 profiles use K q8_0 / V q5_1 for better fine recall.
                    args.extend(["-ctk", "q8_0", "-ctv", "q5_1"])
                elif profile == "qwen36_27b_q6_mtp":
                    # K/V invertidos vs q4_0/q5_1: mismos bytes pero la mayor precision (q5_1) va a K, que es mas sensible
                    args.extend(["-ctk", "q5_1", "-ctv", "q4_0"])
                else:
                    args.extend(["-ctk", "q8_0", "-ctv", "q8_0"])  # Q8_0 KV cache + Hadamard rotations
            # Keep vision on CPU only for profiles that reserve their VRAM headroom for KV.
            if profile in ("qwen36_27b_q6", "qwen36_27b_q4_mtp", "qwen36_27b_q5_mtp") and not is_ik_llama:
                args.extend(["--no-mmproj-offload"])  # keep vision encoder on CPU to save VRAM (mainline only)
            # Sampling params from env vars (set by start-hermes.ps1)
            args.extend(["--presence-penalty", self.config.llama_presence_penalty])
            args.extend(["--min-p", self.config.llama_min_p, "--predict", self.config.llama_predict])
            args.extend(["--temp", self.config.llama_temp, "--top-p", self.config.llama_top_p, "--top-k", self.config.llama_top_k])
            args.extend(["--no-prefill-assistant"])
            if is_ik_llama:
                # ik_llama lacks --kv-unified / --no-cache-idle-slots; checkpoint flag is renamed.
                args.extend(["--ctx-checkpoints", str(self.config.llama_ctx_checkpoints),
                              "--ctx-checkpoints-interval", "1024", "--cache-ram", "16384",
                              "--no-context-shift"])
            else:
                if profile in ("qwen36_27b_bee_q5", "qwen36_27b_bee_q6"):
                    args.extend(["--kv-unified", "--ctx-checkpoints", str(self.config.llama_ctx_checkpoints),
                                  "--checkpoint-min-step", "8192", "--cache-ram", "32768",
                                  "--no-context-shift", "--no-cache-idle-slots"])
                elif self.config.llama_mtp_enabled:
                    # Mainline MTP: 2k spacing retains a broader span of long agentic histories
                    # within the checkpoint limit while keeping rollback reasonably fine-grained.
                    prompt_cache_ram = "32768" if profile in ("qwen36_27b_autoround_q6_mtp", "qwen36_27b_bartowski_q6kl_mtp") else "16384"
                    args.extend(["--kv-unified", "--ctx-checkpoints", str(self.config.llama_ctx_checkpoints),
                                  "--checkpoint-min-step", "2048", "--cache-ram", prompt_cache_ram,
                                  "--no-context-shift"])
                else:
                    args.extend(["--kv-unified", "--ctx-checkpoints", str(self.config.llama_ctx_checkpoints),
                                  "--checkpoint-min-step", "1024", "--cache-ram", "16384",
                                  "--no-context-shift"])
            if profile in ("qwen36_27b_bee_q5", "qwen36_27b_bee_q6"):
                if self.config.llama_draft_model and self.config.llama_draft_model.exists():
                    args.extend(["--spec-type", "dflash"])
                    args.extend(["--spec-draft-model", str(self.config.llama_draft_model)])
                    args.extend(["--spec-draft-ngl", "all"])
                    args.extend(["--spec-dflash-cross-ctx", "1024"])
                    args.extend(["--spec-draft-n-max", "16", "--spec-dm-controller", "profit"])
                args.extend(["--cache-type-k", "turbo4", "--cache-type-v", "turbo3_tcq"])
                args.extend(["--no-mmproj-offload"])
                args.extend(["--log-verbosity", "2", "--perf", "--metrics", "--log-timestamps", "--log-prefix"])
            # MTP (Multi-Token Prediction). Upstream llama.cpp uses draft-mtp;
            # ik_llama used the older -mtp spelling.
            if self.config.llama_mtp_enabled and profile in ("qwen36_27b", "qwen36_27b_q6", "qwen36_27b_q4_mtp", "qwen36_27b_q5_mtp", "qwen36_27b_q6_mtp", "qwen36_27b_autoround_q6_mtp", "qwen36_27b_bartowski_q6kl_mtp"):
                if is_ik_llama:
                    args.extend(["-mtp", "--draft-max", self.config.llama_mtp_draft_n_max])
                else:
                    args.extend(["--spec-type", "draft-mtp", "--spec-draft-n-max", self.config.llama_mtp_draft_n_max])
                    if self.config.llama_mtp_draft_p_min != "0":
                        args.extend(["--spec-draft-p-min", self.config.llama_mtp_draft_p_min])
                    args.extend(["--cache-type-k-draft", "f16", "--cache-type-v-draft", "f16"])
                    args.extend(["--spec-default"])
        elif profile == "gemma4":
            args.extend(["--ubatch-size", "512", "--jinja", "-ctk", "f16", "-ctv", "f16", "--repeat-penalty", "1.1"])
        else:
            args.extend(["--ubatch-size", "512", "--jinja"])

        if self.config.llama_log_file:
            args.extend(["--log-file", str(self.config.llama_log_file)])

        # Environment variables needed by specific profiles
        extra_env: dict[str, str] = {}
        if profile in ("qwen36", "qwen36q4", "qwen36_27b_bee_q5", "qwen36_27b_bee_q6", "qwen36_27b", "qwen36_27b_q6", "qwen36_27b_q4_mtp", "qwen36_27b_q5_mtp", "qwen36_27b_q6_mtp", "qwen36_27b_autoround_q6_mtp", "qwen36_27b_bartowski_q6kl_mtp"):
            extra_env["LLAMA_CHAT_TEMPLATE_KWARGS"] = '{"preserve_thinking":true}'
        if profile in ("qwen36_27b_bee_q5", "qwen36_27b_bee_q6"):
            extra_env.update(
                {
                    "GGML_DFLASH_PROFILE": "summary",
                }
            )

        if _WT_EXE:
            # Launch as a new tab in the existing Windows Terminal window.
            # Write a .cmd script to avoid cmd /c quoting issues with special
            # characters in env vars (e.g. JSON braces in LLAMA_CHAT_TEMPLATE_KWARGS).
            title = f"llama-server :{self.config.llama_port}"
            launch_script = Path(self.config.llama_server_exe).parent.parent / "llama-launch-broker.cmd"
            lines = ["@echo off"]
            for k, v in extra_env.items():
                lines.append(f"set {k}={v}")
            lines.append(subprocess.list2cmdline(args))
            launch_script.write_text("\r\n".join(lines), encoding="ascii")
            wt_args = [_WT_EXE, "-w", "0", "new-tab", "--title", title, "--", "cmd", "/c", f'"{launch_script}" & exit 0']
            process = subprocess.Popen(
                wt_args,
                cwd=str(self.config.llama_server_exe.parent),
                creationflags=CREATE_NO_WINDOW,
            )
        else:
            env = os.environ.copy()
            env.update(extra_env)
            process = subprocess.Popen(
                args,
                cwd=str(self.config.llama_server_exe.parent),
                env=env,
                creationflags=CREATE_NEW_CONSOLE,
            )
        self._log(f"Started llama-server process (pid={process.pid}, profile={profile})")

        startup_timeout = 360  # large models with big ctx can take 4-6 min
        self._log(f"Waiting up to {startup_timeout}s for llama-server health endpoint")
        deadline = time.time() + startup_timeout
        while time.time() < deadline:
            if self.llama_is_ready():
                self._log("llama-server health endpoint is ready")
                return
            time.sleep(3)
        raise RuntimeError(f"Timed out waiting for llama-server to become ready after {startup_timeout}s")

    def _warmup_llama_server(self) -> None:
        try:
            models = request_json("GET", f"{self.config.llama_base_url}/v1/models", timeout=10)
            data = models.get("data", [])
            model_id = None
            for entry in data:
                entry_id = entry.get("id")
                if entry_id and entry_id != "default" and "draft" not in entry_id:
                    model_id = entry_id
                    break
            if not model_id and data:
                model_id = data[0].get("id")
            if not model_id:
                return
            body = {
                "model": model_id,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
                "temperature": 0,
                "stream": False,
            }
            request_json("POST", f"{self.config.llama_base_url}/v1/chat/completions", payload=body, timeout=300)
            self._log(f"llama-server warmup completed with model {model_id}")
        except Exception:
            return

    # -- gpu-exec worker (arbitrary GPU commands with llama swap) -----------

    def _gpu_exec_worker_loop(self) -> None:
        self._log("gpu-exec worker thread started")
        while True:
            with self.gpu_exec_cond:
                while not self.gpu_exec_queue:
                    self.gpu_exec_cond.wait()
                job = self.gpu_exec_queue.pop(0)

            # For no-gpu jobs, run immediately without any swap logic.
            if not job.needs_gpu:
                try:
                    self._process_gpu_exec(job)
                except Exception as exc:
                    self._log(f"gpu-exec worker exception: {exc}")
                    self._log(traceback.format_exc())
                    self.last_error = str(exc)
                    job.error = str(exc)
                finally:
                    job.event.set()
                continue

            # GPU job: batch consecutive GPU jobs to avoid stop/start thrashing.
            # Collect this job + any others already queued that also need GPU.
            gpu_batch = [job]
            with self.gpu_exec_cond:
                while self.gpu_exec_queue and self.gpu_exec_queue[0].needs_gpu:
                    gpu_batch.append(self.gpu_exec_queue.pop(0))

            self._process_gpu_exec_batch(gpu_batch)

    def _process_gpu_exec_batch(self, batch: list[GpuExecJob]) -> None:
        """Run a batch of GPU jobs with a single llama stop/start cycle.

        Stops llama once, runs all jobs sequentially, then restarts llama.
        Between jobs, checks if more GPU jobs arrived and includes them.
        """
        GPU_EXEC_DRAIN_WAIT = 2.0  # seconds to wait for more jobs between executions

        restore_error: str | None = None
        with self.swap_lock:
            llama_was_running = self.llama_is_ready() or self._llama_process_exists()
            whisper_was_running = self.whisper_is_running()
            self._log(f"gpu-exec batch: {len(batch)} job(s); llama_running={llama_was_running}, whisper_running={whisper_was_running}")
            if whisper_was_running:
                self._stop_whisper_server(blocking=False)
            self._log("Stopping llama-server to free VRAM for gpu-exec batch")
            self._stop_llama_server()

            try:
                while batch:
                    for job in batch:
                        try:
                            self._run_gpu_exec_job(job)
                        except Exception as exc:
                            self._log(f"gpu-exec worker exception: {exc}")
                            self._log(traceback.format_exc())
                            self.last_error = str(exc)
                            job.error = str(exc)
                        finally:
                            job.event.set()

                    # After processing batch, wait briefly for more arriving jobs.
                    batch = []
                    with self.gpu_exec_cond:
                        self.gpu_exec_cond.wait(timeout=GPU_EXEC_DRAIN_WAIT)
                        while self.gpu_exec_queue and self.gpu_exec_queue[0].needs_gpu:
                            batch.append(self.gpu_exec_queue.pop(0))
                    if batch:
                        self._log(f"gpu-exec batch: draining {len(batch)} more job(s) without restarting llama")
            finally:
                if llama_was_running:
                    try:
                        self._log("Restarting llama-server after gpu-exec batch")
                        self._start_llama_server()
                        self._warmup_llama_server()
                        self._restore_llama_slots()
                        self._log("llama-server restored and ready after gpu-exec batch")
                    except Exception as exc:
                        restore_error = f"Failed to restore llama-server: {exc}"
                        self.last_error = restore_error
                        self._log(restore_error)
                if whisper_was_running:
                    try:
                        self._start_whisper_server()
                    except Exception as exc:
                        self._log(f"Warning: failed to restart whisper-server: {exc}")

        if restore_error:
            # Mark any remaining un-errored jobs with the restore error
            pass  # jobs already signaled

    def _run_gpu_exec_job(self, job: GpuExecJob) -> None:
        """Execute a single gpu-exec job (llama already stopped)."""
        cmd_preview = " ".join(job.command[:6])
        self._log(f"gpu-exec {job.job_id}: running command={cmd_preview!r}")
        try:
            result = subprocess.run(
                job.command,
                capture_output=True,
                text=True,
                timeout=job.timeout_seconds,
                cwd=job.cwd,
            )
            job.result = {
                "job_id": job.job_id,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            self._log(f"gpu-exec {job.job_id}: exit_code={result.returncode}")
            if result.returncode != 0:
                job.error = f"Command exited with code {result.returncode}"
        except subprocess.TimeoutExpired:
            job.error = f"Command timed out after {job.timeout_seconds}s"
            job.result = {"job_id": job.job_id, "exit_code": -1, "stdout": "", "stderr": "Timed out"}
            self._log(f"gpu-exec {job.job_id}: TIMED OUT")
        except FileNotFoundError as exc:
            job.error = f"Command not found: {exc}"
            self._log(f"gpu-exec {job.job_id}: {job.error}")

    def _process_gpu_exec(self, job: GpuExecJob) -> None:
        restore_error: str | None = None
        cmd_preview = " ".join(job.command[:6])  # log first few args for debugging
        self._log(f"gpu-exec {job.job_id}: command={cmd_preview!r}, needs_gpu={job.needs_gpu}")

        # If the job doesn't need GPU, run it directly without swapping llama/whisper.
        if not job.needs_gpu:
            try:
                result = subprocess.run(
                    job.command,
                    capture_output=True,
                    text=True,
                    timeout=job.timeout_seconds,
                    cwd=job.cwd,
                )
                job.result = {
                    "job_id": job.job_id,
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
                self._log(f"gpu-exec {job.job_id} (no-gpu): exit_code={result.returncode}")
                if result.returncode != 0:
                    job.error = f"Command exited with code {result.returncode}"
            except subprocess.TimeoutExpired:
                job.error = f"Command timed out after {job.timeout_seconds}s"
                job.result = {"job_id": job.job_id, "exit_code": -1, "stdout": "", "stderr": "Timed out"}
            except FileNotFoundError as exc:
                job.error = f"Command not found: {exc}"
            return

        with self.swap_lock:
            llama_was_running = self.llama_is_ready() or self._llama_process_exists()
            whisper_was_running = self.whisper_is_running()
            self._log(f"gpu-exec {job.job_id}: starting command; llama_running={llama_was_running}, whisper_running={whisper_was_running}")
            if whisper_was_running:
                self._stop_whisper_server(blocking=False)
            # Always stop llama-server (may be busy but still holding VRAM)
            self._log("Stopping llama-server to free VRAM for gpu-exec")
            self._stop_llama_server()

            try:
                result = subprocess.run(
                    job.command,
                    capture_output=True,
                    text=True,
                    timeout=job.timeout_seconds,
                    cwd=job.cwd,
                )
                job.result = {
                    "job_id": job.job_id,
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
                self._log(f"gpu-exec {job.job_id}: exit_code={result.returncode}")
                if result.returncode != 0:
                    job.error = f"Command exited with code {result.returncode}"
            except subprocess.TimeoutExpired:
                job.error = f"Command timed out after {job.timeout_seconds}s"
                job.result = {"job_id": job.job_id, "exit_code": -1, "stdout": "", "stderr": "Timed out"}
                self._log(f"gpu-exec {job.job_id}: TIMED OUT")
            except FileNotFoundError as exc:
                job.error = f"Command not found: {exc}"
                self._log(f"gpu-exec {job.job_id}: {job.error}")
            finally:
                if llama_was_running:
                    try:
                        self._log("Restarting llama-server after gpu-exec")
                        self._start_llama_server()
                        self._warmup_llama_server()
                        self._restore_llama_slots()
                        self._log("llama-server restored and ready after gpu-exec")
                    except Exception as exc:
                        restore_error = f"Failed to restore llama-server: {exc}"
                        self.last_error = restore_error
                        self._log(restore_error)
                if whisper_was_running:
                    try:
                        self._start_whisper_server()
                    except Exception as exc:
                        self._log(f"Warning: failed to restart whisper-server: {exc}")

        if restore_error and not job.error:
            job.error = restore_error

    # -- ComfyUI job execution -----------------------------------------------

    def _run_job(self, job: Job) -> dict[str, Any]:
        client_id = f"openclaw-broker-{uuid.uuid4()}"
        response = request_json(
            "POST",
            f"{self.config.comfy_base_url}/prompt",
            payload={"prompt": job.workflow, "client_id": client_id},
            timeout=30,
        )
        prompt_id = response.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI did not return prompt_id: {response}")
        self._log(f"Submitted prompt {prompt_id} for job {job.job_id}")

        deadline = time.time() + job.timeout_seconds
        last_seen = None
        poll_errors = 0
        while time.time() < deadline:
            if self.comfy_process and self.comfy_process.poll() is not None:
                raise RuntimeError(f"ComfyUI process died (exit code {self.comfy_process.returncode}) while waiting for prompt {prompt_id}")
            try:
                history = request_json("GET", f"{self.config.comfy_base_url}/history/{prompt_id}", timeout=30)
            except Exception as poll_exc:
                poll_errors += 1
                if poll_errors <= 3 or poll_errors % 10 == 0:
                    self._log(f"Poll error #{poll_errors} for prompt {prompt_id}: {poll_exc}")
                time.sleep(2)
                continue
            if history:
                record = history.get(prompt_id)
                if record is None and len(history) == 1:
                    record = next(iter(history.values()))
                if record:
                    last_seen = record
                    status = record.get("status", {})
                    status_text = status.get("status_str")
                    if status_text == "error":
                        messages = status.get("messages") or []
                        raise RuntimeError(f"ComfyUI prompt failed: {messages}")
                    outputs = self._extract_outputs(record)
                    if outputs:
                        self._wait_for_output_files(outputs)
                        if poll_errors:
                            self._log(f"Prompt {prompt_id} finished with {len(outputs)} output file(s) ({poll_errors} transient poll errors)")
                        else:
                            self._log(f"Prompt {prompt_id} finished with {len(outputs)} output file(s)")
                        return {
                            "job_id": job.job_id,
                            "prompt_id": prompt_id,
                            "outputs": outputs,
                            "status": status,
                        }
            time.sleep(1)

        raise RuntimeError(f"Timed out waiting for prompt {prompt_id}; last_seen={last_seen}")

    def _wait_for_output_files(self, outputs: list[dict[str, Any]], timeout: float = 15.0) -> None:
        """Wait until all output files exist on disk (guards against flush race)."""
        deadline = time.time() + timeout
        for out in outputs:
            path = Path(out.get("path", ""))
            if not path.name:
                continue
            while time.time() < deadline:
                if path.exists() and path.stat().st_size > 0:
                    break
                time.sleep(0.5)
            else:
                self._log(f"Warning: output file not found after {timeout}s: {path}")

    def _extract_outputs(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        outputs_root = record.get("outputs", {})
        results: list[dict[str, Any]] = []
        for node_id, node_output in outputs_root.items():
            if not isinstance(node_output, dict):
                continue
            for media_key in ("images", "audio", "gifs"):
                items = node_output.get(media_key, [])
                for item in items:
                    filename = item.get("filename")
                    if not filename:
                        continue
                    subfolder = item.get("subfolder", "")
                    item_type = item.get("type", "output")
                    base_dir = self.config.comfy_output_dir if item_type == "output" else self.config.comfy_input_dir
                    path = base_dir / subfolder / filename if subfolder else base_dir / filename
                    results.append(
                        {
                            "node_id": node_id,
                            "filename": filename,
                            "subfolder": subfolder,
                            "type": item_type,
                            "path": str(path),
                        }
                    )
        return results


class BrokerHandler(BaseHTTPRequestHandler):
    state: BrokerState

    def do_GET(self) -> None:
        parsed = urlparse.urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(200, self.state.status())
            return
        if parsed.path == "/v1/file":
            self.state._log(f"GET /v1/file query={parsed.query}")
            self._handle_file(parsed.query)
            return
        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        self.state._log(f"POST {self.path} from {self.client_address}")
        if self.path == "/v1/generate":
            self._handle_generate()
            return
        if self.path == "/v1/gpu-exec":
            self._handle_gpu_exec()
            return
        if self.path == "/v1/gpu-exec-poll":
            self._handle_gpu_exec_poll()
            return
        if self.path == "/v1/upload":
            self._handle_upload()
            return
        self.send_error(404, "Not Found")

    def _handle_generate(self) -> None:
        try:
            payload = self._read_json_body()
            jobs = self._build_jobs(payload)
        except Exception as exc:
            self._send_json(400, {"error": str(exc)})
            return

        for job in jobs:
            self.state.enqueue(job)

        for job in jobs:
            job.event.wait(timeout=job.timeout_seconds + 60)

        errors = [job.error for job in jobs if job.error]
        if errors:
            self._send_json(
                500,
                {
                    "status": "error",
                    "errors": errors,
                    "results": [job.result for job in jobs if job.result],
                },
            )
            return

        self._send_json(
            200,
            {
                "status": "ok",
                "count": len(jobs),
                "results": [job.result for job in jobs if job.result],
            },
        )

    def _handle_file(self, query: str) -> None:
        params = urlparse.parse_qs(query, keep_blank_values=True)
        filename = (params.get("filename") or [""])[0]
        subfolder = (params.get("subfolder") or [""])[0]
        image_type = (params.get("type") or ["output"])[0]

        if not filename:
            self.send_error(400, "Missing filename")
            return

        try:
            target_path = self._resolve_file_path(filename=filename, subfolder=subfolder, image_type=image_type)
        except ValueError as exc:
            self.send_error(400, str(exc))
            return

        if not target_path.exists() or not target_path.is_file():
            self.send_error(404, "File not found")
            return

        body = target_path.read_bytes()
        media_type, _ = mimetypes.guess_type(target_path.name)
        self.send_response(200)
        self.send_header("Content-Type", media_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'inline; filename="{target_path.name}"')
        self.end_headers()
        self.wfile.write(body)

    def _resolve_file_path(self, filename: str, subfolder: str, image_type: str) -> Path:
        if image_type not in {"output", "input"}:
            raise ValueError("type must be 'output' or 'input'")

        if Path(filename).name != filename:
            raise ValueError("filename must not include directories")

        base_dir = self.state.config.comfy_output_dir if image_type == "output" else self.state.config.comfy_input_dir
        candidate = (base_dir / subfolder / filename) if subfolder else (base_dir / filename)
        resolved = candidate.resolve()
        base_resolved = base_dir.resolve()

        try:
            resolved.relative_to(base_resolved)
        except ValueError as exc:
            raise ValueError("requested file is outside allowed directory") from exc

        return resolved

    def _handle_gpu_exec(self) -> None:
        """Accept a gpu-exec request: run a command with GPU access (swaps llama-server).

        Blocking mode (default): waits for the command to finish and returns result.
        Async mode (async=true): queues the job and returns immediately with job_id.
        """
        try:
            payload = self._read_json_body()
        except Exception as exc:
            self._send_json(400, {"error": str(exc)})
            return

        command = payload.get("command")
        if not command or not isinstance(command, list):
            self._send_json(400, {"error": "command must be a non-empty list of strings"})
            return
        for i, arg in enumerate(command):
            if not isinstance(arg, str):
                self._send_json(400, {"error": f"command[{i}] must be a string"})
                return

        timeout_seconds = int(payload.get("timeout_seconds", 900))
        cwd = payload.get("cwd")
        async_mode = payload.get("async", False)
        use_wsl = payload.get("wsl", False)
        needs_gpu = payload.get("needs_gpu", True)

        # Auto-wrap command with WSL if requested
        if use_wsl:
            command = ["wsl", "-d", "Ubuntu", "--"] + command

        job = GpuExecJob(
            command=command,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            needs_gpu=bool(needs_gpu),
        )
        self.state.enqueue_gpu_exec(job)
        self.state._log(f"gpu-exec job {job.job_id} queued (timeout={timeout_seconds}s, async={async_mode})")

        if async_mode:
            self._send_json(202, {"status": "queued", "job_id": job.job_id})
            return

        # Blocking: wait for completion
        if not job.event.wait(timeout=timeout_seconds + 120):
            self._send_json(504, {"error": "Timed out waiting for gpu-exec result", "job_id": job.job_id})
            return

        status_code = 200 if not job.error else 500
        response: dict[str, Any] = {"status": "ok" if not job.error else "error", "job_id": job.job_id}
        if job.result:
            response.update(job.result)
        if job.error:
            response["error"] = job.error
        self._send_json(status_code, response)

    def _handle_gpu_exec_poll(self) -> None:
        """Poll for a gpu-exec job result (unused for now — reserved for async mode)."""
        self._send_json(501, {"error": "Poll not implemented yet; use blocking mode"})

    def _handle_upload(self) -> None:
        """Accept a binary file upload (image or audio) → save to ComfyUI input dir, return filename."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self._send_json(400, {"error": "Empty body"})
            return
        max_size = 50 * 1024 * 1024  # 50 MB
        if content_length > max_size:
            self._send_json(413, {"error": f"File too large (max {max_size} bytes)"})
            return

        body = self.rfile.read(content_length)
        ext = ".png"
        ct = (self.headers.get("Content-Type") or "").lower()
        if "jpeg" in ct or "jpg" in ct:
            ext = ".jpg"
        elif "webp" in ct:
            ext = ".webp"
        elif "audio/wav" in ct or "audio/x-wav" in ct:
            ext = ".wav"
        elif "audio/mpeg" in ct:
            ext = ".mp3"
        elif "audio/ogg" in ct:
            ext = ".ogg"
        elif "audio/flac" in ct:
            ext = ".flac"
        elif "audio/mp4" in ct or "audio/m4a" in ct:
            ext = ".m4a"
        elif "audio/aac" in ct:
            ext = ".aac"

        filename = f"openclaw-upload-{uuid.uuid4().hex[:12]}{ext}"
        target = self.state.config.comfy_input_dir / filename
        target.write_bytes(body)
        self.state._log(f"Uploaded {len(body)} bytes -> {target}")
        self._send_json(200, {"filename": filename, "size": len(body)})

    def _build_jobs(self, payload: dict[str, Any]) -> list[Job]:
        workflow = payload.get("workflow")
        workflow_path = payload.get("workflow_path")
        replacements = payload.get("replacements") or {}
        copies = int(payload.get("copies", 1))
        timeout_seconds = int(payload.get("timeout_seconds", self.state.config.default_timeout_seconds))

        if copies < 1:
            raise ValueError("copies must be >= 1")
        if workflow is None and not workflow_path:
            raise ValueError("Provide workflow or workflow_path")
        if workflow is not None and not isinstance(workflow, dict):
            raise ValueError("workflow must be an object")
        if workflow_path and workflow is None:
            workflow = read_json_file(workflow_path)

        jobs: list[Job] = []
        for _ in range(copies):
            graph = copy.deepcopy(workflow)
            if replacements:
                graph = replace_placeholders(graph, replacements)
            jobs.append(Job(workflow=graph, timeout_seconds=timeout_seconds))
        return jobs

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            raise ValueError("Missing JSON body")
        raw = self.rfile.read(content_length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # Client disconnected before response was sent

    def log_message(self, format: str, *args: Any) -> None:
        _raw_log(f"HTTP {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenClaw ComfyUI broker")
    parser.add_argument("--port", type=int, default=None, help="Broker port override")
    args = parser.parse_args()

    config = BrokerConfig.from_env(broker_port_override=args.port)
    setup_logging(config.broker_log_file)
    state = BrokerState(config)
    BrokerHandler.state = state

    server = ExclusiveHTTPServer((config.broker_host, config.broker_port), BrokerHandler)
    _raw_log(f"Listening on http://{config.broker_host}:{config.broker_port}")
    _raw_log(f"ComfyUI port: {config.comfy_port} | batch_wait={config.batch_wait_seconds}s | batch_max={config.batch_max}")
    _raw_log(f"Comfy app dir: {config.comfy_app_dir}")
    _raw_log(f"Broker log file: {config.broker_log_file or 'disabled'}")
    _raw_log(f"llama_server_exe: {config.llama_server_exe}")
    _raw_log(f"llama_model: {config.llama_model}")
    _raw_log(f"use_backend: {config.use_backend} | llama_port: {config.llama_port}")
    if config.llama_mmproj and config.llama_mmproj.exists():
        _raw_log("KV slot persistence: disabled for multimodal llama-server (--mmproj); upstream slot save/restore returns 501")
    else:
        _raw_log(f"KV slot persistence: enabled | slot_save_path={config.llama_slot_save_path}")
    _raw_log("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        state._stop_comfy()


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""Local Whisper transcription server using faster-whisper.

Runs on CPU with the 'medium' model (~5GB RAM).
Listens on port 8787 for:
  POST /transcribe              – legacy raw-body endpoint
  POST /v1/audio/transcriptions – OpenAI-compatible multipart endpoint

Usage:
    py -3.12 whisper-server.py
    py -3.12 whisper-server.py --model large-v3 --port 8787
"""

import argparse
import cgi
import io
import json
import os
import sys
import tempfile
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

# Lazy-loaded model
_model = None
_model_name = None


def get_model(model_name: str):
    """Load the Whisper model (lazy, loads once on first request)."""
    global _model, _model_name
    if _model is None or _model_name != model_name:
        from faster_whisper import WhisperModel
        print(f"[whisper] Loading model '{model_name}' on CPU (int8)...")
        t0 = time.time()
        _model = WhisperModel(model_name, device="cpu", compute_type="int8")
        _model_name = model_name
        print(f"[whisper] Model loaded in {time.time() - t0:.1f}s")
    return _model


class WhisperHandler(BaseHTTPRequestHandler):
    """HTTP handler for /transcribe endpoint."""

    protocol_version = "HTTP/1.1"
    model_name = "medium"

    def do_POST(self):
        if self.path == "/transcribe":
            self._handle_raw_transcribe()
        elif self.path == "/v1/audio/transcriptions":
            self._handle_openai_transcribe()
        else:
            self.send_error(404, "Not Found")

    def _handle_raw_transcribe(self):
        """Legacy endpoint: raw audio bytes in request body."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self.send_error(400, "No audio data")
            return
        audio_data = self.rfile.read(content_length)

        # Get optional language and prompt from headers
        language = self.headers.get("X-Language", "es")
        prompt = self.headers.get("X-Prompt", None)
        self._transcribe_and_respond(audio_data, ".ogg", language, prompt, openai_format=False)

    def _handle_openai_transcribe(self):
        """OpenAI-compatible multipart/form-data endpoint used by ZeroClaw."""
        content_length = int(self.headers.get("Content-Length", 0))
        content_type = self.headers.get("Content-Type", "")
        if content_length == 0:
            self.send_error(400, "No audio data")
            return
        body = self.rfile.read(content_length)

        # Parse multipart form data
        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": str(content_length),
        }
        form = cgi.FieldStorage(fp=io.BytesIO(body), environ=environ, keep_blank_values=True)

        file_item = form.getvalue("file")
        if file_item is None:
            self.send_error(400, "Missing 'file' field in multipart form")
            return
        # cgi may return bytes or a MiniFieldStorage; normalise to bytes
        if not isinstance(file_item, bytes):
            self.send_error(400, "Could not read audio file bytes")
            return

        # Derive extension from uploaded filename (for temp file suffix)
        file_field = form["file"]
        filename = getattr(file_field, "filename", None) or "audio.ogg"
        ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".ogg"

        language = form.getvalue("language") or "es"
        self._transcribe_and_respond(file_item, ext, language, prompt=None, openai_format=True)

    def _transcribe_and_respond(self, audio_data, suffix, language, prompt, openai_format):
        """Core transcription logic shared by both endpoints."""
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name

        try:
            model = get_model(self.model_name)
            t0 = time.time()

            kwargs = {"language": language, "beam_size": 5, "vad_filter": True}
            if prompt:
                kwargs["initial_prompt"] = prompt

            segments, info = model.transcribe(tmp_path, **kwargs)
            text = " ".join(seg.text.strip() for seg in segments)
            elapsed = time.time() - t0

            if openai_format:
                # OpenAI-compatible response: {"text": "..."}
                result = {"text": text}
            else:
                result = {
                    "text": text,
                    "language": info.language,
                    "language_probability": round(info.language_probability, 3),
                    "duration": round(info.duration, 2),
                    "processing_time": round(elapsed, 2),
                }

            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

            print(f"[whisper] Transcribed {info.duration:.1f}s audio in {elapsed:.1f}s: {text[:80]}...")

        except Exception as e:
            self.send_error(500, str(e))
        finally:
            os.unlink(tmp_path)

    def do_GET(self):
        if self.path == "/health":
            body = json.dumps({
                "status": "ok",
                "model": self.model_name,
                "loaded": _model is not None,
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404, "Not Found")

    def log_message(self, format, *args):
        # Quieter logging
        pass


def main():
    parser = argparse.ArgumentParser(description="Faster-Whisper transcription server")
    parser.add_argument("--model", default="medium", help="Whisper model (tiny/base/small/medium/large-v3)")
    parser.add_argument("--port", type=int, default=8787, help="Server port")
    parser.add_argument("--preload", action="store_true", help="Load model immediately on startup")
    args = parser.parse_args()

    WhisperHandler.model_name = args.model

    if args.preload:
        get_model(args.model)

    server = HTTPServer(("0.0.0.0", args.port), WhisperHandler)
    print(f"[whisper] Server listening on http://0.0.0.0:{args.port}")
    print(f"[whisper] Model: {args.model} | Device: CPU (int8)")
    print(f"[whisper] {'Model preloaded' if args.preload else 'Model will load on first request'}")
    print(f"[whisper] Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[whisper] Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()

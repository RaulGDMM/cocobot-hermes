#!/usr/bin/env python3
"""Wyoming protocol bridge for the existing Whisper HTTP server.

Bridges the Wyoming protocol (used by Home Assistant Assist) to the local
whisper-server.py running on port 8787 with OpenAI-compatible API.

This avoids loading a second Whisper model — it reuses the already-running
faster-whisper server, just translating the protocol.

Usage:
    py -3.12 wyoming-whisper-bridge.py
    py -3.12 wyoming-whisper-bridge.py --whisper-url http://localhost:8787 --port 10300
"""

import argparse
import asyncio
import io
import json
import logging
import uuid
import wave
from functools import partial
from urllib.request import Request, urlopen

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioChunkConverter, AudioStop
from wyoming.event import Event
from wyoming.info import AsrModel, AsrProgram, Attribution, Describe, Info
from wyoming.server import AsyncEventHandler, AsyncServer

_LOGGER = logging.getLogger(__name__)


class WhisperBridgeHandler(AsyncEventHandler):
    """Bridges Wyoming STT requests to existing Whisper HTTP server."""

    def __init__(
        self,
        wyoming_info: Info,
        whisper_url: str,
        default_language: str,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.wyoming_info = wyoming_info
        self.whisper_url = whisper_url
        self._language = default_language
        self._audio_converter = AudioChunkConverter(rate=16000, width=2, channels=1)
        self._wav_io: io.BytesIO | None = None
        self._wav_file: wave.Wave_write | None = None

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info.event())
            return True

        if Transcribe.is_type(event.type):
            t = Transcribe.from_event(event)
            if t.language:
                self._language = t.language
            _LOGGER.debug("Language: %s", self._language)
            return True

        if AudioChunk.is_type(event.type):
            chunk = self._audio_converter.convert(AudioChunk.from_event(event))
            if self._wav_file is None:
                self._wav_io = io.BytesIO()
                self._wav_file = wave.open(self._wav_io, "wb")
                self._wav_file.setframerate(chunk.rate)
                self._wav_file.setsampwidth(chunk.width)
                self._wav_file.setnchannels(chunk.channels)
            self._wav_file.writeframes(chunk.audio)
            return True

        if AudioStop.is_type(event.type):
            if self._wav_file is None:
                await self.write_event(Transcript(text="").event())
                return False

            self._wav_file.close()
            wav_data = self._wav_io.getvalue()

            _LOGGER.debug("Audio received: %d bytes WAV", len(wav_data))

            # Transcribe via HTTP in a thread to avoid blocking
            text = await asyncio.to_thread(
                self._transcribe_http, wav_data
            )

            _LOGGER.info("Transcript: %s", text)
            await self.write_event(Transcript(text=text).event())

            # Reset
            self._wav_file = None
            self._wav_io = None
            return False

        return True

    def _transcribe_http(self, wav_data: bytes) -> str:
        """Send WAV data to whisper-server via multipart POST."""
        boundary = uuid.uuid4().hex

        body = b""
        # File part
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="file"; filename="speech.wav"\r\n'
        body += b"Content-Type: audio/wav\r\n\r\n"
        body += wav_data
        body += b"\r\n"
        # Language part
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="language"\r\n\r\n'
        body += self._language.encode()
        body += b"\r\n"
        body += f"--{boundary}--\r\n".encode()

        url = f"{self.whisper_url}/v1/audio/transcriptions"
        req = Request(
            url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("text", "")
        except Exception:
            _LOGGER.exception("Whisper HTTP request failed")
            return ""


async def main():
    parser = argparse.ArgumentParser(description="Wyoming ↔ Whisper HTTP bridge")
    parser.add_argument(
        "--whisper-url",
        default="http://localhost:8787",
        help="URL of the whisper-server.py HTTP endpoint (default: http://localhost:8787)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=10300,
        help="Wyoming TCP port to listen on (default: 10300)",
    )
    parser.add_argument(
        "--language",
        default="es",
        help="Default language for transcription (default: es)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    wyoming_info = Info(
        asr=[
            AsrProgram(
                name="whisper-bridge",
                description="Whisper HTTP bridge (faster-whisper medium)",
                attribution=Attribution(
                    name="OpenClaw",
                    url="https://github.com/AiClaw/OpenClaw",
                ),
                installed=True,
                version="1.0.0",
                models=[
                    AsrModel(
                        name="medium",
                        description="faster-whisper medium (int8, CPU)",
                        attribution=Attribution(
                            name="Systran",
                            url="https://huggingface.co/Systran",
                        ),
                        installed=True,
                        version="1.0.0",
                        languages=["es", "en", "fr", "de", "it", "pt", "ca", "eu", "gl"],
                    )
                ],
            )
        ],
    )

    server = AsyncServer.from_uri(f"tcp://0.0.0.0:{args.port}")
    _LOGGER.info("Wyoming Whisper Bridge listening on tcp://0.0.0.0:%d", args.port)
    _LOGGER.info("Forwarding to %s (language: %s)", args.whisper_url, args.language)

    await server.run(
        partial(
            WhisperBridgeHandler,
            wyoming_info,
            args.whisper_url,
            args.language,
        )
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

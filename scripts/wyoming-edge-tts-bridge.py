#!/usr/bin/env python3
"""Wyoming protocol bridge for Microsoft Edge TTS.

Bridges the Wyoming protocol (used by Home Assistant Assist) to Microsoft
Edge TTS, using the same voice as OpenClaw/Cocobot (es-ES-AlvaroNeural).

Uses system ffmpeg for MP3→PCM conversion.

Usage:
    python3 wyoming-edge-tts-bridge.py
    python3 wyoming-edge-tts-bridge.py --voice es-ES-AlvaroNeural --port 10200
"""

import argparse
import asyncio
import io
import logging
import shutil
import subprocess
from functools import partial

import edge_tts

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import Attribution, Describe, Info, TtsProgram, TtsVoice
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.tts import Synthesize

_LOGGER = logging.getLogger(__name__)

RATE = 16000
WIDTH = 2       # 16-bit
CHANNELS = 1
SAMPLES_PER_CHUNK = 1024
BYTES_PER_CHUNK = SAMPLES_PER_CHUNK * WIDTH * CHANNELS

# Resolve ffmpeg once at module level
_ffmpeg_path: str | None = None


def _get_ffmpeg() -> str:
    """Get path to ffmpeg binary."""
    global _ffmpeg_path
    if _ffmpeg_path is None:
        _ffmpeg_path = shutil.which("ffmpeg")
        if not _ffmpeg_path:
            raise RuntimeError("ffmpeg not found in PATH")
        _LOGGER.info("ffmpeg: %s", _ffmpeg_path)
    return _ffmpeg_path


class EdgeTtsBridgeHandler(AsyncEventHandler):
    """Bridges Wyoming TTS requests to Microsoft Edge TTS."""

    def __init__(
        self,
        wyoming_info: Info,
        default_voice: str,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.wyoming_info = wyoming_info
        self.default_voice = default_voice

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info.event())
            return True

        if Synthesize.is_type(event.type):
            synth = Synthesize.from_event(event)
            text = synth.text

            # Voice override from pipeline config
            voice = self.default_voice
            if synth.voice and synth.voice.name:
                voice = synth.voice.name

            _LOGGER.info("Synthesize [%s]: %s", voice, text[:100])

            # Generate audio
            pcm_audio = await self._synthesize(text, voice)

            if pcm_audio:
                await self.write_event(
                    AudioStart(rate=RATE, width=WIDTH, channels=CHANNELS).event()
                )

                # Send in chunks
                offset = 0
                while offset < len(pcm_audio):
                    chunk = pcm_audio[offset : offset + BYTES_PER_CHUNK]
                    await self.write_event(
                        AudioChunk(
                            audio=chunk,
                            rate=RATE,
                            width=WIDTH,
                            channels=CHANNELS,
                        ).event()
                    )
                    offset += BYTES_PER_CHUNK

                await self.write_event(AudioStop().event())
                _LOGGER.debug("Sent %d bytes PCM audio", len(pcm_audio))
            else:
                _LOGGER.warning("No audio generated")

            return False  # disconnect after response

        return True

    async def _synthesize(self, text: str, voice: str) -> bytes:
        """Generate PCM audio from text using edge-tts + ffmpeg."""
        # Collect MP3 from edge-tts
        communicate = edge_tts.Communicate(text, voice)
        mp3_data = io.BytesIO()

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_data.write(chunk["data"])

        mp3_bytes = mp3_data.getvalue()
        if not mp3_bytes:
            _LOGGER.warning("Edge TTS returned empty audio")
            return b""

        _LOGGER.debug("Edge TTS produced %d bytes MP3", len(mp3_bytes))

        # Convert MP3 → 16kHz 16-bit mono PCM via ffmpeg
        pcm = await asyncio.to_thread(self._mp3_to_pcm, mp3_bytes)
        return pcm

    @staticmethod
    def _mp3_to_pcm(mp3_bytes: bytes) -> bytes:
        """Convert MP3 bytes to raw PCM (16kHz, 16-bit, mono)."""
        ffmpeg = _get_ffmpeg()
        proc = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel", "error",
                "-i", "pipe:0",
                "-f", "s16le",
                "-ar", str(RATE),
                "-ac", str(CHANNELS),
                "-acodec", "pcm_s16le",
                "pipe:1",
            ],
            input=mp3_bytes,
            capture_output=True,
            timeout=30,
        )
        if proc.returncode != 0:
            _LOGGER.error("ffmpeg error: %s", proc.stderr.decode(errors="replace")[:300])
            return b""
        return proc.stdout


async def main():
    parser = argparse.ArgumentParser(description="Wyoming ↔ Edge TTS bridge")
    parser.add_argument(
        "--voice",
        default="es-ES-AlvaroNeural",
        help="Default Edge TTS voice (default: es-ES-AlvaroNeural)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=10200,
        help="Wyoming TCP port to listen on (default: 10200)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Pre-resolve ffmpeg
    _get_ffmpeg()

    wyoming_info = Info(
        tts=[
            TtsProgram(
                name="edge-tts",
                description="Microsoft Edge TTS",
                attribution=Attribution(
                    name="Microsoft",
                    url="https://www.microsoft.com/",
                ),
                installed=True,
                version="1.0.0",
                voices=[
                    TtsVoice(
                        name="es-ES-AlvaroNeural",
                        description="Alvaro - Spanish (Spain) Neural",
                        attribution=Attribution(
                            name="Microsoft",
                            url="https://www.microsoft.com/",
                        ),
                        installed=True,
                        version="1.0.0",
                        languages=["es"],
                    ),
                    TtsVoice(
                        name="es-ES-ElviraNeural",
                        description="Elvira - Spanish (Spain) Neural",
                        attribution=Attribution(
                            name="Microsoft",
                            url="https://www.microsoft.com/",
                        ),
                        installed=True,
                        version="1.0.0",
                        languages=["es"],
                    ),
                    TtsVoice(
                        name="en-US-GuyNeural",
                        description="Guy - English (US) Neural",
                        attribution=Attribution(
                            name="Microsoft",
                            url="https://www.microsoft.com/",
                        ),
                        installed=True,
                        version="1.0.0",
                        languages=["en"],
                    ),
                ],
            )
        ],
    )

    server = AsyncServer.from_uri(f"tcp://0.0.0.0:{args.port}")
    _LOGGER.info("Wyoming Edge TTS Bridge listening on tcp://0.0.0.0:%d", args.port)
    _LOGGER.info("Default voice: %s", args.voice)

    await server.run(
        partial(
            EdgeTtsBridgeHandler,
            wyoming_info,
            args.voice,
        )
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

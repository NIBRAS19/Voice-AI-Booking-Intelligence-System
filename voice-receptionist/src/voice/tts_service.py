"""
Text-to-Speech service using Piper TTS.
Self-hosted, low-latency, natural-sounding speech.
"""

import asyncio
import subprocess
from typing import Optional
from pathlib import Path
import tempfile
import os

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class TTSService:
    """
    Text-to-Speech service using Piper TTS.
    
    Features:
    - Local/self-hosted (no API costs)
    - Very low latency (~50-100ms)
    - Natural-sounding voices
    - Multiple voice options
    """
    
    def __init__(self):
        self.voice = settings.piper_voice
        self.speed = settings.piper_speed
        self._piper_available = False
        self._check_piper()
    
    def _check_piper(self) -> None:
        """Check if Piper is available."""
        try:
            result = subprocess.run(
                ["piper", "--version"],
                capture_output=True,
                timeout=5,
            )
            self._piper_available = result.returncode == 0
            if self._piper_available:
                logger.info("Piper TTS available", voice=self.voice)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("Piper TTS not installed, using mock TTS")
            self._piper_available = False
    
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> bytes:
        """
        Convert text to speech audio.
        
        Args:
            text: Text to synthesize
            voice: Voice model (optional, uses default)
            speed: Speech speed multiplier (optional)
        
        Returns:
            Raw audio bytes (WAV format, 22050Hz, mono)
        """
        if not self._piper_available:
            return await self._mock_synthesize(text)
        
        voice = voice or self.voice
        speed = speed or self.speed
        
        # Run Piper in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._synthesize_sync,
            text,
            voice,
            speed,
        )
    
    def _synthesize_sync(
        self,
        text: str,
        voice: str,
        speed: float,
    ) -> bytes:
        """Synchronous speech synthesis."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            output_path = f.name
        
        try:
            # Run Piper
            cmd = [
                "piper",
                "--model", voice,
                "--output_file", output_path,
                "--length_scale", str(1.0 / speed),
            ]
            
            process = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=30,
            )
            
            if process.returncode != 0:
                logger.error("Piper synthesis failed", error=process.stderr.decode())
                return b""
            
            # Read output
            with open(output_path, "rb") as f:
                return f.read()
        
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    async def synthesize_stream(
        self,
        text: str,
        chunk_size: int = 4096,
    ):
        """
        Stream synthesized audio in chunks.
        
        For lower latency, we can start sending audio
        before synthesis is complete.
        
        Args:
            text: Text to synthesize
            chunk_size: Size of audio chunks to yield
        
        Yields:
            Audio data chunks
        """
        # For sentence-by-sentence streaming
        sentences = self._split_sentences(text)
        
        for sentence in sentences:
            if sentence.strip():
                audio = await self.synthesize(sentence)
                
                # Yield in chunks
                for i in range(0, len(audio), chunk_size):
                    yield audio[i:i + chunk_size]
    
    def _split_sentences(self, text: str) -> list:
        """Split text into sentences for streaming."""
        import re
        # Split on sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s for s in sentences if s.strip()]
    
    async def _mock_synthesize(self, text: str) -> bytes:
        """Generate mock audio for testing."""
        # Generate a simple WAV header + silence
        sample_rate = 22050
        duration = len(text) * 0.05  # ~50ms per character
        num_samples = int(sample_rate * duration)
        
        # WAV header
        import struct
        
        wav_header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF',
            36 + num_samples * 2,
            b'WAVE',
            b'fmt ',
            16,
            1,  # PCM
            1,  # Mono
            sample_rate,
            sample_rate * 2,
            2,  # Block align
            16,  # Bits per sample
            b'data',
            num_samples * 2,
        )
        
        # Generate silence
        silence = b'\x00' * (num_samples * 2)
        
        return wav_header + silence
    
    @staticmethod
    def get_available_voices() -> list:
        """Get list of available Piper voices."""
        # Common Piper voice models
        return [
            "en_US-lessac-medium",
            "en_US-amy-medium",
            "en_US-ryan-medium",
            "en_GB-alan-medium",
            "en_GB-alba-medium",
        ]


class CartesiaTTSService:
    """
    Alternative TTS using Cartesia API.
    Higher quality but requires API key and costs money.
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.voice_id = "a0e99841-438c-4a64-b679-ae501e7d6091"
        self.api_url = "https://api.cartesia.ai/tts/bytes"
    
    async def synthesize(self, text: str) -> bytes:
        """Synthesize using Cartesia API."""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.api_url,
                headers={
                    "X-API-Key": self.api_key,
                    "Cartesia-Version": "2024-06-10",
                },
                json={
                    "model_id": "sonic-english",
                    "transcript": text,
                    "voice": {"mode": "id", "id": self.voice_id},
                    "output_format": {
                        "container": "raw",
                        "encoding": "pcm_mulaw",
                        "sample_rate": 8000,
                    },
                },
            ) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    logger.error("Cartesia TTS failed", status=response.status)
                    return b""

"""
Speech-to-Text service using faster-whisper.
Self-hosted, low-latency, accurate transcription.
"""

import asyncio
from typing import Optional, List, Callable, AsyncGenerator
from pathlib import Path
import tempfile
import os

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class STTService:
    """
    Speech-to-Text service using faster-whisper.
    
    Features:
    - Local/self-hosted (no API costs)
    - Low latency (~300ms for medium model)
    - High accuracy (95%+)
    - Streaming support
    """
    
    def __init__(self):
        self.model = None
        self.model_name = settings.whisper_model
        self.device = settings.whisper_device
        self._loaded = False
    
    async def load_model(self) -> None:
        """Load the Whisper model asynchronously."""
        if self._loaded:
            return
        
        logger.info(
            "Loading Whisper model",
            model=self.model_name,
            device=self.device,
        )
        
        # Load in thread pool to not block event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_model_sync)
        
        self._loaded = True
        logger.info("Whisper model loaded successfully")
    
    def _load_model_sync(self) -> None:
        """Synchronous model loading."""
        try:
            from faster_whisper import WhisperModel
            
            compute_type = "float16" if self.device == "cuda" else "int8"
            
            self.model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=compute_type,
            )
        except ImportError:
            logger.warning("faster-whisper not installed, using mock STT")
            self.model = None
    
    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "en",
    ) -> dict:
        """
        Transcribe audio data to text.
        
        Args:
            audio_data: Raw audio bytes (PCM or WAV)
            language: Language code
        
        Returns:
            Dict with transcript and metadata
        """
        if not self._loaded:
            await self.load_model()
        
        if self.model is None:
            # Mock response for testing
            return {
                "text": "[Mock transcript - Whisper not loaded]",
                "confidence": 0.0,
                "language": language,
            }
        
        # Write to temp file (faster-whisper needs file path)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_data)
            temp_path = f.name
        
        try:
            # Run transcription in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._transcribe_sync,
                temp_path,
                language,
            )
            return result
        finally:
            # Clean up temp file
            os.unlink(temp_path)
    
    def _transcribe_sync(self, audio_path: str, language: str) -> dict:
        """Synchronous transcription."""
        segments, info = self.model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            best_of=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300),
        )
        
        # Combine segments
        full_text = ""
        total_confidence = 0
        segment_count = 0
        
        for segment in segments:
            full_text += segment.text
            total_confidence += segment.avg_logprob
            segment_count += 1
        
        avg_confidence = total_confidence / max(segment_count, 1)
        
        return {
            "text": full_text.strip(),
            "confidence": min(1.0, max(0.0, 1 + avg_confidence)),
            "language": info.language,
            "duration_seconds": info.duration,
        }
    
    async def transcribe_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None],
        on_transcript: Callable[[str], None],
        language: str = "en",
    ) -> str:
        """
        Transcribe streaming audio.
        
        For real-time voice, we accumulate audio chunks and
        transcribe when silence is detected.
        
        Args:
            audio_stream: Async generator yielding audio chunks
            on_transcript: Callback for interim results
            language: Language code
        
        Returns:
            Final complete transcript
        """
        if not self._loaded:
            await self.load_model()
        
        audio_buffer = bytearray()
        silence_threshold = 0.02
        silence_duration = 0
        max_silence_ms = 500
        
        full_transcript = ""
        
        async for chunk in audio_stream:
            audio_buffer.extend(chunk)
            
            # Check for voice activity (simplified)
            # In production, use webrtcvad or silero-vad
            is_speech = self._detect_speech(chunk)
            
            if not is_speech:
                silence_duration += len(chunk) / 16  # Assuming 16kHz
                
                if silence_duration >= max_silence_ms and len(audio_buffer) > 3200:
                    # Transcribe accumulated audio
                    result = await self.transcribe(bytes(audio_buffer), language)
                    
                    if result["text"]:
                        full_transcript = result["text"]
                        on_transcript(result["text"])
                    
                    audio_buffer.clear()
                    silence_duration = 0
            else:
                silence_duration = 0
        
        # Transcribe remaining audio
        if len(audio_buffer) > 3200:
            result = await self.transcribe(bytes(audio_buffer), language)
            if result["text"]:
                full_transcript = result["text"]
                on_transcript(result["text"])
        
        return full_transcript
    
    def _detect_speech(self, audio_chunk: bytes) -> bool:
        """
        Simple voice activity detection.
        In production, use webrtcvad or silero-vad.
        """
        import struct
        
        if len(audio_chunk) < 2:
            return False
        
        # Calculate RMS amplitude
        samples = struct.unpack(f"<{len(audio_chunk)//2}h", audio_chunk)
        rms = (sum(s**2 for s in samples) / len(samples)) ** 0.5
        
        return rms > 500  # Threshold for speech


class MockSTTService:
    """Mock STT service for testing without model."""
    
    async def transcribe(self, audio_data: bytes, language: str = "en") -> dict:
        return {
            "text": "I'd like to book an appointment",
            "confidence": 0.95,
            "language": language,
        }

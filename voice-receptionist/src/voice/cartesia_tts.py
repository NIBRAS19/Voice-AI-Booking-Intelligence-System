"""
Cartesia TTS Client.

Text-to-speech using Cartesia's streaming API.
Features:
- Low-latency streaming
- Multiple voice options
- Audio format conversion for Twilio
"""

import asyncio
import base64
import json
from typing import Optional, AsyncGenerator
from uuid import uuid4

import aiohttp

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class CartesiaTTSClient:
    """
    TTS client for Cartesia.
    
    Usage:
        client = CartesiaTTSClient()
        async for audio_chunk in client.synthesize("Hello!"):
            # Send audio to Twilio
            await send_audio(audio_chunk)
    """
    
    CARTESIA_API_URL = "https://api.cartesia.ai/tts/stream"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
        model_id: str = "sonic-english",
        sample_rate: int = 8000,
        output_format: str = "pcm_mulaw",  # Twilio format
    ):
        """
        Initialize Cartesia client.
        
        Args:
            api_key: Cartesia API key
            voice_id: Cartesia voice ID (use default if not specified)
            model_id: Model ID
            sample_rate: Output sample rate (8000 for Twilio)
            output_format: Audio format (pcm_mulaw for Twilio)
        """
        self.api_key = api_key or getattr(settings, 'cartesia_api_key', None)
        self.voice_id = voice_id or getattr(settings, 'cartesia_voice_id', 'a0e99841-438c-4a64-b679-ae501e7d6091')  # Default voice
        self.model_id = model_id
        self.sample_rate = sample_rate
        self.output_format = output_format
        
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure aiohttp session exists."""
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def synthesize(self, text: str) -> AsyncGenerator[str, None]:
        """
        Synthesize speech from text.
        
        Args:
            text: Text to convert to speech
            
        Yields:
            Base64-encoded audio chunks (mulaw format for Twilio)
        """
        if not self.api_key:
            logger.error("Cartesia API key not configured")
            return
        
        if not text.strip():
            return
        
        session = await self._ensure_session()
        
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Cartesia-Version": "2024-06-10",
        }
        
        payload = {
            "model_id": self.model_id,
            "transcript": text,
            "voice": {
                "mode": "id",
                "id": self.voice_id,
            },
            "output_format": {
                "container": "raw",
                "encoding": self.output_format,
                "sample_rate": self.sample_rate,
            },
            "language": "en",
        }
        
        try:
            async with session.post(
                self.CARTESIA_API_URL,
                headers=headers,
                json=payload,
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        "Cartesia API error",
                        status=response.status,
                        error=error_text,
                    )
                    return
                
                # Stream audio chunks
                async for chunk in response.content.iter_chunked(640):  # ~80ms of audio
                    if chunk:
                        # Convert to base64 for Twilio
                        audio_base64 = base64.b64encode(chunk).decode('ascii')
                        yield audio_base64
                        
        except Exception as e:
            logger.error("Cartesia synthesis error", error=str(e))
    
    async def synthesize_full(self, text: str) -> Optional[str]:
        """
        Synthesize full audio at once.
        
        Args:
            text: Text to convert to speech
            
        Returns:
            Base64-encoded full audio or None on error
        """
        chunks = []
        async for chunk in self.synthesize(text):
            chunks.append(base64.b64decode(chunk))
        
        if chunks:
            full_audio = b''.join(chunks)
            return base64.b64encode(full_audio).decode('ascii')
        
        return None
    
    async def close(self) -> None:
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
        
        logger.info("Cartesia client closed")


class AudioConverter:
    """
    Audio format conversion utilities.
    
    Handles conversion between:
    - PCM (16-bit signed) - Most TTS outputs
    - μ-law (8-bit) - Twilio format
    """
    
    # μ-law encoding table
    MULAW_MAX = 0x1FFF
    MULAW_BIAS = 33
    
    @staticmethod
    def pcm_to_mulaw(pcm_data: bytes) -> bytes:
        """
        Convert 16-bit PCM to 8-bit μ-law.
        
        Args:
            pcm_data: 16-bit PCM audio bytes
            
        Returns:
            μ-law encoded bytes
        """
        import struct
        
        mulaw_bytes = bytearray()
        
        # Process 2 bytes at a time (16-bit samples)
        for i in range(0, len(pcm_data), 2):
            if i + 1 >= len(pcm_data):
                break
                
            # Read 16-bit sample
            sample = struct.unpack('<h', pcm_data[i:i+2])[0]
            
            # Convert to μ-law
            mulaw_sample = AudioConverter._encode_mulaw_sample(sample)
            mulaw_bytes.append(mulaw_sample)
        
        return bytes(mulaw_bytes)
    
    @staticmethod
    def _encode_mulaw_sample(sample: int) -> int:
        """Encode a single PCM sample to μ-law."""
        # Get sign
        sign = (sample >> 8) & 0x80
        if sign:
            sample = -sample
        
        # Add bias
        sample = sample + AudioConverter.MULAW_BIAS
        
        # Clamp
        if sample > AudioConverter.MULAW_MAX:
            sample = AudioConverter.MULAW_MAX
        
        # Find segment
        exponent = 7
        segment_mask = 0x1000
        while exponent > 0 and not (sample & segment_mask):
            exponent -= 1
            segment_mask >>= 1
        
        # Get mantissa
        mantissa = (sample >> (exponent + 3)) & 0x0F
        
        # Combine and invert
        return ~(sign | (exponent << 4) | mantissa) & 0xFF
    
    @staticmethod
    def mulaw_to_pcm(mulaw_data: bytes) -> bytes:
        """
        Convert 8-bit μ-law to 16-bit PCM.
        
        Args:
            mulaw_data: μ-law encoded bytes
            
        Returns:
            16-bit PCM audio bytes
        """
        import struct
        
        pcm_bytes = bytearray()
        
        for mulaw_byte in mulaw_data:
            pcm_sample = AudioConverter._decode_mulaw_sample(mulaw_byte)
            pcm_bytes.extend(struct.pack('<h', pcm_sample))
        
        return bytes(pcm_bytes)
    
    @staticmethod
    def _decode_mulaw_sample(mulaw_byte: int) -> int:
        """Decode a single μ-law byte to PCM."""
        mulaw_byte = ~mulaw_byte & 0xFF
        
        sign = mulaw_byte & 0x80
        exponent = (mulaw_byte >> 4) & 0x07
        mantissa = mulaw_byte & 0x0F
        
        sample = (mantissa << 3) + AudioConverter.MULAW_BIAS
        sample <<= exponent
        
        if sign:
            sample = -sample
        
        return sample

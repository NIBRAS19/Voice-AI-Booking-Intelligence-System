"""
Deepgram Streaming STT Client.

Real-time speech-to-text using Deepgram's WebSocket API.
Features:
- Streaming transcription
- Interim results (for barge-in)
- Endpointing detection
"""

import asyncio
import base64
import json
from typing import Optional, Callable, Awaitable
from uuid import uuid4

import websockets
from websockets.exceptions import ConnectionClosed

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class DeepgramSTTClient:
    """
    Streaming STT client for Deepgram.
    
    Usage:
        client = DeepgramSTTClient(on_transcript=handle_transcript)
        await client.connect()
        await client.send_audio(audio_bytes)
        await client.close()
    """
    
    DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"
    
    def __init__(
        self,
        on_transcript: Callable[[str, bool, float], Awaitable[None]],
        api_key: Optional[str] = None,
        model: str = "nova-2",
        language: str = "en-US",
        sample_rate: int = 8000,
        encoding: str = "mulaw",
        channels: int = 1,
    ):
        """
        Initialize Deepgram client.
        
        Args:
            on_transcript: Async callback (text, is_final, confidence)
            api_key: Deepgram API key (defaults to settings)
            model: Deepgram model (nova-2, nova, enhanced)
            language: Language code
            sample_rate: Audio sample rate (8000 for Twilio)
            encoding: Audio encoding (mulaw for Twilio)
            channels: Number of audio channels
        """
        self.api_key = api_key or getattr(settings, 'deepgram_api_key', None)
        self.on_transcript = on_transcript
        self.model = model
        self.language = language
        self.sample_rate = sample_rate
        self.encoding = encoding
        self.channels = channels
        
        self.websocket = None
        self.receive_task = None
        self._is_connected = False
    
    async def connect(self) -> bool:
        """
        Connect to Deepgram WebSocket.
        
        Returns:
            True if connected successfully
        """
        if not self.api_key:
            logger.error("Deepgram API key not configured")
            return False
        
        try:
            # Build URL with query parameters
            params = {
                "model": self.model,
                "language": self.language,
                "sample_rate": str(self.sample_rate),
                "encoding": self.encoding,
                "channels": str(self.channels),
                "interim_results": "true",
                "punctuate": "true",
                "endpointing": "300",  # 300ms silence = end of utterance
                "utterance_end_ms": "1000",
            }
            
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{self.DEEPGRAM_WS_URL}?{query_string}"
            
            headers = {
                "Authorization": f"Token {self.api_key}",
            }
            
            self.websocket = await websockets.connect(
                url,
                extra_headers=headers,
                ping_interval=20,
                ping_timeout=10,
            )
            
            self._is_connected = True
            
            # Start receiving responses
            self.receive_task = asyncio.create_task(self._receive_loop())
            
            logger.info("Connected to Deepgram STT")
            return True
            
        except Exception as e:
            logger.error("Failed to connect to Deepgram", error=str(e))
            return False
    
    async def send_audio(self, audio_bytes: bytes) -> None:
        """
        Send audio chunk to Deepgram.
        
        Args:
            audio_bytes: Raw audio bytes (mulaw for Twilio)
        """
        if not self._is_connected or not self.websocket:
            return
        
        try:
            await self.websocket.send(audio_bytes)
        except ConnectionClosed:
            logger.warning("Deepgram connection closed while sending")
            self._is_connected = False
        except Exception as e:
            logger.error("Error sending audio to Deepgram", error=str(e))
    
    async def close(self) -> None:
        """Close the Deepgram connection."""
        self._is_connected = False
        
        if self.receive_task:
            self.receive_task.cancel()
            try:
                await self.receive_task
            except asyncio.CancelledError:
                pass
        
        if self.websocket:
            try:
                # Send close message
                await self.websocket.send(json.dumps({"type": "CloseStream"}))
                await self.websocket.close()
            except Exception:
                pass
        
        logger.info("Deepgram connection closed")
    
    async def _receive_loop(self) -> None:
        """Receive and process Deepgram responses."""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    await self._handle_response(data)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from Deepgram")
                    
        except ConnectionClosed:
            logger.info("Deepgram connection closed by server")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Deepgram receive error", error=str(e))
        finally:
            self._is_connected = False
    
    async def _handle_response(self, data: dict) -> None:
        """Handle Deepgram response message."""
        msg_type = data.get("type")
        
        if msg_type == "Results":
            # Speech recognition result
            channel = data.get("channel", {})
            alternatives = channel.get("alternatives", [])
            
            if alternatives:
                best = alternatives[0]
                transcript = best.get("transcript", "")
                confidence = best.get("confidence", 0.0)
                is_final = data.get("is_final", False)
                
                if transcript.strip():
                    await self.on_transcript(transcript, is_final, confidence)
                    
        elif msg_type == "UtteranceEnd":
            # End of utterance detected
            logger.debug("Utterance end detected")
            
        elif msg_type == "Metadata":
            # Connection metadata
            logger.debug("Deepgram metadata", data=data)
            
        elif msg_type == "Error":
            logger.error("Deepgram error", error=data)
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to Deepgram."""
        return self._is_connected

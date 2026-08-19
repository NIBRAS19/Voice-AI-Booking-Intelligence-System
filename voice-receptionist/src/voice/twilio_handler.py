"""
Voice Pipeline - Twilio Media Streams Integration.

Handles real-time voice calls via Twilio:
1. Twilio connects via WebSocket (mulaw/8kHz audio)
2. Audio → Deepgram STT (streaming)
3. Transcripts → Conversation Orchestrator → Response
4. Response → Cartesia TTS → Audio back to Twilio
"""

import asyncio
import base64
import json
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import Response

from src.core.config import settings
from src.core.database import get_db
from src.core.logging import get_logger
from src.conversation.orchestrator import ConversationOrchestrator

logger = get_logger(__name__)
router = APIRouter()


class TwilioMediaStreamHandler:
    """
    Handles Twilio Media Streams protocol.
    
    Twilio sends JSON messages with:
    - start: Call metadata
    - media: Audio chunks (base64 mulaw)
    - stop: Call ended
    """
    
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        self.session_id: Optional[str] = None
        self.business_id: Optional[str] = None
        
        # Audio buffers
        self.audio_buffer = bytearray()
        self.last_audio_time = 0
        
        # Speech detection
        self.silence_threshold = 0.5  # seconds
        self.is_speaking = False
        
        # Services
        self.stt_client = None
        self.tts_client = None
        self.orchestrator = None
    
    async def handle_message(self, message: dict) -> None:
        """Handle incoming Twilio message."""
        event = message.get("event")
        
        if event == "start":
            await self._handle_start(message)
        elif event == "media":
            await self._handle_media(message)
        elif event == "stop":
            await self._handle_stop(message)
        elif event == "mark":
            # Audio playback marker
            logger.debug("Mark received", mark=message.get("mark", {}).get("name"))
    
    async def _handle_start(self, message: dict) -> None:
        """Handle call start event."""
        start_data = message.get("start", {})
        
        self.stream_sid = start_data.get("streamSid")
        self.call_sid = start_data.get("callSid")
        self.session_id = str(uuid4())
        
        # Extract custom parameters (business_id passed via TwiML)
        custom_params = start_data.get("customParameters", {})
        self.business_id = custom_params.get("business_id")
        
        logger.info(
            "Twilio stream started",
            stream_sid=self.stream_sid,
            call_sid=self.call_sid,
            session_id=self.session_id,
            business_id=self.business_id,
        )
        
        # Initialize conversation session
        if self.business_id:
            async with get_db() as db:
                await db.execute("""
                    INSERT INTO conversation_sessions 
                    (id, business_id, channel, phone_number, status)
                    VALUES ($1, $2, 'phone', $3, 'active')
                """, UUID(self.session_id), UUID(self.business_id), 
                start_data.get("from", "unknown"))
                
                # Get business greeting
                business = await db.fetchrow(
                    "SELECT * FROM businesses WHERE id = $1", 
                    UUID(self.business_id)
                )
                
                if business:
                    settings = business.get("settings", {})
                    greeting = settings.get(
                        "greeting",
                        f"Thank you for calling {business['name']}. How can I help you?"
                    )
                    
                    # Initialize orchestrator
                    self.orchestrator = ConversationOrchestrator(db, self.business_id)
                    await self.orchestrator.start_session(
                        phone_number=start_data.get("from"),
                        session_id=self.session_id,
                    )
                    
                    # Play greeting
                    await self._speak(greeting)
    
    async def _handle_media(self, message: dict) -> None:
        """Handle audio chunk from caller."""
        media = message.get("media", {})
        
        # Decode base64 mulaw audio
        audio_payload = media.get("payload", "")
        if audio_payload:
            audio_bytes = base64.b64decode(audio_payload)
            self.audio_buffer.extend(audio_bytes)
            
            # Process when we have enough audio (~0.5 seconds at 8kHz)
            if len(self.audio_buffer) >= 4000:  # ~0.5s of mulaw audio
                await self._process_audio()
    
    async def _process_audio(self) -> None:
        """
        Process buffered audio through STT.
        
        In production, this would stream to Deepgram.
        """
        if not self.audio_buffer:
            return
        
        # Copy and clear buffer
        audio_data = bytes(self.audio_buffer)
        self.audio_buffer.clear()
        
        # TODO: Send to Deepgram for real-time transcription
        # For now, log that we received audio
        logger.debug(
            "Processing audio chunk",
            session_id=self.session_id,
            audio_bytes=len(audio_data),
        )
        
        # In real implementation:
        # 1. Convert mulaw to PCM
        # 2. Send to Deepgram streaming API
        # 3. Handle partial and final transcripts
    
    async def _on_transcript(self, transcript: str, is_final: bool) -> None:
        """
        Handle transcript from STT.
        
        Called by Deepgram when speech is detected.
        """
        if not transcript.strip():
            return
        
        logger.info(
            "User speech",
            session_id=self.session_id,
            transcript=transcript[:100],
            is_final=is_final,
        )
        
        if is_final and self.orchestrator:
            # Process through conversation engine
            async with get_db() as db:
                orchestrator = ConversationOrchestrator(db, self.business_id)
                result = await orchestrator.process_input(
                    session_id=self.session_id,
                    user_input=transcript,
                )
                
                # Speak the response
                if result.get("response"):
                    await self._speak(result["response"])
                    
                    # Store turns
                    await db.execute("""
                        INSERT INTO conversation_turns 
                        (session_id, turn_number, role, content, intent)
                        VALUES ($1, $2, 'user', $3, $4)
                    """, UUID(self.session_id), result.get("turn", 1), 
                    transcript, result.get("intent"))
                    
                    await db.execute("""
                        INSERT INTO conversation_turns 
                        (session_id, turn_number, role, content)
                        VALUES ($1, $2, 'assistant', $3)
                    """, UUID(self.session_id), result.get("turn", 1) + 1); 
                    result["response"]
    
    async def _speak(self, text: str) -> None:
        """
        Send text to Cartesia TTS and stream audio back to Twilio.
        """
        if not text:
            return
        
        logger.info(
            "Speaking response",
            session_id=self.session_id,
            text=text[:100],
        )
        
        # TODO: Integrate with Cartesia TTS
        # 1. Send text to Cartesia API
        # 2. Receive audio chunks
        # 3. Convert to mulaw if needed
        # 4. Send to Twilio via media messages
        
        # For now, use a placeholder that would work with Twilio
        # In production, you'd stream actual audio
        
        # Send a media message with synthesized audio
        # audio_base64 = await self._synthesize_speech(text)
        # await self._send_audio(audio_base64)
        
        # Mark end of speech for tracking
        mark_message = {
            "event": "mark",
            "streamSid": self.stream_sid,
            "mark": {"name": f"response_{uuid4().hex[:8]}"}
        }
        await self.websocket.send_json(mark_message)
    
    async def _send_audio(self, audio_base64: str) -> None:
        """Send audio chunk back to Twilio."""
        media_message = {
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {
                "payload": audio_base64
            }
        }
        await self.websocket.send_json(media_message)
    
    async def _handle_stop(self, message: dict) -> None:
        """Handle call end event."""
        logger.info(
            "Twilio stream stopped",
            stream_sid=self.stream_sid,
            session_id=self.session_id,
        )
        
        # Update session status
        if self.session_id:
            async with get_db() as db:
                await db.execute("""
                    UPDATE conversation_sessions 
                    SET status = 'completed', ended_at = NOW()
                    WHERE id = $1
                """, UUID(self.session_id))


@router.websocket("/twilio/stream")
async def twilio_media_stream(websocket: WebSocket):
    """
    Twilio Media Streams WebSocket endpoint.
    
    Twilio connects here when a call starts.
    Configure in TwiML with:
    <Stream url="wss://your-domain.com/api/v1/voice/twilio/stream">
        <Parameter name="business_id" value="{business_id}"/>
    </Stream>
    """
    await websocket.accept()
    
    handler = TwilioMediaStreamHandler(websocket)
    
    try:
        while True:
            try:
                # Receive message from Twilio
                data = await websocket.receive_text()
                message = json.loads(data)
                
                await handler.handle_message(message)
                
            except WebSocketDisconnect:
                logger.info("Twilio disconnected", stream_sid=handler.stream_sid)
                break
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON from Twilio", error=str(e))
                
    except Exception as e:
        logger.error("Twilio stream error", error=str(e))
    finally:
        # Cleanup
        if handler.session_id:
            async with get_db() as db:
                await db.execute("""
                    UPDATE conversation_sessions 
                    SET status = 'completed', ended_at = NOW()
                    WHERE id = $1
                """, UUID(handler.session_id))


@router.post("/twilio/webhook")
async def twilio_voice_webhook(request: Request):
    """
    Twilio Voice webhook - receives incoming calls.
    
    Returns TwiML to start Media Stream.
    """
    form_data = await request.form()
    
    from_number = form_data.get("From", "unknown")
    to_number = form_data.get("To", "")
    call_sid = form_data.get("CallSid", "")
    
    logger.info(
        "Incoming call webhook",
        from_number=from_number,
        to_number=to_number,
        call_sid=call_sid,
    )
    
    # Look up business by phone number
    business_id = None
    async with get_db() as db:
        business = await db.fetchrow(
            "SELECT id FROM businesses WHERE phone_number = $1",
            to_number,
        )
        if business:
            business_id = str(business["id"])
    
    if not business_id:
        # No business found - reject call
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Sorry, this number is not configured. Goodbye.</Say>
    <Hangup/>
</Response>"""
        return Response(content=twiml, media_type="application/xml")
    
    # Build WebSocket URL
    # In production, use your actual domain
    ws_url = f"wss://{request.headers.get('host', 'localhost:8000')}/api/v1/voice/twilio/stream"
    
    # Return TwiML to start media stream
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}">
            <Parameter name="business_id" value="{business_id}"/>
        </Stream>
    </Connect>
</Response>"""
    
    return Response(content=twiml, media_type="application/xml")

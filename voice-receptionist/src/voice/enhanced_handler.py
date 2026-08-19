"""
Enhanced Voice Pipeline with Barge-in, Latency Optimization, and Human Handoff.

Features:
- Barge-in: Interrupt AI while it's speaking
- Latency optimization: Parallel processing, audio prefetching
- Human handoff: Transfer to live agent when requested
"""

import asyncio
import base64
import json
import time
from typing import Optional, Dict, Any, Callable, Awaitable
from uuid import UUID, uuid4
from enum import Enum

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import Response

from src.core.config import settings
from src.core.database import get_db
from src.core.logging import get_logger
from src.voice.deepgram_stt import DeepgramSTTClient
from src.voice.cartesia_tts import CartesiaTTSClient

logger = get_logger(__name__)
router = APIRouter()


class CallState(Enum):
    """Voice call state machine."""
    INITIALIZING = "initializing"
    GREETING = "greeting"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    HANDOFF_PENDING = "handoff_pending"
    TRANSFERRED = "transferred"
    ENDED = "ended"


class BargeInController:
    """
    Handles barge-in detection and response interruption.
    
    When user speaks while AI is speaking, interrupts the AI response
    and starts processing the user's speech immediately.
    """
    
    def __init__(self):
        self.is_ai_speaking = False
        self.speaking_start_time: Optional[float] = None
        self.user_speech_detected = False
        self.pending_audio_chunks: list = []
        self.interrupt_requested = False
        
        # Sensitivity settings
        self.min_speech_duration_ms = 200  # Minimum speech to trigger interrupt
        self.speech_energy_threshold = 0.1  # Energy level to detect speech
    
    def start_speaking(self) -> None:
        """Mark that AI started speaking."""
        self.is_ai_speaking = True
        self.speaking_start_time = time.time()
        self.user_speech_detected = False
        self.interrupt_requested = False
    
    def stop_speaking(self) -> None:
        """Mark that AI stopped speaking."""
        self.is_ai_speaking = False
        self.speaking_start_time = None
    
    def on_user_speech(self, energy_level: float = 1.0) -> bool:
        """
        Called when user speech is detected.
        
        Returns:
            True if barge-in should be triggered
        """
        if not self.is_ai_speaking:
            return False
        
        if energy_level < self.speech_energy_threshold:
            return False
        
        self.user_speech_detected = True
        
        # Check if AI has been speaking long enough
        if self.speaking_start_time:
            speaking_duration = (time.time() - self.speaking_start_time) * 1000
            if speaking_duration > self.min_speech_duration_ms:
                self.interrupt_requested = True
                return True
        
        return False
    
    def should_interrupt(self) -> bool:
        """Check if AI speech should be interrupted."""
        return self.interrupt_requested
    
    def clear_pending_audio(self) -> None:
        """Clear any pending audio to be sent."""
        self.pending_audio_chunks.clear()


class HumanHandoffManager:
    """
    Manages human handoff/transfer to live agent.
    
    Triggers when:
    - User explicitly requests human
    - AI confidence is low
    - Conversation exceeds max turns without resolution
    """
    
    # Phrases that trigger handoff
    HANDOFF_TRIGGERS = [
        "talk to a human",
        "speak to someone",
        "transfer me",
        "real person",
        "live agent",
        "customer service",
        "representative",
        "human please",
        "can't understand me",
    ]
    
    def __init__(self, max_turns: int = 10, confidence_threshold: float = 0.3):
        self.max_turns = max_turns
        self.confidence_threshold = confidence_threshold
        self.turn_count = 0
        self.low_confidence_count = 0
        self.handoff_reason: Optional[str] = None
    
    def should_handoff(self, transcript: str, confidence: float) -> bool:
        """
        Check if call should be transferred to human.
        
        Args:
            transcript: User's speech
            confidence: AI confidence score
        
        Returns:
            True if handoff should occur
        """
        self.turn_count += 1
        
        # Check for explicit handoff request
        transcript_lower = transcript.lower()
        for trigger in self.HANDOFF_TRIGGERS:
            if trigger in transcript_lower:
                self.handoff_reason = "user_request"
                return True
        
        # Check for low confidence
        if confidence < self.confidence_threshold:
            self.low_confidence_count += 1
            if self.low_confidence_count >= 3:
                self.handoff_reason = "low_confidence"
                return True
        
        # Check for too many turns
        if self.turn_count >= self.max_turns:
            self.handoff_reason = "max_turns"
            return True
        
        return False
    
    def get_handoff_message(self) -> str:
        """Get the message to play before handoff."""
        messages = {
            "user_request": "I understand you'd like to speak with someone. Let me transfer you to a team member.",
            "low_confidence": "I'm having trouble understanding. Let me connect you with someone who can help better.",
            "max_turns": "This seems complex. Let me transfer you to a specialist who can assist you.",
        }
        return messages.get(self.handoff_reason, "Please hold while I transfer you.")


class LatencyOptimizer:
    """
    Optimizes voice pipeline latency.
    
    Strategies:
    - Parallel STT/processing
    - Response prefetching
    - Audio chunk streaming
    - Connection pooling
    """
    
    def __init__(self):
        self.metrics: Dict[str, list] = {
            "stt_latency": [],
            "llm_latency": [],
            "tts_latency": [],
            "total_latency": [],
        }
        self.prefetch_queue: asyncio.Queue = asyncio.Queue(maxsize=3)
    
    def record_latency(self, stage: str, duration_ms: float) -> None:
        """Record latency for a processing stage."""
        if stage in self.metrics:
            self.metrics[stage].append(duration_ms)
            # Keep last 100 measurements
            if len(self.metrics[stage]) > 100:
                self.metrics[stage] = self.metrics[stage][-100:]
    
    def get_average_latency(self, stage: str) -> float:
        """Get average latency for a stage."""
        values = self.metrics.get(stage, [])
        return sum(values) / len(values) if values else 0
    
    def get_p95_latency(self, stage: str) -> float:
        """Get 95th percentile latency."""
        values = sorted(self.metrics.get(stage, []))
        if not values:
            return 0
        index = int(len(values) * 0.95)
        return values[min(index, len(values) - 1)]
    
    async def prefetch_response(self, likely_intent: str) -> Optional[str]:
        """
        Prefetch a likely response based on context.
        
        This can reduce perceived latency for common intents.
        """
        common_responses = {
            "greeting": "Hello! How can I help you today?",
            "booking_confirmation": "Great, your appointment is confirmed.",
            "goodbye": "Thank you for calling. Have a great day!",
            "unclear": "I'm sorry, could you please repeat that?",
        }
        return common_responses.get(likely_intent)


class EnhancedTwilioHandler:
    """
    Enhanced Twilio Media Streams handler with:
    - Barge-in support
    - Human handoff
    - Latency optimization
    """
    
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        self.session_id: Optional[str] = None
        self.business_id: Optional[str] = None
        
        # State management
        self.state = CallState.INITIALIZING
        
        # Audio
        self.audio_buffer = bytearray()
        
        # Enhanced features
        self.barge_in = BargeInController()
        self.handoff = HumanHandoffManager()
        self.latency = LatencyOptimizer()
        
        # Services
        self.stt: Optional[DeepgramSTTClient] = None
        self.tts: Optional[CartesiaTTSClient] = None
        
        # Queue for outgoing audio
        self.audio_out_queue: asyncio.Queue = asyncio.Queue()
        self.send_audio_task: Optional[asyncio.Task] = None
    
    async def initialize(self) -> None:
        """Initialize STT and TTS clients."""
        # Initialize Deepgram STT
        self.stt = DeepgramSTTClient(
            on_transcript=self._on_transcript,
            sample_rate=8000,
            encoding="mulaw",
        )
        await self.stt.connect()
        
        # Initialize Cartesia TTS
        self.tts = CartesiaTTSClient(
            sample_rate=8000,
            output_format="pcm_mulaw",
        )
        
        # Start audio sender task
        self.send_audio_task = asyncio.create_task(self._audio_sender())
        
        logger.info("Enhanced handler initialized")
    
    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.stt:
            await self.stt.close()
        if self.tts:
            await self.tts.close()
        if self.send_audio_task:
            self.send_audio_task.cancel()
    
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
            await self._handle_mark(message)
    
    async def _handle_start(self, message: dict) -> None:
        """Handle call start."""
        start_data = message.get("start", {})
        
        self.stream_sid = start_data.get("streamSid")
        self.call_sid = start_data.get("callSid")
        self.session_id = str(uuid4())
        
        custom_params = start_data.get("customParameters", {})
        self.business_id = custom_params.get("business_id")
        
        logger.info(
            "Enhanced stream started",
            stream_sid=self.stream_sid,
            session_id=self.session_id,
        )
        
        await self.initialize()
        
        # Set state and play greeting
        self.state = CallState.GREETING
        
        if self.business_id:
            async with get_db() as db:
                business = await db.fetchrow(
                    "SELECT * FROM businesses WHERE id = $1",
                    UUID(self.business_id)
                )
                
                if business:
                    biz_settings = business.get("settings", {})
                    greeting = biz_settings.get(
                        "greeting",
                        f"Thank you for calling {business['name']}. How can I help you?"
                    )
                    
                    # AI disclosure if required
                    if biz_settings.get("ai_disclosure", True):
                        greeting = "This call may be assisted by AI. " + greeting
                    
                    await self._speak(greeting)
    
    async def _handle_media(self, message: dict) -> None:
        """Handle audio from caller with barge-in detection."""
        media = message.get("media", {})
        audio_payload = media.get("payload", "")
        
        if not audio_payload:
            return
        
        audio_bytes = base64.b64decode(audio_payload)
        
        # Check for barge-in
        if self.barge_in.on_user_speech():
            logger.info("Barge-in detected", session_id=self.session_id)
            await self._handle_barge_in()
        
        # Send audio to STT
        if self.stt and self.stt.is_connected:
            await self.stt.send_audio(audio_bytes)
    
    async def _handle_barge_in(self) -> None:
        """Handle user interruption."""
        # Stop current speech
        self.barge_in.stop_speaking()
        
        # Clear pending audio
        self.barge_in.clear_pending_audio()
        
        # Send clear message to Twilio
        clear_message = {
            "event": "clear",
            "streamSid": self.stream_sid,
        }
        await self.websocket.send_json(clear_message)
        
        # Update state
        self.state = CallState.LISTENING
        
        logger.info("Barge-in: cleared audio queue", session_id=self.session_id)
    
    async def _on_transcript(self, transcript: str, is_final: bool, confidence: float) -> None:
        """Handle STT transcript with handoff check."""
        if not transcript.strip():
            return
        
        logger.info(
            "Transcript received",
            transcript=transcript[:100],
            is_final=is_final,
            confidence=confidence,
        )
        
        if not is_final:
            # Partial transcript - just for logging/monitoring
            return
        
        # Record STT latency
        start_time = time.time()
        
        # Check for handoff
        if self.handoff.should_handoff(transcript, confidence):
            await self._initiate_handoff()
            return
        
        # Process through conversation engine
        self.state = CallState.PROCESSING
        
        # TODO: Connect to actual conversation orchestrator
        # For now, use placeholder response
        response = await self._get_response(transcript)
        
        # Record processing latency
        self.latency.record_latency("llm_latency", (time.time() - start_time) * 1000)
        
        # Speak response
        if response:
            await self._speak(response)
    
    async def _get_response(self, transcript: str) -> str:
        """Get response from conversation engine."""
        # Placeholder - integrate with actual orchestrator
        from src.conversation.orchestrator import ConversationOrchestrator
        
        async with get_db() as db:
            orchestrator = ConversationOrchestrator(db, self.business_id)
            result = await orchestrator.process_input(
                session_id=self.session_id,
                user_input=transcript,
            )
            return result.get("response", "I'm sorry, I didn't understand that. Could you please repeat?")
    
    async def _speak(self, text: str) -> None:
        """Speak text with barge-in awareness."""
        if not text or not self.tts:
            return
        
        self.state = CallState.SPEAKING
        self.barge_in.start_speaking()
        
        start_time = time.time()
        
        logger.info("Speaking", text=text[:100], session_id=self.session_id)
        
        # Stream audio chunks to Twilio
        async for audio_chunk in self.tts.synthesize(text):
            # Check for barge-in before sending each chunk
            if self.barge_in.should_interrupt():
                logger.info("Speech interrupted by user")
                break
            
            await self.audio_out_queue.put(audio_chunk)
        
        # Record TTS latency
        self.latency.record_latency("tts_latency", (time.time() - start_time) * 1000)
        
        # Mark end of speech
        mark_message = {
            "event": "mark",
            "streamSid": self.stream_sid,
            "mark": {"name": f"speech_end_{uuid4().hex[:8]}"}
        }
        await self.websocket.send_json(mark_message)
        
        self.barge_in.stop_speaking()
        self.state = CallState.LISTENING
    
    async def _audio_sender(self) -> None:
        """Background task to send audio to Twilio."""
        try:
            while True:
                audio_chunk = await self.audio_out_queue.get()
                
                # Check for barge-in
                if self.barge_in.should_interrupt():
                    continue
                
                media_message = {
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": audio_chunk}
                }
                await self.websocket.send_json(media_message)
                
        except asyncio.CancelledError:
            pass
    
    async def _initiate_handoff(self) -> None:
        """Transfer call to human agent."""
        self.state = CallState.HANDOFF_PENDING
        
        handoff_message = self.handoff.get_handoff_message()
        await self._speak(handoff_message)
        
        logger.info(
            "Initiating handoff",
            reason=self.handoff.handoff_reason,
            session_id=self.session_id,
        )
        
        # Update session in database
        async with get_db() as db:
            await db.execute("""
                UPDATE conversation_sessions 
                SET status = 'transferred', 
                    handoff_reason = $2,
                    ended_at = NOW()
                WHERE id = $1
            """, UUID(self.session_id), self.handoff.handoff_reason)
        
        # Send transfer instruction to Twilio
        # This would typically redirect to a queue or specific agent
        logger.info("Call marked for transfer", session_id=self.session_id)
        
        self.state = CallState.TRANSFERRED
    
    async def _handle_mark(self, message: dict) -> None:
        """Handle audio playback marker."""
        mark_name = message.get("mark", {}).get("name", "")
        logger.debug("Mark received", mark=mark_name)
    
    async def _handle_stop(self, message: dict) -> None:
        """Handle call end."""
        self.state = CallState.ENDED
        
        logger.info(
            "Stream stopped",
            session_id=self.session_id,
            latency_stats={
                "stt_avg": self.latency.get_average_latency("stt_latency"),
                "llm_avg": self.latency.get_average_latency("llm_latency"),
                "tts_avg": self.latency.get_average_latency("tts_latency"),
            }
        )
        
        await self.cleanup()


@router.websocket("/twilio/stream/enhanced")
async def enhanced_twilio_stream(websocket: WebSocket):
    """
    Enhanced Twilio Media Streams endpoint with:
    - Barge-in support
    - Human handoff
    - Latency optimization
    """
    await websocket.accept()
    
    handler = EnhancedTwilioHandler(websocket)
    
    try:
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                await handler.handle_message(message)
                
            except WebSocketDisconnect:
                logger.info("Enhanced stream disconnected")
                break
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON", error=str(e))
                
    except Exception as e:
        logger.error("Enhanced stream error", error=str(e))
    finally:
        await handler.cleanup()


@router.post("/twilio/handoff/{session_id}")
async def request_handoff(session_id: str, reason: str = "user_request"):
    """
    API endpoint to manually trigger handoff for a call.
    
    Used by admin dashboard to transfer calls.
    """
    async with get_db() as db:
        await db.execute("""
            UPDATE conversation_sessions 
            SET status = 'transferred', 
                handoff_reason = $2,
                ended_at = NOW()
            WHERE id = $1
        """, UUID(session_id), reason)
    
    return {"message": f"Handoff initiated for session {session_id}"}

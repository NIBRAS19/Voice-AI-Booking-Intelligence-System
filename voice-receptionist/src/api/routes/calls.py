"""
Call handling routes for voice AI integration.
"""

import asyncio
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from pydantic import BaseModel

from src.core.database import get_db
from src.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


class IncomingCallWebhook(BaseModel):
    """Incoming call webhook payload."""
    call_id: str
    from_number: str
    to_number: str
    business_id: Optional[str] = None


@router.post("/incoming")
async def handle_incoming_call(webhook: IncomingCallWebhook):
    """
    Handle incoming call webhook from telephony provider.
    
    Returns configuration for the call:
    - WebSocket URL for audio streaming
    - Greeting to play
    - Business context
    """
    logger.info(
        "Incoming call received",
        call_id=webhook.call_id,
        from_number=webhook.from_number,
        to_number=webhook.to_number,
    )
    
    # Look up business by phone number
    async with get_db() as db:
        business = await db.fetchrow(
            "SELECT * FROM businesses WHERE phone_number = $1",
            webhook.to_number,
        )
        
        if not business:
            logger.warning("Business not found for number", phone=webhook.to_number)
            return {
                "action": "reject",
                "reason": "Business not configured",
            }
        
        # Get greeting from settings
        settings = business.get("settings", {})
        greeting = settings.get(
            "greeting",
            f"Thank you for calling {business['name']}. How can I help you today?"
        )
        
        # Create session
        session_id = str(uuid4())
        
        return {
            "action": "connect",
            "session_id": session_id,
            "business_id": str(business["id"]),
            "business_name": business["name"],
            "greeting": greeting,
            "websocket_url": f"/api/v1/calls/stream/{session_id}",
            "ai_disclosure": settings.get("ai_disclosure", True),
        }


@router.websocket("/stream/{session_id}")
async def voice_stream(
    websocket: WebSocket,
    session_id: str,
    business_id: str = Query(...),
):
    """
    WebSocket endpoint for voice streaming.
    
    This handles:
    1. Audio from caller → STT → Intent → Response
    2. Response → TTS → Audio to caller
    """
    await websocket.accept()
    
    logger.info("Voice stream connected", session_id=session_id)
    
    try:
        # Initialize session in database
        async with get_db() as db:
            await db.execute("""
                INSERT INTO conversation_sessions (id, business_id, channel, status)
                VALUES ($1, $2, 'phone', 'active')
            """, UUID(session_id), UUID(business_id))
        
        # Main processing loop
        # In production, this integrates with:
        # - Whisper for STT
        # - Ollama for LLM
        # - Piper for TTS
        
        turn_number = 0
        
        while True:
            try:
                # Receive audio/message from client
                data = await websocket.receive_json()
                
                event_type = data.get("event")
                
                if event_type == "audio":
                    # Audio chunk from caller
                    # In production: Forward to STT service
                    audio_payload = data.get("audio")
                    
                    # Placeholder for STT processing
                    # transcript = await stt_service.transcribe(audio_payload)
                    
                    logger.debug("Audio received", session_id=session_id)
                    
                elif event_type == "transcript":
                    # Final transcript ready
                    transcript = data.get("text", "")
                    
                    if transcript.strip():
                        turn_number += 1
                        
                        logger.info(
                            "User speech",
                            session_id=session_id,
                            transcript=transcript[:100],
                        )
                        
                        # Process through conversation engine
                        # response = await conversation_engine.process(transcript)
                        
                        # Placeholder response
                        response = {
                            "text": "I understand. How can I help you with that?",
                            "intent": "unclear",
                            "should_continue": True,
                        }
                        
                        await websocket.send_json({
                            "event": "response",
                            "text": response["text"],
                            "intent": response["intent"],
                        })
                        
                        # Store turn in database
                        async with get_db() as db:
                            await db.execute("""
                                INSERT INTO conversation_turns 
                                (session_id, turn_number, role, content)
                                VALUES ($1, $2, 'user', $3)
                            """, UUID(session_id), turn_number, transcript)
                            
                            await db.execute("""
                                INSERT INTO conversation_turns 
                                (session_id, turn_number, role, content)
                                VALUES ($1, $2, 'assistant', $3)
                            """, UUID(session_id), turn_number + 1, response["text"])
                
                elif event_type == "end":
                    # Call ended
                    logger.info("Call ended", session_id=session_id)
                    break
                    
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected", session_id=session_id)
                break
                
    except Exception as e:
        logger.error("Voice stream error", session_id=session_id, error=str(e))
        
    finally:
        # Update session status
        async with get_db() as db:
            await db.execute("""
                UPDATE conversation_sessions 
                SET status = 'completed', ended_at = NOW()
                WHERE id = $1
            """, UUID(session_id))
        
        logger.info("Voice stream closed", session_id=session_id)


@router.get("/sessions/{session_id}")
async def get_call_session(session_id: UUID):
    """Get call session details."""
    async with get_db() as db:
        from src.data.repositories.session_repo import SessionRepository
        repo = SessionRepository(db)
        
        session = await repo.get_with_turns(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return session

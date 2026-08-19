"""
Simulation routes for testing conversation flow via HTTP/JSON.
This allows testing the AI logic without real voice calls.
"""

from typing import Dict, Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

from src.core.database import get_db
from src.core.logging import get_logger
from src.conversation.orchestrator import ConversationOrchestrator
from src.conversation.state_machine import ConversationContext, ConversationState, Intent

router = APIRouter()
logger = get_logger(__name__)


class StartSimulationRequest(BaseModel):
    phone_number: str
    business_id: UUID


class ProcessInputRequest(BaseModel):
    session_id: UUID
    user_text: str


@router.post("/start")
async def start_simulation(request: StartSimulationRequest):
    """
    Start a simulated conversation session.
    """
    async with get_db() as db:
        # Verify business
        business = await db.fetchrow(
            "SELECT * FROM businesses WHERE id = $1",
            request.business_id
        )
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
            
        settings = business.get("settings", {})
        greeting = settings.get(
            "greeting", 
            f"Thank you for calling {business['name']}. How can I help you today?"
        )
        
        session_id = uuid4()
        
        # Create session in DB
        await db.execute("""
            INSERT INTO conversation_sessions (id, business_id, channel, phone_number, status)
            VALUES ($1, $2, 'web', $3, 'active')
        """, session_id, request.business_id, request.phone_number)
        
        return {
            "session_id": str(session_id),
            "greeting": greeting,
            "state": "GREETING",
            "business_name": business["name"]
        }


@router.post("/process")
async def process_input(request: ProcessInputRequest):
    """
    Process text input for a session.
    """
    async with get_db() as db:
        # Load session
        session = await db.fetchrow(
            "SELECT * FROM conversation_sessions WHERE id = $1",
            request.session_id
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        # Load state from metadata
        import json
        metadata = json.loads(session["metadata"]) if isinstance(session["metadata"], str) else session.get("metadata", {})
        
        # Reconstruct context
        context = ConversationContext(
            session_id=str(request.session_id),
            business_id=str(session["business_id"]),
            caller_phone=session["phone_number"],
            current_state=ConversationState(metadata.get("state", "greeting")),
            current_intent=Intent(metadata.get("intent")) if metadata.get("intent") else None,
        )
        
        # Restore filled slots
        if "filled_slots" in metadata:
            from src.conversation.state_machine import FilledSlot
            for name, data in metadata["filled_slots"].items():
                context.filled_slots[name] = FilledSlot(**data)
                
        # Restore required slots
        if "required_slots" in metadata:
            from src.conversation.state_machine import SlotDefinition
            for name, data in metadata["required_slots"].items():
                context.required_slots[name] = SlotDefinition(**data)

        # Initialize orchestrator
        orchestrator = ConversationOrchestrator(context, db)
        
        # Process input
        response_text, should_continue = await orchestrator.process_user_input(request.user_text)
        
        # Persist state to metadata
        new_metadata = metadata.copy()
        new_metadata.update({
            "state": context.current_state.value,
            "intent": context.current_intent.value if context.current_intent else None,
            "filled_slots": {k: v.dict() for k, v in context.filled_slots.items()},
            "required_slots": {k: v.dict() for k, v in context.required_slots.items()},
        })
        
        await db.execute("""
            UPDATE conversation_sessions 
            SET metadata = $1, current_intent = $2
            WHERE id = $3
        """, json.dumps(new_metadata), context.current_intent.value if context.current_intent else None, request.session_id)
        
        return {
            "response": response_text,
            "should_continue": should_continue,
            "detected_intent": context.current_intent,
            "filled_slots": {k: v.dict() for k, v in context.filled_slots.items()},
            "current_state": context.current_state.value
        }

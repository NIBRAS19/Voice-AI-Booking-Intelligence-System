"""
Session repository for conversation database operations.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from asyncpg import Connection

from src.data.models import (
    ConversationSession, ConversationSessionCreate, ConversationStatus,
    ConversationTurn, ConversationTurnCreate, ConversationSessionWithTurns
)
from src.core.logging import get_logger

logger = get_logger(__name__)


class SessionRepository:
    """Repository for conversation session database operations."""
    
    def __init__(self, db: Connection):
        self.db = db
    
    async def create(self, session: ConversationSessionCreate) -> ConversationSession:
        """Create a new conversation session."""
        query = """
            INSERT INTO conversation_sessions 
            (business_id, user_id, channel, phone_number, metadata)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
        """
        
        row = await self.db.fetchrow(
            query,
            session.business_id,
            session.user_id,
            session.channel.value,
            session.phone_number,
            session.metadata,
        )
        
        logger.info(
            "Conversation session created",
            session_id=str(row["id"]),
            channel=session.channel.value,
        )
        return ConversationSession(**dict(row))
    
    async def get_by_id(self, session_id: UUID) -> Optional[ConversationSession]:
        """Get a session by ID."""
        query = "SELECT * FROM conversation_sessions WHERE id = $1"
        row = await self.db.fetchrow(query, session_id)
        
        if row:
            return ConversationSession(**dict(row))
        return None
    
    async def get_with_turns(self, session_id: UUID) -> Optional[ConversationSessionWithTurns]:
        """Get a session with all its turns."""
        session = await self.get_by_id(session_id)
        if not session:
            return None
        
        turns = await self.get_turns(session_id)
        return ConversationSessionWithTurns(**session.model_dump(), turns=turns)
    
    async def update_status(
        self,
        session_id: UUID,
        status: ConversationStatus,
        final_outcome: Optional[str] = None,
    ) -> None:
        """Update session status."""
        query = """
            UPDATE conversation_sessions 
            SET status = $1, final_outcome = $2
            WHERE id = $3
        """
        await self.db.execute(query, status.value, final_outcome, session_id)
    
    async def end_session(
        self,
        session_id: UUID,
        status: ConversationStatus = ConversationStatus.COMPLETED,
        final_outcome: Optional[str] = None,
    ) -> None:
        """End a conversation session."""
        query = """
            UPDATE conversation_sessions 
            SET status = $1, ended_at = $2, final_outcome = $3,
                duration_seconds = EXTRACT(EPOCH FROM ($2 - started_at))::INT
            WHERE id = $4
        """
        await self.db.execute(
            query,
            status.value,
            datetime.utcnow(),
            final_outcome,
            session_id,
        )
        logger.info("Session ended", session_id=str(session_id), status=status.value)
    
    async def update_intent(
        self,
        session_id: UUID,
        intent: str,
        confidence: float,
    ) -> None:
        """Update current detected intent."""
        query = """
            UPDATE conversation_sessions 
            SET current_intent = $1, intent_confidence = $2
            WHERE id = $3
        """
        await self.db.execute(query, intent, confidence, session_id)
    
    async def update_slots(self, session_id: UUID, slots: dict) -> None:
        """Update collected slots."""
        query = """
            UPDATE conversation_sessions 
            SET slots_collected = slots_collected || $1::jsonb
            WHERE id = $2
        """
        await self.db.execute(query, slots, session_id)
    
    async def mark_transferred(self, session_id: UUID, reason: str) -> None:
        """Mark session as transferred to human."""
        query = """
            UPDATE conversation_sessions 
            SET transferred_to_human = true, transfer_reason = $1, 
                status = $2
            WHERE id = $3
        """
        await self.db.execute(
            query,
            reason,
            ConversationStatus.TRANSFERRED.value,
            session_id,
        )
    
    async def link_booking(self, session_id: UUID, booking_id: UUID) -> None:
        """Link a booking to the session."""
        query = "UPDATE conversation_sessions SET booking_id = $1 WHERE id = $2"
        await self.db.execute(query, booking_id, session_id)
    
    async def link_order(self, session_id: UUID, order_id: UUID) -> None:
        """Link an order to the session."""
        query = "UPDATE conversation_sessions SET order_id = $1 WHERE id = $2"
        await self.db.execute(query, order_id, session_id)
    
    # Conversation Turns
    
    async def add_turn(self, turn: ConversationTurnCreate) -> ConversationTurn:
        """Add a conversation turn."""
        query = """
            INSERT INTO conversation_turns 
            (session_id, turn_number, role, content, intent, entities, 
             confidence, audio_duration_ms, processing_time_ms)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
        """
        
        row = await self.db.fetchrow(
            query,
            turn.session_id,
            turn.turn_number,
            turn.role,
            turn.content,
            turn.intent,
            turn.entities,
            turn.confidence,
            turn.audio_duration_ms,
            turn.processing_time_ms,
        )
        
        return ConversationTurn(**dict(row))
    
    async def get_turns(self, session_id: UUID) -> List[ConversationTurn]:
        """Get all turns for a session."""
        query = """
            SELECT * FROM conversation_turns 
            WHERE session_id = $1 
            ORDER BY turn_number
        """
        rows = await self.db.fetch(query, session_id)
        return [ConversationTurn(**dict(row)) for row in rows]
    
    async def get_recent_turns(
        self,
        session_id: UUID,
        limit: int = 10,
    ) -> List[ConversationTurn]:
        """Get recent turns for context window."""
        query = """
            SELECT * FROM conversation_turns 
            WHERE session_id = $1 
            ORDER BY turn_number DESC
            LIMIT $2
        """
        rows = await self.db.fetch(query, session_id, limit)
        # Reverse to get chronological order
        return [ConversationTurn(**dict(row)) for row in reversed(rows)]
    
    async def get_turn_count(self, session_id: UUID) -> int:
        """Get the number of turns in a session."""
        query = "SELECT COUNT(*) FROM conversation_turns WHERE session_id = $1"
        return await self.db.fetchval(query, session_id)

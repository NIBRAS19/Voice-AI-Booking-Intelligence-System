"""
Waitlist system for managing booking waitlists.
Allows customers to join a waitlist when no slots are available.
"""

from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID
from enum import Enum

from asyncpg import Connection

from src.core.logging import get_logger

logger = get_logger(__name__)


class WaitlistStatus(str, Enum):
    """Waitlist entry status."""
    ACTIVE = "active"
    NOTIFIED = "notified"
    CONVERTED = "converted"  # Became a booking
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class WaitlistEntry:
    """Waitlist entry model."""
    
    def __init__(
        self,
        id: UUID,
        business_id: UUID,
        user_id: UUID,
        service_id: UUID,
        preferred_dates: List[date],
        preferred_times: List[str],
        status: WaitlistStatus,
        priority: int,
        notes: Optional[str],
        created_at: datetime,
    ):
        self.id = id
        self.business_id = business_id
        self.user_id = user_id
        self.service_id = service_id
        self.preferred_dates = preferred_dates
        self.preferred_times = preferred_times
        self.status = status
        self.priority = priority
        self.notes = notes
        self.created_at = created_at


class WaitlistService:
    """
    Service for managing booking waitlists.
    
    Features:
    - Add customers to waitlist when slots unavailable
    - Automatic notification when slots open up
    - Priority-based queue management
    - Expiration handling
    """
    
    def __init__(self, db: Connection):
        self.db = db
        self.expiration_days = 30
    
    async def add_to_waitlist(
        self,
        business_id: UUID,
        user_id: UUID,
        service_id: UUID,
        preferred_dates: List[date],
        preferred_times: List[str] = None,
        notes: Optional[str] = None,
        priority: int = 5,  # 1=highest, 10=lowest
    ) -> Dict[str, Any]:
        """
        Add a customer to the waitlist.
        
        Args:
            business_id: Business ID
            user_id: Customer user ID
            service_id: Desired service
            preferred_dates: List of acceptable dates
            preferred_times: List of preferred times (HH:MM format)
            notes: Customer notes
            priority: Priority level (1-10)
        
        Returns:
            Dict with waitlist entry details
        """
        # Check if already on waitlist
        existing = await self.db.fetchval("""
            SELECT id FROM waitlist 
            WHERE business_id = $1 AND user_id = $2 AND service_id = $3
            AND status = 'active'
        """, business_id, user_id, service_id)
        
        if existing:
            return {
                "success": False,
                "error": "Already on waitlist for this service",
                "waitlist_id": str(existing),
            }
        
        # Calculate position
        position = await self.db.fetchval("""
            SELECT COUNT(*) + 1 FROM waitlist
            WHERE business_id = $1 AND service_id = $2 AND status = 'active'
        """, business_id, service_id)
        
        # Insert
        result = await self.db.fetchrow("""
            INSERT INTO waitlist (
                business_id, user_id, service_id,
                preferred_dates, preferred_times,
                status, priority, notes
            )
            VALUES ($1, $2, $3, $4, $5, 'active', $6, $7)
            RETURNING id, created_at
        """, 
            business_id, user_id, service_id,
            [d.isoformat() for d in preferred_dates],
            preferred_times or [],
            priority, notes
        )
        
        logger.info(
            "Added to waitlist",
            waitlist_id=str(result["id"]),
            user_id=str(user_id),
            position=position,
        )
        
        return {
            "success": True,
            "waitlist_id": str(result["id"]),
            "position": position,
            "message": f"You're #{position} on the waitlist. We'll notify you when a slot opens.",
        }
    
    async def check_and_notify(
        self,
        business_id: UUID,
        available_slot: datetime,
        service_id: UUID,
    ) -> List[Dict[str, Any]]:
        """
        Check waitlist and notify eligible customers.
        Called when a slot becomes available (cancellation, new hours, etc.)
        
        Returns:
            List of notified waitlist entries
        """
        slot_date = available_slot.date()
        slot_time = available_slot.strftime("%H:%M")
        
        # Find matching waitlist entries
        entries = await self.db.fetch("""
            SELECT w.*, u.phone, u.email, u.name
            FROM waitlist w
            JOIN users u ON w.user_id = u.id
            WHERE w.business_id = $1 
            AND w.service_id = $2
            AND w.status = 'active'
            AND $3 = ANY(w.preferred_dates::date[])
            ORDER BY w.priority ASC, w.created_at ASC
            LIMIT 3
        """, business_id, service_id, slot_date.isoformat())
        
        notified = []
        for entry in entries:
            # Update status
            await self.db.execute("""
                UPDATE waitlist SET status = 'notified', notified_at = NOW()
                WHERE id = $1
            """, entry["id"])
            
            notified.append({
                "waitlist_id": str(entry["id"]),
                "user_id": str(entry["user_id"]),
                "phone": entry["phone"],
                "email": entry["email"],
                "name": entry["name"],
                "slot_time": available_slot.isoformat(),
            })
            
            logger.info(
                "Waitlist notification sent",
                waitlist_id=str(entry["id"]),
                slot_time=available_slot.isoformat(),
            )
        
        return notified
    
    async def convert_to_booking(
        self,
        waitlist_id: UUID,
        booking_id: UUID,
    ) -> None:
        """Mark waitlist entry as converted to booking."""
        await self.db.execute("""
            UPDATE waitlist 
            SET status = 'converted', booking_id = $2, converted_at = NOW()
            WHERE id = $1
        """, waitlist_id, booking_id)
    
    async def cancel_waitlist(self, waitlist_id: UUID) -> bool:
        """Cancel a waitlist entry."""
        result = await self.db.execute("""
            UPDATE waitlist SET status = 'cancelled'
            WHERE id = $1 AND status = 'active'
        """, waitlist_id)
        return result == "UPDATE 1"
    
    async def get_position(
        self,
        waitlist_id: UUID,
    ) -> Optional[int]:
        """Get current position in waitlist."""
        entry = await self.db.fetchrow("""
            SELECT business_id, service_id, priority, created_at
            FROM waitlist WHERE id = $1
        """, waitlist_id)
        
        if not entry:
            return None
        
        position = await self.db.fetchval("""
            SELECT COUNT(*) FROM waitlist
            WHERE business_id = $1 
            AND service_id = $2
            AND status = 'active'
            AND (priority < $3 OR (priority = $3 AND created_at < $4))
        """, entry["business_id"], entry["service_id"], entry["priority"], entry["created_at"])
        
        return position + 1
    
    async def cleanup_expired(self) -> int:
        """Remove expired waitlist entries."""
        expiry_date = datetime.utcnow() - timedelta(days=self.expiration_days)
        
        result = await self.db.execute("""
            UPDATE waitlist SET status = 'expired'
            WHERE status = 'active' AND created_at < $1
        """, expiry_date)
        
        count = int(result.split()[-1]) if result else 0
        if count > 0:
            logger.info(f"Expired {count} waitlist entries")
        
        return count


# SQL for waitlist table
WAITLIST_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS waitlist (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    service_id UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    
    preferred_dates TEXT[] NOT NULL,
    preferred_times TEXT[] DEFAULT '{}',
    
    status VARCHAR(20) DEFAULT 'active',
    priority INT DEFAULT 5 CHECK (priority >= 1 AND priority <= 10),
    notes TEXT,
    
    booking_id UUID REFERENCES bookings(id),
    
    notified_at TIMESTAMPTZ,
    converted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT unique_active_waitlist UNIQUE (business_id, user_id, service_id)
        WHERE status = 'active'
);

CREATE INDEX IF NOT EXISTS idx_waitlist_business ON waitlist(business_id, service_id);
CREATE INDEX IF NOT EXISTS idx_waitlist_status ON waitlist(status) WHERE status = 'active';
"""

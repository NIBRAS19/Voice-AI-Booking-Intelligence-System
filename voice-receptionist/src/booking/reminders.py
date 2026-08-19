"""
Automated reminder system for bookings.
Sends reminders via SMS/Email before appointments.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID
from enum import Enum

from asyncpg import Connection

from src.core.config import settings
from src.core.logging import get_logger
from src.notifications.sms_service import SMSService
from src.notifications.email_service import EmailService

logger = get_logger(__name__)


class ReminderType(str, Enum):
    """Types of reminders."""
    DAY_BEFORE = "day_before"
    HOURS_BEFORE = "hours_before"
    CONFIRMATION = "confirmation"
    FOLLOW_UP = "follow_up"


class ReminderService:
    """
    Automated reminder service.
    
    Features:
    - 24-hour advance reminders
    - Same-day reminders
    - Confirmation requests
    - Follow-up messages
    """
    
    def __init__(self, db: Connection):
        self.db = db
        self.sms = SMSService()
        self.email = EmailService()
    
    async def schedule_reminders(self, booking_id: UUID) -> List[Dict[str, Any]]:
        """
        Schedule all reminders for a booking.
        
        Args:
            booking_id: The booking to schedule reminders for
        
        Returns:
            List of scheduled reminders
        """
        booking = await self.db.fetchrow("""
            SELECT b.*, s.name as service_name, u.phone, u.email, u.name as customer_name,
                   bus.name as business_name
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN users u ON b.user_id = u.id
            JOIN businesses bus ON b.business_id = bus.id
            WHERE b.id = $1
        """, booking_id)
        
        if not booking:
            return []
        
        scheduled = []
        
        # 24 hours before
        reminder_time = booking["start_time"] - timedelta(hours=24)
        if reminder_time > datetime.utcnow():
            await self._create_reminder(
                booking_id=booking_id,
                reminder_type=ReminderType.DAY_BEFORE,
                scheduled_at=reminder_time,
            )
            scheduled.append({"type": "day_before", "time": reminder_time})
        
        # 2 hours before
        reminder_time = booking["start_time"] - timedelta(hours=2)
        if reminder_time > datetime.utcnow():
            await self._create_reminder(
                booking_id=booking_id,
                reminder_type=ReminderType.HOURS_BEFORE,
                scheduled_at=reminder_time,
            )
            scheduled.append({"type": "hours_before", "time": reminder_time})
        
        logger.info(
            "Scheduled reminders",
            booking_id=str(booking_id),
            count=len(scheduled),
        )
        
        return scheduled
    
    async def _create_reminder(
        self,
        booking_id: UUID,
        reminder_type: ReminderType,
        scheduled_at: datetime,
    ) -> UUID:
        """Create a reminder in the database."""
        result = await self.db.fetchrow("""
            INSERT INTO reminders (booking_id, reminder_type, scheduled_at, status)
            VALUES ($1, $2, $3, 'pending')
            ON CONFLICT (booking_id, reminder_type) DO UPDATE
            SET scheduled_at = $3, status = 'pending'
            RETURNING id
        """, booking_id, reminder_type.value, scheduled_at)
        
        return result["id"]
    
    async def process_pending_reminders(self) -> int:
        """
        Process all pending reminders that are due.
        Should be called by a background task/scheduler.
        
        Returns:
            Number of reminders processed
        """
        # Get due reminders
        reminders = await self.db.fetch("""
            SELECT r.*, b.start_time, b.status as booking_status,
                   s.name as service_name, u.phone, u.email, u.name,
                   bus.name as business_name
            FROM reminders r
            JOIN bookings b ON r.booking_id = b.id
            JOIN services s ON b.service_id = s.id
            JOIN users u ON b.user_id = u.id
            JOIN businesses bus ON b.business_id = bus.id
            WHERE r.status = 'pending'
            AND r.scheduled_at <= NOW()
            AND b.status = 'confirmed'
            LIMIT 100
        """)
        
        processed = 0
        for reminder in reminders:
            try:
                await self._send_reminder(reminder)
                await self.db.execute("""
                    UPDATE reminders SET status = 'sent', sent_at = NOW()
                    WHERE id = $1
                """, reminder["id"])
                processed += 1
            except Exception as e:
                logger.error(
                    "Failed to send reminder",
                    reminder_id=str(reminder["id"]),
                    error=str(e),
                )
                await self.db.execute("""
                    UPDATE reminders SET status = 'failed', error = $2
                    WHERE id = $1
                """, reminder["id"], str(e))
        
        if processed > 0:
            logger.info(f"Processed {processed} reminders")
        
        return processed
    
    async def _send_reminder(self, reminder: Dict[str, Any]) -> None:
        """Send a reminder via appropriate channel."""
        message = self._format_reminder_message(reminder)
        
        # Send SMS
        if reminder.get("phone"):
            await self.sms.send(
                to=reminder["phone"],
                message=message,
                business_id=str(reminder.get("business_id")),
            )
        
        # Send Email
        if reminder.get("email"):
            await self.email.send(
                to=reminder["email"],
                subject=f"Reminder: {reminder['service_name']} Appointment",
                body=message,
            )
    
    def _format_reminder_message(self, reminder: Dict[str, Any]) -> str:
        """Format reminder message based on type."""
        start_time = reminder["start_time"]
        formatted_time = start_time.strftime("%A, %B %d at %I:%M %p")
        
        if reminder["reminder_type"] == ReminderType.DAY_BEFORE.value:
            return (
                f"Reminder: You have a {reminder['service_name']} appointment "
                f"tomorrow at {start_time.strftime('%I:%M %p')}.\n\n"
                f"Reply CONFIRM to confirm or CANCEL to cancel."
            )
        elif reminder["reminder_type"] == ReminderType.HOURS_BEFORE.value:
            return (
                f"Your {reminder['service_name']} appointment is in 2 hours "
                f"at {start_time.strftime('%I:%M %p')}.\n\n"
                f"See you soon!"
            )
        else:
            return (
                f"Reminder: {reminder['service_name']} - {formatted_time}\n"
                f"Location: {reminder.get('business_name', 'Our office')}"
            )
    
    async def cancel_reminders(self, booking_id: UUID) -> None:
        """Cancel all pending reminders for a booking."""
        await self.db.execute("""
            UPDATE reminders SET status = 'cancelled'
            WHERE booking_id = $1 AND status = 'pending'
        """, booking_id)


async def reminder_worker(db_pool):
    """
    Background worker that processes reminders.
    Run this as a separate process or thread.
    """
    while True:
        try:
            async with db_pool.acquire() as db:
                service = ReminderService(db)
                await service.process_pending_reminders()
        except Exception as e:
            logger.error("Reminder worker error", error=str(e))
        
        # Wait 1 minute before next check
        await asyncio.sleep(60)


# SQL for reminders table
REMINDERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS reminders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    reminder_type VARCHAR(20) NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    sent_at TIMESTAMPTZ,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT unique_reminder UNIQUE (booking_id, reminder_type)
);

CREATE INDEX IF NOT EXISTS idx_reminders_pending 
ON reminders(scheduled_at) WHERE status = 'pending';
"""

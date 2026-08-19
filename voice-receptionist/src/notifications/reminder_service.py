"""
Appointment Reminder Service.

Sends automated reminders to customers before their appointments:
- SMS reminders (24h, 1h before)
- Email reminders (24h before)
- Supports confirmation/cancellation via SMS reply
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from src.core.config import settings
from src.core.database import get_db
from src.core.logging import get_logger
from src.notifications.sms_service import SMSService
from src.notifications.email_service import EmailService

logger = get_logger(__name__)


class AppointmentReminderService:
    """
    Automated appointment reminder system.
    
    Sends reminders at configurable intervals before appointments.
    Tracks reminder status to avoid duplicates.
    """
    
    DEFAULT_REMINDER_SCHEDULE = [
        {"hours_before": 24, "channel": "email", "name": "24h_email"},
        {"hours_before": 24, "channel": "sms", "name": "24h_sms"},
        {"hours_before": 2, "channel": "sms", "name": "2h_sms"},
    ]
    
    def __init__(self):
        self.sms_service = SMSService()
        self.email_service = EmailService()
    
    async def send_due_reminders(self) -> Dict[str, int]:
        """
        Find and send all due reminders.
        
        This should be called periodically (e.g., every 5 minutes).
        
        Returns:
            Stats on reminders sent
        """
        stats = {"sent": 0, "failed": 0, "skipped": 0}
        
        async with get_db() as db:
            # Get confirmed bookings within reminder windows
            for schedule in self.DEFAULT_REMINDER_SCHEDULE:
                hours = schedule["hours_before"]
                channel = schedule["channel"]
                reminder_name = schedule["name"]
                
                # Calculate time window
                now = datetime.utcnow()
                target_start = now + timedelta(hours=hours)
                target_end = target_start + timedelta(minutes=10)  # 10-minute window
                
                # Find bookings needing this reminder
                bookings = await db.fetch("""
                    SELECT b.*, 
                           s.name as service_name,
                           bus.name as business_name,
                           bus.phone_number as business_phone
                    FROM bookings b
                    JOIN services s ON b.service_id = s.id
                    JOIN businesses bus ON b.business_id = bus.id
                    WHERE b.status = 'confirmed'
                      AND b.start_time >= $1
                      AND b.start_time < $2
                      AND NOT EXISTS (
                          SELECT 1 FROM notification_logs nl
                          WHERE nl.booking_id = b.id
                            AND nl.notification_type = $3
                      )
                """, target_start, target_end, reminder_name)
                
                for booking in bookings:
                    try:
                        success = await self._send_reminder(
                            booking, channel, reminder_name, hours
                        )
                        if success:
                            stats["sent"] += 1
                        else:
                            stats["failed"] += 1
                    except Exception as e:
                        logger.error(
                            "Reminder failed",
                            booking_id=str(booking["id"]),
                            error=str(e),
                        )
                        stats["failed"] += 1
        
        if stats["sent"] > 0 or stats["failed"] > 0:
            logger.info("Reminder batch complete", **stats)
        
        return stats
    
    async def _send_reminder(
        self,
        booking: dict,
        channel: str,
        reminder_name: str,
        hours_before: int,
    ) -> bool:
        """Send a single reminder."""
        booking_id = booking["id"]
        customer_phone = booking.get("customer_phone")
        customer_email = booking.get("customer_email")
        customer_name = booking.get("customer_name", "Valued Customer")
        
        # Format appointment time
        start_time = booking["start_time"]
        formatted_time = start_time.strftime("%A, %B %d at %I:%M %p")
        
        # Build message
        service_name = booking.get("service_name", "your appointment")
        business_name = booking.get("business_name", "us")
        
        success = False
        
        if channel == "sms" and customer_phone:
            message = (
                f"Reminder: Your {service_name} at {business_name} is "
                f"{'tomorrow' if hours_before >= 20 else f'in {hours_before} hours'} "
                f"({formatted_time}). Reply CONFIRM or CANCEL."
            )
            
            result = await self.sms_service.send_sms(
                to_phone=customer_phone,
                message=message,
            )
            success = result.get("success", False)
            
        elif channel == "email" and customer_email:
            subject = f"Appointment Reminder: {service_name} at {business_name}"
            
            body = f"""
Dear {customer_name},

This is a friendly reminder about your upcoming appointment:

📅 {formatted_time}
🏢 {business_name}
📋 {service_name}

If you need to reschedule or cancel, please contact us at {booking.get('business_phone', 'our office')}.

Thank you,
{business_name}
            """.strip()
            
            result = await self.email_service.send_email(
                to_email=customer_email,
                subject=subject,
                body=body,
            )
            success = result.get("success", False)
        
        # Log the reminder
        async with get_db() as db:
            await db.execute("""
                INSERT INTO notification_logs 
                (booking_id, channel, notification_type, status, sent_at)
                VALUES ($1, $2, $3, $4, NOW())
            """, booking_id, channel, reminder_name, 
            "sent" if success else "failed")
        
        logger.info(
            "Reminder sent",
            booking_id=str(booking_id),
            channel=channel,
            reminder=reminder_name,
            success=success,
        )
        
        return success
    
    async def handle_sms_reply(self, from_phone: str, message: str) -> str:
        """
        Handle SMS reply to reminder (CONFIRM/CANCEL).
        
        Args:
            from_phone: Customer phone number
            message: SMS message content
        
        Returns:
            Response message to send
        """
        message_lower = message.lower().strip()
        
        async with get_db() as db:
            # Find recent pending booking for this phone
            booking = await db.fetchrow("""
                SELECT b.*, s.name as service_name, bus.name as business_name
                FROM bookings b
                JOIN services s ON b.service_id = s.id
                JOIN businesses bus ON b.business_id = bus.id
                WHERE b.customer_phone = $1
                  AND b.status = 'confirmed'
                  AND b.start_time > NOW()
                ORDER BY b.start_time ASC
                LIMIT 1
            """, from_phone)
            
            if not booking:
                return "We couldn't find an upcoming appointment for your number."
            
            if "confirm" in message_lower or "yes" in message_lower:
                # Mark as confirmed
                await db.execute("""
                    UPDATE bookings SET notes = notes || ' [CONFIRMED VIA SMS]'
                    WHERE id = $1
                """, booking["id"])
                
                return (
                    f"Great! Your {booking['service_name']} appointment at "
                    f"{booking['business_name']} is confirmed. See you soon!"
                )
            
            elif "cancel" in message_lower or "no" in message_lower:
                # Cancel the booking
                await db.execute("""
                    UPDATE bookings 
                    SET status = 'cancelled', 
                        notes = notes || ' [CANCELLED VIA SMS]'
                    WHERE id = $1
                """, booking["id"])
                
                return (
                    f"Your {booking['service_name']} appointment has been cancelled. "
                    f"Please call {booking['business_name']} if you'd like to reschedule."
                )
            
            else:
                return (
                    "Reply CONFIRM to confirm your appointment "
                    "or CANCEL to cancel it."
                )


# Background task for running reminders
async def reminder_background_task():
    """
    Background task that runs every 5 minutes to send due reminders.
    
    Usage:
        asyncio.create_task(reminder_background_task())
    """
    service = AppointmentReminderService()
    
    while True:
        try:
            await service.send_due_reminders()
        except Exception as e:
            logger.error("Reminder task error", error=str(e))
        
        # Wait 5 minutes
        await asyncio.sleep(300)

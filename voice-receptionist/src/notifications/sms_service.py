"""
SMS notification service using Twilio.
"""

from typing import Optional
from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class SMSService:
    """Service for sending SMS notifications via Twilio."""
    
    def __init__(self):
        self.enabled = settings.sms_enabled
        self.from_number = settings.twilio_phone_number
        self.client = None
        
        if self.enabled and settings.twilio_account_sid:
            from twilio.rest import Client
            self.client = Client(
                settings.twilio_account_sid,
                settings.twilio_auth_token
            )
    
    async def send(
        self,
        to: str,
        message: str,
        business_id: Optional[str] = None,
    ) -> dict:
        """
        Send an SMS message.
        
        Args:
            to: Recipient phone number
            message: Message content
            business_id: Business ID for logging
        
        Returns:
            Result dict with success status
        """
        if not self.enabled or not self.client:
            logger.warning("SMS service not configured")
            return {"success": False, "error": "SMS not configured"}
        
        try:
            # Format phone number
            to_number = self._format_phone(to)
            
            # Send via Twilio
            result = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=to_number,
            )
            
            logger.info(
                "SMS sent",
                to=to_number,
                message_sid=result.sid,
                business_id=business_id,
            )
            
            return {
                "success": True,
                "message_id": result.sid,
            }
        
        except Exception as e:
            logger.error("SMS send failed", error=str(e), to=to)
            return {
                "success": False,
                "error": str(e),
            }
    
    async def send_booking_confirmation(
        self,
        to: str,
        booking_details: dict,
    ) -> dict:
        """Send booking confirmation SMS."""
        message = self._format_confirmation_message(booking_details)
        return await self.send(to, message, booking_details.get("business_id"))
    
    async def send_booking_reminder(
        self,
        to: str,
        booking_details: dict,
    ) -> dict:
        """Send booking reminder SMS."""
        message = self._format_reminder_message(booking_details)
        return await self.send(to, message, booking_details.get("business_id"))
    
    async def send_approval_notification(
        self,
        to: str,
        booking_details: dict,
        approved: bool,
    ) -> dict:
        """Send approval/rejection notification."""
        if approved:
            message = self._format_confirmation_message(booking_details)
        else:
            message = f"Your booking request for {booking_details.get('service_name', 'your appointment')} was not available. Please call us to reschedule."
        
        return await self.send(to, message, booking_details.get("business_id"))
    
    def _format_phone(self, phone: str) -> str:
        """Format phone number for Twilio."""
        digits = ''.join(c for c in phone if c.isdigit())
        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits[0] == '1':
            return f"+{digits}"
        return f"+{digits}"
    
    def _format_confirmation_message(self, details: dict) -> str:
        """Format booking confirmation message."""
        return (
            f"Your appointment is confirmed!\n\n"
            f"Service: {details.get('service_name', 'Appointment')}\n"
            f"Date/Time: {details.get('formatted_time', 'TBD')}\n"
            f"Location: {details.get('business_name', 'Our office')}\n\n"
            f"Reply CANCEL to cancel."
        )
    
    def _format_reminder_message(self, details: dict) -> str:
        """Format booking reminder message."""
        return (
            f"Reminder: You have an appointment tomorrow!\n\n"
            f"Service: {details.get('service_name', 'Appointment')}\n"
            f"Time: {details.get('formatted_time', 'TBD')}\n\n"
            f"Reply CONFIRM to confirm or CANCEL to cancel."
        )

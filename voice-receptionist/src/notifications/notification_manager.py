"""
Unified Notification Manager.

Coordinates SMS, Email, and Push notifications for:
- Admin notifications on new bookings
- Customer notifications on approval/rejection
- Real-time dashboard updates via WebSocket
"""

import asyncio
from typing import Dict, Any, List, Optional
from uuid import UUID

from asyncpg import Connection

from src.notifications.sms_service import SMSService
from src.notifications.email_service import EmailService
from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class NotificationManager:
    """
    Centralized notification orchestrator.
    
    Handles all notification logic including:
    - Channel selection based on preferences
    - Parallel sending across channels
    - Fallback handling
    - Logging to notification_logs table
    """
    
    def __init__(self, db: Connection):
        self.db = db
        self.sms = SMSService()
        self.email = EmailService()
    
    async def notify_admins_new_booking(
        self,
        booking_details: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Notify all active admins about a new pending booking.
        
        Args:
            booking_details: Dict containing booking info (booking_id, customer_name, 
                           customer_phone, service_name, formatted_time, business_id)
        
        Returns:
            Dict with notification results per admin
        """
        business_id = booking_details.get("business_id")
        if not business_id:
            logger.error("No business_id in booking_details")
            return {"success": False, "error": "No business_id"}
        
        # Get all active admins for this business
        admins = await self._get_admins_for_business(UUID(business_id))
        
        if not admins:
            logger.warning(
                "No active admins found for business",
                business_id=business_id,
            )
            return {"success": False, "error": "No admins found"}
        
        results = []
        
        for admin in admins:
            admin_result = {"admin_id": str(admin["id"]), "channels": {}}
            
            # Get notification preferences
            prefs = admin.get("notification_preferences", {})
            if isinstance(prefs, str):
                import json
                prefs = json.loads(prefs)
            
            # Send SMS if enabled and phone available
            if prefs.get("sms", False) and admin.get("phone"):
                sms_result = await self._send_admin_sms(
                    admin["phone"],
                    booking_details,
                )
                admin_result["channels"]["sms"] = sms_result
            
            # Send Email if enabled
            if prefs.get("email", True) and admin.get("email"):
                email_result = await self.email.send_admin_notification(
                    admin["email"],
                    booking_details,
                )
                admin_result["channels"]["email"] = email_result
            
            # Push notification (WebSocket) - always attempt
            if prefs.get("push", True):
                push_result = await self._broadcast_to_dashboard(
                    business_id,
                    "new_booking",
                    booking_details,
                )
                admin_result["channels"]["push"] = push_result
            
            results.append(admin_result)
        
        # Log notification
        await self._log_notification(
            business_id=business_id,
            channel="multi",
            recipient="admins",
            template="new_booking",
            content=f"New booking from {booking_details.get('customer_name', 'Customer')}",
            status="sent",
        )
        
        logger.info(
            "Admin notifications sent",
            business_id=business_id,
            booking_id=booking_details.get("booking_id"),
            admin_count=len(admins),
        )
        
        return {"success": True, "results": results}
    
    async def notify_customer_approval(
        self,
        booking_id: UUID,
        approved: bool,
    ) -> Dict[str, Any]:
        """
        Notify customer about booking approval or rejection.
        
        Args:
            booking_id: The booking ID
            approved: True if approved, False if rejected
        
        Returns:
            Dict with notification results
        """
        # Get booking with customer details
        booking = await self._get_booking_with_customer(booking_id)
        
        if not booking:
            logger.error("Booking not found for notification", booking_id=str(booking_id))
            return {"success": False, "error": "Booking not found"}
        
        customer_phone = booking.get("customer_phone")
        customer_email = booking.get("customer_email")
        business_id = str(booking.get("business_id"))
        
        results = {"channels": {}}
        
        # Build booking details for templates
        booking_details = {
            "booking_id": str(booking_id),
            "service_name": booking.get("service_name", "Appointment"),
            "formatted_time": booking.get("formatted_time", ""),
            "business_name": booking.get("business_name", ""),
            "customer_name": booking.get("customer_name", ""),
            "business_id": business_id,
        }
        
        # Send SMS
        if customer_phone:
            sms_result = await self.sms.send_approval_notification(
                customer_phone,
                booking_details,
                approved,
            )
            results["channels"]["sms"] = sms_result
        
        # Send Email
        if customer_email:
            if approved:
                email_result = await self.email.send_booking_confirmation(
                    customer_email,
                    booking_details,
                )
            else:
                # Rejection email
                email_result = await self.email.send(
                    customer_email,
                    subject=f"Booking Update - {booking_details['service_name']}",
                    body=f"Unfortunately, your booking request for {booking_details['service_name']} on {booking_details['formatted_time']} could not be confirmed. Please call us to reschedule.",
                    business_id=business_id,
                )
            results["channels"]["email"] = email_result
        
        # Log
        status = "approved" if approved else "rejected"
        await self._log_notification(
            business_id=business_id,
            user_id=booking.get("user_id"),
            channel="multi",
            recipient=customer_phone or customer_email,
            template=f"booking_{status}",
            content=f"Booking {status}",
            status="sent",
        )
        
        logger.info(
            f"Customer notified of booking {status}",
            booking_id=str(booking_id),
            customer_phone=customer_phone,
            approved=approved,
        )
        
        return {"success": True, "approved": approved, **results}
    
    async def _get_admins_for_business(self, business_id: UUID) -> List[Dict]:
        """Get all active admins for a business with their notification preferences."""
        query = """
            SELECT id, email, name, role, notification_preferences, phone_number as phone
            FROM admin_users
            WHERE business_id = $1 AND is_active = true
        """
        
        # Note: admin_users may not have phone_number column - we'll handle gracefully
        try:
            rows = await self.db.fetch(query, business_id)
            return [dict(row) for row in rows]
        except Exception as e:
            # Fallback without phone
            logger.warning("Admin phone query failed, trying without phone", error=str(e))
            query = """
                SELECT id, email, name, role, notification_preferences
                FROM admin_users
                WHERE business_id = $1 AND is_active = true
            """
            rows = await self.db.fetch(query, business_id)
            return [dict(row) for row in rows]
    
    async def _get_booking_with_customer(self, booking_id: UUID) -> Optional[Dict]:
        """Get booking with customer and service details."""
        query = """
            SELECT 
                b.id as booking_id,
                b.business_id,
                b.user_id,
                b.start_time,
                TO_CHAR(b.start_time AT TIME ZONE 'UTC', 'Day, Month DD at HH12:MI AM') as formatted_time,
                u.phone as customer_phone,
                u.email as customer_email,
                u.name as customer_name,
                s.name as service_name,
                biz.name as business_name
            FROM bookings b
            LEFT JOIN users u ON b.user_id = u.id
            LEFT JOIN services s ON b.service_id = s.id
            LEFT JOIN businesses biz ON b.business_id = biz.id
            WHERE b.id = $1
        """
        row = await self.db.fetchrow(query, booking_id)
        return dict(row) if row else None
    
    async def _send_admin_sms(
        self,
        phone: str,
        booking_details: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send SMS notification to admin about new booking."""
        message = (
            f"New booking request!\n"
            f"Customer: {booking_details.get('customer_name', 'Unknown')}\n"
            f"Phone: {booking_details.get('customer_phone', 'N/A')}\n"
            f"Service: {booking_details.get('service_name', 'N/A')}\n"
            f"Time: {booking_details.get('formatted_time', 'TBD')}\n\n"
            f"Login to approve or reject."
        )
        
        return await self.sms.send(
            phone,
            message,
            booking_details.get("business_id"),
        )
    
    async def _broadcast_to_dashboard(
        self,
        business_id: str,
        event_type: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Broadcast event to connected admin dashboards via WebSocket.
        
        Args:
            business_id: Target business ID
            event_type: Event type (e.g., 'new_booking')
            data: Event payload
        
        Returns:
            Dict with success status and count of notified clients
        """
        try:
            from src.api.routes.websocket import broadcast_to_business
            
            # Filter out non-serializable data
            serializable_data = {
                k: v for k, v in data.items()
                if isinstance(v, (str, int, float, bool, list, dict, type(None)))
            }
            
            sent_count = await broadcast_to_business(
                business_id,
                event_type,
                serializable_data,
            )
            
            logger.info(
                "Dashboard broadcast sent",
                business_id=business_id,
                event_type=event_type,
                clients_notified=sent_count,
            )
            
            return {"success": True, "clients_notified": sent_count}
            
        except Exception as e:
            logger.error(
                "Dashboard broadcast failed",
                error=str(e),
                business_id=business_id,
            )
            return {"success": False, "error": str(e)}
    
    async def _log_notification(
        self,
        business_id: str,
        channel: str,
        recipient: str,
        template: str,
        content: str,
        status: str,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Log notification to database."""
        try:
            query = """
                INSERT INTO notification_logs 
                (business_id, user_id, channel, recipient, template, content, status, sent_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
            """
            await self.db.execute(
                query,
                UUID(business_id),
                user_id,
                channel,
                recipient,
                template,
                content,
                status,
            )
        except Exception as e:
            logger.error("Failed to log notification", error=str(e))

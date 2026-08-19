"""
Email notification service.
"""

from typing import Optional, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiosmtplib

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class EmailService:
    """Service for sending email notifications."""
    
    def __init__(self):
        self.enabled = settings.email_enabled
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        self.smtp_user = settings.smtp_user
        self.smtp_pass = settings.smtp_pass
        self.from_email = settings.email_from
    
    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        business_id: Optional[str] = None,
    ) -> dict:
        """
        Send an email.
        
        Args:
            to: Recipient email
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            business_id: Business ID for logging
        
        Returns:
            Result dict with success status
        """
        if not self.enabled:
            logger.warning("Email service not configured")
            return {"success": False, "error": "Email not configured"}
        
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to
            
            # Add text part
            msg.attach(MIMEText(body, "plain"))
            
            # Add HTML part if provided
            if html_body:
                msg.attach(MIMEText(html_body, "html"))
            
            # Send via SMTP
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_pass,
                start_tls=True,
            )
            
            logger.info(
                "Email sent",
                to=to,
                subject=subject,
                business_id=business_id,
            )
            
            return {"success": True}
        
        except Exception as e:
            logger.error("Email send failed", error=str(e), to=to)
            return {
                "success": False,
                "error": str(e),
            }
    
    async def send_booking_confirmation(
        self,
        to: str,
        booking_details: dict,
    ) -> dict:
        """Send booking confirmation email."""
        subject = f"Booking Confirmed - {booking_details.get('service_name', 'Appointment')}"
        
        body = self._format_confirmation_text(booking_details)
        html = self._format_confirmation_html(booking_details)
        
        return await self.send(to, subject, body, html, booking_details.get("business_id"))
    
    async def send_admin_notification(
        self,
        to: str,
        booking_details: dict,
    ) -> dict:
        """Send admin notification for new booking."""
        subject = f"New Booking Request - {booking_details.get('customer_name', 'Customer')}"
        
        body = f"""New booking request received.

Customer: {booking_details.get('customer_name')}
Phone: {booking_details.get('customer_phone')}
Service: {booking_details.get('service_name')}
Time: {booking_details.get('formatted_time')}

Please log in to approve or reject this booking.
"""
        
        return await self.send(to, subject, body, business_id=booking_details.get("business_id"))
    
    def _format_confirmation_text(self, details: dict) -> str:
        """Format plain text confirmation."""
        return f"""Your booking is confirmed!

Service: {details.get('service_name', 'Appointment')}
Date/Time: {details.get('formatted_time', 'TBD')}
Location: {details.get('business_name', 'Our office')}

If you need to cancel or reschedule, please call us.

Thank you!
"""
    
    def _format_confirmation_html(self, details: dict) -> str:
        """Format HTML confirmation email."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #4A90D9; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; background: #f9f9f9; }}
        .details {{ background: white; padding: 15px; border-radius: 5px; margin: 15px 0; }}
        .detail-row {{ display: flex; padding: 8px 0; border-bottom: 1px solid #eee; }}
        .label {{ font-weight: bold; width: 100px; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Booking Confirmed!</h1>
        </div>
        <div class="content">
            <p>Your appointment has been confirmed. Here are the details:</p>
            <div class="details">
                <div class="detail-row">
                    <span class="label">Service:</span>
                    <span>{details.get('service_name', 'Appointment')}</span>
                </div>
                <div class="detail-row">
                    <span class="label">Date/Time:</span>
                    <span>{details.get('formatted_time', 'TBD')}</span>
                </div>
                <div class="detail-row">
                    <span class="label">Location:</span>
                    <span>{details.get('business_name', 'Our office')}</span>
                </div>
            </div>
            <p>If you need to cancel or reschedule, please call us.</p>
        </div>
        <div class="footer">
            <p>Thank you for choosing {details.get('business_name', 'us')}!</p>
        </div>
    </div>
</body>
</html>
"""

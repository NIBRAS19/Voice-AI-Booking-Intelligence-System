"""
Calendar synchronization with Google Calendar and Outlook.
Two-way sync for bookings.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from uuid import UUID
from abc import ABC, abstractmethod

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class CalendarProvider(ABC):
    """Abstract calendar provider interface."""
    
    @abstractmethod
    async def create_event(self, booking: Dict[str, Any]) -> str:
        """Create calendar event. Returns event ID."""
        pass
    
    @abstractmethod
    async def update_event(self, event_id: str, booking: Dict[str, Any]) -> bool:
        """Update calendar event."""
        pass
    
    @abstractmethod
    async def delete_event(self, event_id: str) -> bool:
        """Delete calendar event."""
        pass
    
    @abstractmethod
    async def get_busy_times(self, start: datetime, end: datetime) -> List[tuple]:
        """Get busy time ranges from calendar."""
        pass


class GoogleCalendarProvider(CalendarProvider):
    """
    Google Calendar integration.
    
    Setup:
    1. Create project in Google Cloud Console
    2. Enable Google Calendar API
    3. Create service account credentials
    4. Share calendar with service account email
    """
    
    def __init__(self, credentials_path: str, calendar_id: str):
        self.credentials_path = credentials_path
        self.calendar_id = calendar_id
        self.service = None
    
    async def _get_service(self):
        """Get authenticated Google Calendar service."""
        if self.service:
            return self.service
        
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            
            self.service = build('calendar', 'v3', credentials=credentials)
            return self.service
        except ImportError:
            logger.error("Google API client not installed")
            return None
        except Exception as e:
            logger.error("Failed to authenticate with Google", error=str(e))
            return None
    
    async def create_event(self, booking: Dict[str, Any]) -> Optional[str]:
        """Create Google Calendar event."""
        service = await self._get_service()
        if not service:
            return None
        
        event = {
            'summary': f"{booking.get('service_name', 'Appointment')} - {booking.get('customer_name', 'Customer')}",
            'description': f"Booking ID: {booking.get('id')}\nPhone: {booking.get('customer_phone', 'N/A')}\nNotes: {booking.get('customer_notes', 'None')}",
            'start': {
                'dateTime': booking['start_time'].isoformat(),
                'timeZone': booking.get('timezone', 'UTC'),
            },
            'end': {
                'dateTime': booking['end_time'].isoformat(),
                'timeZone': booking.get('timezone', 'UTC'),
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 60},
                ],
            },
        }
        
        try:
            result = service.events().insert(
                calendarId=self.calendar_id,
                body=event
            ).execute()
            
            logger.info("Google Calendar event created", event_id=result['id'])
            return result['id']
        except Exception as e:
            logger.error("Failed to create Google event", error=str(e))
            return None
    
    async def update_event(self, event_id: str, booking: Dict[str, Any]) -> bool:
        """Update Google Calendar event."""
        service = await self._get_service()
        if not service:
            return False
        
        try:
            event = service.events().get(
                calendarId=self.calendar_id,
                eventId=event_id
            ).execute()
            
            event['start']['dateTime'] = booking['start_time'].isoformat()
            event['end']['dateTime'] = booking['end_time'].isoformat()
            
            service.events().update(
                calendarId=self.calendar_id,
                eventId=event_id,
                body=event
            ).execute()
            
            return True
        except Exception as e:
            logger.error("Failed to update Google event", error=str(e))
            return False
    
    async def delete_event(self, event_id: str) -> bool:
        """Delete Google Calendar event."""
        service = await self._get_service()
        if not service:
            return False
        
        try:
            service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id
            ).execute()
            return True
        except Exception as e:
            logger.error("Failed to delete Google event", error=str(e))
            return False
    
    async def get_busy_times(
        self,
        start: datetime,
        end: datetime,
    ) -> List[tuple]:
        """Get busy times from Google Calendar."""
        service = await self._get_service()
        if not service:
            return []
        
        try:
            body = {
                "timeMin": start.isoformat() + 'Z',
                "timeMax": end.isoformat() + 'Z',
                "items": [{"id": self.calendar_id}]
            }
            
            result = service.freebusy().query(body=body).execute()
            busy_times = result['calendars'][self.calendar_id]['busy']
            
            return [
                (
                    datetime.fromisoformat(b['start'].replace('Z', '+00:00')),
                    datetime.fromisoformat(b['end'].replace('Z', '+00:00'))
                )
                for b in busy_times
            ]
        except Exception as e:
            logger.error("Failed to get Google busy times", error=str(e))
            return []


class OutlookCalendarProvider(CalendarProvider):
    """
    Microsoft Outlook/Office 365 Calendar integration.
    
    Setup:
    1. Register app in Azure Portal
    2. Configure API permissions for Calendar
    3. Get client credentials
    """
    
    def __init__(self, client_id: str, client_secret: str, tenant_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.access_token = None
    
    async def _get_token(self) -> Optional[str]:
        """Get OAuth token for Microsoft Graph API."""
        if self.access_token:
            return self.access_token
        
        try:
            import aiohttp
            
            url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.access_token = result["access_token"]
                        return self.access_token
        except Exception as e:
            logger.error("Failed to get Outlook token", error=str(e))
        
        return None
    
    async def create_event(self, booking: Dict[str, Any]) -> Optional[str]:
        """Create Outlook Calendar event."""
        token = await self._get_token()
        if not token:
            return None
        
        try:
            import aiohttp
            
            event = {
                "subject": f"{booking.get('service_name', 'Appointment')} - {booking.get('customer_name', 'Customer')}",
                "body": {
                    "contentType": "text",
                    "content": f"Booking ID: {booking.get('id')}\nPhone: {booking.get('customer_phone', 'N/A')}"
                },
                "start": {
                    "dateTime": booking['start_time'].isoformat(),
                    "timeZone": "UTC"
                },
                "end": {
                    "dateTime": booking['end_time'].isoformat(),
                    "timeZone": "UTC"
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://graph.microsoft.com/v1.0/me/calendar/events",
                    headers={"Authorization": f"Bearer {token}"},
                    json=event
                ) as response:
                    if response.status == 201:
                        result = await response.json()
                        return result["id"]
        except Exception as e:
            logger.error("Failed to create Outlook event", error=str(e))
        
        return None
    
    async def update_event(self, event_id: str, booking: Dict[str, Any]) -> bool:
        """Update Outlook Calendar event."""
        # Implementation similar to create_event with PATCH
        return False
    
    async def delete_event(self, event_id: str) -> bool:
        """Delete Outlook Calendar event."""
        token = await self._get_token()
        if not token:
            return False
        
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"https://graph.microsoft.com/v1.0/me/calendar/events/{event_id}",
                    headers={"Authorization": f"Bearer {token}"}
                ) as response:
                    return response.status == 204
        except Exception as e:
            logger.error("Failed to delete Outlook event", error=str(e))
        
        return False
    
    async def get_busy_times(self, start: datetime, end: datetime) -> List[tuple]:
        """Get busy times from Outlook Calendar."""
        return []  # Implement using /me/calendar/getSchedule


class CalendarSyncService:
    """
    Unified calendar sync service.
    Manages synchronization across multiple calendar providers.
    """
    
    def __init__(self, db, providers: Dict[str, CalendarProvider] = None):
        self.db = db
        self.providers = providers or {}
    
    def add_provider(self, name: str, provider: CalendarProvider):
        """Add a calendar provider."""
        self.providers[name] = provider
    
    async def sync_booking(self, booking_id: UUID) -> Dict[str, str]:
        """
        Sync booking to all configured calendars.
        
        Returns:
            Dict mapping provider name to event ID
        """
        booking = await self.db.fetchrow("""
            SELECT b.*, s.name as service_name, u.name as customer_name, u.phone as customer_phone
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            LEFT JOIN users u ON b.user_id = u.id
            WHERE b.id = $1
        """, booking_id)
        
        if not booking:
            return {}
        
        event_ids = {}
        for name, provider in self.providers.items():
            event_id = await provider.create_event(dict(booking))
            if event_id:
                event_ids[name] = event_id
        
        # Store event IDs
        if event_ids:
            await self.db.execute("""
                UPDATE bookings SET calendar_events = $1 WHERE id = $2
            """, event_ids, booking_id)
        
        return event_ids
    
    async def delete_booking_events(self, booking_id: UUID) -> None:
        """Delete calendar events for a booking."""
        booking = await self.db.fetchrow(
            "SELECT calendar_events FROM bookings WHERE id = $1",
            booking_id
        )
        
        if not booking or not booking["calendar_events"]:
            return
        
        for name, event_id in booking["calendar_events"].items():
            if name in self.providers:
                await self.providers[name].delete_event(event_id)

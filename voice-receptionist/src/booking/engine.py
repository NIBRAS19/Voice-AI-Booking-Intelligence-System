"""
Booking engine - Main business logic for creating and managing bookings.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from uuid import UUID

from asyncpg import Connection
from asyncpg.exceptions import ExclusionViolationError

from src.booking.availability import AvailabilityCalculator
from src.data.models import (
    Booking, BookingCreate, BookingStatus, BookingSource,
    Service, User, TimeSlot
)
from src.data.repositories.booking_repo import BookingRepository
from src.data.repositories.user_repo import UserRepository
from src.data.repositories.business_repo import BusinessRepository
from src.core.logging import get_logger

logger = get_logger(__name__)


class BookingEngine:
    """
    Main booking engine that orchestrates the booking process.
    
    Handles:
    - Availability checking
    - User creation/lookup
    - Booking creation with conflict prevention
    - Confirmation and notification triggering
    """
    
    def __init__(self, db: Connection):
        self.db = db
        self.availability = AvailabilityCalculator(db)
        self.booking_repo = BookingRepository(db)
        self.user_repo = UserRepository(db)
        self.business_repo = BusinessRepository(db)
    
    async def check_availability(
        self,
        business_id: UUID,
        service_id: UUID,
        date_str: str,
        preferred_time: Optional[str] = None,
        resource_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Check availability for a given date.
        
        Args:
            business_id: Business ID
            service_id: Service ID
            date_str: Date string (YYYY-MM-DD)
            preferred_time: Optional preferred time (HH:MM)
            resource_id: Optional specific resource
        
        Returns:
            Dict with date, slots, and suggestions
        """
        from datetime import date, time as time_type
        
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        pref_time = None
        if preferred_time:
            pref_time = datetime.strptime(preferred_time, "%H:%M").time()
        
        slots = await self.availability.get_available_slots(
            business_id=business_id,
            service_id=service_id,
            target_date=target_date,
            resource_id=resource_id,
            preferred_time=pref_time,
        )
        
        result = {
            "date": date_str,
            "service_id": str(service_id),
            "slots": [
                {
                    "start": slot.start.isoformat(),
                    "end": slot.end.isoformat(),
                    "formatted_time": slot.start.strftime("%I:%M %p"),
                }
                for slot in slots[:10]  # Limit response
            ],
            "total_available": len(slots),
        }
        
        # If no slots, suggest alternatives
        if not slots:
            alternatives = await self.availability.suggest_alternative_dates(
                business_id=business_id,
                service_id=service_id,
                start_date=target_date,
                resource_id=resource_id,
            )
            result["alternatives"] = alternatives
        
        return result
    
    async def create_booking(
        self,
        business_id: UUID,
        service_id: UUID,
        start_time: datetime,
        customer_phone: str,
        customer_name: Optional[str] = None,
        customer_notes: Optional[str] = None,
        resource_id: Optional[UUID] = None,
        conversation_id: Optional[UUID] = None,
        source: BookingSource = BookingSource.VOICE_AI,
    ) -> Dict[str, Any]:
        """
        Create a new booking atomically.
        
        The database EXCLUDE constraint prevents double-bookings even
        if two requests arrive simultaneously.
        
        Args:
            business_id: Business ID
            service_id: Service ID
            start_time: Booking start time
            customer_phone: Customer phone number
            customer_name: Optional customer name
            customer_notes: Optional notes from customer
            resource_id: Optional resource ID
            conversation_id: Optional conversation session ID
            source: Booking source
        
        Returns:
            Dict with booking details or error
        """
        try:
            # Get service for duration
            service = await self.business_repo.get_service(service_id)
            if not service:
                return {"success": False, "error": "Service not found"}
            
            # Calculate end time
            end_time = start_time + timedelta(minutes=service.duration_minutes)
            
            # Get or create user
            user = await self.user_repo.get_or_create_by_phone(
                business_id=business_id,
                phone=customer_phone,
                name=customer_name,
            )
            
            # Check slot still available (pre-check)
            is_available = await self.availability.check_slot_available(
                business_id=business_id,
                resource_id=resource_id,
                start_time=start_time,
                end_time=end_time,
            )
            
            if not is_available:
                logger.warning(
                    "Slot no longer available",
                    business_id=str(business_id),
                    start_time=str(start_time),
                )
                return {
                    "success": False,
                    "error": "This time slot is no longer available",
                    "code": "SLOT_TAKEN",
                }
            
            # Determine if approval is required
            requires_approval = service.requires_approval
            initial_status = (
                BookingStatus.PENDING_APPROVAL if requires_approval 
                else BookingStatus.CONFIRMED
            )
            
            # Create booking
            booking_create = BookingCreate(
                business_id=business_id,
                user_id=user.id,
                service_id=service_id,
                resource_id=resource_id,
                start_time=start_time,
                end_time=end_time,
                source=source,
                conversation_id=conversation_id,
                customer_notes=customer_notes,
            )
            
            # Attempt insert (EXCLUDE constraint handles conflicts)
            booking = await self.booking_repo.create(booking_create)
            
            # If not requiring approval, mark as confirmed
            if not requires_approval:
                from src.data.models import BookingUpdate
                booking = await self.booking_repo.update(
                    booking.id,
                    BookingUpdate(status=BookingStatus.CONFIRMED)
                )
            
            logger.info(
                "Booking created successfully",
                booking_id=str(booking.id),
                business_id=str(business_id),
                status=initial_status.value,
            )
            
            result = {
                "success": True,
                "booking_id": str(booking.id),
                "status": booking.status.value,
                "requires_approval": requires_approval,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "formatted_time": start_time.strftime("%A, %B %d at %I:%M %p"),
                "service_name": service.name,
                "customer_name": user.name,
                "customer_phone": user.phone,
                "business_id": str(business_id),
            }
            
            # Trigger admin notification for pending approvals
            if requires_approval:
                try:
                    from src.notifications import NotificationManager
                    notification_manager = NotificationManager(self.db)
                    await notification_manager.notify_admins_new_booking(result)
                except Exception as e:
                    # Don't fail the booking if notification fails
                    logger.error(
                        "Failed to send admin notification",
                        error=str(e),
                        booking_id=str(booking.id),
                    )
            
            return result
            
        except ExclusionViolationError:
            # Database caught the double-booking
            logger.warning(
                "Double-booking prevented by constraint",
                business_id=str(business_id),
                start_time=str(start_time),
            )
            return {
                "success": False,
                "error": "This time slot was just taken by another booking",
                "code": "CONFLICT",
            }
        except Exception as e:
            logger.error(
                "Booking creation failed",
                error=str(e),
                business_id=str(business_id),
            )
            return {
                "success": False,
                "error": "Failed to create booking. Please try again.",
                "code": "ERROR",
            }
    
    async def get_best_slot(
        self,
        business_id: UUID,
        service_id: UUID,
        date_str: str,
        preferred_time: Optional[str] = None,
    ) -> Optional[TimeSlot]:
        """
        Get the best available slot for a date.
        If preferred_time is provided, returns closest slot.
        """
        from datetime import date as date_type
        
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        pref_time = None
        if preferred_time:
            pref_time = datetime.strptime(preferred_time, "%H:%M").time()
        
        slots = await self.availability.get_available_slots(
            business_id=business_id,
            service_id=service_id,
            target_date=target_date,
            preferred_time=pref_time,
        )
        
        return slots[0] if slots else None
    
    async def reschedule_booking(
        self,
        booking_id: UUID,
        new_start_time: datetime,
    ) -> Dict[str, Any]:
        """Reschedule an existing booking to a new time."""
        # Get existing booking
        booking = await self.booking_repo.get_by_id(booking_id)
        if not booking:
            return {"success": False, "error": "Booking not found"}
        
        if booking.status == BookingStatus.CANCELLED:
            return {"success": False, "error": "Cannot reschedule cancelled booking"}
        
        # Get service for duration
        service = await self.business_repo.get_service(booking.service_id)
        new_end_time = new_start_time + timedelta(minutes=service.duration_minutes)
        
        # Check new slot available
        is_available = await self.availability.check_slot_available(
            business_id=booking.business_id,
            resource_id=booking.resource_id,
            start_time=new_start_time,
            end_time=new_end_time,
        )
        
        if not is_available:
            return {"success": False, "error": "New time slot not available"}
        
        # Update booking
        from src.data.models import BookingUpdate
        updated = await self.booking_repo.update(
            booking_id,
            BookingUpdate(start_time=new_start_time, end_time=new_end_time),
        )
        
        return {
            "success": True,
            "booking_id": str(booking_id),
            "new_time": new_start_time.isoformat(),
            "formatted_time": new_start_time.strftime("%A, %B %d at %I:%M %p"),
        }
    
    async def cancel_booking(
        self,
        booking_id: UUID,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel a booking."""
        booking = await self.booking_repo.get_by_id(booking_id)
        if not booking:
            return {"success": False, "error": "Booking not found"}
        
        if booking.status == BookingStatus.CANCELLED:
            return {"success": False, "error": "Booking already cancelled"}
        
        from src.data.models import BookingUpdate
        await self.booking_repo.update(
            booking_id,
            BookingUpdate(status=BookingStatus.CANCELLED, admin_notes=reason),
        )
        
        return {"success": True, "booking_id": str(booking_id)}

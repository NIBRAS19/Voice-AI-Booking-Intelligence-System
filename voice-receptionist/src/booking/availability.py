"""
Availability calculation engine.
Implements: Available Slots = Working Hours - Existing Bookings - Buffer Time
"""

from datetime import datetime, date, time, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID

from asyncpg import Connection

from src.data.models import TimeSlot, Service, WorkingHours, Booking
from src.core.logging import get_logger

logger = get_logger(__name__)


class AvailabilityCalculator:
    """
    Calculates available time slots for booking.
    
    The core principle: Availability is CALCULATED, not stored.
    Available = Working Hours - Existing Bookings - Buffer Time
    """
    
    def __init__(self, db: Connection):
        self.db = db
        self.slot_granularity_minutes = 30  # Time slot intervals
    
    async def get_available_slots(
        self,
        business_id: UUID,
        service_id: UUID,
        target_date: date,
        resource_id: Optional[UUID] = None,
        preferred_time: Optional[time] = None,
    ) -> List[TimeSlot]:
        """
        Calculate available slots for a given date and service.
        
        Args:
            business_id: Business ID
            service_id: Service ID (for duration)
            target_date: The date to check
            resource_id: Optional specific resource
            preferred_time: Optional preferred time for sorting
        
        Returns:
            List of available TimeSlot objects
        """
        # Step 1: Get service details
        service = await self._get_service(service_id, business_id)
        if not service:
            logger.warning("Service not found", service_id=str(service_id))
            return []
        
        # Step 2: Get working hours for the day
        day_of_week = target_date.weekday()  # 0=Monday in Python
        # Convert to 0=Sunday format if needed by adjusting
        day_of_week_sunday_start = (day_of_week + 1) % 7
        
        working_hours = await self._get_working_hours(
            business_id, day_of_week_sunday_start, resource_id
        )
        if not working_hours:
            logger.debug("Business closed on this day", date=str(target_date))
            return []
        
        # Step 3: Get existing bookings
        existing_bookings = await self._get_existing_bookings(
            business_id, target_date, resource_id
        )
        
        # Step 4: Generate available slots
        slots = self._calculate_available_slots(
            target_date=target_date,
            working_hours=working_hours,
            existing_bookings=existing_bookings,
            service_duration=service.duration_minutes,
            buffer_minutes=service.buffer_minutes,
        )
        
        # Step 5: Filter past slots if today
        if target_date == date.today():
            now = datetime.now()
            # Add 30 min buffer for same-day bookings
            cutoff = now + timedelta(minutes=30)
            slots = [s for s in slots if s.start >= cutoff]
        
        # Step 6: Sort by proximity to preferred time
        if preferred_time:
            preferred_dt = datetime.combine(target_date, preferred_time)
            slots.sort(key=lambda s: abs((s.start - preferred_dt).total_seconds()))
        
        logger.debug(
            "Availability calculated",
            date=str(target_date),
            available_slots=len(slots),
        )
        
        return slots
    
    async def suggest_alternative_dates(
        self,
        business_id: UUID,
        service_id: UUID,
        start_date: date,
        resource_id: Optional[UUID] = None,
        days_to_check: int = 7,
        min_slots: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Find alternative dates with availability.
        
        Returns:
            List of dicts with date and slot count
        """
        alternatives = []
        
        for i in range(1, days_to_check + 1):
            check_date = start_date + timedelta(days=i)
            slots = await self.get_available_slots(
                business_id=business_id,
                service_id=service_id,
                target_date=check_date,
                resource_id=resource_id,
            )
            
            if len(slots) >= min_slots:
                alternatives.append({
                    "date": check_date,
                    "date_formatted": check_date.strftime("%A, %B %d"),
                    "slot_count": len(slots),
                    "first_slot": slots[0].start if slots else None,
                })
                
                if len(alternatives) >= 3:
                    break
        
        return alternatives
    
    async def check_slot_available(
        self,
        business_id: UUID,
        resource_id: Optional[UUID],
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        """
        Check if a specific time slot is still available.
        Used before final booking to handle race conditions.
        """
        query = """
            SELECT COUNT(*) FROM bookings
            WHERE business_id = $1
            AND ($2::uuid IS NULL OR resource_id = $2)
            AND status NOT IN ('cancelled', 'no_show')
            AND (start_time, end_time) OVERLAPS ($3, $4)
        """
        
        count = await self.db.fetchval(
            query, business_id, resource_id, start_time, end_time
        )
        
        return count == 0
    
    def _calculate_available_slots(
        self,
        target_date: date,
        working_hours: WorkingHours,
        existing_bookings: List[Booking],
        service_duration: int,
        buffer_minutes: int = 0,
    ) -> List[TimeSlot]:
        """
        Core slot calculation logic.
        
        Iterates through working hours in slot_granularity intervals,
        checking each against existing bookings.
        """
        slots = []
        
        # Start and end as datetime
        current = datetime.combine(target_date, working_hours.start_time)
        day_end = datetime.combine(target_date, working_hours.end_time)
        
        slot_duration = timedelta(minutes=service_duration)
        total_duration = timedelta(minutes=service_duration + buffer_minutes)
        
        # Convert bookings to datetime ranges for faster comparison
        booked_ranges = [
            (b.start_time, b.end_time) for b in existing_bookings
        ]
        
        while current + slot_duration <= day_end:
            slot_end = current + slot_duration
            slot_with_buffer = current + total_duration
            
            # Check for overlap with any existing booking
            is_available = True
            for book_start, book_end in booked_ranges:
                # Overlap exists if: slot_start < book_end AND slot_end > book_start
                if current < book_end and slot_with_buffer > book_start:
                    is_available = False
                    break
            
            if is_available:
                slots.append(TimeSlot(
                    start=current,
                    end=slot_end,
                    available=True,
                ))
            
            # Move to next slot
            current += timedelta(minutes=self.slot_granularity_minutes)
        
        return slots
    
    async def _get_service(
        self,
        service_id: UUID,
        business_id: UUID,
    ) -> Optional[Service]:
        """Get service details."""
        query = """
            SELECT * FROM services 
            WHERE id = $1 AND business_id = $2 AND is_active = true
        """
        row = await self.db.fetchrow(query, service_id, business_id)
        return Service(**dict(row)) if row else None
    
    async def _get_working_hours(
        self,
        business_id: UUID,
        day_of_week: int,
        resource_id: Optional[UUID] = None,
    ) -> Optional[WorkingHours]:
        """Get working hours for a specific day."""
        if resource_id:
            query = """
                SELECT * FROM working_hours 
                WHERE business_id = $1 AND day_of_week = $2 AND resource_id = $3
                AND is_active = true
                LIMIT 1
            """
            row = await self.db.fetchrow(query, business_id, day_of_week, resource_id)
        else:
            query = """
                SELECT * FROM working_hours 
                WHERE business_id = $1 AND day_of_week = $2 
                AND (resource_id IS NULL OR is_active = true)
                LIMIT 1
            """
            row = await self.db.fetchrow(query, business_id, day_of_week)
        
        return WorkingHours(**dict(row)) if row else None
    
    async def _get_existing_bookings(
        self,
        business_id: UUID,
        target_date: date,
        resource_id: Optional[UUID] = None,
    ) -> List[Booking]:
        """Get all bookings for a date that affect availability."""
        if resource_id:
            query = """
                SELECT * FROM bookings 
                WHERE business_id = $1 
                AND DATE(start_time) = $2
                AND resource_id = $3
                AND status NOT IN ('cancelled', 'no_show')
                ORDER BY start_time
            """
            rows = await self.db.fetch(query, business_id, target_date, resource_id)
        else:
            query = """
                SELECT * FROM bookings 
                WHERE business_id = $1 
                AND DATE(start_time) = $2
                AND status NOT IN ('cancelled', 'no_show')
                ORDER BY start_time
            """
            rows = await self.db.fetch(query, business_id, target_date)
        
        return [Booking(**dict(row)) for row in rows]

"""
Advanced validation rules for bookings.
Business-specific rules for accepting/rejecting bookings.
"""

from datetime import datetime, date, time, timedelta
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
from enum import Enum
from dataclasses import dataclass

from asyncpg import Connection

from src.core.logging import get_logger

logger = get_logger(__name__)


class ValidationResult:
    """Result of validation check."""
    
    def __init__(self, is_valid: bool, message: str = "", code: str = ""):
        self.is_valid = is_valid
        self.message = message
        self.code = code
    
    @classmethod
    def valid(cls) -> "ValidationResult":
        return cls(True)
    
    @classmethod
    def invalid(cls, message: str, code: str = "INVALID") -> "ValidationResult":
        return cls(False, message, code)


@dataclass
class BookingRule:
    """A booking validation rule."""
    name: str
    enabled: bool
    params: Dict[str, Any]


class BookingValidator:
    """
    Advanced booking validation engine.
    
    Rules:
    - Minimum advance booking time
    - Maximum advance booking time
    - Business hours validation
    - Blackout dates
    - Customer booking limits
    - Service-specific restrictions
    """
    
    def __init__(self, db: Connection):
        self.db = db
        self.rules_cache: Dict[UUID, List[BookingRule]] = {}
    
    async def validate_booking(
        self,
        business_id: UUID,
        service_id: UUID,
        start_time: datetime,
        user_id: Optional[UUID] = None,
        is_new: bool = True,
    ) -> ValidationResult:
        """
        Run all validation rules on a booking.
        
        Args:
            business_id: Business ID
            service_id: Service ID
            start_time: Proposed booking time
            user_id: Customer ID (optional)
            is_new: True for new bookings, False for reschedules
        
        Returns:
            ValidationResult with success/failure and message
        """
        # Load business settings
        business = await self.db.fetchrow(
            "SELECT * FROM businesses WHERE id = $1",
            business_id
        )
        
        if not business:
            return ValidationResult.invalid("Business not found", "BUSINESS_NOT_FOUND")
        
        settings = business.get("settings", {})
        
        # Run each validation
        validations = [
            self._validate_advance_time(start_time, settings),
            await self._validate_business_hours(business_id, start_time),
            await self._validate_blackout_dates(business_id, start_time.date()),
            await self._validate_service_availability(service_id, start_time),
        ]
        
        if user_id:
            validations.append(
                await self._validate_customer_limits(business_id, user_id, settings)
            )
        
        for result in validations:
            if not result.is_valid:
                return result
        
        return ValidationResult.valid()
    
    def _validate_advance_time(
        self,
        start_time: datetime,
        settings: Dict[str, Any],
    ) -> ValidationResult:
        """Validate minimum and maximum advance booking time."""
        now = datetime.utcnow()
        
        # Minimum advance (default: 1 hour)
        min_advance_hours = settings.get("min_advance_hours", 1)
        min_time = now + timedelta(hours=min_advance_hours)
        
        if start_time < min_time:
            return ValidationResult.invalid(
                f"Bookings must be made at least {min_advance_hours} hour(s) in advance",
                "TOO_SOON"
            )
        
        # Maximum advance (default: 60 days)
        max_advance_days = settings.get("max_advance_days", 60)
        max_time = now + timedelta(days=max_advance_days)
        
        if start_time > max_time:
            return ValidationResult.invalid(
                f"Bookings can only be made up to {max_advance_days} days in advance",
                "TOO_FAR"
            )
        
        return ValidationResult.valid()
    
    async def _validate_business_hours(
        self,
        business_id: UUID,
        start_time: datetime,
    ) -> ValidationResult:
        """Validate booking is within business hours."""
        day_of_week = (start_time.weekday() + 1) % 7  # Convert to Sunday=0
        
        hours = await self.db.fetchrow("""
            SELECT start_time, end_time FROM working_hours
            WHERE business_id = $1 AND day_of_week = $2 AND is_active = true
        """, business_id, day_of_week)
        
        if not hours:
            return ValidationResult.invalid(
                f"We're closed on {start_time.strftime('%A')}s",
                "CLOSED_DAY"
            )
        
        booking_time = start_time.time()
        
        if booking_time < hours["start_time"] or booking_time >= hours["end_time"]:
            return ValidationResult.invalid(
                f"Bookings available between {hours['start_time'].strftime('%I:%M %p')} "
                f"and {hours['end_time'].strftime('%I:%M %p')}",
                "OUTSIDE_HOURS"
            )
        
        return ValidationResult.valid()
    
    async def _validate_blackout_dates(
        self,
        business_id: UUID,
        booking_date: date,
    ) -> ValidationResult:
        """Check for blackout dates (holidays, closures)."""
        blackout = await self.db.fetchrow("""
            SELECT reason FROM blackout_dates
            WHERE business_id = $1 AND $2 BETWEEN start_date AND end_date
        """, business_id, booking_date)
        
        if blackout:
            return ValidationResult.invalid(
                f"Sorry, we're unavailable that day: {blackout['reason']}",
                "BLACKOUT_DATE"
            )
        
        return ValidationResult.valid()
    
    async def _validate_service_availability(
        self,
        service_id: UUID,
        start_time: datetime,
    ) -> ValidationResult:
        """Check service-specific availability rules."""
        service = await self.db.fetchrow(
            "SELECT * FROM services WHERE id = $1",
            service_id
        )
        
        if not service:
            return ValidationResult.invalid("Service not found", "SERVICE_NOT_FOUND")
        
        if not service["is_active"]:
            return ValidationResult.invalid(
                "This service is currently unavailable",
                "SERVICE_UNAVAILABLE"
            )
        
        # Check service-specific rules in metadata
        metadata = service.get("metadata", {})
        
        # Example: Some services only on certain days
        allowed_days = metadata.get("allowed_days")
        if allowed_days:
            day_name = start_time.strftime("%A").lower()
            if day_name not in allowed_days:
                return ValidationResult.invalid(
                    f"This service is only available on {', '.join(allowed_days)}",
                    "DAY_RESTRICTED"
                )
        
        return ValidationResult.valid()
    
    async def _validate_customer_limits(
        self,
        business_id: UUID,
        user_id: UUID,
        settings: Dict[str, Any],
    ) -> ValidationResult:
        """Check customer booking limits."""
        # Max active bookings per customer
        max_active = settings.get("max_active_bookings_per_customer", 5)
        
        active_count = await self.db.fetchval("""
            SELECT COUNT(*) FROM bookings
            WHERE business_id = $1 AND user_id = $2
            AND status IN ('pending_approval', 'confirmed')
            AND start_time > NOW()
        """, business_id, user_id)
        
        if active_count >= max_active:
            return ValidationResult.invalid(
                f"Maximum of {max_active} active bookings allowed per customer",
                "LIMIT_REACHED"
            )
        
        # No-show penalty check
        no_show_count = await self.db.fetchval("""
            SELECT COUNT(*) FROM bookings
            WHERE business_id = $1 AND user_id = $2
            AND status = 'no_show'
            AND created_at > NOW() - INTERVAL '30 days'
        """, business_id, user_id)
        
        if no_show_count >= 3:
            return ValidationResult.invalid(
                "Too many missed appointments. Please call to book.",
                "NO_SHOW_PENALTY"
            )
        
        return ValidationResult.valid()


class RecurringBookingService:
    """
    Service for handling recurring/repeat bookings.
    """
    
    def __init__(self, db: Connection):
        self.db = db
        self.validator = BookingValidator(db)
    
    async def create_recurring(
        self,
        business_id: UUID,
        user_id: UUID,
        service_id: UUID,
        start_time: datetime,
        pattern: str,  # 'weekly', 'biweekly', 'monthly'
        occurrences: int,
        resource_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Create a series of recurring bookings.
        
        Args:
            business_id: Business ID
            user_id: Customer ID
            service_id: Service ID
            start_time: First occurrence time
            pattern: Recurrence pattern
            occurrences: Number of occurrences
            resource_id: Resource ID (optional)
        
        Returns:
            Dict with created bookings and any failures
        """
        # Get service duration
        service = await self.db.fetchrow(
            "SELECT duration_minutes FROM services WHERE id = $1",
            service_id
        )
        
        if not service:
            return {"success": False, "error": "Service not found"}
        
        duration = timedelta(minutes=service["duration_minutes"])
        
        # Calculate dates
        dates = self._calculate_recurrence_dates(start_time, pattern, occurrences)
        
        created = []
        failed = []
        
        # Create series ID
        from uuid import uuid4
        series_id = uuid4()
        
        for booking_date in dates:
            # Validate each date
            validation = await self.validator.validate_booking(
                business_id, service_id, booking_date, user_id
            )
            
            if not validation.is_valid:
                failed.append({
                    "date": booking_date.isoformat(),
                    "error": validation.message,
                })
                continue
            
            # Create booking
            try:
                result = await self.db.fetchrow("""
                    INSERT INTO bookings (
                        business_id, user_id, service_id, resource_id,
                        start_time, end_time, status, source,
                        metadata
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, 'pending_approval', 'voice_ai', $7)
                    RETURNING id
                """,
                    business_id, user_id, service_id, resource_id,
                    booking_date, booking_date + duration,
                    {"series_id": str(series_id), "pattern": pattern}
                )
                
                created.append({
                    "booking_id": str(result["id"]),
                    "date": booking_date.isoformat(),
                })
            except Exception as e:
                failed.append({
                    "date": booking_date.isoformat(),
                    "error": str(e),
                })
        
        return {
            "success": len(created) > 0,
            "series_id": str(series_id),
            "created": created,
            "failed": failed,
            "total_created": len(created),
            "total_failed": len(failed),
        }
    
    def _calculate_recurrence_dates(
        self,
        start: datetime,
        pattern: str,
        count: int,
    ) -> List[datetime]:
        """Calculate dates for recurring pattern."""
        dates = [start]
        current = start
        
        for _ in range(count - 1):
            if pattern == "weekly":
                current += timedelta(weeks=1)
            elif pattern == "biweekly":
                current += timedelta(weeks=2)
            elif pattern == "monthly":
                # Add one month (handle month boundaries)
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1)
                else:
                    current = current.replace(month=current.month + 1)
            else:
                break
            
            dates.append(current)
        
        return dates
    
    async def cancel_series(self, series_id: UUID) -> int:
        """Cancel all future bookings in a series."""
        result = await self.db.execute("""
            UPDATE bookings 
            SET status = 'cancelled'
            WHERE metadata->>'series_id' = $1
            AND start_time > NOW()
            AND status != 'cancelled'
        """, str(series_id))
        
        count = int(result.split()[-1]) if result else 0
        logger.info(f"Cancelled {count} bookings in series {series_id}")
        return count


# SQL for blackout dates table
BLACKOUT_DATES_SQL = """
CREATE TABLE IF NOT EXISTS blackout_dates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    reason VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT valid_date_range CHECK (end_date >= start_date)
);

CREATE INDEX IF NOT EXISTS idx_blackout_business ON blackout_dates(business_id, start_date, end_date);
"""

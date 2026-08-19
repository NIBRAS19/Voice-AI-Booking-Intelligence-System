"""
Booking repository for database operations.
"""

from datetime import datetime, date
from typing import List, Optional
from uuid import UUID

from asyncpg import Connection

from src.data.models import (
    Booking, BookingCreate, BookingUpdate, BookingStatus, BookingWithDetails
)
from src.core.logging import get_logger

logger = get_logger(__name__)


class BookingRepository:
    """Repository for booking-related database operations."""
    
    def __init__(self, db: Connection):
        self.db = db
    
    async def create(self, booking: BookingCreate) -> Booking:
        """
        Create a new booking.
        The database EXCLUDE constraint prevents double-bookings.
        """
        query = """
            INSERT INTO bookings (
                business_id, user_id, service_id, resource_id,
                start_time, end_time, status, source, conversation_id,
                customer_notes, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING *
        """
        
        row = await self.db.fetchrow(
            query,
            booking.business_id,
            booking.user_id,
            booking.service_id,
            booking.resource_id,
            booking.start_time,
            booking.end_time,
            BookingStatus.PENDING_APPROVAL.value,
            booking.source.value,
            booking.conversation_id,
            booking.customer_notes,
            booking.metadata,
        )
        
        logger.info(
            "Booking created",
            booking_id=str(row["id"]),
            business_id=str(booking.business_id),
        )
        
        return Booking(**dict(row))
    
    async def get_by_id(self, booking_id: UUID) -> Optional[Booking]:
        """Get a booking by ID."""
        query = "SELECT * FROM bookings WHERE id = $1"
        row = await self.db.fetchrow(query, booking_id)
        
        if row:
            return Booking(**dict(row))
        return None
    
    async def get_by_id_with_details(self, booking_id: UUID) -> Optional[BookingWithDetails]:
        """Get a booking with related entities."""
        query = """
            SELECT 
                b.*,
                u.id as user_id, u.phone as user_phone, u.name as user_name, u.email as user_email,
                s.id as service_id, s.name as service_name, s.duration_minutes, s.price,
                r.id as resource_id, r.name as resource_name, r.type as resource_type
            FROM bookings b
            LEFT JOIN users u ON b.user_id = u.id
            LEFT JOIN services s ON b.service_id = s.id
            LEFT JOIN resources r ON b.resource_id = r.id
            WHERE b.id = $1
        """
        row = await self.db.fetchrow(query, booking_id)
        
        if row:
            return self._build_booking_with_details(dict(row))
        return None
    
    async def list_by_business(
        self,
        business_id: UUID,
        status: Optional[BookingStatus] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Booking]:
        """List bookings for a business with optional filters."""
        conditions = ["business_id = $1"]
        params = [business_id]
        param_count = 1
        
        if status:
            param_count += 1
            conditions.append(f"status = ${param_count}")
            params.append(status.value)
        
        if start_date:
            param_count += 1
            conditions.append(f"DATE(start_time) >= ${param_count}")
            params.append(start_date)
        
        if end_date:
            param_count += 1
            conditions.append(f"DATE(start_time) <= ${param_count}")
            params.append(end_date)
        
        query = f"""
            SELECT * FROM bookings 
            WHERE {' AND '.join(conditions)}
            ORDER BY start_time DESC
            LIMIT ${param_count + 1} OFFSET ${param_count + 2}
        """
        params.extend([limit, offset])
        
        rows = await self.db.fetch(query, *params)
        return [Booking(**dict(row)) for row in rows]
    
    async def list_pending(self, business_id: UUID) -> List[BookingWithDetails]:
        """List pending approval bookings for a business."""
        query = """
            SELECT 
                b.*,
                u.id as user_id, u.phone as user_phone, u.name as user_name, u.email as user_email,
                s.id as service_id, s.name as service_name, s.duration_minutes, s.price,
                r.id as resource_id, r.name as resource_name, r.type as resource_type
            FROM bookings b
            LEFT JOIN users u ON b.user_id = u.id
            LEFT JOIN services s ON b.service_id = s.id
            LEFT JOIN resources r ON b.resource_id = r.id
            WHERE b.business_id = $1 AND b.status = $2
            ORDER BY b.created_at DESC
        """
        rows = await self.db.fetch(query, business_id, BookingStatus.PENDING_APPROVAL.value)
        return [self._build_booking_with_details(dict(row)) for row in rows]
    
    async def update(self, booking_id: UUID, update: BookingUpdate) -> Optional[Booking]:
        """Update a booking."""
        updates = []
        params = []
        param_count = 0
        
        if update.start_time is not None:
            param_count += 1
            updates.append(f"start_time = ${param_count}")
            params.append(update.start_time)
        
        if update.end_time is not None:
            param_count += 1
            updates.append(f"end_time = ${param_count}")
            params.append(update.end_time)
        
        if update.status is not None:
            param_count += 1
            updates.append(f"status = ${param_count}")
            params.append(update.status.value)
        
        if update.admin_notes is not None:
            param_count += 1
            updates.append(f"admin_notes = ${param_count}")
            params.append(update.admin_notes)
        
        if not updates:
            return await self.get_by_id(booking_id)
        
        updates.append(f"updated_at = ${param_count + 1}")
        params.append(datetime.utcnow())
        params.append(booking_id)
        
        query = f"""
            UPDATE bookings 
            SET {', '.join(updates)}
            WHERE id = ${param_count + 2}
            RETURNING *
        """
        
        row = await self.db.fetchrow(query, *params)
        
        if row:
            return Booking(**dict(row))
        return None
    
    async def approve(
        self,
        booking_id: UUID,
        admin_id: UUID,
        notes: Optional[str] = None,
    ) -> Optional[Booking]:
        """Approve a booking."""
        query = """
            UPDATE bookings 
            SET status = $1, approval_admin_id = $2, approved_at = $3, 
                admin_notes = COALESCE($4, admin_notes), updated_at = $3
            WHERE id = $5
            RETURNING *
        """
        
        now = datetime.utcnow()
        row = await self.db.fetchrow(
            query,
            BookingStatus.CONFIRMED.value,
            admin_id,
            now,
            notes,
            booking_id,
        )
        
        if row:
            logger.info(
                "Booking approved",
                booking_id=str(booking_id),
                admin_id=str(admin_id),
            )
            return Booking(**dict(row))
        return None
    
    async def reject(
        self,
        booking_id: UUID,
        admin_id: UUID,
        notes: Optional[str] = None,
    ) -> Optional[Booking]:
        """Reject/cancel a booking."""
        query = """
            UPDATE bookings 
            SET status = $1, approval_admin_id = $2, updated_at = $3,
                admin_notes = COALESCE($4, admin_notes)
            WHERE id = $5
            RETURNING *
        """
        
        now = datetime.utcnow()
        row = await self.db.fetchrow(
            query,
            BookingStatus.CANCELLED.value,
            admin_id,
            now,
            notes,
            booking_id,
        )
        
        if row:
            logger.info(
                "Booking rejected",
                booking_id=str(booking_id),
                admin_id=str(admin_id),
            )
            return Booking(**dict(row))
        return None
    
    async def get_for_date(
        self,
        business_id: UUID,
        target_date: date,
        resource_id: Optional[UUID] = None,
    ) -> List[Booking]:
        """Get all bookings for a specific date."""
        if resource_id:
            query = """
                SELECT * FROM bookings 
                WHERE business_id = $1 AND DATE(start_time) = $2 
                AND resource_id = $3 AND status NOT IN ('cancelled', 'no_show')
                ORDER BY start_time
            """
            rows = await self.db.fetch(query, business_id, target_date, resource_id)
        else:
            query = """
                SELECT * FROM bookings 
                WHERE business_id = $1 AND DATE(start_time) = $2 
                AND status NOT IN ('cancelled', 'no_show')
                ORDER BY start_time
            """
            rows = await self.db.fetch(query, business_id, target_date)
        
        return [Booking(**dict(row)) for row in rows]
    
    async def count_by_status(self, business_id: UUID) -> dict:
        """Count bookings by status for a business."""
        query = """
            SELECT status, COUNT(*) as count 
            FROM bookings 
            WHERE business_id = $1
            GROUP BY status
        """
        rows = await self.db.fetch(query, business_id)
        return {row["status"]: row["count"] for row in rows}
    
    def _build_booking_with_details(self, row: dict) -> BookingWithDetails:
        """Build BookingWithDetails from joined row."""
        from src.data.models import User, Service, Resource
        
        # Extract booking fields
        booking_data = {k: v for k, v in row.items() if not k.startswith(("user_", "service_", "resource_"))}
        
        # Build related entities
        user = None
        if row.get("user_id"):
            user = User(
                id=row["user_id"],
                business_id=row["business_id"],
                phone=row.get("user_phone", ""),
                name=row.get("user_name"),
                email=row.get("user_email"),
            )
        
        service = None
        if row.get("service_id"):
            service = Service(
                id=row["service_id"],
                business_id=row["business_id"],
                name=row.get("service_name", ""),
                duration_minutes=row.get("duration_minutes", 30),
                price=row.get("price"),
            )
        
        resource = None
        if row.get("resource_id"):
            resource = Resource(
                id=row["resource_id"],
                business_id=row["business_id"],
                name=row.get("resource_name", ""),
                type=row.get("resource_type", "staff"),
            )
        
        return BookingWithDetails(
            **booking_data,
            user=user,
            service=service,
            resource=resource,
        )

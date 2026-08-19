"""
Booking and availability routes.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.core.database import get_db
from src.booking.engine import BookingEngine
from src.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


class AvailabilityQuery(BaseModel):
    """Availability query parameters."""
    business_id: UUID
    service_id: UUID
    date: str  # YYYY-MM-DD
    preferred_time: Optional[str] = None  # HH:MM
    resource_id: Optional[UUID] = None


class CreateBookingRequest(BaseModel):
    """Create booking request body."""
    business_id: UUID
    service_id: UUID
    start_time: datetime
    customer_phone: str
    customer_name: Optional[str] = None
    customer_notes: Optional[str] = None
    resource_id: Optional[UUID] = None
    conversation_id: Optional[UUID] = None


@router.get("/availability")
async def get_availability(
    business_id: UUID = Query(...),
    service_id: UUID = Query(...),
    date: str = Query(..., regex=r"^\d{4}-\d{2}-\d{2}$"),
    preferred_time: Optional[str] = Query(None),
    resource_id: Optional[UUID] = Query(None),
):
    """
    Get available time slots for a date.
    
    Returns list of available slots with formatted times.
    """
    async with get_db() as db:
        engine = BookingEngine(db)
        
        result = await engine.check_availability(
            business_id=business_id,
            service_id=service_id,
            date_str=date,
            preferred_time=preferred_time,
            resource_id=resource_id,
        )
        
        return result


@router.post("/bookings", status_code=status.HTTP_201_CREATED)
async def create_booking(request: CreateBookingRequest):
    """
    Create a new booking.
    
    The database EXCLUDE constraint prevents double-bookings.
    """
    async with get_db() as db:
        engine = BookingEngine(db)
        
        result = await engine.create_booking(
            business_id=request.business_id,
            service_id=request.service_id,
            start_time=request.start_time,
            customer_phone=request.customer_phone,
            customer_name=request.customer_name,
            customer_notes=request.customer_notes,
            resource_id=request.resource_id,
            conversation_id=request.conversation_id,
        )
        
        if not result.get("success"):
            error_code = result.get("code", "ERROR")
            status_code = (
                status.HTTP_409_CONFLICT if error_code == "CONFLICT" 
                else status.HTTP_400_BAD_REQUEST
            )
            raise HTTPException(
                status_code=status_code,
                detail=result.get("error"),
            )
        
        return result


@router.get("/bookings/{booking_id}")
async def get_booking(booking_id: UUID):
    """Get booking details."""
    async with get_db() as db:
        from src.data.repositories.booking_repo import BookingRepository
        repo = BookingRepository(db)
        
        booking = await repo.get_by_id_with_details(booking_id)
        
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found",
            )
        
        return booking


@router.delete("/bookings/{booking_id}")
async def cancel_booking(booking_id: UUID, reason: Optional[str] = None):
    """Cancel a booking."""
    async with get_db() as db:
        engine = BookingEngine(db)
        
        result = await engine.cancel_booking(booking_id, reason)
        
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error"),
            )
        
        return {"message": "Booking cancelled", "booking_id": str(booking_id)}

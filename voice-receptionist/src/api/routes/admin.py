"""
Admin routes for booking management and approvals.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.core.database import get_db
from src.api.middleware.auth import get_current_admin, AdminUser
from src.data.repositories.booking_repo import BookingRepository
from src.data.models import BookingStatus, BookingWithDetails
from src.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


class ApprovalRequest(BaseModel):
    """Approval/rejection request."""
    notes: Optional[str] = None


class DashboardStats(BaseModel):
    """Dashboard statistics."""
    pending_approvals: int
    today_bookings: int
    total_bookings: int
    this_week_bookings: int


@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard(admin: AdminUser = Depends(get_current_admin)):
    """Get dashboard statistics."""
    async with get_db() as db:
        repo = BookingRepository(db)
        
        # Get counts
        status_counts = await repo.count_by_status(UUID(admin.business_id))
        
        # Today's bookings
        today = date.today()
        today_bookings = await repo.list_by_business(
            UUID(admin.business_id),
            start_date=today,
            end_date=today,
        )
        
        # This week
        from datetime import timedelta
        week_start = today - timedelta(days=today.weekday())
        week_bookings = await repo.list_by_business(
            UUID(admin.business_id),
            start_date=week_start,
            end_date=today + timedelta(days=6),
        )
        
        return DashboardStats(
            pending_approvals=status_counts.get("pending_approval", 0),
            today_bookings=len(today_bookings),
            total_bookings=sum(status_counts.values()),
            this_week_bookings=len(week_bookings),
        )


@router.get("/pending")
async def list_pending_approvals(admin: AdminUser = Depends(get_current_admin)):
    """List all pending approval bookings."""
    async with get_db() as db:
        repo = BookingRepository(db)
        
        bookings = await repo.list_pending(UUID(admin.business_id))
        
        return {
            "count": len(bookings),
            "bookings": bookings,
        }


@router.get("/bookings")
async def list_bookings(
    status: Optional[BookingStatus] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(get_current_admin),
):
    """List bookings with filters."""
    async with get_db() as db:
        repo = BookingRepository(db)
        
        bookings = await repo.list_by_business(
            business_id=UUID(admin.business_id),
            status=status,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
        
        return {
            "count": len(bookings),
            "bookings": bookings,
        }


@router.patch("/bookings/{booking_id}/approve")
async def approve_booking(
    booking_id: UUID,
    request: ApprovalRequest = None,
    admin: AdminUser = Depends(get_current_admin),
):
    """Approve a pending booking."""
    async with get_db() as db:
        repo = BookingRepository(db)
        
        # Verify booking exists and belongs to business
        booking = await repo.get_by_id(booking_id)
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found",
            )
        
        if str(booking.business_id) != admin.business_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        
        if booking.status != BookingStatus.PENDING_APPROVAL:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Booking is already {booking.status.value}",
            )
        
        # Approve
        updated = await repo.approve(
            booking_id=booking_id,
            admin_id=UUID(admin.id),
            notes=request.notes if request else None,
        )
        
        logger.info(
            "Booking approved",
            booking_id=str(booking_id),
            admin_id=admin.id,
        )
        
        # Notify customer of approval
        try:
            from src.notifications import NotificationManager
            notification_manager = NotificationManager(db)
            await notification_manager.notify_customer_approval(
                booking_id=booking_id,
                approved=True,
            )
        except Exception as e:
            logger.error(
                "Failed to send customer approval notification",
                error=str(e),
                booking_id=str(booking_id),
            )
        
        return {
            "message": "Booking approved",
            "booking": updated,
        }


@router.patch("/bookings/{booking_id}/reject")
async def reject_booking(
    booking_id: UUID,
    request: ApprovalRequest = None,
    admin: AdminUser = Depends(get_current_admin),
):
    """Reject/cancel a booking."""
    async with get_db() as db:
        repo = BookingRepository(db)
        
        # Verify booking exists and belongs to business
        booking = await repo.get_by_id(booking_id)
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found",
            )
        
        if str(booking.business_id) != admin.business_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        
        # Reject
        updated = await repo.reject(
            booking_id=booking_id,
            admin_id=UUID(admin.id),
            notes=request.notes if request else None,
        )
        
        logger.info(
            "Booking rejected",
            booking_id=str(booking_id),
            admin_id=admin.id,
        )
        
        # Notify customer of rejection
        try:
            from src.notifications import NotificationManager
            notification_manager = NotificationManager(db)
            await notification_manager.notify_customer_approval(
                booking_id=booking_id,
                approved=False,
            )
        except Exception as e:
            logger.error(
                "Failed to send customer rejection notification",
                error=str(e),
                booking_id=str(booking_id),
            )
        
        return {
            "message": "Booking rejected",
            "booking": updated,
        }


@router.get("/conversations")
async def list_conversations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(get_current_admin),
):
    """List conversation sessions."""
    async with get_db() as db:
        query = """
            SELECT * FROM conversation_sessions 
            WHERE business_id = $1
            ORDER BY started_at DESC
            LIMIT $2 OFFSET $3
        """
        rows = await db.fetch(query, UUID(admin.business_id), limit, offset)
        
        return {
            "count": len(rows),
            "conversations": [dict(row) for row in rows],
        }


@router.get("/conversations/{session_id}/transcript")
async def get_conversation_transcript(
    session_id: UUID,
    admin: AdminUser = Depends(get_current_admin),
):
    """Get full conversation transcript."""
    async with get_db() as db:
        from src.data.repositories.session_repo import SessionRepository
        repo = SessionRepository(db)
        
        session = await repo.get_with_turns(session_id)
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        
        if str(session.business_id) != admin.business_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        
        return session

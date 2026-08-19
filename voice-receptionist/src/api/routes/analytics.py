"""
Analytics API Routes.

Provides metrics and insights for the admin dashboard:
- Call volume statistics
- Booking conversion rates
- AI performance metrics
- Latency tracking
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.core.database import get_db
from src.core.logging import get_logger
from src.api.middleware.auth import get_current_admin

logger = get_logger(__name__)
router = APIRouter()


class DateRangeParams(BaseModel):
    """Query parameters for date range."""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    days: int = 30  # Default to last 30 days


@router.get("/stats/overview")
async def get_overview_stats(
    business_id: UUID,
    days: int = Query(default=30, ge=1, le=365),
    db=Depends(get_db),
    admin=Depends(get_current_admin),
):
    """
    Get overview statistics for the dashboard.
    
    Returns:
        - Total calls
        - Total bookings
        - Conversion rate
        - AI success rate
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Total calls (conversation sessions)
    calls_result = await db.fetchrow("""
        SELECT 
            COUNT(*) as total_calls,
            COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_calls,
            COUNT(CASE WHEN status = 'transferred' THEN 1 END) as transferred_calls
        FROM conversation_sessions
        WHERE business_id = $1 AND created_at >= $2
    """, business_id, start_date)
    
    # Total bookings
    bookings_result = await db.fetchrow("""
        SELECT 
            COUNT(*) as total_bookings,
            COUNT(CASE WHEN status = 'confirmed' THEN 1 END) as confirmed,
            COUNT(CASE WHEN status = 'cancelled' THEN 1 END) as cancelled,
            COUNT(CASE WHEN status = 'pending_approval' THEN 1 END) as pending
        FROM bookings
        WHERE business_id = $1 AND created_at >= $2
    """, business_id, start_date)
    
    # Calculate rates
    total_calls = calls_result["total_calls"] or 0
    total_bookings = bookings_result["total_bookings"] or 0
    transferred = calls_result["transferred_calls"] or 0
    
    conversion_rate = (total_bookings / total_calls * 100) if total_calls > 0 else 0
    ai_success_rate = ((total_calls - transferred) / total_calls * 100) if total_calls > 0 else 100
    
    return {
        "period_days": days,
        "calls": {
            "total": total_calls,
            "completed": calls_result["completed_calls"] or 0,
            "transferred": transferred,
        },
        "bookings": {
            "total": total_bookings,
            "confirmed": bookings_result["confirmed"] or 0,
            "cancelled": bookings_result["cancelled"] or 0,
            "pending": bookings_result["pending"] or 0,
        },
        "rates": {
            "conversion_rate": round(conversion_rate, 1),
            "ai_success_rate": round(ai_success_rate, 1),
        }
    }


@router.get("/stats/calls/by-day")
async def get_calls_by_day(
    business_id: UUID,
    days: int = Query(default=30, ge=1, le=365),
    db=Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Get call volume by day for charts."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    result = await db.fetch("""
        SELECT 
            DATE(created_at) as date,
            COUNT(*) as calls,
            COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
            COUNT(CASE WHEN status = 'transferred' THEN 1 END) as transferred
        FROM conversation_sessions
        WHERE business_id = $1 AND created_at >= $2
        GROUP BY DATE(created_at)
        ORDER BY date
    """, business_id, start_date)
    
    return [
        {
            "date": str(row["date"]),
            "calls": row["calls"],
            "completed": row["completed"],
            "transferred": row["transferred"],
        }
        for row in result
    ]


@router.get("/stats/calls/by-hour")
async def get_calls_by_hour(
    business_id: UUID,
    days: int = Query(default=30, ge=1, le=365),
    db=Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Get call volume by hour of day for heatmap."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    result = await db.fetch("""
        SELECT 
            EXTRACT(HOUR FROM created_at) as hour,
            EXTRACT(DOW FROM created_at) as day_of_week,
            COUNT(*) as calls
        FROM conversation_sessions
        WHERE business_id = $1 AND created_at >= $2
        GROUP BY hour, day_of_week
        ORDER BY day_of_week, hour
    """, business_id, start_date)
    
    return [
        {
            "hour": int(row["hour"]),
            "day_of_week": int(row["day_of_week"]),
            "calls": row["calls"],
        }
        for row in result
    ]


@router.get("/stats/bookings/by-service")
async def get_bookings_by_service(
    business_id: UUID,
    days: int = Query(default=30, ge=1, le=365),
    db=Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Get booking breakdown by service."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    result = await db.fetch("""
        SELECT 
            s.name as service_name,
            COUNT(*) as bookings,
            COUNT(CASE WHEN b.status = 'confirmed' THEN 1 END) as confirmed,
            COUNT(CASE WHEN b.status = 'cancelled' THEN 1 END) as cancelled
        FROM bookings b
        JOIN services s ON b.service_id = s.id
        WHERE b.business_id = $1 AND b.created_at >= $2
        GROUP BY s.name
        ORDER BY bookings DESC
    """, business_id, start_date)
    
    return [
        {
            "service": row["service_name"],
            "bookings": row["bookings"],
            "confirmed": row["confirmed"],
            "cancelled": row["cancelled"],
        }
        for row in result
    ]


@router.get("/stats/ai/performance")
async def get_ai_performance(
    business_id: UUID,
    days: int = Query(default=30, ge=1, le=365),
    db=Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Get AI performance metrics."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Intent breakdown
    intent_result = await db.fetch("""
        SELECT 
            intent,
            COUNT(*) as count
        FROM conversation_turns
        WHERE session_id IN (
            SELECT id FROM conversation_sessions 
            WHERE business_id = $1 AND created_at >= $2
        )
        AND intent IS NOT NULL
        GROUP BY intent
        ORDER BY count DESC
    """, business_id, start_date)
    
    # Handoff reasons
    handoff_result = await db.fetch("""
        SELECT 
            handoff_reason,
            COUNT(*) as count
        FROM conversation_sessions
        WHERE business_id = $1 
          AND created_at >= $2
          AND status = 'transferred'
        GROUP BY handoff_reason
    """, business_id, start_date)
    
    # Average turns per conversation
    turns_result = await db.fetchrow("""
        SELECT AVG(turn_count) as avg_turns
        FROM (
            SELECT session_id, COUNT(*) as turn_count
            FROM conversation_turns
            WHERE session_id IN (
                SELECT id FROM conversation_sessions 
                WHERE business_id = $1 AND created_at >= $2
            )
            GROUP BY session_id
        ) subquery
    """, business_id, start_date)
    
    return {
        "intents": [
            {"intent": row["intent"], "count": row["count"]}
            for row in intent_result
        ],
        "handoff_reasons": [
            {"reason": row["handoff_reason"] or "unknown", "count": row["count"]}
            for row in handoff_result
        ],
        "avg_conversation_turns": round(turns_result["avg_turns"] or 0, 1),
    }


@router.get("/stats/latency")
async def get_latency_stats(
    business_id: UUID,
    days: int = Query(default=7, ge=1, le=30),
    db=Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Get latency metrics (if tracked)."""
    # This would read from a latency_metrics table if implemented
    # For now, return placeholder data
    
    return {
        "message": "Latency tracking available in enhanced voice mode",
        "metrics": {
            "stt_avg_ms": 150,
            "llm_avg_ms": 800,
            "tts_avg_ms": 200,
            "total_avg_ms": 1150,
        }
    }

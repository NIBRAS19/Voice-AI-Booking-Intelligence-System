"""
WebSocket hub for real-time admin dashboard notifications.

Enables push notifications to connected admin clients for:
- New booking requests
- Status changes
- System alerts
"""

import asyncio
from typing import Dict, Set
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from starlette.websockets import WebSocketState

from src.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections per business.
    
    Allows broadcasting events to all connected admins for a business.
    """
    
    def __init__(self):
        # business_id -> set of connected websockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, business_id: str) -> None:
        """Accept connection and register for business."""
        await websocket.accept()
        
        async with self._lock:
            if business_id not in self.active_connections:
                self.active_connections[business_id] = set()
            self.active_connections[business_id].add(websocket)
        
        logger.info(
            "WebSocket connected",
            business_id=business_id,
            total_connections=len(self.active_connections.get(business_id, [])),
        )
    
    async def disconnect(self, websocket: WebSocket, business_id: str) -> None:
        """Remove connection from business."""
        async with self._lock:
            if business_id in self.active_connections:
                self.active_connections[business_id].discard(websocket)
                if not self.active_connections[business_id]:
                    del self.active_connections[business_id]
        
        logger.info("WebSocket disconnected", business_id=business_id)
    
    async def broadcast_to_business(
        self,
        business_id: str,
        event_type: str,
        data: dict,
    ) -> int:
        """
        Broadcast event to all connected admins for a business.
        
        Args:
            business_id: Target business
            event_type: Event type (e.g., 'new_booking', 'booking_updated')
            data: Event payload
        
        Returns:
            Number of clients notified
        """
        connections = self.active_connections.get(business_id, set())
        if not connections:
            logger.debug("No active connections for business", business_id=business_id)
            return 0
        
        message = {
            "type": event_type,
            "data": data,
        }
        
        # Send to all connected clients
        disconnected = []
        sent_count = 0
        
        for websocket in connections:
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json(message)
                    sent_count += 1
            except Exception as e:
                logger.warning("Failed to send to websocket", error=str(e))
                disconnected.append(websocket)
        
        # Clean up disconnected clients
        for ws in disconnected:
            await self.disconnect(ws, business_id)
        
        logger.info(
            "Broadcast sent",
            business_id=business_id,
            event_type=event_type,
            sent_count=sent_count,
        )
        
        return sent_count


# Global connection manager instance
manager = ConnectionManager()


@router.websocket("/ws/admin/{business_id}")
async def admin_websocket(
    websocket: WebSocket,
    business_id: str,
    token: str = Query(None),
):
    """
    WebSocket endpoint for admin dashboard real-time updates.
    
    Connect to receive:
    - new_booking: When a new booking needs approval
    - booking_updated: When a booking status changes
    - notification: General admin notifications
    
    Usage:
        ws://localhost:8000/api/v1/ws/admin/{business_id}?token={jwt_token}
    """
    # TODO: Validate token (for now, accept all connections)
    # In production, verify JWT and ensure admin belongs to business
    
    await manager.connect(websocket, business_id)
    
    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "data": {"message": "Connected to admin notifications"},
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for any message (ping/pong handled automatically)
                data = await websocket.receive_text()
                
                # Handle client messages if needed
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except WebSocketDisconnect:
                break
                
    except Exception as e:
        logger.error("WebSocket error", error=str(e), business_id=business_id)
    finally:
        await manager.disconnect(websocket, business_id)


# Helper function for other modules to broadcast
async def broadcast_to_business(
    business_id: str,
    event_type: str,
    data: dict,
) -> int:
    """
    Broadcast an event to all connected admin dashboards for a business.
    
    This is the main entry point for other modules to send real-time updates.
    
    Args:
        business_id: Business ID (as string)
        event_type: Event type string
        data: Event data dict
    
    Returns:
        Number of clients that received the message
    """
    return await manager.broadcast_to_business(business_id, event_type, data)

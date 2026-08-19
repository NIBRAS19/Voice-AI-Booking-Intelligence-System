"""
Audit Logging System.

Tracks sensitive system actions for security and compliance.
Logs events like:
- User logins/failures
- Booking modifications
- Settings changes
- Data exports
"""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from src.core.logging import get_logger
from src.core.database import get_db

logger = get_logger("audit")


class AuditLogger:
    """
    Structured audit logger.
    """
    
    async def log_event(
        self,
        action: str,
        actor_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[UUID] = None,
        details: Optional[Dict[str, Any]] = None,
        status: str = "success",
        ip_address: Optional[str] = None,
    ):
        """
        Record an audit event.
        
        Args:
            action: unique action name (e.g., 'booking.approve')
            actor_id: ID of user performing action
            resource_type: Type of resource modified
            resource_id: ID of resource modified
            details: Additional context
            status: success/failure
            ip_address: Client IP
        """
        event_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "actor_id": str(actor_id) if actor_id else None,
            "resource_type": resource_type,
            "resource_id": str(resource_id) if resource_id else None,
            "details": details or {},
            "status": status,
            "ip_address": ip_address,
        }
        
        # 1. Log to structured file logging
        logger.info("AUDIT_EVENT", **event_data)
        
        # 2. Persist to database (if table exists)
        # We wrap this in try/except to avoid failing the action if audit db fails
        try:
            async with get_db() as db:
                await db.execute("""
                    INSERT INTO audit_logs (
                        action, actor_id, resource_type, 
                        resource_id, details, status, ip_address, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """, 
                    action, 
                    actor_id, 
                    resource_type, 
                    resource_id, 
                    str(details) if details else None, # Store as string/JSON
                    status, 
                    ip_address, 
                    datetime.utcnow()
                )
        except Exception as e:
            # Don't crash the app, just log the failure
            logger.error("Failed to write audit log to database", error=str(e))

# Global instance
audit = AuditLogger()

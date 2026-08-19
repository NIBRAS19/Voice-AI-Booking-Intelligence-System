"""
Business repository for database operations.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from asyncpg import Connection

from src.data.models import Business, BusinessCreate, Service, ServiceCreate, WorkingHours
from src.core.logging import get_logger

logger = get_logger(__name__)


class BusinessRepository:
    """Repository for business-related database operations."""
    
    def __init__(self, db: Connection):
        self.db = db
    
    async def create(self, business: BusinessCreate) -> Business:
        """Create a new business."""
        query = """
            INSERT INTO businesses (name, timezone, phone_number, email, settings)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
        """
        
        row = await self.db.fetchrow(
            query,
            business.name,
            business.timezone,
            business.phone_number,
            business.email,
            business.settings,
        )
        
        logger.info("Business created", business_id=str(row["id"]), name=business.name)
        return Business(**dict(row))
    
    async def get_by_id(self, business_id: UUID) -> Optional[Business]:
        """Get a business by ID."""
        query = "SELECT * FROM businesses WHERE id = $1"
        row = await self.db.fetchrow(query, business_id)
        
        if row:
            return Business(**dict(row))
        return None
    
    async def get_by_phone(self, phone: str) -> Optional[Business]:
        """Get a business by phone number."""
        query = "SELECT * FROM businesses WHERE phone_number = $1"
        row = await self.db.fetchrow(query, phone)
        
        if row:
            return Business(**dict(row))
        return None
    
    async def list_all(self, limit: int = 100) -> List[Business]:
        """List all businesses."""
        query = "SELECT * FROM businesses ORDER BY created_at DESC LIMIT $1"
        rows = await self.db.fetch(query, limit)
        return [Business(**dict(row)) for row in rows]
    
    async def update_settings(self, business_id: UUID, settings: dict) -> None:
        """Update business settings (merge with existing)."""
        query = """
            UPDATE businesses 
            SET settings = settings || $1::jsonb, updated_at = $2
            WHERE id = $3
        """
        await self.db.execute(query, settings, datetime.utcnow(), business_id)
    
    # Services
    
    async def create_service(self, service: ServiceCreate) -> Service:
        """Create a new service."""
        query = """
            INSERT INTO services 
            (business_id, name, description, duration_minutes, buffer_minutes, 
             price, is_active, requires_approval, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
        """
        
        row = await self.db.fetchrow(
            query,
            service.business_id,
            service.name,
            service.description,
            service.duration_minutes,
            service.buffer_minutes,
            service.price,
            service.is_active,
            service.requires_approval,
            service.metadata,
        )
        
        return Service(**dict(row))
    
    async def get_service(self, service_id: UUID) -> Optional[Service]:
        """Get a service by ID."""
        query = "SELECT * FROM services WHERE id = $1"
        row = await self.db.fetchrow(query, service_id)
        
        if row:
            return Service(**dict(row))
        return None
    
    async def list_services(
        self,
        business_id: UUID,
        active_only: bool = True,
    ) -> List[Service]:
        """List services for a business."""
        if active_only:
            query = "SELECT * FROM services WHERE business_id = $1 AND is_active = true ORDER BY name"
        else:
            query = "SELECT * FROM services WHERE business_id = $1 ORDER BY name"
        
        rows = await self.db.fetch(query, business_id)
        return [Service(**dict(row)) for row in rows]
    
    async def find_service_by_name(
        self,
        business_id: UUID,
        name: str,
    ) -> Optional[Service]:
        """Find a service by name (fuzzy match)."""
        query = """
            SELECT * FROM services 
            WHERE business_id = $1 AND is_active = true
            AND LOWER(name) LIKE $2
            ORDER BY name
            LIMIT 1
        """
        row = await self.db.fetchrow(query, business_id, f"%{name.lower()}%")
        
        if row:
            return Service(**dict(row))
        return None
    
    # Working Hours
    
    async def get_working_hours(
        self,
        business_id: UUID,
        day_of_week: int,
    ) -> Optional[WorkingHours]:
        """Get working hours for a specific day."""
        query = """
            SELECT * FROM working_hours 
            WHERE business_id = $1 AND day_of_week = $2 AND is_active = true
            LIMIT 1
        """
        row = await self.db.fetchrow(query, business_id, day_of_week)
        
        if row:
            return WorkingHours(**dict(row))
        return None
    
    async def list_working_hours(self, business_id: UUID) -> List[WorkingHours]:
        """List all working hours for a business."""
        query = """
            SELECT * FROM working_hours 
            WHERE business_id = $1 AND is_active = true
            ORDER BY day_of_week
        """
        rows = await self.db.fetch(query, business_id)
        return [WorkingHours(**dict(row)) for row in rows]

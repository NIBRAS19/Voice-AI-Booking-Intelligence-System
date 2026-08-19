"""
User repository for database operations.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from asyncpg import Connection

from src.data.models import User, UserCreate
from src.core.logging import get_logger

logger = get_logger(__name__)


class UserRepository:
    """Repository for user-related database operations."""
    
    def __init__(self, db: Connection):
        self.db = db
    
    async def create(self, user: UserCreate) -> User:
        """Create a new user."""
        query = """
            INSERT INTO users (business_id, phone, email, name, preferred_contact, metadata)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
        """
        
        row = await self.db.fetchrow(
            query,
            user.business_id,
            user.phone,
            user.email,
            user.name,
            user.preferred_contact,
            user.metadata,
        )
        
        logger.info("User created", user_id=str(row["id"]), phone=user.phone)
        return User(**dict(row))
    
    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        """Get a user by ID."""
        query = "SELECT * FROM users WHERE id = $1"
        row = await self.db.fetchrow(query, user_id)
        
        if row:
            return User(**dict(row))
        return None
    
    async def get_by_phone(self, business_id: UUID, phone: str) -> Optional[User]:
        """Get a user by phone number within a business."""
        query = "SELECT * FROM users WHERE business_id = $1 AND phone = $2"
        row = await self.db.fetchrow(query, business_id, phone)
        
        if row:
            return User(**dict(row))
        return None
    
    async def get_or_create_by_phone(
        self,
        business_id: UUID,
        phone: str,
        name: Optional[str] = None,
    ) -> User:
        """Get existing user or create new one by phone."""
        # Try to find existing
        existing = await self.get_by_phone(business_id, phone)
        if existing:
            # Update name if provided and different
            if name and name != existing.name:
                await self.update_name(existing.id, name)
                existing.name = name
            return existing
        
        # Create new
        user_create = UserCreate(
            business_id=business_id,
            phone=phone,
            name=name,
        )
        return await self.create(user_create)
    
    async def update_name(self, user_id: UUID, name: str) -> None:
        """Update user's name."""
        query = "UPDATE users SET name = $1, updated_at = $2 WHERE id = $3"
        await self.db.execute(query, name, datetime.utcnow(), user_id)
    
    async def update_contact_preference(self, user_id: UUID, preference: str) -> None:
        """Update user's preferred contact method."""
        query = "UPDATE users SET preferred_contact = $1, updated_at = $2 WHERE id = $3"
        await self.db.execute(query, preference, datetime.utcnow(), user_id)

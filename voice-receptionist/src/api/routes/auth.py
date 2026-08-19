"""
Authentication routes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from src.core.database import get_db
from src.core.security import (
    verify_password, get_password_hash, create_token_pair, 
    validate_refresh_token, TokenPair
)
from src.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


class LoginRequest(BaseModel):
    """Login request body."""
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    """Register request body."""
    email: EmailStr
    password: str
    name: str
    business_id: str


class RefreshRequest(BaseModel):
    """Token refresh request."""
    refresh_token: str


@router.post("/login", response_model=TokenPair)
async def login(request: LoginRequest):
    """
    Authenticate admin user and return tokens.
    """
    async with get_db() as db:
        # Find user by email
        user = await db.fetchrow(
            "SELECT * FROM admin_users WHERE email = $1 AND is_active = true",
            request.email,
        )
        
        if not user:
            logger.warning("Login failed - user not found", email=request.email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        
        # Verify password
        if not verify_password(request.password, user["password_hash"]):
            logger.warning("Login failed - wrong password", email=request.email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        
        # Create tokens
        tokens = create_token_pair(
            user_id=str(user["id"]),
            business_id=str(user["business_id"]),
            role=user["role"],
        )
        
        logger.info("Login successful", user_id=str(user["id"]))
        return tokens


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(request: RefreshRequest):
    """
    Refresh access token using refresh token.
    """
    token_data = validate_refresh_token(request.refresh_token)
    
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    
    # Verify user still exists and is active
    async with get_db() as db:
        user = await db.fetchrow(
            "SELECT id, business_id, role FROM admin_users WHERE id = $1 AND is_active = true",
            token_data.sub,
        )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User no longer active",
            )
    
    # Create new tokens
    tokens = create_token_pair(
        user_id=str(user["id"]),
        business_id=str(user["business_id"]),
        role=user["role"],
    )
    
    return tokens


@router.post("/logout")
async def logout():
    """
    Logout (client-side token invalidation).
    In a production system, add token to blacklist.
    """
    return {"message": "Logged out successfully"}

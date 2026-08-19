"""
Security utilities for authentication, authorization, and encryption.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
import bcrypt
from pydantic import BaseModel

from src.core.config import settings


class TokenData(BaseModel):
    """JWT token payload data."""
    sub: str  # Subject (user ID)
    exp: datetime
    type: str  # "access" or "refresh"
    business_id: Optional[str] = None
    role: Optional[str] = None


class TokenPair(BaseModel):
    """Access and refresh token pair."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


def verify_password(plain_password: str, hashed_password: str) -> bool:

    """Verify a plain password against its hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Hash a password for storage."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')



def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Token payload (should include 'sub' for user ID)
        expires_delta: Optional custom expiry time
    
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )
    
    to_encode.update({
        "exp": expire,
        "type": "access",
        "iat": datetime.now(timezone.utc),
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )
    
    return encoded_jwt


def create_refresh_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT refresh token.
    
    Args:
        data: Token payload (should include 'sub' for user ID)
        expires_delta: Optional custom expiry time
    
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.jwt_refresh_token_expire_days
        )
    
    to_encode.update({
        "exp": expire,
        "type": "refresh",
        "iat": datetime.now(timezone.utc),
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )
    
    return encoded_jwt


def create_token_pair(user_id: str, business_id: Optional[str] = None, role: Optional[str] = None) -> TokenPair:
    """
    Create both access and refresh tokens for a user.
    
    Args:
        user_id: User's unique identifier
        business_id: Optional business context
        role: User's role (admin, manager, staff)
    
    Returns:
        TokenPair with both tokens
    """
    token_data = {
        "sub": user_id,
        "business_id": business_id,
        "role": role,
    }
    
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


def decode_token(token: str) -> Optional[TokenData]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: Encoded JWT token
    
    Returns:
        TokenData if valid, None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        
        return TokenData(
            sub=payload.get("sub"),
            exp=datetime.fromtimestamp(payload.get("exp"), tz=timezone.utc),
            type=payload.get("type", "access"),
            business_id=payload.get("business_id"),
            role=payload.get("role"),
        )
    except JWTError:
        return None


def is_token_expired(token: str) -> bool:
    """Check if a token is expired."""
    token_data = decode_token(token)
    if token_data is None:
        return True
    return token_data.exp < datetime.now(timezone.utc)


def validate_access_token(token: str) -> Optional[TokenData]:
    """
    Validate an access token.
    
    Args:
        token: Encoded JWT token
    
    Returns:
        TokenData if valid access token, None otherwise
    """
    token_data = decode_token(token)
    
    if token_data is None:
        return None
    
    if token_data.type != "access":
        return None
    
    if token_data.exp < datetime.now(timezone.utc):
        return None
    
    return token_data


def validate_refresh_token(token: str) -> Optional[TokenData]:
    """
    Validate a refresh token.
    
    Args:
        token: Encoded JWT token
    
    Returns:
        TokenData if valid refresh token, None otherwise
    """
    token_data = decode_token(token)
    
    if token_data is None:
        return None
    
    if token_data.type != "refresh":
        return None
    
    if token_data.exp < datetime.now(timezone.utc):
        return None
    
    return token_data


# Role-based access control helpers
class Roles:
    """Role constants for RBAC."""
    OWNER = "owner"
    MANAGER = "manager"
    STAFF = "staff"
    
    # Role hierarchy (higher index = more permissions)
    HIERARCHY = [STAFF, MANAGER, OWNER]


def has_permission(user_role: str, required_role: str) -> bool:
    """
    Check if a user role has sufficient permissions.
    
    Args:
        user_role: The user's current role
        required_role: The minimum required role
    
    Returns:
        True if user has permission
    """
    if user_role not in Roles.HIERARCHY:
        return False
    if required_role not in Roles.HIERARCHY:
        return False
    
    user_level = Roles.HIERARCHY.index(user_role)
    required_level = Roles.HIERARCHY.index(required_role)
    
    return user_level >= required_level

"""
Authentication middleware.
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from src.core.security import validate_access_token, TokenData

security = HTTPBearer()


class AdminUser(BaseModel):
    """Authenticated admin user context."""
    id: str
    business_id: str
    role: str


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AdminUser:
    """
    Dependency to get the current authenticated admin user.
    
    Usage:
        @router.get("/protected")
        async def protected_route(admin: AdminUser = Depends(get_current_admin)):
            ...
    """
    token = credentials.credentials
    
    token_data = validate_access_token(token)
    
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return AdminUser(
        id=token_data.sub,
        business_id=token_data.business_id,
        role=token_data.role,
    )


def require_role(required_role: str):
    """
    Dependency factory for role-based access control.
    
    Usage:
        @router.delete("/sensitive")
        async def delete_thing(admin: AdminUser = Depends(require_role("owner"))):
            ...
    """
    async def role_checker(
        admin: AdminUser = Depends(get_current_admin),
    ) -> AdminUser:
        from src.core.security import has_permission
        
        if not has_permission(admin.role, required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {required_role} role or higher",
            )
        
        return admin
    
    return role_checker

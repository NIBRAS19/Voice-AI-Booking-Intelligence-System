"""
Health check endpoints.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any

from src.core.database import get_pool
from src.core.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic health check endpoint."""
    return HealthResponse(
        status="ok",
        version="1.0.0",
        environment=settings.app_env,
    )


@router.get("/health/detailed")
async def detailed_health_check() -> Dict[str, Any]:
    """
    Comprehensive health check for all system components.
    
    Checks:
    - Database (PostgreSQL)
    - Redis
    - Twilio API
    - Deepgram STT
    - Cartesia TTS
    - Ollama LLM
    """
    import aiohttp
    
    checks = {}
    
    # Database
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
            checks["database"] = {"status": "healthy"}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}
    
    # Redis
    if settings.redis_url:
        try:
            import redis.asyncio as redis
            r = redis.from_url(settings.redis_url)
            await r.ping()
            await r.close()
            checks["redis"] = {"status": "healthy"}
        except Exception as e:
            checks["redis"] = {"status": "unhealthy", "error": str(e)}
    else:
        checks["redis"] = {"status": "not_configured"}
    
    # Twilio
    if settings.twilio_account_sid and settings.twilio_auth_token:
        try:
            async with aiohttp.ClientSession() as session:
                auth = aiohttp.BasicAuth(settings.twilio_account_sid, settings.twilio_auth_token)
                url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}.json"
                async with session.get(url, auth=auth, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    checks["twilio"] = {"status": "healthy" if resp.status == 200 else "unhealthy"}
        except Exception as e:
            checks["twilio"] = {"status": "unhealthy", "error": str(e)}
    else:
        checks["twilio"] = {"status": "not_configured"}
    
    # Deepgram
    if settings.deepgram_api_key:
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Token {settings.deepgram_api_key}"}
                async with session.get("https://api.deepgram.com/v1/projects", headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    checks["deepgram"] = {"status": "healthy" if resp.status == 200 else "unhealthy"}
        except Exception as e:
            checks["deepgram"] = {"status": "unhealthy", "error": str(e)}
    else:
        checks["deepgram"] = {"status": "not_configured"}
    
    # Cartesia
    if settings.cartesia_api_key:
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"X-API-Key": settings.cartesia_api_key}
                async with session.get("https://api.cartesia.ai/voices", headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    checks["cartesia"] = {"status": "healthy" if resp.status == 200 else "unhealthy"}
        except Exception as e:
            checks["cartesia"] = {"status": "unhealthy", "error": str(e)}
    else:
        checks["cartesia"] = {"status": "not_configured"}
    
    # Ollama
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{settings.ollama_host}/api/tags", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m["name"] for m in data.get("models", [])][:3]
                    checks["ollama"] = {"status": "healthy", "models": models}
                else:
                    checks["ollama"] = {"status": "unhealthy"}
    except Exception:
        checks["ollama"] = {"status": "not_configured"}
    
    # Overall status
    all_healthy = all(
        c.get("status") in ["healthy", "not_configured"] 
        for c in checks.values()
    )
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "version": "1.0.0",
        "environment": settings.app_env,
        "checks": checks,
    }


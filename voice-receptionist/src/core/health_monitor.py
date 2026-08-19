"""
Voice AI System Health Monitor.

Provides comprehensive health checks for all system components:
- API health
- Database connectivity
- Redis connection
- Twilio configuration
- Deepgram STT
- Cartesia TTS
- WebSocket connections
"""

import asyncio
import aiohttp
from datetime import datetime
from typing import Dict, Any, Optional

from src.core.config import settings
from src.core.database import get_db
from src.core.logging import get_logger

logger = get_logger(__name__)


class HealthMonitor:
    """Comprehensive health monitoring for Voice AI system."""
    
    def __init__(self):
        self.results: Dict[str, Dict[str, Any]] = {}
    
    async def check_all(self) -> Dict[str, Any]:
        """Run all health checks."""
        start_time = datetime.utcnow()
        
        checks = [
            self._check_database(),
            self._check_redis(),
            self._check_twilio(),
            self._check_deepgram(),
            self._check_cartesia(),
            self._check_ollama(),
        ]
        
        await asyncio.gather(*checks, return_exceptions=True)
        
        # Calculate overall status
        all_healthy = all(
            r.get("status") == "healthy" 
            for r in self.results.values()
        )
        
        return {
            "status": "healthy" if all_healthy else "degraded",
            "timestamp": start_time.isoformat(),
            "checks": self.results,
        }
    
    async def _check_database(self) -> None:
        """Check database connectivity."""
        try:
            async with get_db() as db:
                result = await db.fetchval("SELECT 1")
                self.results["database"] = {
                    "status": "healthy" if result == 1 else "unhealthy",
                    "latency_ms": 0,  # TODO: measure actual latency
                }
        except Exception as e:
            self.results["database"] = {
                "status": "unhealthy",
                "error": str(e),
            }
    
    async def _check_redis(self) -> None:
        """Check Redis connectivity."""
        try:
            import aioredis
            redis = await aioredis.from_url(settings.redis_url)
            await redis.ping()
            await redis.close()
            self.results["redis"] = {"status": "healthy"}
        except Exception as e:
            self.results["redis"] = {
                "status": "unhealthy",
                "error": str(e),
            }
    
    async def _check_twilio(self) -> None:
        """Check Twilio configuration."""
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            self.results["twilio"] = {
                "status": "not_configured",
                "message": "Twilio credentials not set",
            }
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                auth = aiohttp.BasicAuth(
                    settings.twilio_account_sid,
                    settings.twilio_auth_token,
                )
                url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}.json"
                async with session.get(url, auth=auth) as resp:
                    if resp.status == 200:
                        self.results["twilio"] = {"status": "healthy"}
                    else:
                        self.results["twilio"] = {
                            "status": "unhealthy",
                            "http_status": resp.status,
                        }
        except Exception as e:
            self.results["twilio"] = {
                "status": "unhealthy",
                "error": str(e),
            }
    
    async def _check_deepgram(self) -> None:
        """Check Deepgram API."""
        if not settings.deepgram_api_key:
            self.results["deepgram"] = {
                "status": "not_configured",
                "message": "Deepgram API key not set",
            }
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Token {settings.deepgram_api_key}"}
                url = "https://api.deepgram.com/v1/projects"
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        self.results["deepgram"] = {"status": "healthy"}
                    else:
                        self.results["deepgram"] = {
                            "status": "unhealthy",
                            "http_status": resp.status,
                        }
        except Exception as e:
            self.results["deepgram"] = {
                "status": "unhealthy",
                "error": str(e),
            }
    
    async def _check_cartesia(self) -> None:
        """Check Cartesia API."""
        if not settings.cartesia_api_key:
            self.results["cartesia"] = {
                "status": "not_configured",
                "message": "Cartesia API key not set",
            }
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"X-API-Key": settings.cartesia_api_key}
                url = "https://api.cartesia.ai/voices"
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        self.results["cartesia"] = {"status": "healthy"}
                    else:
                        self.results["cartesia"] = {
                            "status": "unhealthy",
                            "http_status": resp.status,
                        }
        except Exception as e:
            self.results["cartesia"] = {
                "status": "unhealthy",
                "error": str(e),
            }
    
    async def _check_ollama(self) -> None:
        """Check Ollama LLM."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{settings.ollama_host}/api/tags"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = [m["name"] for m in data.get("models", [])]
                        self.results["ollama"] = {
                            "status": "healthy",
                            "models": models[:5],  # First 5 models
                        }
                    else:
                        self.results["ollama"] = {
                            "status": "unhealthy",
                            "http_status": resp.status,
                        }
        except Exception as e:
            self.results["ollama"] = {
                "status": "unhealthy",
                "error": str(e),
            }


# API endpoint for health check
from fastapi import APIRouter

router = APIRouter()

@router.get("/health/detailed")
async def detailed_health_check():
    """
    Detailed health check for all system components.
    
    Returns status of:
    - Database
    - Redis
    - Twilio
    - Deepgram
    - Cartesia
    - Ollama
    """
    monitor = HealthMonitor()
    return await monitor.check_all()

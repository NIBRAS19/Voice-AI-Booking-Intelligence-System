"""
FastAPI main application.
Entry point for the Voice Receptionist API.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time

from src.core.config import settings
from src.core.database import init_db, close_pool
from src.core.logging import get_logger, log_request
from src.api.middleware.rate_limit import RateLimitMiddleware

# Import routers
from src.api.routes import auth, bookings, admin, calls, health

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager."""
    import asyncio
    
    # Startup
    logger.info("Starting Voice Receptionist API", env=settings.app_env)
    await init_db()
    
    # Start background tasks
    background_tasks = []
    
    # Appointment reminder service
    try:
        from src.notifications.reminder_service import reminder_background_task
        reminder_task = asyncio.create_task(reminder_background_task())
        background_tasks.append(reminder_task)
        logger.info("Appointment reminder service started")
    except ImportError as e:
        logger.warning("Reminder service not available", error=str(e))
    
    yield
    
    # Shutdown
    logger.info("Shutting down Voice Receptionist API")
    
    # Cancel background tasks
    for task in background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    await close_pool()


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="AI-Powered Virtual Receptionist System",
    version="1.0.0",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting middleware
app.add_middleware(RateLimitMiddleware)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    start_time = time.time()
    
    response = await call_next(request)
    
    duration_ms = (time.time() - start_time) * 1000
    
    log_request(
        logger,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    
    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    logger.error(
        "Unhandled exception",
        path=request.url.path,
        error=str(exc),
    )
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(bookings.router, prefix="/api/v1", tags=["Bookings"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(calls.router, prefix="/api/v1/calls", tags=["Calls"])

# Import simulation router here to avoid circular imports if any
from src.api.routes import simulation
app.include_router(simulation.router, prefix="/api/v1/voice", tags=["Simulation"])

# WebSocket for real-time notifications
from src.api.routes import websocket
app.include_router(websocket.router, prefix="/api/v1", tags=["WebSocket"])

# Twilio voice pipeline
from src.voice.twilio_handler import router as twilio_voice_router
app.include_router(twilio_voice_router, prefix="/api/v1/voice", tags=["Voice Pipeline"])

# Enhanced voice pipeline (barge-in, handoff)
from src.voice.enhanced_handler import router as enhanced_voice_router
app.include_router(enhanced_voice_router, prefix="/api/v1/voice", tags=["Voice Enhanced"])

# Analytics dashboard
from src.api.routes import analytics
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["Analytics"])


# Root endpoint
@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "status": "running",
    }

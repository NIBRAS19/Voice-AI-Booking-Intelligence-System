"""
Application configuration using Pydantic Settings.
All settings are loaded from environment variables with sensible defaults.
"""

from functools import lru_cache
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # ============================================
    # APPLICATION
    # ============================================
    app_env: str = Field(default="development", description="Environment: development, staging, production")
    app_debug: bool = Field(default=True, description="Enable debug mode")
    app_name: str = Field(default="Voice Receptionist", description="Application name")
    app_secret_key: str = Field(default="change-me-in-production", description="Secret key for encryption")
    
    # ============================================
    # DATABASE
    # ============================================
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/voice_receptionist",
        description="PostgreSQL connection URL"
    )
    database_pool_size: int = Field(default=10, description="Connection pool size")
    database_max_overflow: int = Field(default=5, description="Max overflow connections")
    
    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    
    # ============================================
    # VOICE AI SERVICES
    # ============================================
    # Whisper (STT) - Local fallback
    whisper_model: str = Field(default="medium", description="Whisper model size")
    whisper_device: str = Field(default="cpu", description="Device: cpu or cuda")
    
    # Deepgram (STT) - Cloud streaming
    deepgram_api_key: Optional[str] = Field(default=None, description="Deepgram API key")
    deepgram_model: str = Field(default="nova-2", description="Deepgram model")
    
    # Ollama (LLM)
    ollama_host: str = Field(default="http://localhost:11434", description="Ollama API host")
    ollama_model: str = Field(default="mistral:7b-instruct", description="Ollama model name")
    
    # Piper (TTS) - Local fallback
    piper_voice: str = Field(default="en_US-lessac-medium", description="Piper voice model")
    piper_speed: float = Field(default=1.0, description="Speech speed multiplier")
    
    # Cartesia (TTS) - Cloud streaming
    cartesia_api_key: Optional[str] = Field(default=None, description="Cartesia API key")
    cartesia_voice_id: Optional[str] = Field(default=None, description="Cartesia voice ID")
    
    # ============================================
    # TELEPHONY
    # ============================================
    # Asterisk
    asterisk_host: str = Field(default="localhost", description="Asterisk AMI host")
    asterisk_ami_port: int = Field(default=5038, description="Asterisk AMI port")
    asterisk_ami_user: str = Field(default="voice_ai", description="Asterisk AMI username")
    asterisk_ami_secret: str = Field(default="", description="Asterisk AMI secret")
    
    # Twilio (alternative)
    twilio_account_sid: Optional[str] = Field(default=None, description="Twilio Account SID")
    twilio_auth_token: Optional[str] = Field(default=None, description="Twilio Auth Token")
    twilio_phone_number: Optional[str] = Field(default=None, description="Twilio phone number")
    
    # SIP Trunk
    sip_trunk_host: Optional[str] = Field(default=None, description="SIP trunk host")
    sip_trunk_user: Optional[str] = Field(default=None, description="SIP trunk username")
    sip_trunk_pass: Optional[str] = Field(default=None, description="SIP trunk password")
    
    # ============================================
    # NOTIFICATIONS
    # ============================================
    sms_enabled: bool = Field(default=True, description="Enable SMS notifications")
    sms_provider: str = Field(default="twilio", description="SMS provider")
    
    email_enabled: bool = Field(default=True, description="Enable email notifications")
    smtp_host: str = Field(default="smtp.gmail.com", description="SMTP server host")
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_user: Optional[str] = Field(default=None, description="SMTP username")
    smtp_pass: Optional[str] = Field(default=None, description="SMTP password")
    email_from: str = Field(default="noreply@example.com", description="From email address")
    
    whatsapp_enabled: bool = Field(default=False, description="Enable WhatsApp notifications")
    whatsapp_api_url: Optional[str] = Field(default=None, description="WhatsApp API URL")
    whatsapp_api_token: Optional[str] = Field(default=None, description="WhatsApp API token")
    
    # ============================================
    # SECURITY
    # ============================================
    jwt_secret_key: str = Field(default="jwt-secret-change-me", description="JWT signing key")
    jwt_access_token_expire_minutes: int = Field(default=15, description="Access token expiry")
    jwt_refresh_token_expire_days: int = Field(default=7, description="Refresh token expiry")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="Allowed CORS origins"
    )
    rate_limit_per_minute: int = Field(default=60, description="Rate limit per minute")
    
    # ============================================
    # LOGGING
    # ============================================
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format: json or text")
    
    # ============================================
    # BUSINESS DEFAULTS
    # ============================================
    default_timezone: str = Field(default="UTC", description="Default timezone")
    default_language: str = Field(default="en", description="Default language")
    call_recording_enabled: bool = Field(default=True, description="Enable call recording")
    recording_retention_days: int = Field(default=30, description="Recording retention period")
    
    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",")]
        return v
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env == "development"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == "production"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()

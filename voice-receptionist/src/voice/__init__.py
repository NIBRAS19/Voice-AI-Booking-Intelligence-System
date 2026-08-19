"""
Voice module initialization.
Contains STT, TTS, and telephony services.
"""

from src.voice.stt_service import STTService
from src.voice.tts_service import TTSService
from src.voice.audio_utils import AudioConverter
from src.voice.deepgram_stt import DeepgramSTTClient
from src.voice.cartesia_tts import CartesiaTTSClient
from src.voice.twilio_handler import TwilioMediaStreamHandler, router as twilio_router
from src.voice.enhanced_handler import (
    EnhancedTwilioHandler, 
    BargeInController, 
    HumanHandoffManager,
    LatencyOptimizer,
    router as enhanced_router,
)

__all__ = [
    "STTService", 
    "TTSService", 
    "AudioConverter",
    "DeepgramSTTClient",
    "CartesiaTTSClient",
    "TwilioMediaStreamHandler",
    "twilio_router",
    "EnhancedTwilioHandler",
    "BargeInController",
    "HumanHandoffManager",
    "LatencyOptimizer",
    "enhanced_router",
]


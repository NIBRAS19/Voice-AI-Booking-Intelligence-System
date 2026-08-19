Complete Voice AI + Booking Intelligence System
Production Implementation Blueprint
I'll build this as a unified system that combines the best patterns from both guides while solving the unique challenges of real-time conversational booking.

--

System Architecture Overview

┌─────────────────────────────────────────────────────────────────┐
│                        ENTRY POINTS                              │
├──────────────────┬──────────────────┬──────────────────────────┤
│  Phone (Twilio)  │  Web (WebRTC)    │  Mobile App (WebRTC)     │
│  - Inbound calls │  - Widget embed  │  - React Native          │
│  - Outbound      │  - Live chat     │  - Native voice          │
└────────┬─────────┴────────┬─────────┴────────┬─────────────────┘
         │                   │                   │
         └───────────────────┴───────────────────┘
                             │
                    WebSocket/MediaStream
                             │
┌────────────────────────────▼──────────────────────────────────┐
│              CONVERSATION ORCHESTRATOR                         │
│  (FastAPI + Python - Single Service, Multiple Workers)        │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │          CONVERSATION STATE MACHINE                      │ │
│  │  - Session management                                    │ │
│  │  - Intent tracking                                       │ │
│  │  - Slot filling state                                    │ │
│  │  - Confidence scoring                                    │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  Audio   │  │  Intent  │  │ Booking  │  │  Human   │    │
│  │ Pipeline │  │ Detection│  │ Manager  │  │ Handoff  │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└───┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬──┘
    │     │     │     │     │     │     │     │     │     │
    ▼     ▼     ▼     ▼     ▼     ▼     ▼     ▼     ▼     ▼
┌────────┐│┌────────┐│┌──────────┐│┌─────────┐│┌──────────┐
│Deepgram││ │ Groq   ││ │PostgreSQL││ │ Redis   ││ │ External │
│ (STT)  ││ │ (LLM)  ││ │ (ACID)   ││ │ (Cache) ││ │ Systems  │
│Nova-2  ││ │Llama3.1││ │ Bookings ││ │ Session ││ │          │
└────────┘│ └────────┘│ └──────────┘│ └─────────┘│ └──────────┘
┌─────────▼┐┌─────────▼┐            │            │
│Cartesia  ││ Tools:   │            │            │
│(TTS)     ││- Calendar│            │            │
│Sonic     ││- CRM     │            │            │
└──────────┘│- Booking │            │            │
            └──────────┘            │            │
                                    ▼            ▼
                            ┌──────────────────────────┐
                            │   Integration Layer      │
                            ├──────────────────────────┤
                            │ - Google Calendar API    │
                            │ - Outlook Calendar       │
                            │ - Custom Booking APIs    │
                            │ - CRM (HubSpot/SF)      │
                            │ - Twilio (SMS)          │
                            │ - Resend (Email)        │
                            └──────────────────────────┘


Core Data Model
Database Schema (PostgreSQL)

-- Users and businesses
CREATE TABLE businesses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  timezone VARCHAR(50) DEFAULT 'UTC',
  settings JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID REFERENCES businesses(id),
  email VARCHAR(255),
  phone VARCHAR(20),
  name VARCHAR(255),
  role VARCHAR(20) DEFAULT 'CUSTOMER',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Services offered
CREATE TABLE services (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID REFERENCES businesses(id),
  name VARCHAR(100) NOT NULL,
  duration_minutes INT NOT NULL,
  buffer_minutes INT DEFAULT 0,
  price DECIMAL(10,2),
  is_active BOOLEAN DEFAULT true,
  metadata JSONB DEFAULT '{}'
);

-- Working hours (supports multiple staff/resources)
CREATE TABLE working_hours (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID REFERENCES businesses(id),
  resource_id UUID, -- staff member, room, equipment
  day_of_week INT NOT NULL, -- 0=Mon, 6=Sun
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,
  is_active BOOLEAN DEFAULT true,
  CHECK (end_time > start_time)
);

-- Bookings with exclusion constraint
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE bookings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID REFERENCES businesses(id),
  user_id UUID REFERENCES users(id),
  service_id UUID REFERENCES services(id),
  resource_id UUID, -- which staff/room
  start_time TIMESTAMPTZ NOT NULL,
  end_time TIMESTAMPTZ NOT NULL,
  status VARCHAR(20) DEFAULT 'CONFIRMED',
  source VARCHAR(50), -- 'voice_ai', 'web', 'manual'
  conversation_id UUID,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  
  CHECK (end_time > start_time)
);

-- Prevent double-booking per resource
ALTER TABLE bookings 
ADD CONSTRAINT no_overlapping_bookings 
EXCLUDE USING gist (
  business_id WITH =,
  resource_id WITH =,
  tstzrange(start_time, end_time) WITH &&
) WHERE (status != 'CANCELLED');

CREATE INDEX idx_bookings_business_time ON bookings(business_id, start_time);
CREATE INDEX idx_bookings_user ON bookings(user_id);

-- Conversation sessions
CREATE TABLE conversation_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID REFERENCES businesses(id),
  user_id UUID REFERENCES users(id),
  channel VARCHAR(20), -- 'phone', 'web', 'mobile'
  phone_number VARCHAR(20),
  started_at TIMESTAMPTZ DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  status VARCHAR(20) DEFAULT 'ACTIVE',
  
  -- Conversation state
  current_intent VARCHAR(50),
  intent_confidence DECIMAL(3,2),
  slots JSONB DEFAULT '{}', -- {"date": "2024-11-15", "time": "14:00"}
  
  -- Metadata
  call_sid VARCHAR(100), -- Twilio
  duration_seconds INT,
  transferred_to_human BOOLEAN DEFAULT false,
  
  metadata JSONB DEFAULT '{}'
);

-- Conversation turns (full transcript)
CREATE TABLE conversation_turns (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID REFERENCES conversation_sessions(id),
  turn_number INT NOT NULL,
  role VARCHAR(20), -- 'user', 'assistant', 'system'
  content TEXT,
  intent VARCHAR(50),
  confidence DECIMAL(3,2),
  entities JSONB DEFAULT '{}',
  audio_duration_ms INT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_turns_session ON conversation_turns(session_id, turn_number);

-- Integration credentials (encrypted)
CREATE TABLE integrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID REFERENCES businesses(id),
  provider VARCHAR(50), -- 'google_calendar', 'outlook', 'custom_api'
  credentials JSONB, -- encrypted OAuth tokens
  settings JSONB DEFAULT '{}',
  is_active BOOLEAN DEFAULT true
); 

--                 

Conversation State Machine
Intent Taxonomy

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel

class Intent(str, Enum):
    """Primary user intents"""
    BOOK_APPOINTMENT = "book_appointment"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"
    CHECK_AVAILABILITY = "check_availability"
    ASK_INFORMATION = "ask_information"
    COMPLAINT = "complaint"
    TRANSFER_TO_HUMAN = "transfer_to_human"
    UNCLEAR = "unclear"

class ConversationState(str, Enum):
    """State machine states"""
    GREETING = "greeting"
    INTENT_DETECTION = "intent_detection"
    SLOT_FILLING = "slot_filling"
    AVAILABILITY_CHECK = "availability_check"
    CONFIRMATION = "confirmation"
    BOOKING_EXECUTION = "booking_execution"
    COMPLETION = "completion"
    HUMAN_TRANSFER = "human_transfer"
    ERROR_RECOVERY = "error_recovery"

class Slot(BaseModel):
    """Required information slots"""
    name: str
    value: Optional[str] = None
    confirmed: bool = False
    confidence: float = 0.0
    attempts: int = 0
    
class SessionContext(BaseModel):
    """Complete conversation context"""
    session_id: str
    business_id: str
    user_id: Optional[str]
    
    # State tracking
    current_state: ConversationState = ConversationState.GREETING
    current_intent: Optional[Intent] = None
    intent_confidence: float = 0.0
    
    # Slot filling
    required_slots: Dict[str, Slot] = {}
    
    # Conversation history
    turns: List[Dict] = []
    
    # Booking context
    selected_service_id: Optional[str] = None
    proposed_time: Optional[str] = None
    booking_id: Optional[str] = None
    
    # Handoff tracking
    transfer_reason: Optional[str] = None
    low_confidence_count: int = 0
    user_frustration_detected: bool = False


State Machine Logic

# app/services/conversation_manager.py
from datetime import datetime, timedelta
from typing import Optional, Tuple
import asyncio

class ConversationManager:
    """
    Manages conversation state and transitions.
    Implements slot filling, intent detection, and booking orchestration.
    """
    
    def __init__(self, session: SessionContext, db, llm, booking_engine):
        self.session = session
        self.db = db
        self.llm = llm
        self.booking_engine = booking_engine
        
        # Confidence thresholds
        self.INTENT_CONFIDENCE_THRESHOLD = 0.75
        self.SLOT_CONFIDENCE_THRESHOLD = 0.70
        self.TRANSFER_THRESHOLD = 3  # Low confidence attempts
    
    async def process_user_input(self, transcript: str) -> Tuple[str, bool]:
        """
        Main processing loop. Returns (response_text, should_continue)
        """
        # Add to history
        self.session.turns.append({
            "role": "user",
            "content": transcript,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # State-based processing
        if self.session.current_state == ConversationState.GREETING:
            return await self._handle_greeting(transcript)
        
        elif self.session.current_state == ConversationState.INTENT_DETECTION:
            return await self._handle_intent_detection(transcript)
        
        elif self.session.current_state == ConversationState.SLOT_FILLING:
            return await self._handle_slot_filling(transcript)
        
        elif self.session.current_state == ConversationState.AVAILABILITY_CHECK:
            return await self._handle_availability_check(transcript)
        
        elif self.session.current_state == ConversationState.CONFIRMATION:
            return await self._handle_confirmation(transcript)
        
        elif self.session.current_state == ConversationState.BOOKING_EXECUTION:
            return await self._handle_booking_execution(transcript)
        
        elif self.session.current_state == ConversationState.COMPLETION:
            return "Thank you! Is there anything else I can help with?", True
        
        else:
            return await self._handle_error_recovery(transcript)
    
    async def _handle_intent_detection(self, transcript: str) -> Tuple[str, bool]:
        """
        Detect user intent using LLM with structured output.
        """
        prompt = f"""Analyze this user message and determine their intent.

User message: "{transcript}"

Context: This is a booking system for {await self._get_business_name()}.

Respond with JSON:
{{
  "intent": "book_appointment|reschedule|cancel|check_availability|ask_information|complaint|transfer_to_human|unclear",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "extracted_entities": {{
    "date": "YYYY-MM-DD or null",
    "time": "HH:MM or null",
    "service": "service name or null"
  }}
}}"""
        
        result = await self.llm.get_structured_output(prompt)
        
        self.session.current_intent = Intent(result["intent"])
        self.session.intent_confidence = result["confidence"]
        
        # Low confidence handling
        if result["confidence"] < self.INTENT_CONFIDENCE_THRESHOLD:
            self.session.low_confidence_count += 1
            
            if self.session.low_confidence_count >= self.TRANSFER_THRESHOLD:
                return await self._initiate_human_transfer(
                    "Low intent confidence"
                )
            
            # Ask clarifying question
            return await self._ask_clarifying_question(transcript)
        
        # Route based on intent
        if self.session.current_intent == Intent.BOOK_APPOINTMENT:
            # Initialize required slots
            self.session.required_slots = {
                "service": Slot(name="service"),
                "date": Slot(name="date"),
                "time": Slot(name="time"),
                "name": Slot(name="name"),
                "phone": Slot(name="phone")
            }
            
            # Pre-fill from extraction
            for key, value in result["extracted_entities"].items():
                if value and key in self.session.required_slots:
                    self.session.required_slots[key].value = value
                    self.session.required_slots[key].confidence = result["confidence"]
            
            self.session.current_state = ConversationState.SLOT_FILLING
            return await self._handle_slot_filling(transcript)
        
        elif self.session.current_intent == Intent.TRANSFER_TO_HUMAN:
            return await self._initiate_human_transfer("User requested human")
        
        elif self.session.current_intent == Intent.ASK_INFORMATION:
            return await self._handle_information_request(transcript)
        
        else:
            return f"I can help with that. {await self._next_question()}", True
    
    async def _handle_slot_filling(self, transcript: str) -> Tuple[str, bool]:
        """
        Fill required slots one at a time.
        """
        # Find first unfilled slot
        unfilled_slot = None
        for slot in self.session.required_slots.values():
            if not slot.value or not slot.confirmed:
                unfilled_slot = slot
                break
        
        if not unfilled_slot:
            # All slots filled, move to availability check
            self.session.current_state = ConversationState.AVAILABILITY_CHECK
            return await self._handle_availability_check(transcript)
        
        # Extract value for current slot
        extraction_prompt = f"""Extract the {unfilled_slot.name} from this user message.

User message: "{transcript}"

Previous context: {self._get_filled_slots_summary()}

Respond with JSON:
{{
  "value": "extracted value or null",
  "confidence": 0.0-1.0,
  "needs_clarification": true/false,
  "clarification_question": "question to ask if unclear"
}}"""
        
        result = await self.llm.get_structured_output(extraction_prompt)
        
        if result["value"] and result["confidence"] > self.SLOT_CONFIDENCE_THRESHOLD:
            unfilled_slot.value = result["value"]
            unfilled_slot.confidence = result["confidence"]
            unfilled_slot.confirmed = True
            
            # Validate the value
            validation_result = await self._validate_slot(unfilled_slot)
            if not validation_result["valid"]:
                unfilled_slot.confirmed = False
                return validation_result["message"], True
            
            # Move to next slot
            return await self._ask_next_slot()
        
        else:
            # Low confidence or no value
            unfilled_slot.attempts += 1
            
            if unfilled_slot.attempts >= 3:
                return await self._initiate_human_transfer(
                    f"Unable to extract {unfilled_slot.name} after 3 attempts"
                )
            
            question = result.get("clarification_question") or \
                       await self._default_slot_question(unfilled_slot.name)
            
            return question, True
    
    async def _handle_availability_check(self, transcript: str) -> Tuple[str, bool]:
        """
        Check availability and propose options.
        """
        service_id = await self._resolve_service_id(
            self.session.required_slots["service"].value
        )
        
        requested_date = self.session.required_slots["date"].value
        requested_time = self.session.required_slots.get("time", Slot(name="time")).value
        
        # Query availability
        available_slots = await self.booking_engine.get_available_slots(
            business_id=self.session.business_id,
            service_id=service_id,
            date=requested_date,
            preferred_time=requested_time
        )
        
        if not available_slots:
            # No availability - offer alternatives
            alternative_dates = await self.booking_engine.suggest_alternative_dates(
                business_id=self.session.business_id,
                service_id=service_id,
                start_date=requested_date
            )
            
            response = f"I'm sorry, we don't have availability on {requested_date}"
            if requested_time:
                response += f" at {requested_time}"
            
            response += ". "
            
            if alternative_dates:
                response += f"We do have openings on {', '.join(alternative_dates[:3])}. Would any of those work?"
                self.session.current_state = ConversationState.SLOT_FILLING
                # Need to re-fill date slot
                self.session.required_slots["date"].confirmed = False
            else:
                response += "Would you like me to transfer you to our scheduling team?"
                self.session.current_state = ConversationState.HUMAN_TRANSFER
            
            return response, True
        
        # Found availability
        best_slot = available_slots[0]  # Closest to requested time
        
        self.session.proposed_time = best_slot["start"]
        self.session.selected_service_id = service_id
        
        # Format confirmation
        formatted_time = self._format_time(best_slot["start"])
        service_name = await self._get_service_name(service_id)
        
        response = f"Great! I can book you for {service_name} on {formatted_time}. "
        response += f"Can I confirm your name is {self.session.required_slots['name'].value} "
        response += f"and your phone number is {self.session.required_slots['phone'].value}?"
        
        self.session.current_state = ConversationState.CONFIRMATION
        return response, True
    
    async def _handle_confirmation(self, transcript: str) -> Tuple[str, bool]:
        """
        Get explicit confirmation before booking.
        """
        confirmation_prompt = f"""Is the user confirming or declining the booking?

User message: "{transcript}"

Respond with JSON:
{{
  "confirmed": true/false,
  "confidence": 0.0-1.0
}}"""
        
        result = await self.llm.get_structured_output(confirmation_prompt)
        
        if result["confidence"] < 0.80:
            return "I didn't quite catch that. Should I go ahead and book this appointment for you?", True
        
        if result["confirmed"]:
            self.session.current_state = ConversationState.BOOKING_EXECUTION
            return await self._handle_booking_execution(transcript)
        else:
            # User declined
            return "No problem. Would you like to try a different time, or should I transfer you to our team?", True
    
    async def _handle_booking_execution(self, transcript: str) -> Tuple[str, bool]:
        """
        Execute the booking atomically.
        """
        try:
            # Create booking in database
            booking = await self.booking_engine.create_booking(
                business_id=self.session.business_id,
                user_id=self.session.user_id,
                service_id=self.session.selected_service_id,
                start_time=self.session.proposed_time,
                slots=self.session.required_slots,
                conversation_id=self.session.session_id
            )
            
            self.session.booking_id = booking["id"]
            
            # Trigger confirmations (async, don't wait)
            asyncio.create_task(self._send_confirmations(booking))
            
            # Success response
            response = f"Perfect! Your appointment is confirmed for {self._format_time(booking['start_time'])}. "
            response += f"You'll receive a confirmation text at {self.session.required_slots['phone'].value}. "
            response += "Is there anything else I can help you with?"
            
            self.session.current_state = ConversationState.COMPLETION
            return response, True
        
        except Exception as e:
            # Booking failed (likely double-booking race condition)
            print(f"Booking failed: {e}")
            
            response = "I apologize, but that time slot was just taken by another booking. "
            response += "Let me find you another option. One moment..."
            
            # Go back to availability check
            self.session.current_state = ConversationState.AVAILABILITY_CHECK
            self.session.proposed_time = None
            
            return response, True
    
    async def _initiate_human_transfer(self, reason: str) -> Tuple[str, bool]:
        """
        Transfer to human agent.
        """
        self.session.current_state = ConversationState.HUMAN_TRANSFER
        self.session.transfer_reason = reason
        
        # Log transfer
        await self.db.execute("""
            UPDATE conversation_sessions 
            SET transferred_to_human = true,
                metadata = metadata || $1::jsonb
            WHERE id = $2
        """, {"transfer_reason": reason}, self.session.session_id)
        
        response = "I'd like to connect you with one of our team members who can better assist you. "
        response += "Please hold for just a moment."
        
        # Return should_continue=False to trigger transfer
        return response, False
    
    # Helper methods
    
    def _get_filled_slots_summary(self) -> str:
        filled = [f"{k}: {v.value}" for k, v in self.session.required_slots.items() if v.value]
        return ", ".join(filled) if filled else "None"
    
    async def _ask_next_slot(self) -> Tuple[str, bool]:
        """Ask for the next unfilled slot."""
        for slot in self.session.required_slots.values():
            if not slot.confirmed:
                question = await self._default_slot_question(slot.name)
                return question, True
        
        # All filled
        self.session.current_state = ConversationState.AVAILABILITY_CHECK
        return "Let me check our availability...", True
    
    async def _default_slot_question(self, slot_name: str) -> str:
        questions = {
            "service": "What service would you like to book?",
            "date": "What day works best for you?",
            "time": "What time would you prefer?",
            "name": "Can I get your name?",
            "phone": "And what's the best phone number to reach you?"
        }
        return questions.get(slot_name, f"I need your {slot_name}. What is it?")
    
    async def _validate_slot(self, slot: Slot) -> dict:
        """Validate slot value."""
        if slot.name == "phone":
            # Basic phone validation
            cleaned = ''.join(c for c in slot.value if c.isdigit())
            if len(cleaned) < 10:
                return {
                    "valid": False,
                    "message": "I didn't catch a complete phone number. Can you repeat that?"
                }
            slot.value = cleaned  # Normalize
        
        elif slot.name == "date":
            # Parse and validate date
            try:
                from dateutil import parser
                parsed_date = parser.parse(slot.value)
                if parsed_date.date() < datetime.now().date():
                    return {
                        "valid": False,
                        "message": "That date is in the past. What's a future date that works?"
                    }
                slot.value = parsed_date.strftime("%Y-%m-%d")
            except:
                return {
                    "valid": False,
                    "message": "I didn't understand that date. Can you say it again?"
                }
        
        return {"valid": True}
    
    def _format_time(self, iso_timestamp: str) -> str:
        """Format timestamp for natural speech."""
        dt = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
        return dt.strftime("%A, %B %d at %I:%M %p")


Real-Time Voice Pipeline Implementation
WebSocket Handler with Barge-In

# app/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from app.services.deepgram import DeepgramService
from app.services.groq_llm import GroqLLMService
from app.services.cartesia_tts import CartesiaService
from app.services.conversation_manager import ConversationManager
from app.services.booking_engine import BookingEngine
import asyncio
import json
import base64

app = FastAPI()

# Services
deepgram = DeepgramService()
llm = GroqLLMService()
tts = CartesiaService()
booking_engine = BookingEngine()

class VoiceSession:
    def __init__(self, call_sid: str, business_id: str, db):
        self.call_sid = call_sid
        self.stream_sid = None
        self.is_ai_speaking = False
        self.speech_buffer = []
        self.current_tts_task = None
        
        # Initialize conversation manager
        from app.models.conversation import SessionContext, ConversationState
        context = SessionContext(
            session_id=call_sid,
            business_id=business_id
        )
        self.conversation_manager = ConversationManager(
            session=context,
            db=db,
            llm=llm,
            booking_engine=booking_engine
        )

@app.websocket("/ws/media")
async def voice_websocket(websocket: WebSocket):
    """
    Main WebSocket handler for voice calls.
    Handles: Phone (Twilio), Web (WebRTC), Mobile
    """
    await websocket.accept()
    
    session = None
    deepgram_conn = None
    
    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event = data.get("event")
            
            if event == "start":
                # Initialize session
                call_sid = data["start"]["callSid"]
                business_id = data["start"]["customParameters"]["business_id"]
                
                session = VoiceSession(call_sid, business_id, db=get_db())
                session.stream_sid = data["start"]["streamSid"]
                
                # Start Deepgram
                deepgram_conn = await deepgram.start_stream(
                    on_transcript=lambda text: asyncio.create_task(
                        handle_user_speech(session, text, websocket)
                    ),
                    on_speech_started=lambda: handle_speech_started(session),
                    on_speech_ended=lambda: handle_speech_ended(session)
                )
                
                # Send greeting
                greeting = await get_business_greeting(business_id)
                await speak_to_user(session, websocket, greeting)
            
            elif event == "media":
                if deepgram_conn and not session.is_ai_speaking:
                    # Forward audio to STT
                    audio = base64.b64decode(data["media"]["payload"])
                    await deepgram_conn.send(audio)
            
            elif event == "stop":
                if deepgram_conn:
                    await deepgram_conn.close()
                await finalize_session(session)
                break
    
    except WebSocketDisconnect:
        if session:
            await finalize_session(session)
    except Exception as e:
        print(f"WebSocket error: {e}")
        if session:
            await finalize_session(session)


async def handle_user_speech(session: VoiceSession, transcript: str, websocket: WebSocket):
    """
    Process user's speech through conversation manager.
    """
    if not transcript.strip():
        return
    
    print(f"[{session.call_sid}] User: {transcript}")
    
    # Cancel any ongoing TTS (barge-in)
    if session.current_tts_task and not session.current_tts_task.done():
        session.current_tts_task.cancel()
        session.is_ai_speaking = False
        await send_clear_audio(websocket, session.stream_sid)
    
    # Process through conversation manager
    try:
        response_text, should_continue = await session.conversation_manager.process_user_input(transcript)
        
        print(f"[{session.call_sid}] AI: {response_text}")
        
        if should_continue:
            # Speak response
            await speak_to_user(session, websocket, response_text)
        else:
            # Transfer to human
            await initiate_human_transfer(session, websocket)
    
    except Exception as e:
        print(f"Error processing speech: {e}")
        fallback = "I'm having trouble processing that. Let me connect you with someone who can help."
        await speak_to_user(session, websocket, fallback)
        await initiate_human_transfer(session, websocket)


async def speak_to_user(session: VoiceSession, websocket: WebSocket, text: str):
    """
    Convert text to speech and stream to user.
    """
    session.is_ai_speaking = True
    
    try:
        # Get TTS audio
        audio_data = await tts.synthesize(text)
        # Convert to mulaw and send
    mulaw_audio = convert_pcm_to_mulaw(audio_data)
    payload = base64.b64encode(mulaw_audio).decode('utf-8')
    
    await websocket.send_json({
        "event": "media",
        "streamSid": session.stream_sid,
        "media": {"payload": payload}
    })
    
    # Mark message to transcript
    await session.conversation_manager.session.turns.append({
        "role": "assistant",
        "content": text,
        "timestamp": datetime.utcnow().isoformat()
    })

finally:
    session.is_ai_speaking = False

    def handle_speech_started(session: VoiceSession):
"""Called when Deepgram detects user started speaking."""
# Could cancel TTS here for faster barge-in
pass
def handle_speech_ended(session: VoiceSession):
"""Called when Deepgram detects user stopped speaking."""
pass

---

## Booking Engine with Real Calendar Integration
```python
# app/services/booking_engine.py
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional
import asyncpg
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class BookingEngine:
    """
    Handles availability checking and booking creation.
    Integrates with external calendars and CRMs.
    """
    
    def __init__(self):
        self.slot_duration_minutes = 30  # Default granularity
    
    async def get_available_slots(
        self,
        business_id: str,
        service_id: str,
        date: str,
        preferred_time: Optional[str] = None
    ) -> List[Dict]:
        """
        Calculate available slots for a given date.
        
        Logic:
        1. Get service duration
        2. Get working hours for that day
        3. Get existing bookings (from DB + external calendars)
        4. Calculate: Working Hours - Existing Bookings - Buffer Time
        5. Return slots, sorted by proximity to preferred_time
        """
        db = await get_db_connection()
        
        # Step 1: Get service details
        service = await db.fetchrow("""
            SELECT duration_minutes, buffer_minutes
            FROM services
            WHERE id = $1 AND business_id = $2
        """, service_id, business_id)
        
        if not service:
            raise ValueError(f"Service {service_id} not found")
        
        # Step 2: Get working hours
        target_date = datetime.strptime(date, "%Y-%m-%d")
        day_of_week = target_date.weekday()
        
        working_hours = await db.fetchrow("""
            SELECT start_time, end_time
            FROM working_hours
            WHERE business_id = $1
              AND day_of_week = $2
              AND is_active = true
            LIMIT 1
        """, business_id, day_of_week)
        
        if not working_hours:
            return []  # Closed this day
        
        # Step 3: Get existing bookings
        existing_bookings = await self._get_all_bookings_for_day(
            business_id, target_date, db
        )
        
        # Step 4: Generate slots
        slots = []
        current_time = datetime.combine(target_date.date(), working_hours['start_time'])
        end_time = datetime.combine(target_date.date(), working_hours['end_time'])
        
        slot_duration = timedelta(minutes=service['duration_minutes'])
        buffer_time = timedelta(minutes=service['buffer_minutes'])
        
        while current_time + slot_duration <= end_time:
            slot_end = current_time + slot_duration + buffer_time
            
            # Check for conflicts
            is_available = True
            for booking in existing_bookings:
                if self._time_ranges_overlap(
                    current_time, slot_end,
                    booking['start_time'], booking['end_time']
                ):
                    is_available = False
                    break
            
            if is_available:
                slots.append({
                    "start": current_time.isoformat(),
                    "end": slot_end.isoformat(),
                    "duration_minutes": service['duration_minutes']
                })
            
            # Move to next slot
            current_time += timedelta(minutes=self.slot_duration_minutes)
        
        # Step 5: Sort by proximity to preferred time
        if preferred_time:
            pref_dt = datetime.combine(target_date.date(), 
                                      datetime.strptime(preferred_time, "%H:%M").time())
            slots.sort(key=lambda s: abs(
                (datetime.fromisoformat(s['start']) - pref_dt).total_seconds()
            ))
        
        return slots
    
    async def _get_all_bookings_for_day(
        self,
        business_id: str,
        date: datetime,
        db: asyncpg.Connection
    ) -> List[Dict]:
        """
        Get bookings from both database and external calendars.
        """
        # Database bookings
        db_bookings = await db.fetch("""
            SELECT start_time, end_time
            FROM bookings
            WHERE business_id = $1
              AND DATE(start_time) = $2
              AND status != 'CANCELLED'
        """, business_id, date.date())
        
        # External calendar bookings
        calendar_bookings = await self._fetch_calendar_bookings(business_id, date)
        
        # Merge
        all_bookings = [dict(b) for b in db_bookings] + calendar_bookings
        return all_bookings
    
    async def _fetch_calendar_bookings(
        self,
        business_id: str,
        date: datetime
    ) -> List[Dict]:
        """
        Fetch bookings from Google Calendar, Outlook, etc.
        """
        db = await get_db_connection()
        
        # Get integration credentials
        integration = await db.fetchrow("""
            SELECT provider, credentials
            FROM integrations
            WHERE business_id = $1
              AND provider IN ('google_calendar', 'outlook')
              AND is_active = true
        """, business_id)
        
        if not integration:
            return []
        
        if integration['provider'] == 'google_calendar':
            return await self._fetch_google_calendar_events(
                integration['credentials'],
                date
            )
        
        # Add other providers...
        return []
    
    async def _fetch_google_calendar_events(
        self,
        credentials_data: dict,
        date: datetime
    ) -> List[Dict]:
        """
        Fetch events from Google Calendar.
        """
        try:
            creds = Credentials(**credentials_data)
            service = build('calendar', 'v3', credentials=creds)
            
            time_min = datetime.combine(date.date(), time.min).isoformat() + 'Z'
            time_max = datetime.combine(date.date(), time.max).isoformat() + 'Z'
            
            events_result = service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            bookings = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                
                bookings.append({
                    "start_time": datetime.fromisoformat(start.replace('Z', '+00:00')),
                    "end_time": datetime.fromisoformat(end.replace('Z', '+00:00'))
                })
            
            return bookings
        
        except Exception as e:
            print(f"Error fetching Google Calendar: {e}")
            return []
    
    async def create_booking(
        self,
        business_id: str,
        user_id: Optional[str],
        service_id: str,
        start_time: str,
        slots: Dict,
        conversation_id: str
    ) -> Dict:
        """
        Create booking atomically with conflict detection.
        """
        db = await get_db_connection()
        
        # Get service to calculate end_time
        service = await db.fetchrow("""
            SELECT duration_minutes FROM services WHERE id = $1
        """, service_id)
        
        start_dt = datetime.fromisoformat(start_time)
        end_dt = start_dt + timedelta(minutes=service['duration_minutes'])
        
        # Create or get user
        if not user_id:
            user_id = await self._create_user_from_slots(business_id, slots, db)
        
        try:
            async with db.transaction():
                # Atomic insert with exclusion constraint
                booking = await db.fetchrow("""
                    INSERT INTO bookings (
                        business_id, user_id, service_id,
                        start_time, end_time, status,
                        source, conversation_id
                    )
                    VALUES ($1, $2, $3, $4, $5, 'CONFIRMED', 'voice_ai', $6)
                    RETURNING *
                """, business_id, user_id, service_id,
                     start_dt, end_dt, conversation_id)
                
                # Also create in external calendar
                await self._create_external_calendar_event(
                    business_id, booking, db
                )
                
                return dict(booking)
        
        except asyncpg.exceptions.ExclusionViolationError:
            # Slot was taken by another booking
            raise ValueError("Time slot no longer available")
    
    async def _create_user_from_slots(
        self,
        business_id: str,
        slots: Dict,
        db: asyncpg.Connection
    ) -> str:
        """Create user from conversation slots."""
        user = await db.fetchrow("""
            INSERT INTO users (business_id, name, phone, role)
            VALUES ($1, $2, $3, 'CUSTOMER')
            ON CONFLICT (business_id, phone) DO UPDATE
            SET name = EXCLUDED.name
            RETURNING id
        """, business_id,
             slots.get('name', {}).get('value'),
             slots.get('phone', {}).get('value'))
        
        return user['id']
    
    def _time_ranges_overlap(
        self,
        start1: datetime,
        end1: datetime,
        start2: datetime,
        end2: datetime
    ) -> bool:
        """Check if two time ranges overlap."""
        return start1 < end2 and end1 > start2
    
    async def suggest_alternative_dates(
        self,
        business_id: str,
        service_id: str,
        start_date: str,
        days_to_check: int = 7
    ) -> List[str]:
        """
        Find next available dates if requested date is full.
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        available_dates = []
        
        for i in range(1, days_to_check + 1):
            check_date = start + timedelta(days=i)
            slots = await self.get_available_slots(
                business_id, service_id, check_date.strftime("%Y-%m-%d")
            )
            
            if slots:
                available_dates.append(check_date.strftime("%A, %B %d"))
                if len(available_dates) >= 3:
                    break
        
        return available_dates
```

---

## MVP Build Timeline

### Day 1: Voice Pipeline Proof of Concept

**Goal:** Make a phone call and have the AI respond to you
```bash
# Setup
pip install fastapi uvicorn websockets deepgram-sdk groq cartesia python-dotenv

# Create basic WebSocket handler (simplified version of above)
# Test with ngrok + Twilio
ngrok http 8000

# Configure Twilio number webhook:
# https://your-ngrok-url.ngrok.io/ws/media
```

**Success Criteria:**
- Call your number
- Hear a greeting
- Say something
- AI responds (even if just echoing)

**Cost:** $0 (free tiers)

---

### Week 1: Intent Detection + Basic Booking

**Days 2-3: Intent Detection**
- Implement LLM-based intent classification
- Test with 10 sample phrases
- Achieve >80% accuracy

**Days 4-5: Slot Filling**
- Implement state machine
- Test multi-turn conversation
- Extract: service, date, time, name, phone

**Days 6-7: Database + Simple Availability**
- Set up PostgreSQL with schema
- Implement availability calculation (no external calendars yet)
- Test booking creation

**Success Criteria:**
- Complete a booking over the phone
- Booking appears in database
- No double-bookings when testing concurrent calls

**Cost:** $5/month (Railway database)

---

### Week 2-3: Production Features

**Week 2: External Integrations**
- Google Calendar OAuth flow
- Sync bookings bidirectionally
- Email confirmations (Resend)
- SMS confirmations (Twilio)

**Week 3: Edge Cases**
- Low confidence handling
- Human transfer logic
- No availability scenarios
- Rescheduling flow

**Success Criteria:**
- 90% success rate on test calls
- Human transfer works
- External calendar stays in sync

**Cost:** $20/month (Rails + some usage)

---

### Month 1: Pilot Ready

**Week 4: Multi-Tenancy**
- Add business_id to all queries
- Build admin dashboard (simple Streamlit app)
- Client can view transcripts and bookings

**Success Criteria:**
- Deploy for 1-2 pilot clients
- Monitor 50+ real calls
- Collect feedback

**Cost:** $50-100/month (includes pilot usage)

---

## Cost Optimization Strategies

### Per-Minute Breakdown

For a **5-minute booking call**:
Twilio:          $0.0425  (5 min × $0.0085/min)
Deepgram STT:    $0.0215  (5 min × $0.0043/min)
Groq LLM:        $0.006   (~3K tokens)
Cartesia TTS:    $0.0835  (5 min × $0.0167/min)
Server:          $0.0025  (amortized)
─────────────────────────
TOTAL:           $0.156 per call
Your Price:      $1.50 per call (10x markup)
Margin:          $1.34 per call (89%)

### Passing Costs to Clients

**Model 1: Platform Fee + Usage**
Setup: $2,000 one-time
Monthly: $500 base
Usage: $0.50/min of talk time
Average client: 300 calls/month × 4 min = 1,200 min
Their cost: $500 + $600 = $1,100/month
Your cost: $187/month
Profit: $913/month per client

**Model 2: Per-Booking Fee**
$15 per successfully booked appointment
Client with 150 bookings/month pays: $2,250
Your cost (150 calls × 4 min × $0.031): ~$19
Profit: $2,231/month per client

**Recommendation:** Use Model 1 for predictable businesses (medical, salons), Model 2 for high-variance (real estate, legal)

---

## Real Example Walkthrough

### Complete Call Flow: Dental Appointment Booking
[Call initiated - 10:34 AM]
AI: "Thanks for calling Smile Dental! This call may be recorded. How can I help you?"
User: "Yeah hi, I need to get my teeth cleaned."
[Intent Detection: book_appointment, confidence: 0.92]
[Service extracted: "cleaning"]
[State → SLOT_FILLING]
AI: "I'd be happy to help you book a cleaning. What day works best for you?"
User: "Um, maybe Friday?"
[Date extraction: ambiguous - which Friday?]
[Confidence: 0.65 - below threshold]
AI: "Just to confirm, do you mean this coming Friday, November 15th?"
User: "Yes, that works."
[Date confirmed: 2024-11-15]
[State → SLOT_FILLING (time)]
AI: "Great! What time would you prefer?"
User: "Afternoon, like 2 or 3?"
[Time extraction: "14:00" or "15:00", preference: afternoon]
[State → AVAILABILITY_CHECK]
AI: "Let me check our afternoon availability for Friday the 15th..."
[Backend queries database + Google Calendar]
[Found: 2:00 PM, 2:30 PM, 3:00 PM available]
[Selects closest to "2 or 3" → 2:00 PM]
AI: "Perfect! I have 2 PM available. Can I get your name for the appointment?"
User: "It's Sarah Johnson."
[Name: "Sarah Johnson", confidence: 0.95]
AI: "Thanks Sarah. And what's the best phone number to reach you?"
User: "555-123-4567"
[Phone: "5551234567" (normalized)]
[All slots filled]
[State → CONFIRMATION]
AI: "Wonderful! Let me confirm: I have you scheduled for a dental cleaning this Friday, November 15th at 2:00 PM. Can I go ahead and book that for you?"
User: "Yep, that's perfect."
[Confirmation: true, confidence: 0.98]
[State → BOOKING_EXECUTION]
[Backend creates booking atomically]
[Checks: No conflicts found]
[Inserts into database]
[Creates Google Calendar event]
[Triggers SMS confirmation]
AI: "Perfect! Your cleaning is confirmed for Friday at 2:00 PM. You'll get a text confirmation at 555-123-4567, and we'll send you a reminder the day before. Is there anything else I can help you with?"
User: "No, that's it. Thanks!"
AI: "You're welcome! We'll see you Friday. Have a great day!"
[Call ends - Duration: 2 min 18 sec]
[Costs: Twilio $0.02, Deepgram $0.01, Groq $0.002, Cartesia $0.04 = $0.072 total]

**Transcript stored in database:**
```json
{
  "session_id": "call_abc123",
  "business_id": "smile_dental",
  "user_id": "user_789",
  "booking_id": "booking_456",
  "duration_seconds": 138,
  "turns": [
    {"role": "assistant", "content": "Thanks for calling...", "timestamp": "..."},
    {"role": "user", "content": "Yeah hi, I need to get my teeth cleaned", "timestamp": "..."},
    ...
  ],
  "intent": "book_appointment",
  "slots_filled": {
    "service": "cleaning",
    "date": "2024-11-15",
    "time": "14:00",
    "name": "Sarah Johnson",
    "phone": "5551234567"
  },
  "outcome": "booked",
  "transferred_to_human": false
}
```

---

## Launch Checklist

### Pre-Launch (1 Week Before)

**Technical**
- [ ] WebSocket server stable for 72+ hours
- [ ] Database exclusion constraint tested under load
- [ ] Latency benchmark: <1.5s end-to-end
- [ ] Barge-in working (user can interrupt AI)
- [ ] Human transfer flow tested
- [ ] External calendar sync verified
- [ ] SMS/Email confirmations sending
- [ ] Error monitoring (Sentry) configured

**Business**
- [ ] Pilot client contract signed
- [ ] Phone number ported or forwarding configured
- [ ] Privacy policy covers call recording
- [ ] Business insurance (E&O) in place

### Launch Day

- [ ] Deploy to production (Railway/AWS)
- [ ] Monitor first 10 calls in real-time
- [ ] Fix any critical bugs within 1 hour
- [ ] Collect client feedback after each call

### Week 1 Post-Launch

- [ ] Review all call transcripts
- [ ] Identify common failure patterns
- [ ] Optimize prompts for low-confidence cases
- [ ] Adjust slot-filling logic based on real data
- [ ] Calculate actual costs vs. projections

---

## Key Takeaways

**What Makes This System Work:**

1. **PostgreSQL EXCLUDE Constraint** - Prevents double-booking at database level, independent of application logic

2. **Streaming Everything** - STT, LLM, TTS all stream to keep latency <1s

3. **Explicit State Machine** - Conversation doesn't rely on LLM "memory" - we track state explicitly

4. **Low-Confidence Fallbacks** - Always have an escape hatch to human transfer

5. **External Calendar Sync** - Check ALL sources of bookings, not just your database

6. **Cost Control** - 90% margins by avoiding expensive platforms, using Groq + Deepgram + Cartesia

**What Will Break (And How to Fix):**

- **High Latency** → Use Groq (not OpenAI), cache greetings, stream responses
- **Wrong Intent** → Lower confidence threshold, add more training examples to prompts
- **Missing Calendar Events** → Poll external calendars every 5 min, cache results
- **Double Bookings** → Trust the database constraint, don't try to prevent in code
- **User Frustration** → Detect early (3 low-confidence turns), transfer to human immediately

**Your 60-Day Mission:**

- **Week 1-2:** Working voice AI that can have a conversation
- **Week 3-4:** Slot filling + database booking working
- **Week 5-6:** External calendar integration + confirmations
- **Week 7-8:** First pilot client live with real customers
- **Month 2:** Refine based on real data, onboard 3-5 more clients

At **5 clients × $1,100/month = $5,500 MRR** with 85% margins = **$4,675/month profit**.

That's sustainable full-time income in 60 days, built with commodity tools and focused execution.

**Now go build it.** The market is massive, the tech is commoditized, and execution wins.
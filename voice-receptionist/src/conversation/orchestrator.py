"""
Conversation orchestrator.
Main loop that coordinates STT -> LLM -> TTS.
"""

from datetime import datetime
from typing import Tuple, Optional, Dict, Any
from uuid import UUID

from asyncpg import Connection

from src.conversation.state_machine import (
    StateMachine, ConversationState, ConversationContext, Intent, FilledSlot
)
from src.conversation.intent_router import IntentRouter
from src.booking.engine import BookingEngine
from src.core.logging import get_logger

logger = get_logger(__name__)


class ConversationOrchestrator:
    """
    Main orchestrator for voice conversations.
    
    Manages the conversation flow:
    1. Receives user transcript
    2. Determines intent/extracts slots
    3. Executes actions (availability check, booking)
    4. Returns response text
    """
    
    def __init__(
        self,
        context: ConversationContext,
        db: Connection,
        llm_service=None,
    ):
        self.context = context
        self.db = db
        self.state_machine = StateMachine(context)
        self.intent_router = IntentRouter(llm_service)
        self.booking_engine = BookingEngine(db)
        self.llm = llm_service
    
    async def process_user_input(self, transcript: str) -> Tuple[str, bool]:
        """
        Process user input and return response.
        
        Args:
            transcript: User's spoken text
        
        Returns:
            Tuple of (response_text, should_continue)
        """
        # Add to conversation history
        self.context.turn_count += 1
        self.context.turns.append({
            "role": "user",
            "content": transcript,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        logger.info(
            "Processing user input",
            session_id=self.context.session_id,
            state=self.context.current_state.value,
            transcript=transcript[:100],
        )
        
        try:
            # Route based on current state
            if self.context.current_state == ConversationState.GREETING:
                return await self._handle_greeting(transcript)
            
            elif self.context.current_state == ConversationState.INTENT_DETECTION:
                return await self._handle_intent_detection(transcript)
            
            elif self.context.current_state == ConversationState.SLOT_FILLING:
                return await self._handle_slot_filling(transcript)
            
            elif self.context.current_state == ConversationState.AVAILABILITY_CHECK:
                return await self._handle_availability_check(transcript)
            
            elif self.context.current_state == ConversationState.CONFIRMATION:
                return await self._handle_confirmation(transcript)
            
            elif self.context.current_state == ConversationState.ACTION_EXECUTION:
                return await self._handle_action_execution(transcript)
            
            elif self.context.current_state == ConversationState.COMPLETION:
                return "Is there anything else I can help you with?", True
            
            else:
                return await self._handle_error_recovery(transcript)
        
        except Exception as e:
            logger.error(
                "Error processing input",
                session_id=self.context.session_id,
                error=str(e),
            )
            return await self._handle_error_recovery(transcript)
    
    async def _handle_greeting(self, transcript: str) -> Tuple[str, bool]:
        """Handle post-greeting state."""
        self.state_machine.transition(ConversationState.INTENT_DETECTION)
        return await self._handle_intent_detection(transcript)
    
    async def _handle_intent_detection(self, transcript: str) -> Tuple[str, bool]:
        """Detect user intent."""
        transcript_lower = transcript.lower()
        
        # Check if user is confirming a previously detected intent
        if self.context.current_intent and self.context.current_intent != Intent.UNCLEAR:
            confirmation_words = ["yes", "yeah", "correct", "that's right", "right", "yep", "sure", "ok", "okay"]
            denial_words = ["no", "nope", "wrong", "different", "not"]
            
            is_confirmation = any(word in transcript_lower for word in confirmation_words)
            is_denial = any(word in transcript_lower for word in denial_words)
            
            if is_confirmation and not is_denial:
                logger.info(
                    "User confirmed pending intent",
                    session_id=self.context.session_id,
                    intent=self.context.current_intent.value,
                )
                # Proceed with the confirmed intent
                return await self._proceed_with_intent(self.context.current_intent, transcript)
            elif is_denial:
                # User denied, reset intent and ask again
                self.context.current_intent = None
                return "No problem. What would you like help with today?", True
        
        # Get business context
        business = await self.db.fetchrow(
            "SELECT * FROM businesses WHERE id = $1",
            UUID(self.context.business_id)
        )
        business_context = dict(business) if business else {}
        
        # Detect intent
        result = await self.intent_router.detect_intent(
            transcript=transcript,
            business_context=business_context,
            conversation_history=self.context.turns,
        )
        
        self.context.current_intent = result.intent
        self.context.intent_confidence = result.confidence
        
        logger.info(
            "Intent detected",
            session_id=self.context.session_id,
            intent=result.intent.value,
            confidence=result.confidence,
        )
        
        # Low confidence handling
        if result.confidence < 0.75:
            self.context.low_confidence_count += 1
            
            if self.state_machine.should_transfer_to_human():
                return await self._initiate_human_transfer("Low confidence")
            
            return self.intent_router.get_clarifying_question(result.intent), True
        
        # Proceed with high-confidence intent
        return await self._proceed_with_intent(result.intent, transcript, result.extracted_entities, result.confidence)
    
    async def _proceed_with_intent(
        self, 
        intent: Intent, 
        transcript: str, 
        extracted_entities: dict = None, 
        confidence: float = 0.8
    ) -> Tuple[str, bool]:
        """Proceed with a confirmed or high-confidence intent."""
        extracted_entities = extracted_entities or {}
        
        if intent == Intent.BOOK_APPOINTMENT:
            # Initialize slots
            self.context.required_slots = self.state_machine.get_required_slots_for_intent(intent)
            
            # Pre-fill from extracted entities
            for key, value in extracted_entities.items():
                if value and key in self.context.required_slots:
                    self.context.filled_slots[key] = FilledSlot(
                        name=key,
                        value=value,
                        confidence=confidence,
                    )
            
            self.state_machine.transition(ConversationState.SLOT_FILLING)
            return await self._handle_slot_filling(transcript)
        
        elif intent == Intent.TRANSFER_HUMAN:
            return await self._initiate_human_transfer("User requested")
        
        elif intent == Intent.GENERAL_INQUIRY:
            # Handle with LLM
            response = await self._generate_inquiry_response(transcript)
            return response, True
        
        else:
            return f"I can help with that. Let me get some details.", True
    
    async def _handle_slot_filling(self, transcript: str) -> Tuple[str, bool]:
        """Fill required slots."""
        # Get next unfilled slot
        next_slot = self.state_machine.get_next_unfilled_slot()
        
        if not next_slot:
            # All slots filled
            self.state_machine.transition(ConversationState.AVAILABILITY_CHECK)
            return await self._handle_availability_check(transcript)
        
        # Try to extract value from transcript
        filled = self.context.filled_slots.get(next_slot.name)
        
        if not filled or not filled.value:
            # Slot not yet filled, extract from transcript
            value = await self._extract_slot_value(transcript, next_slot)
            
            if value:
                self.context.filled_slots[next_slot.name] = FilledSlot(
                    name=next_slot.name,
                    value=value,
                    confidence=0.8,
                    confirmed=True,
                )
                
                # Check if all slots now filled
                if self.state_machine.all_slots_filled():
                    self.state_machine.transition(ConversationState.AVAILABILITY_CHECK)
                    return await self._handle_availability_check(transcript)
                
                # Get next slot
                next_slot = self.state_machine.get_next_unfilled_slot()
                if next_slot:
                    return next_slot.prompt, True
        
        # Ask for current slot
        return next_slot.prompt, True
    
    async def _handle_availability_check(self, transcript: str) -> Tuple[str, bool]:
        """Check availability and propose time."""
        # Get filled slot values
        service_name = self.context.filled_slots.get("service", FilledSlot(name="service")).value
        date_str = self.context.filled_slots.get("date", FilledSlot(name="date")).value
        time_str = self.context.filled_slots.get("time", FilledSlot(name="time")).value
        
        # Find service
        service = await self.db.fetchrow(
            "SELECT * FROM services WHERE business_id = $1 AND LOWER(name) LIKE $2",
            UUID(self.context.business_id),
            f"%{service_name.lower()}%" if service_name else "%%"
        )
        
        if not service:
            # Clear invalid service slot so user can retry
            if "service" in self.context.filled_slots:
                del self.context.filled_slots["service"]
            
            # Transition back to slot filling
            self.state_machine.transition(ConversationState.SLOT_FILLING)
            return "I couldn't find that service. What service are you looking for?", True
        
        # Check availability
        result = await self.booking_engine.check_availability(
            business_id=UUID(self.context.business_id),
            service_id=service["id"],
            date_str=date_str or datetime.now().strftime("%Y-%m-%d"),
            preferred_time=time_str,
        )
        
        if not result.get("slots"):
            # No availability
            alternatives = result.get("alternatives", [])
            if alternatives:
                alt_dates = ", ".join([a["date_formatted"] for a in alternatives[:3]])
                self.state_machine.transition(ConversationState.SLOT_FILLING)
                return f"I'm sorry, we don't have availability on that day. We do have openings on {alt_dates}. Would any of those work?", True
            else:
                return "I'm sorry, we're fully booked. Would you like me to put you on a waitlist?", True
        
        # Propose best slot
        best_slot = result["slots"][0]
        self.context.proposed_booking = {
            "service_id": str(service["id"]),
            "service_name": service["name"],
            "start_time": best_slot["start"],
            "formatted_time": best_slot["formatted_time"],
        }
        
        name = self.context.filled_slots.get("name", FilledSlot(name="name")).value or "there"
        phone = self.context.filled_slots.get("phone", FilledSlot(name="phone")).value
        
        self.state_machine.transition(ConversationState.CONFIRMATION)
        return f"Great! I can book you for {service['name']} on {best_slot['formatted_time']}. Can I confirm your name is {name} and phone is {phone}?", True
    
    async def _handle_confirmation(self, transcript: str) -> Tuple[str, bool]:
        """Get confirmation before booking."""
        # Check if confirmed
        transcript_lower = transcript.lower()
        
        if any(word in transcript_lower for word in ["yes", "correct", "that's right", "confirm", "book it", "sounds good"]):
            self.state_machine.transition(ConversationState.ACTION_EXECUTION)
            return await self._handle_action_execution(transcript)
        
        elif any(word in transcript_lower for word in ["no", "wrong", "different", "change"]):
            self.state_machine.transition(ConversationState.SLOT_FILLING)
            return "No problem. What would you like to change?", True
        
        else:
            return "Just to confirm, should I go ahead and book this appointment for you?", True
    
    async def _handle_action_execution(self, transcript: str) -> Tuple[str, bool]:
        """Execute the booking."""
        if not self.context.proposed_booking:
            return "I'm sorry, something went wrong. Let me start over.", True
        
        phone = self.context.filled_slots.get("phone", FilledSlot(name="phone")).value
        name = self.context.filled_slots.get("name", FilledSlot(name="name")).value
        
        result = await self.booking_engine.create_booking(
            business_id=UUID(self.context.business_id),
            service_id=UUID(self.context.proposed_booking["service_id"]),
            start_time=datetime.fromisoformat(self.context.proposed_booking["start_time"]),
            customer_phone=phone,
            customer_name=name,
            conversation_id=UUID(self.context.session_id),
        )
        
        if result.get("success"):
            self.context.created_record_id = result["booking_id"]
            self.state_machine.transition(ConversationState.COMPLETION)
            
            if result.get("requires_approval"):
                return f"Your appointment request has been submitted for {self.context.proposed_booking['formatted_time']}. You'll receive a confirmation once it's approved. Is there anything else I can help with?", True
            else:
                return f"Perfect! Your appointment is confirmed for {self.context.proposed_booking['formatted_time']}. You'll receive a confirmation text at {phone}. Is there anything else I can help with?", True
        else:
            # Booking failed
            self.state_machine.transition(ConversationState.AVAILABILITY_CHECK)
            return f"I apologize, but {result.get('error', 'that slot was just taken')}. Let me find you another time.", True
    
    async def _handle_error_recovery(self, transcript: str) -> Tuple[str, bool]:
        """Handle errors and recover."""
        self.context.error_count += 1
        
        if self.state_machine.should_transfer_to_human():
            return await self._initiate_human_transfer("Error recovery failed")
        
        return "I'm sorry, I'm having trouble with that. Could you repeat what you need?", True
    
    async def _initiate_human_transfer(self, reason: str) -> Tuple[str, bool]:
        """Transfer to human agent."""
        self.state_machine.force_transition(ConversationState.HUMAN_TRANSFER)
        
        logger.info(
            "Transferring to human",
            session_id=self.context.session_id,
            reason=reason,
        )
        
        return "I'd like to connect you with one of our team members who can better assist you. Please hold.", False
    
    async def _extract_slot_value(self, transcript: str, slot) -> Optional[str]:
        """Extract slot value from transcript."""
        # Simple extraction - in production use LLM
        transcript_lower = transcript.lower()
        
        if slot.name == "name":
            # Look for name patterns
            if "my name is" in transcript_lower:
                return transcript.split("my name is")[-1].strip().split()[0]
            elif "i'm" in transcript_lower:
                return transcript.split("i'm")[-1].strip().split()[0]
            elif "this is" in transcript_lower:
                return transcript.split("this is")[-1].strip().split()[0]
            else:
                # Assume the input is the name
                return transcript.strip()
        
        elif slot.name == "phone":
            # Extract digits
            import re
            digits = re.sub(r'\D', '', transcript)
            if len(digits) >= 10:
                return digits[-10:]
        
        elif slot.name == "date":
            # Simple date parsing
            from dateutil import parser
            try:
                parsed = parser.parse(transcript, fuzzy=True)
                return parsed.strftime("%Y-%m-%d")
            except:
                pass
        
        elif slot.name == "time":
            # Extract time
            if "morning" in transcript_lower:
                return "10:00"
            elif "afternoon" in transcript_lower:
                return "14:00"
            elif "evening" in transcript_lower:
                return "17:00"
            else:
                # Try to parse
                from dateutil import parser
                try:
                    parsed = parser.parse(transcript, fuzzy=True)
                    return parsed.strftime("%H:%M")
                except:
                    pass
        
        elif slot.name == "service":
            transcript_lower = transcript.lower()
            
            # Get all services for this business
            services = await self.db.fetch(
                "SELECT name FROM services WHERE business_id = $1 AND is_active = true",
                UUID(self.context.business_id)
            )
            
            # Check if any service name appears in the transcript
            for service in services:
                service_name = service["name"]
                if service_name.lower() in transcript_lower:
                    logger.info(f"Found service '{service_name}' in transcript")
                    return service_name
            
            # If no match and transcript is short, assume it's the service name
            if len(transcript.split()) <= 2:
                # Check for exact match
                service = await self.db.fetchrow(
                    "SELECT name FROM services WHERE business_id = $1 AND LOWER(name) = LOWER($2)",
                    UUID(self.context.business_id),
                    transcript.strip()
                )
                if service:
                    return service["name"]
            
            # Return None to indicate extraction failed
            return None
        
        else:
            return transcript.strip()
        
        return None
    
    async def _generate_inquiry_response(self, transcript: str) -> str:
        """Generate response for general inquiries."""
        if self.llm:
            business = await self.db.fetchrow(
                "SELECT * FROM businesses WHERE id = $1",
                UUID(self.context.business_id)
            )
            prompt = f"Customer asked: {transcript}. Business: {business['name']}. Give a brief helpful response."
            return await self.llm.generate(prompt)
        
        return "I can help with bookings and general questions. How can I assist you today?"

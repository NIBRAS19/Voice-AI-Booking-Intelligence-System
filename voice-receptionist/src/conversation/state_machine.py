"""
Conversation state machine.
Manages transitions between conversation states.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class ConversationState(str, Enum):
    """Possible conversation states."""
    IDLE = "idle"
    GREETING = "greeting"
    INTENT_DETECTION = "intent_detection"
    SLOT_FILLING = "slot_filling"
    AVAILABILITY_CHECK = "availability_check"
    CONFIRMATION = "confirmation"
    ACTION_EXECUTION = "action_execution"
    PENDING_APPROVAL = "pending_approval"
    COMPLETION = "completion"
    HUMAN_TRANSFER = "human_transfer"
    ERROR_RECOVERY = "error_recovery"


class Intent(str, Enum):
    """Detected intents."""
    BOOK_APPOINTMENT = "book_appointment"
    PLACE_ORDER = "place_order"
    SERVICE_REQUEST = "service_request"
    GENERAL_INQUIRY = "general_inquiry"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"
    CHECK_STATUS = "check_status"
    COMPLAINT = "complaint"
    TRANSFER_HUMAN = "transfer_human"
    UNCLEAR = "unclear"


class SlotDefinition(BaseModel):
    """Definition of a required slot."""
    name: str
    required: bool = True
    prompt: str
    validation_regex: Optional[str] = None
    examples: List[str] = []


class FilledSlot(BaseModel):
    """A filled slot with value and confidence."""
    name: str
    value: Optional[str] = None
    confidence: float = 0.0
    confirmed: bool = False
    attempts: int = 0


class ConversationContext(BaseModel):
    """Complete conversation context."""
    session_id: str
    business_id: str
    caller_phone: Optional[str] = None
    user_id: Optional[str] = None
    
    # State
    current_state: ConversationState = ConversationState.GREETING
    state_history: List[ConversationState] = []
    
    # Intent
    current_intent: Optional[Intent] = None
    intent_confidence: float = 0.0
    
    # Slots
    required_slots: Dict[str, SlotDefinition] = {}
    filled_slots: Dict[str, FilledSlot] = {}
    
    # Conversation history
    turn_count: int = 0
    turns: List[Dict[str, Any]] = []
    
    # Booking context
    proposed_booking: Optional[Dict[str, Any]] = None
    created_record_id: Optional[str] = None
    
    # Error tracking
    low_confidence_count: int = 0
    error_count: int = 0
    max_retries: int = 3


class StateMachine:
    """
    Manages conversation state transitions.
    
    State transitions:
    GREETING -> INTENT_DETECTION
    INTENT_DETECTION -> SLOT_FILLING (if booking intent)
    INTENT_DETECTION -> HUMAN_TRANSFER (if transfer intent)
    SLOT_FILLING -> AVAILABILITY_CHECK (when slots filled)
    AVAILABILITY_CHECK -> CONFIRMATION (if available)
    CONFIRMATION -> ACTION_EXECUTION (if confirmed)
    ACTION_EXECUTION -> COMPLETION (if success)
    Any -> ERROR_RECOVERY (on error)
    Any -> HUMAN_TRANSFER (after max retries)
    """
    
    # Valid state transitions
    TRANSITIONS = {
        ConversationState.IDLE: [ConversationState.GREETING],
        ConversationState.GREETING: [ConversationState.INTENT_DETECTION],
        ConversationState.INTENT_DETECTION: [
            ConversationState.SLOT_FILLING,
            ConversationState.HUMAN_TRANSFER,
            ConversationState.COMPLETION,
            ConversationState.ERROR_RECOVERY,
        ],
        ConversationState.SLOT_FILLING: [
            ConversationState.AVAILABILITY_CHECK,
            ConversationState.HUMAN_TRANSFER,
            ConversationState.ERROR_RECOVERY,
        ],
        ConversationState.AVAILABILITY_CHECK: [
            ConversationState.CONFIRMATION,
            ConversationState.SLOT_FILLING,  # If not available, pick new time
            ConversationState.HUMAN_TRANSFER,
        ],
        ConversationState.CONFIRMATION: [
            ConversationState.ACTION_EXECUTION,
            ConversationState.SLOT_FILLING,  # If declined, offer different time
            ConversationState.HUMAN_TRANSFER,
        ],
        ConversationState.ACTION_EXECUTION: [
            ConversationState.COMPLETION,
            ConversationState.PENDING_APPROVAL,
            ConversationState.ERROR_RECOVERY,
        ],
        ConversationState.PENDING_APPROVAL: [
            ConversationState.COMPLETION,
        ],
        ConversationState.ERROR_RECOVERY: [
            ConversationState.SLOT_FILLING,
            ConversationState.HUMAN_TRANSFER,
        ],
        ConversationState.COMPLETION: [],
        ConversationState.HUMAN_TRANSFER: [],
    }
    
    def __init__(self, context: ConversationContext):
        self.context = context
    
    def can_transition(self, target_state: ConversationState) -> bool:
        """Check if transition to target state is valid."""
        valid_targets = self.TRANSITIONS.get(self.context.current_state, [])
        return target_state in valid_targets
    
    def transition(self, target_state: ConversationState) -> bool:
        """
        Attempt to transition to a new state.
        
        Returns:
            True if transition succeeded, False otherwise
        """
        if not self.can_transition(target_state):
            return False
        
        # Record history
        self.context.state_history.append(self.context.current_state)
        self.context.current_state = target_state
        
        return True
    
    def force_transition(self, target_state: ConversationState) -> None:
        """Force transition (for error recovery)."""
        self.context.state_history.append(self.context.current_state)
        self.context.current_state = target_state
    
    def should_transfer_to_human(self) -> bool:
        """Check if we should transfer to human agent."""
        return (
            self.context.low_confidence_count >= self.context.max_retries or
            self.context.error_count >= 3 or
            self.context.current_intent == Intent.TRANSFER_HUMAN
        )
    
    def get_required_slots_for_intent(self, intent: Intent) -> Dict[str, SlotDefinition]:
        """Get required slots for an intent."""
        if intent == Intent.BOOK_APPOINTMENT:
            return {
                "service": SlotDefinition(
                    name="service",
                    prompt="What service would you like to book?",
                    examples=["appointment", "consultation", "checkup"]
                ),
                "date": SlotDefinition(
                    name="date",
                    prompt="What day works best for you?",
                    validation_regex=r"\d{4}-\d{2}-\d{2}",
                    examples=["tomorrow", "next Monday", "Friday"]
                ),
                "time": SlotDefinition(
                    name="time",
                    prompt="What time would you prefer?",
                    examples=["morning", "2pm", "afternoon"]
                ),
                "name": SlotDefinition(
                    name="name",
                    prompt="Can I get your name please?",
                ),
                "phone": SlotDefinition(
                    name="phone",
                    prompt="And what's the best phone number to reach you?",
                    validation_regex=r"\d{10,}"
                ),
            }
        elif intent == Intent.PLACE_ORDER:
            return {
                "items": SlotDefinition(
                    name="items",
                    prompt="What would you like to order?",
                ),
                "name": SlotDefinition(
                    name="name",
                    prompt="What name is this order for?",
                ),
                "phone": SlotDefinition(
                    name="phone",
                    prompt="What's your phone number?",
                ),
            }
        else:
            return {}
    
    def get_next_unfilled_slot(self) -> Optional[SlotDefinition]:
        """Get the next slot that needs to be filled."""
        for slot_name, slot_def in self.context.required_slots.items():
            filled = self.context.filled_slots.get(slot_name)
            if not filled or not filled.value or not filled.confirmed:
                return slot_def
        return None
    
    def all_slots_filled(self) -> bool:
        """Check if all required slots are filled and confirmed."""
        for slot_name in self.context.required_slots:
            filled = self.context.filled_slots.get(slot_name)
            if not filled or not filled.value or not filled.confirmed:
                return False
        return True

"""
Intent router for classifying user intents.
"""

from enum import Enum
from typing import Dict, Any, Optional, Tuple
from pydantic import BaseModel


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


class IntentResult(BaseModel):
    """Intent detection result."""
    intent: Intent
    confidence: float
    extracted_entities: Dict[str, Any] = {}
    reasoning: Optional[str] = None


# Intent detection keywords (for rule-based fallback)
INTENT_KEYWORDS = {
    Intent.BOOK_APPOINTMENT: [
        "book", "appointment", "schedule", "reserve", "want to come in",
        "make an appointment", "can I come", "available", "opening"
    ],
    Intent.PLACE_ORDER: [
        "order", "buy", "purchase", "want to get", "need to order"
    ],
    Intent.RESCHEDULE: [
        "reschedule", "change", "move", "different time", "different day"
    ],
    Intent.CANCEL: [
        "cancel", "delete", "remove", "don't need", "won't make it"
    ],
    Intent.CHECK_STATUS: [
        "status", "check", "when is", "confirm", "my appointment"
    ],
    Intent.COMPLAINT: [
        "complaint", "problem", "issue", "unhappy", "disappointed", "terrible"
    ],
    Intent.TRANSFER_HUMAN: [
        "human", "person", "someone", "agent", "talk to", "speak with",
        "real person", "operator"
    ],
    Intent.GENERAL_INQUIRY: [
        "hours", "price", "cost", "location", "address", "what do you",
        "services", "do you offer"
    ],
}


class IntentRouter:
    """
    Routes user input to the appropriate intent.
    Uses LLM for primary detection with rule-based fallback.
    """
    
    def __init__(self, llm_service=None):
        """
        Initialize the intent router.
        
        Args:
            llm_service: LLM service for intent detection (optional)
        """
        self.llm = llm_service
        # Lower threshold to support rule-based fallback (0.6-0.8 range)
        self.confidence_threshold = 0.55
    
    async def detect_intent(
        self,
        transcript: str,
        business_context: Dict[str, Any],
        conversation_history: list = None,
    ) -> IntentResult:
        """
        Detect intent from user transcript.
        
        Args:
            transcript: User's spoken text
            business_context: Business information
            conversation_history: Previous turns for context
        
        Returns:
            IntentResult with intent and confidence
        """
        # Try LLM-based detection first
        if self.llm:
            try:
                result = await self._detect_with_llm(
                    transcript, business_context, conversation_history
                )
                if result.confidence >= self.confidence_threshold:
                    return result
            except Exception:
                pass  # Fall through to rule-based
        
        # Fallback to rule-based detection
        return self._detect_with_rules(transcript)
    
    async def _detect_with_llm(
        self,
        transcript: str,
        business_context: Dict[str, Any],
        conversation_history: list = None,
    ) -> IntentResult:
        """Detect intent using LLM."""
        business_name = business_context.get("name", "our business")
        
        prompt = f"""Analyze this user message and determine their intent.

User message: "{transcript}"

Context: This is a phone call to {business_name}.

Respond with JSON only:
{{
    "intent": "book_appointment|place_order|service_request|general_inquiry|reschedule|cancel|check_status|complaint|transfer_human|unclear",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation",
    "extracted_entities": {{
        "date": "YYYY-MM-DD or null",
        "time": "HH:MM or null",
        "service": "service name or null",
        "name": "customer name or null",
        "phone": "phone number or null"
    }}
}}"""
        
        # Call LLM
        response = await self.llm.generate(prompt)
        
        # Parse response
        import json
        data = json.loads(response)
        
        return IntentResult(
            intent=Intent(data["intent"]),
            confidence=data["confidence"],
            extracted_entities=data.get("extracted_entities", {}),
            reasoning=data.get("reasoning"),
        )
    
    def _detect_with_rules(self, transcript: str) -> IntentResult:
        """Fallback rule-based intent detection."""
        transcript_lower = transcript.lower()
        
        best_intent = Intent.UNCLEAR
        best_score = 0
        
        for intent, keywords in INTENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in transcript_lower)
            if score > best_score:
                best_score = score
                best_intent = intent
        
        confidence = min(0.5 + (best_score * 0.1), 0.8)  # Max 0.8 for rule-based
        
        return IntentResult(
            intent=best_intent,
            confidence=confidence if best_score > 0 else 0.3,
            reasoning="Rule-based detection",
        )
    
    def get_clarifying_question(self, intent: Intent) -> str:
        """Get a clarifying question for ambiguous intents."""
        questions = {
            Intent.UNCLEAR: "I want to make sure I understand. Are you looking to book an appointment, place an order, or do you have a question?",
            Intent.BOOK_APPOINTMENT: "Just to confirm, you'd like to schedule an appointment, is that right?",
            Intent.PLACE_ORDER: "You'd like to place an order, correct?",
        }
        return questions.get(intent, "Could you tell me more about what you need help with?")

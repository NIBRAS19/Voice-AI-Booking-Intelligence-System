"""
LLM service using Ollama for local inference.
Self-hosted, low-cost, fast responses.
"""

import asyncio
from typing import Optional, AsyncGenerator, Dict, Any

import httpx

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class LLMService:
    """
    LLM service using Ollama for local inference.
    
    Features:
    - Self-hosted (no API costs)
    - Low latency with proper hardware
    - Supports multiple models (Mistral, Llama)
    - Streaming responses
    """
    
    def __init__(self):
        self.host = settings.ollama_host
        self.model = settings.ollama_model
        self.client = httpx.AsyncClient(timeout=60.0)
        self._available = None
    
    async def is_available(self) -> bool:
        """Check if Ollama is running."""
        if self._available is not None:
            return self._available
        
        try:
            response = await self.client.get(f"{self.host}/api/tags")
            self._available = response.status_code == 200
        except Exception:
            self._available = False
        
        return self._available
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 256,
    ) -> str:
        """
        Generate a response from the LLM.
        
        Args:
            prompt: User prompt
            system_prompt: System instructions
            temperature: Randomness (0=deterministic, 1=creative)
            max_tokens: Maximum response length
        
        Returns:
            Generated text response
        """
        if not await self.is_available():
            logger.warning("Ollama not available, using fallback")
            return self._fallback_response(prompt)
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = await self.client.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                    "stream": False,
                },
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("message", {}).get("content", "")
            else:
                logger.error("Ollama request failed", status=response.status_code)
                return self._fallback_response(prompt)
        
        except Exception as e:
            logger.error("LLM generation failed", error=str(e))
            return self._fallback_response(prompt)
    
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> AsyncGenerator[str, None]:
        """
        Stream response tokens.
        
        For lower latency, we can start TTS before
        the full response is generated.
        
        Yields:
            Token strings
        """
        if not await self.is_available():
            yield self._fallback_response(prompt)
            return
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            async with self.client.stream(
                "POST",
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "options": {
                        "temperature": temperature,
                    },
                    "stream": True,
                },
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        if content := data.get("message", {}).get("content"):
                            yield content
        
        except Exception as e:
            logger.error("LLM streaming failed", error=str(e))
            yield self._fallback_response(prompt)
    
    async def classify_intent(
        self,
        transcript: str,
        business_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Classify user intent from transcript.
        
        Returns:
            Dict with intent, confidence, entities
        """
        system_prompt = """You are an intent classifier for a business phone system.
Analyze the caller's message and determine their intent.

Possible intents:
- book_appointment: Wants to schedule/book something
- place_order: Wants to order products
- reschedule: Wants to change existing booking
- cancel: Wants to cancel booking/order
- check_status: Wants status update
- general_inquiry: Has questions about business
- complaint: Has a problem or complaint
- transfer_human: Wants to speak with a person

Respond in JSON format only:
{"intent": "...", "confidence": 0.0-1.0, "entities": {...}}"""
        
        prompt = f"Caller said: \"{transcript}\""
        
        response = await self.generate(prompt, system_prompt, temperature=0.1)
        
        try:
            import json
            return json.loads(response)
        except:
            return {"intent": "unclear", "confidence": 0.5, "entities": {}}
    
    async def extract_slots(
        self,
        transcript: str,
        required_slots: list,
    ) -> Dict[str, str]:
        """
        Extract slot values from transcript.
        
        Args:
            transcript: User's message
            required_slots: List of slot names to extract
        
        Returns:
            Dict of slot_name -> extracted_value
        """
        slots_str = ", ".join(required_slots)
        
        system_prompt = f"""Extract the following information from the caller's message: {slots_str}

For each piece of information:
- If found, provide the value
- If not found, use null
- For dates, convert to YYYY-MM-DD format
- For times, convert to HH:MM (24h) format
- For phone numbers, extract just digits

Respond in JSON format only."""
        
        response = await self.generate(transcript, system_prompt, temperature=0.1)
        
        try:
            import json
            return json.loads(response)
        except:
            return {}
    
    async def generate_response(
        self,
        context: Dict[str, Any],
        user_message: str,
    ) -> str:
        """
        Generate conversational response.
        
        Args:
            context: Conversation context
            user_message: Latest user message
        
        Returns:
            Response text
        """
        business_name = context.get("business_name", "our business")
        current_intent = context.get("current_intent", "unknown")
        
        system_prompt = f"""You are a helpful AI receptionist for {business_name}.
        
You are currently helping with: {current_intent}

Guidelines:
- Be friendly and professional
- Keep responses concise (1-2 sentences)
- If you don't understand, ask for clarification
- Never make up information
- Guide the caller through the process step by step

Current conversation state:
{context.get('state_summary', 'Initial greeting')}"""
        
        return await self.generate(user_message, system_prompt)
    
    def _fallback_response(self, prompt: str) -> str:
        """Generate fallback response when LLM unavailable."""
        prompt_lower = prompt.lower()
        
        if "book" in prompt_lower or "appointment" in prompt_lower:
            return "I'd be happy to help you book an appointment. What service are you interested in?"
        elif "cancel" in prompt_lower:
            return "I can help you cancel your booking. Can you provide your booking details?"
        elif "reschedule" in prompt_lower:
            return "Let me help you reschedule. What new time works for you?"
        else:
            return "I'd be happy to help. Could you tell me more about what you need?"
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

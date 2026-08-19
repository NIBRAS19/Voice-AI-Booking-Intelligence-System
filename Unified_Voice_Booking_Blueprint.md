# Unified Voice AI + Booking Intelligence System: Principal Engineer's Blueprint

> **Objective:** Build a scalable, low-latency (<1s), and cost-efficient automated booking voice agent for SMBs.  
> **Constraint:** Solo founder / Small team, No VC funding, Pay-as-you-go.

---

## 1. Scalable System Architecture

To achieve low latency and high availability without breaking the bank, we use a **Modular Monolith** architecture. Microservices are overkill for a team of one. We separate concerns logically within the code but deploy as a single high-performance service (initially) to minimize DevOps overhead.

### High-Level Architecture

```ascii
┌─────────────────────────────────────┐      ┌──────────────────────────────┐
│  Voice Gateway (Twilio/WebRTC)      │◄────►│  Orchestration Core (FastAPI)│
│  - Inbound/Outbound Calls           │      │  - WebSocket Server          │
│  - Media Stream (Audio)             │      │  - Event Loop (Asyncio)      │
└─────────────────────────────────────┘      └──────────────┬───────────────┘
                                                            │
          ┌─────────────────────────────────────────────────┼────────────────────────────────────────┐
          ▼                                                 ▼                                        ▼
┌───────────────────┐                             ┌────────────────────┐                   ┌───────────────────┐
│   Voice Layer     │                             │ Conversation Layer │                   │   Booking Layer   │
│ (Streaming I/O)   │                             │   (Intelligence)   │                   │  (Business Logic) │
├───────────────────┤                             ├────────────────────┤                   ├───────────────────┤
│ STT: Deepgram     │◄──────(Audio)──────────────►│ State Machine      │◄──(Availability)──┤ Availability Calc │
│ TTS: Cartesia     │                             │ Intent Detection   │                   │ Resource Locking  │
│ VAD: Silero/WebRTC│                             │ Slot Filling       │───(Create Book)──►│ Conflict Check    │
└───────────────────┘                             │ Context Memory     │                   └─────────┬─────────┘
                                                  └────────────────────┘                             │
                                                            │                                        ▼
                                                            ▼                              ┌───────────────────┐
                                                  ┌────────────────────┐                   │  Persistence Layer│
                                                  ├───────────────────┤                   ├───────────────────┤
                                                  │ Integration Layer  │                   │ PostgreSQL (ACID) │
                                                  ├────────────────────┤                   │ Redis (Hot State) │
                                                  │ Google Calendar    │                   └───────────────────┘
                                                  │ CRM Webhooks       │
                                                  │ SMS/Email Service  │
                                                  └────────────────────┘
```

### Why This is Cost-Efficient & Scalable
1.  **Stateless Compute:** The core application is stateless. Session state is held in memory (for the duration of the call) or Redis. This allows you to scale horizontally by just adding more API servers behind a load balancer.
2.  **Streaming First:** We process audio in streams, not batches. This reduces memory footprint and latency.
3.  **PostgreSQL for Truth:** We use Postgres for bookings with `EXCLUDE` constraints. This handles concurrency natively, preventing double-bookings without complex application locks.
4.  **Pay-As-You-Go:** No fixed component costs.
    *   **Idle System Cost:** ~$5-10/mo (Hosting + DB).
    *   **Active System Cost:** ~$0.04/min per active call.

---

## 2. Real-Time Voice Call Flow (Step-by-Step)

Latency is the enemy. Every step must be optimized.

1.  **Call Initiation (0ms):**
    *   Twilio receives the call.
    *   Webhook hits your internal API. Return TwiML `<Connect><Stream url="wss://..."/>`.
    *   **Optimization:** Use a lightweight edge function for this TwiML response to save ~100ms.

2.  **Audio Streaming & Handshake (50-100ms):**
    *   WebSocket connection established.
    *   **Action:** Immediately send a "Mark" message to establish baseline.
    *   **Action:** Start background connection to Deepgram (STT) and Cartesia (TTS).

3.  **The "Hello" (Fast Path):**
    *   Do NOT wait for the user to speak first.
    *   **Action:** Stream a pre-cached generic greeting audio file ("Hi, thanks for calling...") immediately upon connection.

4.  **Listening & Intent Detection:**
    *   Stream incoming raw audio chunks to Deepgram.
    *   **VAD (Voice Activity Detection):** Detect silence > 400ms.
    *   **Interim Result:** "I'd like to book a..." (Keep listening).
    *   **Final Result:** "I'd like to book a hair cut for Friday." -> Send to LLM.

5.  **Intelligence & Routing:**
    *   LLM (Groq Llama 3 70b) analyzes text.
    *   **Output:** `Intent: booking_request`, `Entities: {service: haircut, date: Friday}`.
    *   **Logic:** State Machine transitions to `CHECK_AVAILABILITY`.

6.  **Availability Calculation (Parallel):**
    *   Query DB for Friday slots. (Async, <20ms).
    *   **LLM Streaming:** While querying DB, LLM starts generating filler if needed ("Let me check Friday for you...").

7.  **Response Synthesis:**
    *   LLM generates response token-by-token.
    *   Stream tokens to Cartesia (TTS).
    *   Cartesia streams audio back.
    *   Server forwards audio to Twilio WebSocket.

8.  **Barge-In Handling:**
    *   If user speaks *while* audio is playing:
    *   **Immediate Action:** Send "Clear" message to Twilio (stops playback).
    *   **State Update:** Cancel current LLM/TTS tasks.
    *   **Loop:** Process new user input.

---

## 3. State & Context Management

We avoid "spaghetti code" by implementing a strict **Finite State Machine (FSM)**.

### Conversation States
*   `IDLE`: Waiting for call.
*   `LISTENING`: Streaming audio to STT.
*   `THINKING`: Determining intent/querying DB.
*   `SPEAKING`: Streaming TTS audio.
*   `HANDOFF`: Transferring to human.

### Slot Filling & Context
The Context Object is passed through every step:
```python
class SessionContext:
    session_id: str
    business_id: str
    current_intent: IntentType
    
    # The "Memory"
    slots: Dict[str, Any] = {
        "service_type": None,
        "date": None,
        "time": None,
        "customer_name": None
    }
    
    # Error Tracking
    retries: int = 0
    last_user_transcript: str = ""
```

**Retry Logic:** 
If slot confidence < 0.7 or validation fails (e.g., date in past):
1.  **Retry 1:** "Sorry, I didn't catch the day."
2.  **Retry 2:** "Could you please repeat just the day you want to come in?"
3.  **Retry 3 (Fail):** "I'm having trouble hearing. Let me pass you to a human." -> **Handoff**.

---

## 4. Project Folder Structure

This structure separates technical concerns (IO) from business logic (Rules).

```text
/src
├── core/
│   ├── config.py           # Env vars, standardized constants
│   ├── audio.py            # Audio format converters (mulaw <-> pcm)
│   └── logger.py           # Structured JSON logging
│
├── voice/                  # THE EARS & MOUTH
│   ├── server.py           # FastAPI WebSocket endpoint
│   ├── stt_service.py      # Deepgram wrapper (streaming)
│   └── tts_service.py      # Cartesia wrapper (streaming)
│   # WHY: Keeps provider-specific implementations isolated. 
│   # Swapping Deepgram for AssemblyAI happens here only.
│
├── conversation/           # THE BRAIN
│   ├── orchestrator.py     # Main loop: Audio -> Text -> State -> Audio
│   ├── state_machine.py    # Managing transitions (Listening -> Speaking)
│   ├── intent_router.py    # Classifying "Book" vs "Cancel" vs "Complaint"
│   └── prompts/            # System prompts for the LLM
│   # WHY: Pure logic. Validates inputs before touching the DB.
│
├── booking/                # THE BUSINESS LOGIC
│   ├── engine.py           # "Find slots", "Create Booking"
│   ├── availability.py     # The heavy date math (Intersections, Buffers)
│   └── validation.py       # Rules: "No double booking", "Open 9-5"
│   # WHY: Critical business rules. Must be tested heavily and isolated from AI hallucinations.
│
├── data/                   # THE MEMORY
│   ├── db.py               # AsyncPG connection pool
│   ├── models.py           # Pydantic & SQLAlchemy/SQLModel definitions
│   └── repositories/       # CRUD operations
│   # WHY: Protects the database. Only this layer writes SQL.
│
├── integrations/
│   ├── twilio_client.py    # SMS / Handoffs
│   ├── calendar_sync.py    # GCal / Outlook sync
│   └── notifications.py    # User confirmations
│   # WHY: External world adapter.
│
└── main.py                 # Entry point
```

---

## 5. Data Models (Conceptual)

### 1. Business
Configuration for the specific client using the system.
*   `id`: UUID
*   `name`: "Joe's Barber"
*   `timezone`: "America/New_York" (CRITICAL)
*   `hours`: JSON `{"mon": ["09:00", "17:00"]}`

### 2. Service
What is being sold.
*   `id`: UUID
*   `name`: "Haircut"
*   `duration_min`: 30
*   `price`: 40.00

### 3. Conversation (Audit Log)
*   `id`: UUID
*   `transcript`: JSONB `[{"role": "user", "text": "..."}, ...]`
*   `status`: "COMPLETED", "HANDOFF", "FAILED"
*   `booking_id`: FK (Nullable)

### 4. Booking (The Truth)
*   `id`: UUID
*   `resource_id`: (Staff/Room)
*   `start_time`: TIMESTAMPTZ (Always UTC)
*   `end_time`: TIMESTAMPTZ (Always UTC)
*   `status`: "CONFIRMED", "CANCELLED"
*   **Constraint:** `EXCLUDE USING gist (tstzrange(start_time, end_time) WITH &&)`

---

## 6. Technology Choices (Cost-First)

| Component | Choice | Why (Cost & Performance) |
|:--- |:--- |:--- |
| **Language** | **Python (3.11+)** | Asyncio is mature, great integrations with Deepgram/LLMs. |
| **Web Framework** | **FastAPI** | Fastest Python framework, native WebSocket support. |
| **STT** | **Deepgram Nova-2** | Cheapest reliable streaming STT (~$0.0043/min). Fast (<300ms). |
| **Brain (LLM)** | **Groq (Llama 3)** | **Speed.** ~800 tokens/sec. 10x faster than GPT-4o. Free tier is generous. |
| **TTS** | **Cartesia Sonic** | Lowest latency (<150ms). Sound is significantly better than competitors. |
| **Database** | **PostgreSQL** | `EXCLUDE` constraints prevent double bookings. Mandatory for booking systems. |
| **Hosting** | **Railway / Render** | Simple deploy. Scale to zero when not in use. |
| **Telephony** | **Twilio** | Industry standard. Reliable. |

---

## 7. MVP Build Plan

**Goal:** Get to revenue in 4 weeks.

*   **Day 1: The "Parrot" Demo** (Validation)
    *   Setup FastAPI w/ WebSockets + Twilio.
    *   Implement Deepgram STT -> Text -> Cartesia TTS.
    *   **Goal:** You speak, it repeats what you said in a nice voice. Latency < 1.5s.

*   **Week 1: The "Receptionist"**
    *   Add Groq LLM.
    *   Implement System Prompt ("You are a receptionist...").
    *   Add basic tool calling (`check_availability` - mocked).
    *   **Goal:** A conversational agent that can "pretend" to book.

*   **Week 2: The "Booker" (Hard Part)**
    *   Implement Postgres DB & Booking Engine.
    *   Implement Availability Logic (Date math).
    *   Connect LLM Tools to Real DB methods.
    *   **Goal:** Real bookings saved to DB.

*   **Week 4: Production Polish**
    *   Barge-in handling (interruption).
    *   Integrate SMS confirmation (Twilio).
    *   Deployment to Railway.
    *   **Goal:** Give phone number to first free pilot client.

---

## 8. Cost Breakdown & Optimization

**Base Monthly:** ~$10 (DB + Hosting).

**Per-Call Cost (Average 3 mins):**
1.  **Twilio:** $0.0085 * 3 = $0.025
2.  **Deepgram:** $0.0043 * 3 = $0.013
3.  **Groq:** ~$0.005 (Tokens)
4.  **Cartesia:** ~$0.05 (TTS is usually the most expensive part)
    *   *Optimization:* Cache greetings and standard responses to skip TTS generation.
**Total:** ~$0.10 - $0.15 per call.

**Pricing Strategy:**
*   Charge client **$99/mo** subscription (covers base).
*   Charge **$0.50/min** usage fee.
*   **Margin:** ~70% on usage.

---

## 9. Security, Logging & Compliance

1.  **Consent (TCPA):** 
    *   **Inbound Only:** Focus on inbound implementations first to bypass strict TCPA outbound rules.
    *   **Disclosure:** System Prompt must include "I am an AI assistant".
    *   **Recording:** Play "This call is recorded" beep/message at start.
    
2.  **Data Security:**
    *   **No PII in Logs:** Scrub names/phones from text logs before writing to disk/cloud watch.
    *   **DB Encryption:** Use encrypted connection strings.
    
3.  **Audit:**
    *   Store full conversation transcript in DB linked to Booking ID. If a user complains "I booked for 2pm!", you have the transcript proving they confirmed 3pm.

---

## 10. Common Failure Points

1.  **Latency Drifting:** 
    *   *Symptom:* System gets slower as call goes on.
    *   *Fix:* Don't send full conversation history to LLM every time if not needed. Summarize context.
2.  **Bad Intent Detection:**
    *   *Symptom:* User says "Tuesday" and AI books "Thursday".
    *   *Fix:* **Explicit Confirmation Step.** "Just to confirm, you said Tuesday the 5th, right?"
3.  **Booking Conflicts:**
    *   *Symptom:* Two users book same slot.
    *   *Fix:* **Postgres EXCLUDE Constraint.** Handled at DB level. Application will receive error and AI will say "So sorry, that slot just went. How about..."
4.  **Hallucinations:**
    *   *Symptom:* AI promises services you don't offer.
    *   *Fix:* Low Temperature (0.1). Strict System Prompt: "If you don't know, say you need to check with a human."

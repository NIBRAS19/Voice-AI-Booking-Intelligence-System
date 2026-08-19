# Local Testing Guide - Voice Receptionist

## Quick Start

```powershell
# Terminal 1: Start backend
cd voice-receptionist
docker compose up -d

# Terminal 2: Start admin dashboard
cd voice-receptionist/admin-dashboard
npm run dev
```

---

## 1. Test via API (Swagger UI)

### Open API Docs
http://localhost:8000/docs

### Create a Booking (simulates voice AI)

1. **POST /api/v1/bookings** with body:
```json
{
  "business_id": "11111111-1111-1111-1111-111111111111",
  "service_id": "GET_FROM_SERVICES_ENDPOINT",
  "start_time": "2026-01-28T10:00:00Z",
  "customer_phone": "+15551234567",
  "customer_name": "Test Customer",
  "customer_notes": "Created via API test"
}
```

2. First get service_id from **GET /api/v1/services?business_id=11111111-1111-1111-1111-111111111111**

---

## 2. Admin Dashboard Testing

### Login
- URL: http://localhost:3000
- Email: `admin@demo.com`
- Password: `admin123`

### Dashboard Features
| Page | What to Test |
|------|--------------|
| Dashboard | View stats, pending approvals |
| Bookings | See all bookings, filter by status |
| Conversations | View call history (empty until calls made) |
| Settings | Toggle notifications, AI settings |

### Approve/Reject Workflow
1. Create a booking via API (status = `pending_approval`)
2. Go to Dashboard → Pending Approvals
3. Click ✓ to Approve or ✕ to Reject

---

## 3. Test Conversation Simulation

Since real voice calls require Twilio setup, you can test the conversation flow via API:

### Start Conversation Session
```powershell
# PowerShell
$headers = @{"Authorization"="Bearer YOUR_TOKEN_HERE"}
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/voice/start" `
  -Method POST -ContentType "application/json" `
  -Headers $headers `
  -Body '{"phone_number": "+15551234567", "business_id": "11111111-1111-1111-1111-111111111111"}'
```

### Process User Input
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/voice/process" `
  -Method POST -ContentType "application/json" `
  -Headers $headers `
  -Body '{"session_id": "SESSION_ID", "user_text": "I want to book an appointment"}'
```

---

## 4. Test Complete Flow

### Step-by-Step Manual Test

1. **Create Booking via API**
   ```powershell
   # Get token
   $login = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" `
     -Method POST -ContentType "application/json" `
     -Body '{"email": "admin@demo.com", "password": "admin123"}'
   $token = $login.access_token
   
   # Create booking
   $headers = @{"Authorization"="Bearer $token"}
   Invoke-RestMethod -Uri "http://localhost:8000/api/v1/bookings" `
     -Method POST -ContentType "application/json" `
     -Headers $headers `
     -Body '{"business_id":"11111111-1111-1111-1111-111111111111","start_time":"2026-01-28T10:00:00Z","customer_phone":"+15551234567"}'
   ```

2. **Check Dashboard** - See booking in pending approvals

3. **Approve Booking** - Click approve button

4. **Verify Status Change** - Booking moves to confirmed

---

## 5. Test Voice AI (Requires Setup)

### Prerequisites for Real Voice Calls
1. Twilio account with phone number
2. Ollama installed with model (for LLM)
3. Piper TTS installed (for voice synthesis)

### Quick Ollama Setup (for LLM)
```powershell
# Install Ollama: https://ollama.ai
ollama pull mistral
ollama serve
```

### WebSocket Voice Test
Connect to: `ws://localhost:8000/api/v1/voice/ws/{session_id}`

---

## 6. Database Access

```powershell
# Connect to PostgreSQL
docker compose exec postgres psql -U postgres -d voice_receptionist

# Useful queries
SELECT * FROM bookings;
SELECT * FROM admin_users;
SELECT * FROM services;
SELECT * FROM conversation_sessions;
```

---

## 7. View Logs

```powershell
# API logs
docker compose logs api -f

# All logs
docker compose logs -f
```

---

## Test Checklist

- [ ] Login to dashboard works
- [ ] Create booking via API
- [ ] Booking appears in Dashboard
- [ ] Approve booking works
- [ ] Booking status changes to confirmed
- [ ] Reject booking works
- [ ] Booking filters work on Bookings page
- [ ] Settings page loads

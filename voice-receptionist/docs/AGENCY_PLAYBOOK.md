# Voice AI Agency Playbook 💼

**Goal**: Acquire and onboard your first 3-5 paying clients ($2k-$5k Monthly Revenue).

This guide explains **exactly** how to execute the "Agency Strategy" using the Voice AI system you just built.

---

## 🏗️ Part 1: Technical Setup (The "Silo" Strategy)

For your first 5 clients, **do not** rewrite the code for multi-tenancy. It takes too long.
Instead, use the **Silo Strategy**: Run a separate copy of the software for each client.

### 1. Server Infrastructure
Get a medium-sized VPS (e.g., DigitalOcean Droplet 4GB RAM, ~$24/mo). This can easily host 5-10 clients.

### 2. File Structure
On your server, create separate folders for each client:
```bash
/var/www/
├── client_dentist_a/   # Clone repo here, Run on Port 8001
├── client_spa_b/       # Clone repo here, Run on Port 8002
└── client_hvac_c/      # Clone repo here, Run on Port 8003
```

### 3. Env Configuration
For each client, edit their `.env.production`:
- **Client A**: `PORT=8001`, `DATABASE_URL=.../db_client_a`
- **Client B**: `PORT=8002`, `DATABASE_URL=.../db_client_b`

### 4. Twilio Sub-Accounts (Crucial!)
Don't put all clients on your main Twilio account.
1.  Go to Twilio Console > **Subaccounts**.
2.  Create a "Subaccount" for "Dr. Smith Dentist".
3.  This gives them their own `SID` and `Token`.
4.  **Benefit**: You see *exact* usage costs for Dr. Smith. You can bill them "Cost + 20%".

---

## 🤝 Part 2: The Sales Process

### 1. The Target
Look for businesses that:
1.  Are "High Ticket" (Dentists, Med Spas, Lawyers, HVAC). One missed call = $200+ lost.
2.  Are "High Volume" (Restaurants) - *Harder for v1, stick to appointment-based first.*
3.  Don't answer their phone (Call them at 12:30 PM lunch time. If they miss it, they are a prospect).

### 2. The Pitch (The "Missed Call" Angle)
> *"Hi Dr. Smith, I called you yesterday at lunch to book an appointment, but nobody answered. I ended up calling the guy down the street.*
>
> *I'm a local software developer. I built a system that answers calls 24/7, answers questions, and books appointments into your calendar.*
>
> *Can I give you a demo number to call right now?"*

### 3. The Demo
Give them a phone number connected to a demo version of your software configured as a "Dentist".
*   Let them ask: "How much is a cleaning?"
*   Let them try to book.
*   **The Wow Factor**: Show them the SMS confirmation hitting their phone instantly.

---

## 📝 Part 3: Onboarding Checklist

When they say "Yes", you need 3 things from them:

### A. The "Knowledge Base" Form
Ask them to fill this out so you can update `system_prompt.py`:
1.  **Business Hours**: (e.g., M-F 9-5)
2.  **Services & Prices**: (e.g., Cleaning $100, Whitening $300)
3.  **Cancellation Policy**: (e.g., 24h notice)
4.  **Parking/Location Info**: (e.g., "Park behind the building")

### B. Call Forwarding Setup
Don't port their number yet. Use **Call Forwarding**.
1.  Buy a Twilio Local Number for them.
2.  Tell them: *"On your office phone, set up 'Busy/No Answer Forwarding' to this Twilio number."*
3.  **Result**: If their front desk is busy or closed, *your* AI picks up. Low risk for them!

---

## 💰 Part 4: Pricing Model

### Recommended "Beta" Pricing (First 3 Clients)
*   **Setup Fee**: **$500** (Waived if they sign a 3-month contract).
*   **Monthly Subscription**: **$299/mo** (Cheap! Get testimonials first).
*   **Usage Fees**: Pass on Twilio costs (approx $0.15/min) or include 300 mins for free.

### Recommended "Standard" Pricing (Clients 4+)
*   **Setup Fee**: **$1,500** (Pays for your onboarding time).
*   **Monthly Subscription**: **$499 - $999/mo**.

---

## 🚀 Summary: Zero to $3k/mo

1.  **Deploy** 1 generic "Demo Dentist" version on your server.
2.  **Call** 20 local dentists. "I couldn't reach you."
3.  **Demo** the number.
4.  **Close** 3 of them at $299/mo + Setup.
5.  **Build** 3 folders on your server (`/client1`, `/client2`...).
6.  **Forward** their missed calls to your system.

**Result**: You have a real business with recurring revenue.

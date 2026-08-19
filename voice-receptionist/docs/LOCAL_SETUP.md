# Local Development Setup Guide

## Prerequisites

1. **Docker Desktop** - [Download](https://www.docker.com/products/docker-desktop/)
2. **Node.js 18+** - [Download](https://nodejs.org/)
3. **Python 3.11+** (optional, for running without Docker)

---

## Quick Start (Docker)

### 1. Start Backend Services

```powershell
cd "C:\Users\mhdni\OneDrive\Desktop\Voice AI + Booking Intelligence System\voice-receptionist"

# Windows uses 'docker compose' (no hyphen)
docker compose up -d
```

This starts:
- PostgreSQL (port 5432)
- Redis (port 6379)
- API (port 8000)

### 2. Check Services are Running

```powershell
docker compose ps
```

### 3. Test API Health

```powershell
curl http://localhost:8000/health
# Or open in browser: http://localhost:8000/health
```

### 4. View API Docs

Open: **http://localhost:8000/docs**

---

## Start Admin Dashboard

```powershell
cd admin-dashboard
npm install
npm run dev
```

Open: **http://localhost:3000**

**Demo Login:** `admin@demo.com` / `admin123`

---

## Without Docker (Manual Setup)

### 1. Install PostgreSQL
- Download from https://www.postgresql.org/download/windows/
- Create database: `voice_receptionist`
- Run schema: `psql -d voice_receptionist -f scripts/init_db.sql`

### 2. Create Python Environment

```powershell
cd voice-receptionist
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Configure Environment

```powershell
copy .env.example .env
# Edit .env with your database settings
```

### 4. Run API

```powershell
uvicorn src.api.main:app --reload --port 8000
```

---

## Troubleshooting

### "docker compose" not working?

1. Open Docker Desktop and ensure it's running
2. Check Docker version: `docker --version`
3. If very old, update Docker Desktop

### Port already in use?

```powershell
# Check what's using port 8000
netstat -ano | findstr :8000

# Or change the port
docker compose up -d --scale api=1 -e API_PORT=8001
```

### Database connection failed?

Wait for PostgreSQL to be healthy:
```powershell
docker compose logs postgres
```

---

## Test the Full Flow

1. **API Health**: http://localhost:8000/health
2. **API Docs**: http://localhost:8000/docs
3. **Dashboard**: http://localhost:3000
4. **Login**: admin@demo.com / admin123
5. **Create test booking via API docs**
6. **See it appear in Dashboard**

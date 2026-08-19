# Production Deployment Guide

Complete guide to deploying the Voice AI system to production.

## Prerequisites

- **Server**: Ubuntu 22.04+ LTS (4GB+ RAM recommended)
- **Domain**: DNS pointing to your server
- **Accounts**: Twilio, Deepgram, Cartesia

---

## Quick Start

```bash
# 1. Clone repository
git clone <your-repo> && cd voice-receptionist

# 2. Configure environment
cp .env.production.template .env.production
nano .env.production  # Edit with your values

# 3. Deploy
chmod +x scripts/deploy.sh
./scripts/deploy.sh setup
./scripts/deploy.sh ssl    # Setup SSL
./scripts/deploy.sh deploy
```

---

## Step-by-Step Guide

### 1. Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt install docker-compose-plugin

# Relogin for docker group
exit
```

### 2. Configure Environment

Edit `.env.production` with your actual values:

| Variable | Where to Get |
|----------|--------------|
| `JWT_SECRET_KEY` | `openssl rand -hex 32` |
| `DATABASE_URL` | Use docker db container |
| `TWILIO_ACCOUNT_SID` | [Twilio Console](https://console.twilio.com) |
| `TWILIO_AUTH_TOKEN` | Twilio Console |
| `DEEPGRAM_API_KEY` | [Deepgram Console](https://console.deepgram.com) |
| `CARTESIA_API_KEY` | [Cartesia](https://cartesia.ai) |

### 3. Configure Twilio Webhooks

In Twilio Console, set your phone number's webhook:

| Setting | Value |
|---------|-------|
| Voice URL | `https://yourdomain.com/api/v1/voice/twilio/webhook` |
| Method | POST |

### 4. SSL Certificate

```bash
# Set domain
export VOICE_AI_DOMAIN=yourdomain.com
export CERTBOT_EMAIL=admin@yourdomain.com

# Setup SSL
./scripts/deploy.sh ssl
```

### 5. Deploy

```bash
./scripts/deploy.sh deploy
```

---

## Monitoring

### View Logs

```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# Specific service
docker compose -f docker-compose.prod.yml logs -f api
```

### Health Check

```bash
curl https://yourdomain.com/health
# Expected: {"status": "ok"}
```

### Resource Usage

```bash
docker stats
```

---

## Backup & Restore

### Backup Database

```bash
./scripts/deploy.sh backup
# Creates: backups/db_backup_YYYYMMDD_HHMMSS.sql.gz
```

### Restore Database

```bash
gunzip backups/db_backup_XXXXXX.sql.gz
docker compose -f docker-compose.prod.yml exec -T db \
    psql -U voice_ai voice_receptionist < backups/db_backup_XXXXXX.sql
```

---

## Scaling

### Horizontal Scaling (Multiple API Instances)

```yaml
# docker-compose.prod.yml
services:
  api:
    deploy:
      replicas: 3
```

### GPU for Ollama (Optional)

```bash
docker compose -f docker-compose.prod.yml --profile gpu up -d
```

---

## Troubleshooting

### API Not Starting

```bash
# Check logs
docker compose -f docker-compose.prod.yml logs api

# Common issues:
# - Database connection: Check DATABASE_URL
# - Port already in use: netstat -tlnp | grep 8000
```

### WebSocket Connection Failed

Check nginx config allows WebSocket upgrade:
```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

### Twilio Can't Reach Webhook

1. Verify server is publicly accessible
2. Check SSL certificate is valid
3. Verify firewall allows ports 80, 443

---

## Security Checklist

- [ ] Strong JWT secret key (32+ bytes)
- [ ] Database password rotated
- [ ] SSL/TLS enabled
- [ ] Firewall configured (only 80, 443 open)
- [ ] Rate limiting enabled in nginx
- [ ] Logs rotated

#!/bin/bash
# SSL setup script using Let's Encrypt
# Usage: ./setup_ssl.sh yourdomain.com admin@yourdomain.com

set -e

DOMAIN=$1
EMAIL=$2
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
    echo "Usage: $0 <domain> <email>"
    echo "Example: $0 voice.example.com admin@example.com"
    exit 1
fi

echo "==================================="
echo "SSL Certificate Setup"
echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo "==================================="

# Create required directories
mkdir -p "$PROJECT_DIR/nginx/ssl"
mkdir -p "$PROJECT_DIR/nginx/certbot"

# Update nginx config with actual domain
sed -i "s/yourdomain.com/$DOMAIN/g" "$PROJECT_DIR/nginx/nginx.conf"

# First, start nginx without SSL to complete the ACME challenge
echo ""
echo "Starting nginx for ACME challenge..."
docker run -d --name temp_nginx \
    -p 80:80 \
    -v "$PROJECT_DIR/nginx/certbot:/var/www/certbot" \
    nginx:alpine

# Get certificate
echo ""
echo "Requesting certificate from Let's Encrypt..."
docker run --rm \
    -v "$PROJECT_DIR/nginx/ssl:/etc/letsencrypt" \
    -v "$PROJECT_DIR/nginx/certbot:/var/www/certbot" \
    certbot/certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN"

# Stop temporary nginx
docker stop temp_nginx
docker rm temp_nginx

echo ""
echo "==================================="
echo "✓ SSL certificate installed!"
echo ""
echo "Certificate location: $PROJECT_DIR/nginx/ssl/live/$DOMAIN/"
echo ""
echo "Now run: ./deploy.sh production"
echo "==================================="

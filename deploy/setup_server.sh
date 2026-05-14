#!/bin/bash
# =============================================================================
# AlphaLens — DigitalOcean Droplet Setup Script
# Ubuntu 22.04 LTS, run as root
#
# Usage:
#   ssh root@<your-droplet-ip>
#   curl -fsSL https://raw.githubusercontent.com/SwethaSrinivasan07/AI-Investment-Analyst/main/deploy/setup_server.sh | bash
#
# Or copy this file to the server and run:
#   bash setup_server.sh
# =============================================================================

set -e  # exit on any error

echo "========================================"
echo " AlphaLens Server Setup"
echo "========================================"

# ── 1. System updates ────────────────────────────────────────────────────────
echo "[1/8] Updating system packages..."
apt-get update -qq && apt-get upgrade -y -qq

# ── 2. Install system dependencies ───────────────────────────────────────────
echo "[2/8] Installing Python 3.11, nginx, git..."
apt-get install -y -qq \
    python3.11 python3.11-venv python3.11-dev \
    python3-pip git nginx curl build-essential \
    libssl-dev libffi-dev

# ── 3. Clone the repo ─────────────────────────────────────────────────────────
echo "[3/8] Cloning AlphaLens repository..."
cd /opt
if [ -d "alphalens" ]; then
    echo "  → /opt/alphalens already exists, pulling latest..."
    cd alphalens && git pull
else
    git clone https://github.com/SwethaSrinivasan07/AI-Investment-Analyst.git alphalens
    cd alphalens
fi

# ── 4. Python virtual environment ─────────────────────────────────────────────
echo "[4/8] Creating Python virtual environment..."
python3.11 -m venv /opt/alphalens-venv
source /opt/alphalens-venv/bin/activate
pip install --upgrade pip -q
pip install -r /opt/alphalens/backend/requirements.txt -q
echo "  ✓ Python dependencies installed"

# ── 5. Environment file ───────────────────────────────────────────────────────
echo "[5/8] Setting up environment file..."
if [ ! -f /opt/alphalens/backend/.env ]; then
    cp /opt/alphalens/backend/.env.example /opt/alphalens/backend/.env
    echo ""
    echo "  ⚠️  ACTION REQUIRED: Edit /opt/alphalens/backend/.env and add your API keys."
    echo "  Run: nano /opt/alphalens/backend/.env"
    echo ""
    echo "  Press ENTER once you've saved your .env file to continue..."
    read -r
else
    echo "  → .env already exists, skipping"
fi

# ── 6. Database + RAG ingestion ───────────────────────────────────────────────
echo "[6/8] Initialising database and ingesting SEC filings..."
cd /opt/alphalens/backend
source /opt/alphalens-venv/bin/activate

alembic upgrade head
echo "  ✓ Database migrations applied"

python -m services.rag_service --ingest --tickers AAPL,MSFT,ABBV,JPM,XOM,NVDA,GOOGL,META,JNJ,LLY
echo "  ✓ SEC filings ingested into ChromaDB"

# ── 7. Systemd service ────────────────────────────────────────────────────────
echo "[7/8] Registering AlphaLens as a system service..."
cat > /etc/systemd/system/alphalens.service << 'EOF'
[Unit]
Description=AlphaLens FastAPI Backend
After=network.target

[Service]
User=root
WorkingDirectory=/opt/alphalens/backend
Environment="PATH=/opt/alphalens-venv/bin"
ExecStart=/opt/alphalens-venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable alphalens
systemctl start alphalens
sleep 3

if systemctl is-active --quiet alphalens; then
    echo "  ✓ AlphaLens service is running"
else
    echo "  ✗ Service failed to start. Check logs: journalctl -u alphalens -n 50"
fi

# ── 8. Nginx reverse proxy ────────────────────────────────────────────────────
echo "[8/8] Configuring nginx reverse proxy..."
cat > /etc/nginx/sites-available/alphalens << 'EOF'
server {
    listen 80;
    server_name _;

    # Increase timeouts for long-running memo generation (SSE streams)
    proxy_read_timeout 300s;
    proxy_connect_timeout 75s;
    proxy_send_timeout 300s;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
        proxy_set_header Connection "";

        # Critical for SSE (Server-Sent Events) streaming
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding on;
    }
}
EOF

rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/alphalens /etc/nginx/sites-enabled/alphalens
nginx -t && systemctl restart nginx
echo "  ✓ nginx configured and restarted"

# ── Done ──────────────────────────────────────────────────────────────────────
DROPLET_IP=$(curl -s http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address 2>/dev/null || hostname -I | awk '{print $1}')

echo ""
echo "========================================"
echo " Setup complete!"
echo "========================================"
echo ""
echo "  Backend health check:"
echo "  → http://${DROPLET_IP}/health"
echo ""
echo "  Next steps:"
echo "  1. Verify: curl http://${DROPLET_IP}/health"
echo "  2. In Cloudflare DNS, create an A record:"
echo "        api.yourdomain.com → ${DROPLET_IP}  (Proxied: ON)"
echo "  3. Update backend/.env FRONTEND_URL to your Cloudflare Pages URL"
echo "  4. Restart the service: systemctl restart alphalens"
echo ""
echo "  Useful commands:"
echo "  systemctl status alphalens       # check service status"
echo "  journalctl -u alphalens -f       # tail live logs"
echo "  systemctl restart alphalens      # restart after .env changes"
echo ""

#!/bin/bash
# =============================================================================
# AlphaLens — Pull latest code and restart
# Run on the Droplet whenever you push new code to GitHub
#
# Usage:  bash /opt/alphalens/deploy/update_server.sh
# =============================================================================

set -e

echo "Pulling latest code from GitHub..."
cd /opt/alphalens
git pull

echo "Installing any new Python dependencies..."
source /opt/alphalens-venv/bin/activate
pip install -r backend/requirements.txt -q

echo "Applying database migrations..."
cd backend
alembic upgrade head

echo "Restarting AlphaLens service..."
systemctl restart alphalens
sleep 2
systemctl is-active --quiet alphalens && echo "✓ Service restarted successfully" || echo "✗ Restart failed — check: journalctl -u alphalens -n 30"

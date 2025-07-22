#!/bin/bash
# Installation script for RememBot

set -e

echo "Installing RememBot..."

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root" 
   exit 1
fi

# Create user and group
if ! id "remembot" &>/dev/null; then
    useradd --system --shell /bin/false --home /opt/remembot --create-home remembot
    echo "Created remembot user"
fi

# Create directories
mkdir -p /opt/remembot
mkdir -p /var/lib/remembot
mkdir -p /var/log/remembot

# Set ownership
chown -R remembot:remembot /opt/remembot
chown -R remembot:remembot /var/lib/remembot
chown -R remembot:remembot /var/log/remembot

# Copy application files
cp -r src/ /opt/remembot/
cp pyproject.toml /opt/remembot/

# Install UV if not present
if ! command -v uv &> /dev/null; then
    echo "Installing UV..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Install dependencies
cd /opt/remembot
sudo -u remembot uv sync

# Install systemd service
cp config/remembot.service /etc/systemd/system/
systemctl daemon-reload

echo "Installation complete!"
echo ""
echo "To start RememBot:"
echo "1. Set your Telegram bot token in /etc/systemd/system/remembot.service"
echo "2. Optionally set your OpenAI API key for AI features"
echo "3. Run: systemctl enable remembot"
echo "4. Run: systemctl start remembot"
echo "5. Check status: systemctl status remembot"
echo ""
echo "Logs can be viewed with: journalctl -u remembot -f"
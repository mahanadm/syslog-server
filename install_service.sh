#!/usr/bin/env bash
# Syslog Server - Linux systemd service installer
set -euo pipefail

SERVICE_NAME="syslog-server"
INSTALL_DIR="/opt/syslog-server"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: This script must be run as root (sudo)."
  exit 1
fi

echo
echo "==================================================="
echo "  Syslog Server - Service Installer (Linux)"
echo "==================================================="
echo
echo "Install directory : $INSTALL_DIR"
echo "Service name      : $SERVICE_NAME"
echo

# Copy files
echo "Copying files to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR"/. "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/SyslogServer" 2>/dev/null || true
echo "Files copied OK."

# Write systemd unit
echo "Creating systemd service..."
cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Syslog Server (web UI at http://localhost:8080)
After=network.target

[Service]
Type=simple
ExecStart=$INSTALL_DIR/SyslogServer
WorkingDirectory=$INSTALL_DIR
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=syslog-server

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

echo
STATUS=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "unknown")
echo "Service status: $STATUS"
echo
echo "==================================================="
echo "  Installation complete!"
echo "  Web UI: http://$(hostname -I | awk '{print $1}'):8080"
echo "==================================================="
echo
echo "Useful commands:"
echo "  systemctl status $SERVICE_NAME"
echo "  journalctl -u $SERVICE_NAME -f"
echo

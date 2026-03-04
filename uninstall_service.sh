#!/usr/bin/env bash
# Syslog Server - Linux systemd service uninstaller
set -euo pipefail

SERVICE_NAME="syslog-server"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
INSTALL_DIR="/opt/syslog-server"

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: This script must be run as root (sudo)."
  exit 1
fi

echo
echo "==================================================="
echo "  Syslog Server - Service Uninstaller (Linux)"
echo "==================================================="
echo

if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
  echo "Stopping service..."
  systemctl stop "$SERVICE_NAME"
fi

if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
  echo "Disabling service..."
  systemctl disable "$SERVICE_NAME"
fi

if [[ -f "$UNIT_FILE" ]]; then
  rm "$UNIT_FILE"
  systemctl daemon-reload
  echo "Service unit removed."
fi

read -rp "Remove installed files from $INSTALL_DIR? (y/n): " REMOVE_FILES
if [[ "$REMOVE_FILES" =~ ^[Yy]$ ]]; then
  rm -rf "$INSTALL_DIR"
  echo "Files removed."
fi

echo
echo "Uninstall complete."

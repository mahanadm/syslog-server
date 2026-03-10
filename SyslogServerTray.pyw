"""Syslog Server Tray Manager launcher (no console window).

Double-click this file to start the tray manager without a console.
Uses pythonw.exe automatically due to the .pyw extension.
"""
import sys
import os

# Add src/ to sys.path so imports work without environment variables
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from syslog_server.tray.tray_manager import main

main()

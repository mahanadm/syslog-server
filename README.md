# Syslog Server

A web-based syslog server designed for OT (Operational Technology) networks. Receives, stores, and displays log messages from industrial network devices including Hirschmann, Cisco IOS, and Rockwell Stratix switches.

Access the interface from any browser on your local network — no client software required.

![Web UI — Live View](https://img.shields.io/badge/UI-Browser--based-blue) ![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-green) ![License: MIT](https://img.shields.io/badge/License-MIT-yellow)

---

## Features

- **Real-time live view** — log messages stream to the browser as they arrive via WebSocket
- **Time range selector** — view the last 15 minutes up to all-time history without leaving the live tab
- **Multi-format parsing** — automatically detects RFC 3164, RFC 5424, Cisco IOS (`%FACILITY-SEV-MNEMONIC`), and Hirschmann HiOS bracket formats
- **Hirschmann enrichment** — translates cryptic MIB OID trap values into human-readable descriptions
- **Full-text search** — search across all stored messages with severity, device, and time filters
- **Device management** — auto-discovers devices, supports custom display names, vendor tags, and colour labels
- **Alert rules** — keyword and severity-based rules with configurable cooldown periods
- **Stats dashboard** — message rate, severity breakdown, top devices
- **CSV export** — export any search result to CSV
- **NTP time sync** — configures the Windows Time Service to serve NTP to all devices on the network (UDP 123), keeping switch timestamps in sync with the server
- **Windows service / Linux daemon** — runs in the background, starts automatically on boot
- **LAN accessible** — web UI served on `http://<server-ip>:8080`, reachable from any device on the network

---

## Requirements

- **Python 3.10 or later**
- Windows 10/11 or Linux (Ubuntu 20.04+, Debian, RHEL, etc.)
- Network devices configured to send syslog to this server's IP on **UDP port 1514** (default) or **514**

---

## Windows Installation

### Option A — Run as a Windows Service (recommended for production)

This installs the server so it starts automatically on boot, requires no login, and configures the Windows Time Service to serve NTP to your network devices.

**1. Install Python**

Download and install Python 3.10 or later from [python.org](https://www.python.org/downloads/).
During installation, check **"Add Python to PATH"**.

**2. Clone or download this repository**

```
git clone https://github.com/mahanadm/syslog-server.git
cd syslog-server
```

Or download and extract the ZIP from the GitHub releases page.

**3. Install Python dependencies**

Open a command prompt in the project folder and run:

```bat
pip install -r requirements.txt
```

**4. Run the installer**

Right-click `install_service.bat` and choose **Run as administrator**.

This will:
- Copy files to `C:\Program Files\SyslogServer\`
- Register and start the **SyslogServer** Windows service (auto-start)
- Enable the Windows Time Service (`W32Time`) as an **NTP server** on UDP 123
- Add a Windows Firewall inbound rule for UDP 123
- Open the web UI in your browser

**5. Configure your network devices**

Point your switches' syslog destination to `<this-server-IP>:514` (UDP).
Point their NTP server to `<this-server-IP>` (UDP 123).

**6. Open the web UI**

```
http://<server-ip>:8080
```

---

### Option B — Run manually (development / testing)

```bat
SyslogServer.bat
```

This starts the server in a console window with logging visible.
The web UI is available at `http://localhost:8080`.

> **NTP note:** To enable NTP when running manually, right-click `enable_ntp_server.bat` and choose **Run as administrator** once. This is a one-time setup — it configures the Windows Time Service permanently.

---

### Uninstalling the Windows service

Right-click `uninstall_service.bat` and choose **Run as administrator**.

---

## Linux Installation

### Option A — Run as a systemd service (recommended for production)

**1. Install Python and dependencies**

```bash
sudo apt update && sudo apt install -y python3 python3-pip git   # Debian/Ubuntu
# or
sudo dnf install -y python3 python3-pip git                       # RHEL/Fedora
```

**2. Clone the repository**

```bash
git clone https://github.com/mahanadm/syslog-server.git
cd syslog-server
```

**3. Install Python dependencies**

```bash
pip3 install -r requirements.txt
```

**4. Run the installer**

```bash
sudo bash install_service.sh
```

This will:
- Copy files to `/opt/SyslogServer/`
- Create and enable a **systemd** service unit (`syslog-server.service`)
- Start the service immediately

**5. Configure your network devices**

Point your switches' syslog destination to `<this-server-IP>:514` (UDP).

> **NTP on Linux:** The Linux installer does not configure NTP automatically. If you want this server to also serve NTP, install and configure `chrony` or `ntpsec`:
> ```bash
> sudo apt install chrony
> # Edit /etc/chrony.conf and add: allow 192.168.0.0/16
> sudo systemctl restart chrony
> ```

**6. Open the web UI**

```
http://<server-ip>:8080
```

---

### Option B — Run manually (development / testing)

```bash
PYTHONPATH=src python3 -m syslog_server
```

The web UI is available at `http://localhost:8080`.

---

### Uninstalling the Linux service

```bash
sudo bash uninstall_service.sh
```

---

## Default Ports

| Service    | Port      | Protocol | Notes                          |
|------------|-----------|----------|--------------------------------|
| Web UI     | 8080      | TCP      | Browser access                 |
| Syslog UDP | 514       | UDP      | Configure switches to send here |
| Syslog TCP | disabled  | TCP      | Enable in Settings if needed   |
| NTP        | 123       | UDP      | Windows Time Service (W32Time) |

All ports are configurable from the **Settings** tab in the web UI.

---

## Supported Device Formats

| Vendor / Format  | Detection                          |
|------------------|------------------------------------|
| RFC 5424         | Version digit after PRI field      |
| RFC 3164         | BSD timestamp format               |
| Cisco IOS        | `%FACILITY-SEVERITY-MNEMONIC`      |
| Hirschmann HiOS  | `[APPNAME TASKNAME TASKID]` brackets |

---

## Project Structure

```
syslog-server/
├── src/syslog_server/
│   ├── app.py                  FastAPI application
│   ├── core/                   Config, dispatcher, message types
│   ├── network/                UDP/TCP/TLS listeners, NTP server
│   ├── parser/                 Format detection and parsers
│   ├── storage/                SQLite database, file writer
│   ├── web/
│   │   ├── api/                REST API endpoints
│   │   ├── ws/                 WebSocket live stream
│   │   └── static/             Single-page web UI (Alpine.js + Tailwind)
│   └── alerts/                 Alert engine and notification history
├── install_service.bat         Windows service installer
├── uninstall_service.bat       Windows service uninstaller
├── install_service.sh          Linux systemd installer
├── uninstall_service.sh        Linux systemd uninstaller
├── enable_ntp_server.bat       One-time NTP setup for dev/manual installs
├── SyslogServer.bat            Dev launcher (Windows)
├── build.bat                   PyInstaller build script
└── requirements.txt
```

---

## License

MIT

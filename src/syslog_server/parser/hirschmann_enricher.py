"""Hirschmann message enricher — translates cryptic MIB OID values to human-readable text.

Hirschmann switches send SNMP trap notifications via syslog with raw MIB object names
and numeric values that are meaningless without the MIB documentation. This module
translates those into plain English descriptions.

Example:
    Input:  "hm2ConfigurationChangedTrap: hm2FMNvmState.0=1"
    Output: "Configuration Changed: NVM state = out of sync (unsaved changes)"
"""

from __future__ import annotations

import re

# --- Trap name translations ---
# Maps Hirschmann trap OID names to human-readable event descriptions

TRAP_NAMES: dict[str, str] = {
    # Configuration management
    "hm2ConfigurationChangedTrap": "Configuration Changed",
    "hm2ConfigurationSavedTrap": "Configuration Saved",
    # Web interface
    "hm2WebLoginSuccessTrap": "Web Login Success",
    "hm2WebLoginFailedTrap": "Web Login Failed",
    "hm2WebLogoutTrap": "Web Logout",
    # Authentication
    "hm2AuthenticationSuccessTrap": "Authentication Success",
    "hm2AuthenticationFailureTrap": "Authentication Failure",
    "hm2LoginTrap": "User Login",
    "hm2LogoutTrap": "User Logout",
    # Link state
    "linkUp": "Link Up",
    "linkDown": "Link Down",
    # Port security
    "hm2PortSecurityTrap": "Port Security Violation",
    "hm2PortSecurityPermittedMacTrap": "Port Security: MAC Permitted",
    "hm2PortSecurityDeniedMacTrap": "Port Security: MAC Denied",
    # Redundancy / Ring
    "hm2MrpRedundancyLossTrap": "MRP Ring: Redundancy Lost",
    "hm2MrpRedundancyRestoredTrap": "MRP Ring: Redundancy Restored",
    "hm2MrpTopologyChangeTrap": "MRP Ring: Topology Change",
    # Power
    "hm2PsuStateTrap": "Power Supply State Change",
    "hm2PsuFailureTrap": "Power Supply Failure",
    # Temperature
    "hm2TempWarningTrap": "Temperature Warning",
    "hm2TempCriticalTrap": "Temperature Critical",
    # Firmware
    "hm2FirmwareUpdateTrap": "Firmware Update",
    # STP / RSTP
    "newRoot": "STP: New Root Bridge",
    "topologyChange": "STP: Topology Change",
    # SNMP
    "authenticationFailure": "SNMP Authentication Failure",
    # Signal contact / relay
    "hm2SignalContactTrap": "Signal Contact State Change",
    # PoE (Power over Ethernet)
    "pethPsePortOnOffNotification": "PoE: Port Power State Change",
    "pethMainPseUsageOnNotification": "PoE: Main PSE Usage On",
}

# --- OID value translations ---
# Maps specific OID names to their possible values with human-readable descriptions

OID_VALUES: dict[str, dict[str, str]] = {
    # NVM (Non-Volatile Memory) state
    "hm2FMNvmState": {
        "0": "in sync",
        "1": "out of sync (unsaved changes)",
        "2": "out of sync (changes pending)",
        "3": "in sync (saved to NVM)",
    },
    # ENVM (External NVM) state
    "hm2FMEnvmState": {
        "0": "in sync",
        "1": "out of sync (unsaved changes)",
        "2": "out of sync (changes pending)",
        "3": "in sync (saved to ENVM)",
    },
    # Port admin state
    "ifAdminStatus": {
        "1": "enabled",
        "2": "disabled",
        "3": "testing",
    },
    # Port operational state
    "ifOperStatus": {
        "1": "up",
        "2": "down",
        "3": "testing",
        "4": "unknown",
        "5": "dormant",
        "6": "not present",
        "7": "lower layer down",
    },
    # Interface type
    "ifType": {
        "6": "ethernet",
        "24": "loopback",
        "53": "virtual",
        "161": "ieee8023adLag",
    },
    # Inet address type
    "hm2WebLastLoginInetAddressType": {
        "0": "unknown",
        "1": "IPv4",
        "2": "IPv6",
    },
    # PSU (Power Supply Unit) state
    "hm2PsuState": {
        "1": "present and OK",
        "2": "present but failed",
        "3": "not present",
        "4": "not installed",
    },
    # Signal contact state
    "hm2SignalContactState": {
        "1": "open",
        "2": "closed",
    },
    # MRP ring state
    "hm2MrpDomainState": {
        "1": "open (no redundancy)",
        "2": "closed (redundant)",
    },
}

# Pattern to match OID=value pairs like "hm2FMNvmState.0=1"
_OID_VALUE_PATTERN = re.compile(r"(\w+)\.(\d+)=(\S+)")


def enrich_message(message: str) -> str:
    """Translate Hirschmann MIB values in a syslog message to human-readable text.

    Processes the message in two passes:
    1. Replace trap names (e.g., hm2ConfigurationChangedTrap → Configuration Changed)
    2. Replace OID=value pairs (e.g., hm2FMNvmState.0=1 → NVM state.0 = out of sync)

    The original raw message is preserved in the SyslogMessage.raw field.
    """
    if not message:
        return message

    enriched = message

    # Pass 1: Replace trap name at the start (before the colon)
    colon_pos = enriched.find(":")
    if colon_pos > 0:
        trap_name = enriched[:colon_pos].strip()
        if trap_name in TRAP_NAMES:
            enriched = TRAP_NAMES[trap_name] + enriched[colon_pos:]

    # Pass 2: Replace OID.instance=value with readable text
    def replace_oid(match: re.Match) -> str:
        oid_name = match.group(1)
        instance = match.group(2)
        value = match.group(3)

        if oid_name in OID_VALUES:
            value_map = OID_VALUES[oid_name]
            readable_value = value_map.get(value, value)
            # Use a friendlier OID name if available
            friendly_name = _friendly_oid_name(oid_name)
            return f"{friendly_name}.{instance} = {readable_value}"

        # For IP addresses stored as OID values, keep them as-is
        return match.group(0)

    enriched = _OID_VALUE_PATTERN.sub(replace_oid, enriched)

    return enriched


def _friendly_oid_name(oid_name: str) -> str:
    """Convert a Hirschmann OID name to a friendlier display name."""
    friendly_names = {
        "hm2FMNvmState": "NVM state",
        "hm2FMEnvmState": "External NVM state",
        "ifAdminStatus": "Admin status",
        "ifOperStatus": "Oper status",
        "ifType": "Interface type",
        "hm2WebLastLoginInetAddressType": "Login address type",
        "hm2WebLastLoginInetAddress": "Login IP",
        "hm2WebLastLoginUserName": "Username",
        "hm2WebLastLogoutUserName": "Username",
        "hm2PsuState": "PSU state",
        "hm2SignalContactState": "Signal contact",
        "hm2MrpDomainState": "MRP ring state",
    }
    return friendly_names.get(oid_name, oid_name)

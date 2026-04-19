"""
Central configuration for NetPulse.

All paths, environment variables, and constants are resolved here.
Other modules import from this file — they never read env vars or
construct paths themselves.

Credentials come exclusively from the .env file (loaded by python-dotenv).
No default credentials are provided; missing values result in an explicit
EnvironmentError when a connection is first attempted (see ssh_client.py).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent.parent
INVENTORY_PATH = BASE_DIR / "inventory" / "devices.yaml"
BACKUP_DIR     = BASE_DIR / "output" / "backups"
LOG_DIR        = BASE_DIR / "output" / "logs"
LOG_FILE       = LOG_DIR / "netpulse.log"
SSOT_DIR       = BASE_DIR / "ssot"   # expected-state YAML files for audit intents

# Create output directories on first import so jobs never have to check.
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── SSH credentials ────────────────────────────────────────────────────────────
# Read from .env only. Empty string means "not set" — checked in ssh_client.py.
SSH_USERNAME: str = os.getenv("NETPULSE_USERNAME", "")
SSH_PASSWORD: str = os.getenv("NETPULSE_PASSWORD", "")
SSH_SECRET:   str = os.getenv("NETPULSE_SECRET", "")   # enable secret; optional
SSH_TIMEOUT:  int = int(os.getenv("NETPULSE_SSH_TIMEOUT", "30"))
SSH_PORT:     int = int(os.getenv("NETPULSE_SSH_PORT", "22"))

# ── Execution ──────────────────────────────────────────────────────────────────
# Maximum concurrent SSH threads for multi-device jobs (scope=all / scope=role).
# Raise if your inventory is large and the server can support more connections.
SSH_WORKERS: int = int(os.getenv("NETPULSE_SSH_WORKERS", "10"))

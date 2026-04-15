"""
Central configuration for NetPulse.

All paths, environment variables, and constants are resolved here.
Other modules import from this file instead of reading env vars directly.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
INVENTORY_PATH = BASE_DIR / "inventory" / "devices.yaml"
BACKUP_DIR = BASE_DIR / "output" / "backups"
LOG_DIR = BASE_DIR / "output" / "logs"
LOG_FILE = LOG_DIR / "netpulse.log"

# Ensure output directories exist on import
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── SSH credentials (read from .env, never hardcoded) ─────────────────────────
SSH_USERNAME: str = os.getenv("NETPULSE_USERNAME", "")
SSH_PASSWORD: str = os.getenv("NETPULSE_PASSWORD", "")
SSH_SECRET: str = os.getenv("NETPULSE_SECRET", "")
SSH_TIMEOUT: int = int(os.getenv("NETPULSE_SSH_TIMEOUT", "30"))
SSH_PORT: int = int(os.getenv("NETPULSE_SSH_PORT", "22"))

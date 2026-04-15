"""
Inventory loader for NetPulse.

Reads devices.yaml and returns Device objects keyed by device name.
All other modules receive Device objects — they never read YAML directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import yaml

from app.config import INVENTORY_PATH
from app.logger import get_logger
from app.models import Device

logger = get_logger(__name__)


def load_inventory(path: Path = INVENTORY_PATH) -> Dict[str, Device]:
    """
    Load and validate the device inventory from a YAML file.

    Returns a dict keyed by device name.
    Raises FileNotFoundError or yaml.YAMLError on read/parse failure.
    Skips malformed entries with a warning rather than crashing.
    """
    try:
        with open(path, "r") as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"Inventory file not found: {path}")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse inventory YAML: {e}")
        raise

    devices: Dict[str, Device] = {}
    for entry in raw.get("devices", []):
        try:
            device = Device(**entry)
            devices[device.name] = device
        except Exception as e:
            logger.warning(f"Skipping invalid inventory entry {entry}: {e}")

    logger.info(f"Loaded {len(devices)} devices from {path}")
    return devices


def get_device(name: str, inventory: Dict[str, Device]) -> Device:
    """Look up a single device by name. Raises ValueError if not found."""
    if name not in inventory:
        raise ValueError(
            f"Device '{name}' not found in inventory.\n"
            f"Known devices: {list(inventory.keys())}"
        )
    return inventory[name]


def get_all_devices(inventory: Dict[str, Device]) -> List[Device]:
    """Return all devices from the inventory as a list."""
    return list(inventory.values())

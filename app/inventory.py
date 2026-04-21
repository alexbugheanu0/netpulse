"""
Inventory loader for NetPulse.

Reads inventory/devices.yaml and returns Device objects keyed by device name.
All other modules receive Device objects — they never read YAML directly.

TODO (SNMP enrichment): After loading, enrich devices where snmp_enabled=true
by calling snmp_client.get_sys_descr() to verify reachability before SSH jobs run.
"""

from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from app.config import INVENTORY_PATH
from app.logger import get_logger
from app.models import Device

logger = get_logger(__name__)


def load_inventory(path: Path = INVENTORY_PATH) -> dict[str, Device]:
    """
    Load and validate the device inventory from a YAML file.

    Returns a dict keyed by device name (e.g. {"sw-core-01": Device(...)}).
    Raises FileNotFoundError or yaml.YAMLError on read/parse failure.
    Malformed entries are skipped with a warning rather than crashing.
    """
    try:
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error(f"Inventory file not found: {path}")
        raise
    except yaml.YAMLError as exc:
        logger.error(f"Failed to parse inventory YAML: {exc}")
        raise

    devices: dict[str, Device] = {}
    for entry in raw.get("devices", []):
        try:
            device = Device(**entry)
            if device.name in devices:
                logger.warning(
                    f"Duplicate device name '{device.name}' in inventory — "
                    "second entry overwrites the first."
                )
            devices[device.name] = device
        except Exception as exc:
            logger.warning(f"Skipping invalid inventory entry {entry}: {exc}")

    logger.info(f"Loaded {len(devices)} device(s) from {path}")
    return devices


def get_device(name: str, inventory: dict[str, Device]) -> Device:
    """Look up a single device by name. Raises ValueError if not found."""
    if name not in inventory:
        raise ValueError(
            f"Device '{name}' not found in inventory.\n"
            f"Known devices: {list(inventory.keys())}"
        )
    return inventory[name]


def get_all_devices(inventory: dict[str, Device]) -> list[Device]:
    """Return all SSH-enabled devices from inventory.

    Filters for ssh_enabled=True to match the behaviour of
    get_devices_by_role() and avoid silently attempting SSH connections
    against devices that are not eligible for them.
    """
    return [d for d in inventory.values() if d.ssh_enabled]


def get_devices_by_role(role: str, inventory: dict[str, Device]) -> list[Device]:
    """Return all SSH-enabled devices that match the given role."""
    return [d for d in inventory.values() if d.role == role and d.ssh_enabled]


def check_reachability(
    inventory: dict[str, Device],
    port: int = 22,
    timeout: float = 2.0,
) -> dict[str, bool]:
    """
    TCP connect check for each device on the given port (default: 22).

    Runs checks in parallel — safe to call on large inventories.
    Returns {device_name: reachable (bool)}.
    """
    def _probe(name: str, ip: str) -> tuple[str, bool]:
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return name, True
        except OSError:
            return name, False

    workers = min(len(inventory), 20)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_probe, name, device.ip)
            for name, device in inventory.items()
        ]
        return dict(f.result() for f in futures)

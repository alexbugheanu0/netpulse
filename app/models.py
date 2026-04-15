"""
Pydantic data models for NetPulse.

These models enforce type safety and validation at every layer of the app.
TODO (OpenClaw integration): IntentRequest and JobResult can be serialized
to JSON and passed directly to OpenClaw as structured tool call inputs/outputs.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class IntentType(str, Enum):
    SHOW_INTERFACES = "show_interfaces"
    SHOW_VLANS = "show_vlans"
    SHOW_TRUNKS = "show_trunks"
    SHOW_VERSION = "show_version"
    BACKUP_CONFIG = "backup_config"
    HEALTH_CHECK = "health_check"


class ScopeType(str, Enum):
    SINGLE = "single"
    ALL = "all"


class Device(BaseModel):
    """Represents a single network device from inventory."""

    name: str
    hostname: str
    ip: str
    platform: str
    role: str
    ssh_enabled: bool = True
    snmp_enabled: bool = False


class IntentRequest(BaseModel):
    """
    A validated, structured intent derived from a natural language query
    or explicit CLI flags.
    """

    intent: IntentType
    device: Optional[str] = None
    scope: ScopeType = ScopeType.SINGLE
    raw_query: str = ""
    confirmation_required: bool = False


class JobResult(BaseModel):
    """
    The result of executing a single job against a single device.
    Returned by every job module's run() function.
    """

    success: bool
    device: str
    intent: str
    command_executed: str
    parsed_data: Optional[Any] = None
    raw_output: str = ""
    error: Optional[str] = None

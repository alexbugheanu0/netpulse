"""
Shared execution engine for NetPulse.

Both main.py (CLI) and openclaw_adapter.py use this module.
It is the single source of truth for how intents map to jobs.

Flow:
    validated IntentRequest + inventory
        → resolve target devices by scope
        → dispatch correct job per device (with timing)
        → return list[JobResult]

IMPORTANT: Callers must call validate_request(req, inventory) BEFORE execute().
This keeps validation and execution as separate, explicit steps.

To add a new intent:
    1. Create app/jobs/your_job.py with run(device) -> JobResult
    2. Add it to JOB_MAP below
    3. Register the IntentType in app/models.py and app/intents.py
"""

from __future__ import annotations

import time
from typing import Callable

from app.inventory import get_all_devices, get_device, get_devices_by_role
from app.logger import get_logger
from app.models import IntentRequest, IntentType, JobResult, ScopeType

from app.jobs import (
    add_vlan,
    audit_trunks,
    audit_vlans,
    backup_config,
    device_facts,
    diff_backup,
    drift_check,
    health_check,
    no_shutdown_interface,
    ping,
    remove_vlan,
    set_interface_vlan,
    show_arp,
    show_cdp,
    show_errors,
    show_etherchannel,
    show_interfaces,
    show_logging,
    show_mac,
    show_port_security,
    show_route,
    show_spanning_tree,
    show_trunks,
    show_version,
    show_vlans,
    shutdown_interface,
)

logger = get_logger(__name__)

# Maps every supported intent to its job module's run(device) function.
# Ping is handled separately (needs ping_target from the request).
JOB_MAP: dict[IntentType, Callable] = {
    IntentType.SHOW_INTERFACES:    show_interfaces.run,
    IntentType.SHOW_VLANS:         show_vlans.run,
    IntentType.SHOW_TRUNKS:        show_trunks.run,
    IntentType.SHOW_VERSION:       show_version.run,
    IntentType.SHOW_ERRORS:        show_errors.run,
    IntentType.SHOW_CDP:           show_cdp.run,
    IntentType.SHOW_MAC:           show_mac.run,
    IntentType.SHOW_SPANNING_TREE: show_spanning_tree.run,
    IntentType.BACKUP_CONFIG:      backup_config.run,
    IntentType.DIFF_BACKUP:        diff_backup.run,
    IntentType.HEALTH_CHECK:       health_check.run,
    # L3 and advanced diagnostic intents
    IntentType.SHOW_ROUTE:         show_route.run,
    IntentType.SHOW_ARP:           show_arp.run,
    IntentType.SHOW_ETHERCHANNEL:  show_etherchannel.run,
    IntentType.SHOW_PORT_SECURITY: show_port_security.run,
    IntentType.SHOW_LOGGING:       show_logging.run,
    # SSOT audit intents
    IntentType.AUDIT_VLANS:        audit_vlans.run,
    IntentType.AUDIT_TRUNKS:       audit_trunks.run,
    IntentType.DEVICE_FACTS:       device_facts.run,
    IntentType.DRIFT_CHECK:        drift_check.run,
    # Write / config-push intents — dispatched via lambdas in execute() to
    # inject write params; entries here keep the registry complete.
    IntentType.ADD_VLAN:              add_vlan.run,
    IntentType.REMOVE_VLAN:           remove_vlan.run,
    IntentType.SHUTDOWN_INTERFACE:    shutdown_interface.run,
    IntentType.NO_SHUTDOWN_INTERFACE: no_shutdown_interface.run,
    IntentType.SET_INTERFACE_VLAN:    set_interface_vlan.run,
}


def _timed_run(job_fn: Callable, device) -> JobResult:
    """Run job_fn(device) and attach wall-clock elapsed_ms to the result."""
    start   = time.monotonic()
    result  = job_fn(device)
    elapsed = (time.monotonic() - start) * 1000
    return result.model_copy(update={"elapsed_ms": round(elapsed, 1)})


def execute(req: IntentRequest, inventory: dict) -> list[JobResult]:
    """
    Dispatch a pre-validated IntentRequest and return timed JobResult objects.

    Caller is responsible for calling validate_request(req, inventory) first.

    Steps:
        1. Build the job function (ping is special — injects ping_target)
        2. Resolve target device(s) based on scope
        3. Run each job with timing; collect results

    All per-device SSH or I/O errors are caught inside each job module and
    returned as JobResult(success=False, error=...) — they do not propagate here.
    """
    # Special cases: intents that inject extra parameters at call time
    if req.intent == IntentType.PING:
        job_fn: Callable = lambda device: ping.run(device, req.ping_target)
    elif req.intent == IntentType.ADD_VLAN:
        job_fn = lambda device: add_vlan.run(device, req.vlan_id, req.vlan_name)
    elif req.intent == IntentType.REMOVE_VLAN:
        job_fn = lambda device: remove_vlan.run(device, req.vlan_id)
    elif req.intent == IntentType.SHUTDOWN_INTERFACE:
        job_fn = lambda device: shutdown_interface.run(device, req.interface)
    elif req.intent == IntentType.NO_SHUTDOWN_INTERFACE:
        job_fn = lambda device: no_shutdown_interface.run(device, req.interface)
    elif req.intent == IntentType.SET_INTERFACE_VLAN:
        job_fn = lambda device: set_interface_vlan.run(device, req.interface, req.vlan_id)
    else:
        job_fn = JOB_MAP[req.intent]

    # Resolve target devices based on scope
    if req.scope == ScopeType.ALL:
        devices = get_all_devices(inventory)
    elif req.scope == ScopeType.ROLE:
        devices = get_devices_by_role(req.role, inventory)  # type: ignore[arg-type]
    else:
        devices = [get_device(req.device, inventory)]  # type: ignore[arg-type]

    logger.info(
        f"execute: intent={req.intent.value}, scope={req.scope.value}, "
        f"devices={[d.name for d in devices]}"
    )

    return [_timed_run(job_fn, device) for device in devices]

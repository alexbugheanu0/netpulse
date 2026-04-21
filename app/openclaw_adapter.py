"""
OpenClaw adapter for NetPulse.

This is the ONLY entry point OpenClaw should use. It accepts structured JSON,
routes through the existing NetPulse execution engine, and returns clean JSON.

OpenClaw must NEVER:
  - generate raw Cisco CLI commands
  - bypass this adapter to call ssh_client directly
  - pass user free-text to intents.py (it must classify first)

Call modes:
    # Explicit JSON string
    python3 -m app.openclaw_adapter --json '{"intent": "show_vlans", "device": "sw-core-01"}'

    # JSON from stdin (pipe-friendly)
    echo '{"intent": "health_check", "scope": "all"}' | python3 -m app.openclaw_adapter

Request → Response flow:
    OpenClaw JSON
        → schema validation (OpenClawRequest)
        → allowlist check
        → load_inventory()
        → validate_request()          ← existing validators.py
        → executor.execute()          ← existing job dispatch (ssh_client → device)
        → list[JobResult]
        → summarize() per result      ← chat-friendly summary string
        → OpenClawResponse JSON

TODO (OpenClaw integration): Map OpenClaw tool call arguments directly to
OpenClawRequest fields. The function run_openclaw(payload) is the tool handler.

TODO (approval workflow for write actions): Before executing backup_config (or
any future write intent), insert an approval checkpoint here. OpenClaw presents
the proposed action in chat; only call executor.execute() after "confirm".

TODO (Telegram/OpenClaw channel integration): Route channel messages through
OpenClaw's intent classifier, then call this adapter with the classified intent.
The raw user message should never reach NetPulse directly.

TODO (SNMP enrichment): Before execution, optionally call snmp_client functions
to add live interface counters or sysDescr to the response context.

TODO (Ansible execution path): For future config-push operations, route the
intent here to an Ansible runner rather than Netmiko SSH. NetPulse stays
read-only; Ansible handles approved write actions.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any, Optional

from pydantic import BaseModel, ValidationError

from app import executor
from app.inventory import load_inventory
from app.logger import get_logger
from app.models import IntentRequest, IntentType, JobResult, ScopeType
from app.query_filter import FILTERABLE_INTENTS, apply_query
from app.summarizer import summarize
from app.validators import validate_request

logger = get_logger("netpulse.openclaw")

# Default sample size returned to OpenClaw when verbose=False. The summary
# normally contains the answer; parsed_data is a small sample for the agent
# to inspect. Set verbose=True to opt out of truncation.
PARSED_DATA_SAMPLE_SIZE = 10

# ── Allowlist ──────────────────────────────────────────────────────────────────
# Intents exposed to OpenClaw. Read-only intents run freely; write intents
# require the agent to obtain explicit Telegram confirmation first (enforced
# in SKILL.md — the adapter executes only after the user confirms).
OPENCLAW_ALLOWED_INTENTS: frozenset[IntentType] = frozenset({
    # Operational show intents
    IntentType.SHOW_INTERFACES,
    IntentType.SHOW_VLANS,
    IntentType.SHOW_TRUNKS,
    IntentType.SHOW_VERSION,
    IntentType.SHOW_ERRORS,
    IntentType.SHOW_CDP,
    IntentType.SHOW_MAC,
    IntentType.SHOW_SPANNING_TREE,
    # L3 and advanced diagnostics
    IntentType.SHOW_ROUTE,
    IntentType.SHOW_ARP,
    IntentType.SHOW_ETHERCHANNEL,
    IntentType.SHOW_PORT_SECURITY,
    IntentType.SHOW_LOGGING,
    # Backup and health
    IntentType.BACKUP_CONFIG,
    IntentType.DIFF_BACKUP,
    IntentType.HEALTH_CHECK,
    IntentType.PING,
    # SSOT audit intents
    IntentType.AUDIT_VLANS,
    IntentType.AUDIT_TRUNKS,
    IntentType.DEVICE_FACTS,
    IntentType.DRIFT_CHECK,
    # Write / config-push intents (scope=single only; Telegram approval required)
    IntentType.ADD_VLAN,
    IntentType.REMOVE_VLAN,
    IntentType.SHUTDOWN_INTERFACE,
    IntentType.NO_SHUTDOWN_INTERFACE,
    IntentType.SET_INTERFACE_VLAN,
})

# Write intents that modify device config — the agent MUST obtain explicit
# user confirmation in chat before calling the adapter with any of these.
WRITE_INTENTS: frozenset[IntentType] = frozenset({
    IntentType.ADD_VLAN,
    IntentType.REMOVE_VLAN,
    IntentType.SHUTDOWN_INTERFACE,
    IntentType.NO_SHUTDOWN_INTERFACE,
    IntentType.SET_INTERFACE_VLAN,
})

# Valid scope strings — checked explicitly before ScopeType conversion
_VALID_SCOPES: frozenset[str] = frozenset(s.value for s in ScopeType)


# ── Request / Response models ──────────────────────────────────────────────────

class OpenClawRequest(BaseModel):
    """
    Structured JSON payload sent by OpenClaw to NetPulse.

    OpenClaw must classify the user request into one of the allowed intents
    before calling this adapter. It must NOT forward raw user text as intent.

    Write intents (add_vlan, remove_vlan, shutdown_interface,
    no_shutdown_interface, set_interface_vlan) require the additional fields
    below and must only be sent after the user confirms the action in chat.
    """

    intent:    str               # must be in OPENCLAW_ALLOWED_INTENTS
    device:    Optional[str] = None
    scope:     str = "single"   # "single" | "all" | "role"
    role:      Optional[str] = None
    raw_query: str = ""          # original user message; logged for audit only
    # Token-saving knobs — see SKILL.md for full documentation
    query:   Optional[str] = None  # server-side filter for show_arp/_mac/_route/etc.
    verbose: bool = False          # when True, return full parsed_data (no truncation)
    # Write intent parameters (ignored for read-only intents)
    vlan_id:   Optional[int] = None   # add_vlan, remove_vlan, set_interface_vlan
    vlan_name: Optional[str] = None   # add_vlan
    interface: Optional[str] = None   # shutdown_interface, no_shutdown_interface, set_interface_vlan


class OpenClawResult(BaseModel):
    """
    Result for a single device, shaped for chat/API consumption.

    `parsed_data` is truncated to PARSED_DATA_SAMPLE_SIZE rows by default to
    keep Telegram round-trips small. Callers wanting the full table set
    `verbose: true` in the request; filter-style lookups should use `query`
    to get exactly the rows they need.
    """

    device:                  str
    success:                 bool
    summary:                 str  # one-line, chat-ready — send this to the user
    parsed_data:             Optional[Any] = None
    parsed_data_truncated:   bool = False
    parsed_data_total_rows:  Optional[int] = None
    elapsed_ms:              Optional[float] = None
    error:                   Optional[str]   = None


class OpenClawResponse(BaseModel):
    """
    Full response returned to OpenClaw.

    'success' is True only if ALL device results succeeded.
    'error' is set only for pre-execution failures (bad schema, validation,
    inventory problems). Per-device SSH failures appear in results[n].error.
    `aggregate_summary` is populated only for multi-device responses so the
    agent can reply with a single line instead of iterating every result.
    """

    success:            bool
    intent:             str
    scope:              str
    results:            list[OpenClawResult]
    aggregate_summary:  Optional[str] = None
    error:              Optional[str] = None


# ── Core adapter function ──────────────────────────────────────────────────────

def run_openclaw(payload: dict) -> dict:
    """
    Main entry point for OpenClaw integration.

    Accepts a raw dict (parsed JSON), returns a dict (serialised as JSON).
    Never raises — every error is captured in the response envelope.

    Importable as a Python tool call handler:
        from app.openclaw_adapter import run_openclaw
        response = run_openclaw({"intent": "show_vlans", "device": "sw-core-01"})
    """
    _t0        = time.monotonic()
    intent_str = payload.get("intent", "unknown")
    scope_str  = payload.get("scope",  "single")

    # ── Step 1: validate request schema ───────────────────────────────────────
    try:
        oc_req = OpenClawRequest(**payload)
    except ValidationError as exc:
        # Extract the first field error only — Pydantic's full message is too verbose
        errors    = exc.errors()
        first     = errors[0] if errors else {}
        field     = ".".join(str(l) for l in first.get("loc", ["?"]))
        msg       = first.get("msg", "validation error")
        human_msg = f"Field '{field}': {msg}."
        # Log only safe fields — never log the raw payload in case callers add extra keys
        logger.warning(
            f"Schema validation failed: {human_msg} "
            f"(intent={intent_str!r}, scope={scope_str!r})"
        )
        return _err(intent_str, scope_str, human_msg)

    _is_write = intent_str in {i.value for i in WRITE_INTENTS}
    # Truncate raw_query before logging — it contains the verbatim user
    # message from Telegram which may include sensitive information.
    _safe_query = (
        oc_req.raw_query[:80] + "…" if len(oc_req.raw_query) > 80
        else oc_req.raw_query
    )
    logger.info(
        f"OpenClaw request — intent={oc_req.intent!r}, scope={oc_req.scope!r}, "
        f"device={oc_req.device!r}, role={oc_req.role!r}, "
        f"query={oc_req.query!r}, verbose={oc_req.verbose!r}, "
        f"raw_query={_safe_query!r}"
        + (
            f", vlan_id={oc_req.vlan_id!r}, vlan_name={oc_req.vlan_name!r}, "
            f"interface={oc_req.interface!r} [WRITE]"
            if _is_write else ""
        )
    )

    # `query` is only meaningful on filterable intents; log a gentle note so
    # the agent can learn when it is wasting a field, but do not error out.
    if oc_req.query and oc_req.intent not in FILTERABLE_INTENTS:
        logger.info(
            f"query={oc_req.query!r} ignored — intent {oc_req.intent!r} is not filterable"
        )

    # ── Step 2: validate scope value ──────────────────────────────────────────
    if oc_req.scope not in _VALID_SCOPES:
        msg = (
            f"Invalid scope '{oc_req.scope}'. "
            f"Valid values: {', '.join(sorted(_VALID_SCOPES))}."
        )
        logger.warning(msg)
        return _err(oc_req.intent, oc_req.scope, msg)

    # ── Step 3: check intent allowlist ────────────────────────────────────────
    try:
        intent_type = IntentType(oc_req.intent)
    except ValueError:
        msg = (
            f"'{oc_req.intent}' is not a recognised NetPulse intent. "
            f"Allowed via OpenClaw: {sorted(i.value for i in OPENCLAW_ALLOWED_INTENTS)}."
        )
        logger.warning(f"Unknown intent blocked: {oc_req.intent!r}")
        return _err(oc_req.intent, oc_req.scope, msg)

    if intent_type not in OPENCLAW_ALLOWED_INTENTS:
        msg = (
            f"Intent '{oc_req.intent}' is not permitted via OpenClaw. "
            f"Allowed: {sorted(i.value for i in OPENCLAW_ALLOWED_INTENTS)}."
        )
        logger.warning(f"Disallowed intent blocked: {oc_req.intent!r}")
        return _err(oc_req.intent, oc_req.scope, msg)

    # ── Step 4: load inventory ─────────────────────────────────────────────────
    try:
        inventory = load_inventory()
    except FileNotFoundError as exc:
        logger.error(f"Inventory file not found: {exc}")
        return _err(oc_req.intent, oc_req.scope, f"Inventory file not found: {exc}.")
    except Exception as exc:
        logger.error(f"Inventory load failed: {exc}")
        return _err(oc_req.intent, oc_req.scope, f"Failed to load inventory: {exc}.")

    # ── Step 5: build IntentRequest and validate ───────────────────────────────
    intent_req = IntentRequest(
        intent=intent_type,
        device=oc_req.device,
        scope=ScopeType(oc_req.scope),
        role=oc_req.role,
        raw_query=oc_req.raw_query or f"openclaw:{oc_req.intent}",
        # Write intent parameters — None for read-only intents
        vlan_id=oc_req.vlan_id,
        vlan_name=oc_req.vlan_name,
        interface=oc_req.interface,
    )

    try:
        validate_request(intent_req, inventory)
    except ValueError as exc:
        logger.warning(f"Validation failed: {exc}")
        return _err(oc_req.intent, oc_req.scope, str(exc))

    logger.info("Validation passed — dispatching to executor")

    # ── Step 6: execute ────────────────────────────────────────────────────────
    try:
        results: list[JobResult] = executor.execute(intent_req, inventory)
    except Exception as exc:
        logger.error(f"Executor raised unexpectedly: {exc}", exc_info=True)
        return _err(oc_req.intent, oc_req.scope, f"Unexpected execution error: {exc}.")

    # ── Step 7: log per-device outcomes ───────────────────────────────────────
    all_ok = all(r.success for r in results)
    for r in results:
        if r.success:
            logger.info(
                f"  {r.device}: OK"
                + (f" ({r.elapsed_ms:.0f}ms)" if r.elapsed_ms else "")
            )
        else:
            logger.warning(f"  {r.device}: FAILED — {r.error}")

    total_ms = round((time.monotonic() - _t0) * 1000, 1)
    logger.info(
        f"OpenClaw complete — intent={oc_req.intent!r}, success={all_ok}, "
        f"{len(results)} result(s), total={total_ms}ms"
    )

    # ── Step 8: build per-device results, applying query + truncation ─────────
    oc_results: list[OpenClawResult] = []
    query_active = bool(oc_req.query) and oc_req.intent in FILTERABLE_INTENTS
    for r in results:
        # Apply the server-side query filter BEFORE summarising or truncating
        # so the summary reflects the filtered view and the sample only
        # contains matching rows.
        filtered_data = apply_query(oc_req.intent, r.parsed_data, oc_req.query)

        # If a query produced zero matches, produce a direct "no match" summary
        # rather than running the normal summariser (which would happily report
        # "0 ARP entries" and mislead the agent).
        if (
            r.success
            and query_active
            and isinstance(filtered_data, list)
            and len(filtered_data) == 0
        ):
            summary = f"{r.device.upper()}: No match for '{oc_req.query}'."
        else:
            summary = summarize(r.model_copy(update={"parsed_data": filtered_data}))

        # Truncate unless the caller explicitly opted into verbose mode.
        sampled_data, truncated, total = _truncate_parsed_data(
            filtered_data, oc_req.verbose
        )

        oc_results.append(OpenClawResult(
            device=r.device,
            success=r.success,
            summary=summary,
            parsed_data=sampled_data,
            parsed_data_truncated=truncated,
            parsed_data_total_rows=total,
            elapsed_ms=r.elapsed_ms,
            error=r.error,
        ))

    aggregate = _build_aggregate_summary(oc_req.intent, oc_results)

    return OpenClawResponse(
        success=all_ok,
        intent=oc_req.intent,
        scope=oc_req.scope,
        results=oc_results,
        aggregate_summary=aggregate,
    ).model_dump()


# ── Response-shaping helpers ───────────────────────────────────────────────────

def _truncate_parsed_data(
    data: Any, verbose: bool
) -> tuple[Any, bool, Optional[int]]:
    """
    Return (sampled_data, truncated_flag, total_rows).

    - If `verbose=True` or `data` is not a list, returns data unchanged.
    - If `len(data) <= PARSED_DATA_SAMPLE_SIZE`, no truncation.
    - Otherwise returns the first N rows, truncated=True, total_rows=len(data).
    """
    if verbose or not isinstance(data, list):
        return data, False, None
    total = len(data)
    if total <= PARSED_DATA_SAMPLE_SIZE:
        return data, False, None
    return data[:PARSED_DATA_SAMPLE_SIZE], True, total


def _build_aggregate_summary(intent: str, results: list[OpenClawResult]) -> Optional[str]:
    """
    One-line cross-device summary for multi-device responses.

    Populated only when more than one device is present. Keeps token cost low:
    the agent can reply with just this line when everything is OK and drill
    into per-device results only when something looks wrong.
    """
    if len(results) <= 1:
        return None

    total  = len(results)
    failed = [r for r in results if not r.success]

    # Audit intents expose a status via the summary text — surface drift counts.
    if intent in ("audit_vlans", "audit_trunks", "drift_check"):
        compliant = sum(
            1 for r in results
            if r.success and "compliant" in (r.summary or "").lower()
        )
        drifted = [r.device for r in results if r.success and r not in failed
                   and "compliant" not in (r.summary or "").lower()]
        parts = [f"{total} device(s)", f"{compliant} compliant"]
        if drifted:
            names = ", ".join(drifted[:3])
            extra = f" (+{len(drifted) - 3} more)" if len(drifted) > 3 else ""
            parts.append(f"{len(drifted)} drift — {names}{extra}")
        if failed:
            parts.append(f"{len(failed)} failed")
        return "; ".join(parts) + "."

    # Default: OK/failed counts plus the first failing device's error.
    if failed:
        first = failed[0]
        err = (first.error or first.summary or "error")[:80]
        return f"{total} device(s) — {total - len(failed)} OK, {len(failed)} failed ({first.device}: {err})."
    return f"{total} device(s) — all OK."


def _err(intent: str, scope: str, error: str) -> dict:
    """Build a failed OpenClawResponse dict for pre-execution errors."""
    return OpenClawResponse(
        success=False,
        intent=intent,
        scope=scope,
        results=[],
        error=error,
    ).model_dump()


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    """
    CLI wrapper so OpenClaw can call this adapter as a subprocess.

    Accepts JSON via --json flag or stdin. Writes JSON to stdout.
    Logs go to output/logs/netpulse.log and WARNING+ to stderr.
    Exit codes: 0 = success, 1 = input error, 2 = job failure.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="netpulse-openclaw",
        description="NetPulse OpenClaw adapter — reads JSON, returns JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 -m app.openclaw_adapter "
            "--json '{\"intent\": \"show_vlans\", \"device\": \"sw-core-01\"}'\n"
            "  echo '{\"intent\": \"health_check\", \"scope\": \"all\"}' "
            "| python3 -m app.openclaw_adapter\n"
        ),
    )
    parser.add_argument("--json", metavar="PAYLOAD", help="JSON payload string")
    args = parser.parse_args()

    raw = args.json if args.json else sys.stdin.read().strip()

    if not raw:
        _fatal("No JSON input provided. Use --json or pipe JSON to stdin.")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        _fatal(f"Invalid JSON input: {exc}.")

    response = run_openclaw(payload)
    # Compact JSON — no indent, no whitespace after separators. The `exec`
    # tool pipes this back into the chat context, and every saved byte is a
    # saved token. Human readers can pipe to `| python -m json.tool` if needed.
    print(json.dumps(response, separators=(",", ":"), default=str))

    if not response.get("success"):
        sys.exit(2)


def _fatal(msg: str) -> None:
    """Print a minimal error envelope to stdout and exit 1."""
    print(json.dumps(
        {"success": False, "intent": "unknown", "scope": "unknown",
         "results": [], "error": msg},
        separators=(",", ":"),
    ))
    sys.exit(1)


if __name__ == "__main__":
    main()

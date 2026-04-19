#!/usr/bin/env python3
"""
NetPulse proactive health and drift scheduler.

Run this script periodically (e.g. via cron) to check all devices without
waiting for a user to ask.  Results are written to output/reports/ as a
timestamped JSON file and printed to stdout.

Exit codes:
    0 — all devices healthy, no drift detected
    1 — startup error (inventory missing, import failure, etc.)
    2 — one or more devices reported failures or drift

Usage:
    # From the project root with the venv active:
    python3 scripts/netpulse_scheduler.py

    # Via the cron helper (sets up venv automatically):
    bash scripts/install_schedule.sh
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Ensure the project root is on the import path when run as a script.
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


def main() -> int:
    try:
        from app.config import BACKUP_DIR  # triggers load_dotenv and dir creation
        from app.executor import execute
        from app.inventory import load_inventory
        from app.models import IntentRequest, IntentType, ScopeType
        from app.validators import validate_request
    except ImportError as exc:
        print(f"[netpulse-scheduler] Import error: {exc}", file=sys.stderr)
        print(json.dumps({"success": False, "error": str(exc), "results": []}))
        return 1

    # ── Load inventory ─────────────────────────────────────────────────────────
    try:
        inventory = load_inventory()
    except Exception as exc:
        print(f"[netpulse-scheduler] Inventory load failed: {exc}", file=sys.stderr)
        print(json.dumps({"success": False, "error": str(exc), "results": []}))
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_results: list[dict] = []
    issues_found = False

    # ── Run health_check and drift_check for all devices ───────────────────────
    for intent_type in (IntentType.HEALTH_CHECK, IntentType.DRIFT_CHECK):
        req = IntentRequest(
            intent=intent_type,
            scope=ScopeType.ALL,
            raw_query=f"scheduler:{intent_type.value}",
        )
        try:
            validate_request(req, inventory)
            job_results = execute(req, inventory)
        except Exception as exc:
            all_results.append({
                "intent": intent_type.value,
                "error": str(exc),
                "device_results": [],
            })
            issues_found = True
            continue

        device_results = []
        for r in job_results:
            entry = {
                "device":      r.device,
                "success":     r.success,
                "elapsed_ms":  r.elapsed_ms,
                "parsed_data": r.parsed_data,
            }
            if not r.success:
                entry["error"] = r.error
                issues_found = True
            else:
                # Flag drift_check findings
                if intent_type == IntentType.DRIFT_CHECK and isinstance(r.parsed_data, dict):
                    status = r.parsed_data.get("status", "")
                    if status not in ("compliant", "ok", ""):
                        issues_found = True
            device_results.append(entry)

        all_results.append({
            "intent":        intent_type.value,
            "device_results": device_results,
        })

    # ── Build and persist the report ───────────────────────────────────────────
    report = {
        "timestamp": timestamp,
        "success":   not issues_found,
        "summary":   "All devices healthy, no drift detected."
                     if not issues_found else
                     "Issues detected — see device_results for details.",
        "results":   all_results,
    }

    reports_dir = _PROJECT_ROOT / "output" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"netpulse_{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(json.dumps(report, indent=2, default=str))

    if issues_found:
        print(
            f"\n[netpulse-scheduler] Issues detected. Report: {report_path}",
            file=sys.stderr,
        )
        return 2

    print(
        f"[netpulse-scheduler] All clear. Report: {report_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

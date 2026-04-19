#!/usr/bin/env bash
# install_schedule.sh — Add a cron job to run the NetPulse proactive health/drift check.
#
# The scheduler script exits 0 when all clear and 2 when issues are found.
# Cron's MAILTO mechanism emails stdout/stderr only on non-zero exits, so you
# will receive a notification exactly when something needs attention.
#
# Usage:
#   bash scripts/install_schedule.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python3"
SCHEDULER="$PROJECT_DIR/scripts/netpulse_scheduler.py"
LOG="$PROJECT_DIR/output/logs/netpulse.log"

# ── Preflight checks ──────────────────────────────────────────────────────────
if [[ ! -f "$VENV_PYTHON" ]]; then
    echo "ERROR: Python venv not found at $VENV_PYTHON"
    echo "       Run 'bash scripts/setup.sh' first to create the virtual environment."
    exit 1
fi

if [[ ! -f "$SCHEDULER" ]]; then
    echo "ERROR: Scheduler script not found at $SCHEDULER"
    exit 1
fi

# ── Prompt for schedule time ──────────────────────────────────────────────────
echo ""
echo "NetPulse Proactive Health/Drift Check — Cron Installer"
echo "======================================================="
echo ""
echo "The scheduler will run 'health_check' and 'drift_check' on all devices."
echo "You will receive a cron email only when issues are detected (exit code 2)."
echo ""
read -rp "Run time (HH:MM, 24-hour, default 06:00): " RUN_TIME
RUN_TIME="${RUN_TIME:-06:00}"

# Validate HH:MM format
if ! echo "$RUN_TIME" | grep -qE '^[0-2][0-9]:[0-5][0-9]$'; then
    echo "ERROR: Invalid time format '$RUN_TIME'. Use HH:MM (e.g. 06:00 or 22:30)."
    exit 1
fi

CRON_HOUR="${RUN_TIME%%:*}"
CRON_MIN="${RUN_TIME##*:}"

# ── Build the cron line ───────────────────────────────────────────────────────
CRON_CMD="$VENV_PYTHON $SCHEDULER >> $LOG 2>&1"
CRON_LINE="$CRON_MIN $CRON_HOUR * * * $CRON_CMD"

# ── Check for duplicate ───────────────────────────────────────────────────────
if crontab -l 2>/dev/null | grep -qF "$SCHEDULER"; then
    echo ""
    echo "A cron entry for netpulse_scheduler.py already exists:"
    crontab -l 2>/dev/null | grep "$SCHEDULER"
    echo ""
    read -rp "Replace it? (y/N): " REPLACE
    if [[ "${REPLACE,,}" != "y" ]]; then
        echo "No changes made."
        exit 0
    fi
    # Remove old entry
    (crontab -l 2>/dev/null | grep -vF "$SCHEDULER") | crontab -
fi

# ── Install ───────────────────────────────────────────────────────────────────
(crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -

echo ""
echo "Cron entry installed:"
echo "  $CRON_LINE"
echo ""
echo "The scheduler will run daily at $RUN_TIME."
echo "Reports are saved to: $PROJECT_DIR/output/reports/"
echo "Cron output is appended to: $LOG"
echo ""
echo "To verify:  crontab -l"
echo "To remove:  crontab -e  (delete the netpulse_scheduler line)"

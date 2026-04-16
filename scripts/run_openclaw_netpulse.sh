#!/usr/bin/env bash
# run_openclaw_netpulse.sh — call the NetPulse OpenClaw adapter
#
# Usage:
#   ./scripts/run_openclaw_netpulse.sh '{"intent": "show_vlans", "device": "sw-core-01"}'
#   echo '{"intent": "health_check", "scope": "all"}' | ./scripts/run_openclaw_netpulse.sh
#
# Accepts JSON from $1 (argument) or stdin (pipe). Writes JSON to stdout.
# Logs go to output/logs/netpulse.log and WARNING+ to stderr.
#
# Exit codes:
#   0  all jobs succeeded
#   1  input error (missing payload, venv not found, .env missing)
#   2  one or more jobs failed at runtime

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON="${PROJECT_ROOT}/.venv/bin/python3"
ENV_FILE="${PROJECT_ROOT}/.env"

# ── Pre-flight checks ─────────────────────────────────────────────────────────

if [ ! -f "$PYTHON" ]; then
    printf '{"success":false,"intent":"unknown","scope":"unknown","results":[],"error":"Virtual environment not found. Run: python3 -m venv .venv && pip install -r requirements.txt"}\n'
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    printf '{"success":false,"intent":"unknown","scope":"unknown","results":[],"error":"Missing .env file. Copy .env.example to .env and fill in NETPULSE_USERNAME / NETPULSE_PASSWORD."}\n'
    exit 1
fi

# ── Read payload from argument or stdin ───────────────────────────────────────

if [ $# -ge 1 ] && [ -n "${1-}" ]; then
    PAYLOAD="$1"
else
    # Read from stdin; fail if nothing arrives (e.g. called interactively with no pipe)
    if [ -t 0 ]; then
        printf '{"success":false,"intent":"unknown","scope":"unknown","results":[],"error":"No JSON payload. Pass as argument or pipe to stdin."}\n'
        exit 1
    fi
    PAYLOAD="$(cat)"
fi

if [ -z "$PAYLOAD" ]; then
    printf '{"success":false,"intent":"unknown","scope":"unknown","results":[],"error":"Empty payload received."}\n'
    exit 1
fi

# ── Execute ───────────────────────────────────────────────────────────────────
# Must cd to project root so `python3 -m app.openclaw_adapter` resolves the
# app package correctly. exec replaces this shell — Python's exit code is ours.

cd "$PROJECT_ROOT"
exec "$PYTHON" -m app.openclaw_adapter --json "$PAYLOAD"

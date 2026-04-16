#!/usr/bin/env bash
# start-openclaw.sh — start (or restart) the OpenClaw gateway with nvm Node 22
#
# Run this once after login. After first-time onboarding you can also use
# the daemon: `openclaw gateway start` (systemd) for auto-start on boot.
#
# Usage:
#   ./scripts/start-openclaw.sh            # start gateway + open dashboard
#   ./scripts/start-openclaw.sh --status   # check gateway status only
#   ./scripts/start-openclaw.sh --stop     # stop the gateway

set -euo pipefail

# Load nvm so openclaw is on PATH
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [ -s "$NVM_DIR/nvm.sh" ]; then
    # shellcheck source=/dev/null
    \. "$NVM_DIR/nvm.sh"
else
    echo "ERROR: nvm not found at $NVM_DIR" >&2
    echo "       Run: curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash" >&2
    exit 1
fi

# Ensure Node 22 is active
nvm use 22 --silent 2>/dev/null || nvm use default --silent

OPENCLAW="$(which openclaw 2>/dev/null || true)"
if [ -z "$OPENCLAW" ]; then
    echo "ERROR: openclaw not found. Was it installed?" >&2
    echo "       Run: curl -fsSL https://openclaw.ai/install.sh | bash" >&2
    exit 1
fi

case "${1:-}" in
    --status)
        "$OPENCLAW" gateway status
        ;;
    --stop)
        "$OPENCLAW" gateway stop
        echo "Gateway stopped."
        ;;
    *)
        echo "Starting OpenClaw gateway..."
        "$OPENCLAW" gateway start
        echo ""
        "$OPENCLAW" gateway status
        echo ""
        echo "Dashboard: http://127.0.0.1:18789/"
        echo "Open it with: $OPENCLAW dashboard"
        ;;
esac

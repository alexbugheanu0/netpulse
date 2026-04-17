#!/usr/bin/env bash
# setup.sh — NetPulse one-command installer for Ubuntu / Debian
#
# Usage:
#   bash scripts/setup.sh
#
# Idempotent: safe to re-run on an already-configured machine.
# Requires: Ubuntu 20.04+ or Debian 11+

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

ok()   { echo -e "${GREEN}[OK]${RESET}  $*"; }
info() { echo -e "${CYAN}[--]${RESET}  $*"; }
warn() { echo -e "${YELLOW}[!!]${RESET}  $*"; }
err()  { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
step() { echo -e "\n${BOLD}${CYAN}=== $* ===${RESET}"; }

# ── Locate project root ───────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Track outcomes for the final summary
S_VENV=false S_DEPS=false S_ENV=false S_DEVICES=0 S_TESTS=false S_OPENCLAW=false

echo -e "\n${BOLD}NetPulse Setup Wizard${RESET}"
echo    "────────────────────────────────────────"
info   "Project root: $PROJECT_ROOT"

# ── Step 1 — System pre-flight ────────────────────────────────────────────────

step "Step 1 — System pre-flight"

if ! command -v apt-get &>/dev/null; then
    err "This script requires apt (Ubuntu / Debian). Exiting."
    exit 1
fi

MISSING_PKGS=()
for pkg in python3 python3-venv python3-pip git; do
    dpkg -s "$pkg" &>/dev/null || MISSING_PKGS+=("$pkg")
done

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    info "Installing missing packages: ${MISSING_PKGS[*]}"
    sudo apt-get update -qq
    sudo apt-get install -y -qq "${MISSING_PKGS[@]}"
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
    err "Python 3.11+ is required. Found: $PYTHON_VERSION"
    info "Install it with: sudo apt install python3.11"
    exit 1
fi

ok "Python $PYTHON_VERSION"

# ── Step 2 — Python venv + dependencies ──────────────────────────────────────

step "Step 2 — Python virtual environment and dependencies"

if [ ! -d ".venv" ]; then
    info "Creating virtual environment..."
    python3 -m venv .venv
fi
ok "Virtual environment ready"
S_VENV=true

info "Installing Python dependencies..."
.venv/bin/pip install -r requirements.txt --quiet --disable-pip-version-check
ok "Dependencies installed"
S_DEPS=true

# ── Step 3 — SSH credentials ──────────────────────────────────────────────────

step "Step 3 — SSH credentials"

WRITE_ENV=true
if [ -f ".env" ]; then
    warn ".env already exists."
    read -rp "  Overwrite it? [y/N]: " OVERWRITE
    [[ "${OVERWRITE,,}" == "y" ]] || WRITE_ENV=false
fi

if $WRITE_ENV; then
    echo ""
    info "Credentials are written to .env (never committed to git)."
    info "Passwords are hidden — nothing is shown while you type.\n"

    read -rp  "  SSH username  [admin]: " SSH_USER
    SSH_USER="${SSH_USER:-admin}"

    read -rsp "  SSH password: " SSH_PASS; echo ""
    while [ -z "$SSH_PASS" ]; do
        warn "Password cannot be empty."
        read -rsp "  SSH password: " SSH_PASS; echo ""
    done

    read -rsp "  Enable secret (leave blank if unused): " SSH_SECRET; echo ""

    read -rp  "  SSH port      [22]: " SSH_PORT
    SSH_PORT="${SSH_PORT:-22}"

    read -rp  "  SSH timeout   [30]: " SSH_TIMEOUT
    SSH_TIMEOUT="${SSH_TIMEOUT:-30}"

    cat > .env <<EOF
NETPULSE_USERNAME=${SSH_USER}
NETPULSE_PASSWORD=${SSH_PASS}
NETPULSE_SECRET=${SSH_SECRET}
NETPULSE_SSH_TIMEOUT=${SSH_TIMEOUT}
NETPULSE_SSH_PORT=${SSH_PORT}
EOF
    chmod 600 .env
    ok "Credentials saved to .env (permissions: 600)"
    warn "Never share .env or commit it to version control."
    S_ENV=true
else
    ok "Keeping existing .env"
    S_ENV=true
fi

# ── Step 4 — Add network devices ─────────────────────────────────────────────

step "Step 4 — Network devices"

# Shared helper used here and in add-device.sh
add_device_interactive() {
    echo ""
    read -rp "  Device name  (e.g. sw-core-01): " DEV_NAME
    while [ -z "$DEV_NAME" ]; do
        warn "Device name cannot be empty."
        read -rp "  Device name: " DEV_NAME
    done

    read -rp "  IP address: " DEV_IP
    while ! [[ "$DEV_IP" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; do
        warn "Enter a valid IPv4 address."
        read -rp "  IP address: " DEV_IP
    done

    echo    "  Role options: core / distribution / access"
    read -rp "  Role [access]: " DEV_ROLE
    DEV_ROLE="${DEV_ROLE:-access}"
    while [[ "$DEV_ROLE" != "core" && "$DEV_ROLE" != "distribution" && "$DEV_ROLE" != "access" ]]; do
        warn "Role must be: core, distribution, or access"
        read -rp "  Role [access]: " DEV_ROLE
        DEV_ROLE="${DEV_ROLE:-access}"
    done

    echo    "  Platform options: cisco_ios / cisco_xe / cisco_nxos / cisco_iosxr"
    read -rp "  Platform [cisco_ios]: " DEV_PLATFORM
    DEV_PLATFORM="${DEV_PLATFORM:-cisco_ios}"

    # inventory/devices.yaml — append if not already present
    if ! grep -q "name: ${DEV_NAME}" inventory/devices.yaml 2>/dev/null; then
        cat >> inventory/devices.yaml <<EOF

  - name: ${DEV_NAME}
    hostname: ${DEV_NAME}
    ip: ${DEV_IP}
    platform: ${DEV_PLATFORM}
    role: ${DEV_ROLE}
    ssh_enabled: true
    snmp_enabled: false
EOF
        ok "Added ${DEV_NAME} to inventory/devices.yaml"
    else
        warn "${DEV_NAME} already exists in inventory/devices.yaml — skipping"
    fi

    # ssot/device_roles.yaml — append role if not present
    if ! grep -q "^  ${DEV_NAME}:" ssot/device_roles.yaml 2>/dev/null; then
        echo "  ${DEV_NAME}: ${DEV_ROLE}" >> ssot/device_roles.yaml
        ok "Added ${DEV_NAME} to ssot/device_roles.yaml"
    fi

    # ssot/protected-resources.yaml — add placeholder uplink entry
    if ! grep -q "device: ${DEV_NAME}" ssot/protected-resources.yaml 2>/dev/null; then
        cat >> ssot/protected-resources.yaml <<EOF

  - device: ${DEV_NAME}
    interfaces: ["Gi1/0/1"]   # TODO: replace with real uplink interface(s)
    reason: "Uplink interface — review and update interface name"
EOF
        ok "Added ${DEV_NAME} uplink placeholder to ssot/protected-resources.yaml"
        warn "Edit ssot/protected-resources.yaml to set the real uplink interface for ${DEV_NAME}"
    fi
}

ADD_MORE=true
DEVICES_ADDED=0

# Ask whether to add devices at all (useful on re-run when devices already exist)
if grep -q "^  - name:" inventory/devices.yaml 2>/dev/null; then
    info "Existing devices found in inventory:"
    grep "name:" inventory/devices.yaml | sed 's/.*name: /    /'
fi

read -rp "  Add a network device now? [y/N]: " WANT_ADD
[[ "${WANT_ADD,,}" == "y" ]] || ADD_MORE=false

while $ADD_MORE; do
    add_device_interactive
    DEVICES_ADDED=$((DEVICES_ADDED + 1))
    read -rp "  Add another device? [y/N]: " AGAIN
    [[ "${AGAIN,,}" == "y" ]] || ADD_MORE=false
done

S_DEVICES=$DEVICES_ADDED
[ "$DEVICES_ADDED" -gt 0 ] && ok "$DEVICES_ADDED device(s) configured" || info "No new devices added"

# ── Step 5 — Verify connectivity ─────────────────────────────────────────────

step "Step 5 — Connectivity check"

if [ "$DEVICES_ADDED" -gt 0 ]; then
    info "Running TCP port-22 reachability test for new devices..."
    # Collect the names of devices just added (last N entries in inventory)
    ADDED_NAMES=$(grep "name:" inventory/devices.yaml | tail -"$DEVICES_ADDED" | awk '{print $NF}')
    for DEV in $ADDED_NAMES; do
        if .venv/bin/python3 -m app.main --intent show_version --device "$DEV" --check 2>/dev/null; then
            ok "Reachable: $DEV"
        else
            warn "Unreachable: $DEV (check IP and SSH access — continuing anyway)"
        fi
    done
else
    info "No new devices — skipping connectivity check"
fi

# ── Step 6 — Run test suite ───────────────────────────────────────────────────

step "Step 6 — Test suite"

info "Running pytest (no live devices required)..."
if .venv/bin/pytest tests/ -q --tb=short 2>&1; then
    ok "All tests passed"
    S_TESTS=true
else
    err "Tests failed — check the output above before using NetPulse"
    S_TESTS=false
fi

# ── Step 7 — OpenClaw (optional) ─────────────────────────────────────────────

step "Step 7 — OpenClaw integration (optional)"

echo ""
info "OpenClaw lets you query your switches from Telegram, WhatsApp, or Discord."
read -rp "  Install OpenClaw now? [y/N]: " WANT_OPENCLAW

if [[ "${WANT_OPENCLAW,,}" == "y" ]]; then
    # Install nvm if not present
    export NVM_DIR="${HOME}/.nvm"
    if [ ! -s "$NVM_DIR/nvm.sh" ]; then
        info "Installing nvm..."
        curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
        # shellcheck source=/dev/null
        \. "$NVM_DIR/nvm.sh"
    else
        # shellcheck source=/dev/null
        \. "$NVM_DIR/nvm.sh"
        ok "nvm already installed"
    fi

    # Install Node 22
    if ! nvm ls 22 &>/dev/null; then
        info "Installing Node.js 22..."
        nvm install 22
    fi
    nvm use 22 --silent
    ok "Node.js $(node --version)"

    # Install OpenClaw
    if ! command -v openclaw &>/dev/null; then
        info "Installing OpenClaw..."
        curl -fsSL https://openclaw.ai/install.sh | bash
    else
        ok "OpenClaw already installed"
    fi

    # Install NetPulse skill
    mkdir -p ~/.openclaw/skills
    cp -r skills/netpulse ~/.openclaw/skills/
    ok "NetPulse skill installed to ~/.openclaw/skills/netpulse/"

    info "Starting OpenClaw onboarding wizard..."
    info "(You will be prompted to choose a model provider and paste your API key)"
    echo ""
    openclaw onboard --install-daemon || warn "Onboarding incomplete — run 'openclaw onboard --install-daemon' manually"

    S_OPENCLAW=true
else
    info "Skipping OpenClaw — run this step later with: bash scripts/setup.sh"
fi

# ── Step 8 — Summary ─────────────────────────────────────────────────────────

step "Step 8 — Summary"
echo ""

_status() { $1 && echo -e "${GREEN}[OK]${RESET}  $2" || echo -e "${RED}[!!]${RESET}  $2"; }

_status $S_VENV     "Python virtual environment"
_status $S_DEPS     "Python dependencies"
_status $S_ENV      "SSH credentials (.env)"
[ "$S_DEVICES" -gt 0 ] \
    && echo -e "${GREEN}[OK]${RESET}  $S_DEVICES device(s) configured" \
    || echo -e "${YELLOW}[--]${RESET}  No devices added (run: bash scripts/add-device.sh)"
_status $S_TESTS    "Test suite"
_status $S_OPENCLAW "OpenClaw integration"

echo ""
echo -e "${BOLD}Next steps:${RESET}"
echo ""
echo "  source .venv/bin/activate"
echo "  python3 -m app.main --intent health_check"
echo ""
echo "  # Add more devices later:"
echo "  bash scripts/add-device.sh"
echo ""

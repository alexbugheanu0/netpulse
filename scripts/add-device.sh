#!/usr/bin/env bash
# add-device.sh — add or remove NetPulse network devices after initial setup
#
# Usage:
#   bash scripts/add-device.sh
#
# Updates inventory/devices.yaml, ssot/device_roles.yaml, and
# ssot/protected-resources.yaml in one pass.

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

# ── Locate project root ───────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

if [ ! -d ".venv" ]; then
    err "Virtual environment not found. Run: bash scripts/setup.sh first."
    exit 1
fi

echo -e "\n${BOLD}NetPulse — Device Manager${RESET}"
echo    "────────────────────────────────────────"

# ── Show current inventory ────────────────────────────────────────────────────

list_devices() {
    echo ""
    info "Current devices in inventory:"
    if grep -q "^  - name:" inventory/devices.yaml 2>/dev/null; then
        grep -E "name:|ip:|role:" inventory/devices.yaml \
            | paste - - - \
            | awk '{printf "    %-20s %-18s %s\n", $2, $4, $6}'
    else
        warn "No devices configured yet."
    fi
    echo ""
}

list_devices

# ── Main menu ─────────────────────────────────────────────────────────────────

echo "  What would you like to do?"
echo "  [1] Add a device"
echo "  [2] Remove a device"
echo "  [3] Check connectivity for all devices"
echo "  [4] Exit"
echo ""
read -rp "  Choice [1]: " CHOICE
CHOICE="${CHOICE:-1}"

# ── Add device ────────────────────────────────────────────────────────────────

add_device() {
    echo ""
    read -rp "  Device name  (e.g. sw-acc-03): " DEV_NAME
    while [ -z "$DEV_NAME" ]; do
        warn "Device name cannot be empty."
        read -rp "  Device name: " DEV_NAME
    done

    # Check for duplicate
    if grep -q "name: ${DEV_NAME}" inventory/devices.yaml 2>/dev/null; then
        warn "${DEV_NAME} already exists in inventory. No changes made."
        return
    fi

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

    read -rp "  Trunk uplink interface (e.g. Gi1/0/1) — leave blank to set later: " DEV_UPLINK
    DEV_UPLINK="${DEV_UPLINK:-Gi1/0/1}"

    # inventory/devices.yaml
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

    # ssot/device_roles.yaml
    if ! grep -q "^  ${DEV_NAME}:" ssot/device_roles.yaml 2>/dev/null; then
        echo "  ${DEV_NAME}: ${DEV_ROLE}" >> ssot/device_roles.yaml
        ok "Added ${DEV_NAME} to ssot/device_roles.yaml"
    fi

    # ssot/protected-resources.yaml
    if ! grep -q "device: ${DEV_NAME}" ssot/protected-resources.yaml 2>/dev/null; then
        cat >> ssot/protected-resources.yaml <<EOF

  - device: ${DEV_NAME}
    interfaces: ["${DEV_UPLINK}"]
    reason: "Uplink interface"
EOF
        ok "Added ${DEV_NAME} uplink (${DEV_UPLINK}) to ssot/protected-resources.yaml"
    fi

    # Connectivity check
    echo ""
    read -rp "  Run connectivity check for ${DEV_NAME} now? [Y/n]: " DO_CHECK
    DO_CHECK="${DO_CHECK:-y}"
    if [[ "${DO_CHECK,,}" == "y" ]]; then
        info "Checking TCP port-22 reachability for ${DEV_NAME}..."
        if .venv/bin/python3 -m app.main --intent show_version --device "$DEV_NAME" --check 2>/dev/null; then
            ok "${DEV_NAME} is reachable"
        else
            warn "${DEV_NAME} is not reachable — check IP ${DEV_IP} and SSH access"
        fi
    fi

    # Remind about skill re-sync
    echo ""
    warn "Remember to update the device table in skills/netpulse/SKILL.md and re-sync:"
    echo "       cp -r skills/netpulse ~/.openclaw/skills/"
}

# ── Remove device ─────────────────────────────────────────────────────────────

remove_device() {
    echo ""
    read -rp "  Device name to remove: " DEV_NAME
    if [ -z "$DEV_NAME" ]; then
        warn "No name entered. Aborting."
        return
    fi

    if ! grep -q "name: ${DEV_NAME}" inventory/devices.yaml 2>/dev/null; then
        warn "${DEV_NAME} not found in inventory."
        return
    fi

    echo ""
    warn "This will remove ${DEV_NAME} from:"
    echo "    - inventory/devices.yaml"
    echo "    - ssot/device_roles.yaml"
    echo "    - ssot/protected-resources.yaml"
    read -rp "  Confirm removal? [y/N]: " CONFIRM
    [[ "${CONFIRM,,}" == "y" ]] || { info "Cancelled."; return; }

    # inventory/devices.yaml — remove the 7-line device block
    # Use Python for reliable multi-line YAML block removal
    .venv/bin/python3 - "$DEV_NAME" <<'PYEOF'
import sys, re, pathlib

name = sys.argv[1]
path = pathlib.Path("inventory/devices.yaml")
text = path.read_text()

# Match a device block: starts with "  - name: <name>" and runs until next "  - name:" or EOF
pattern = rf'(\n  - name: {re.escape(name)}\n(?:    [^\n]*\n)*)'
new_text = re.sub(pattern, '', text)
path.write_text(new_text)
print(f"  Removed {name} from inventory/devices.yaml")
PYEOF

    # ssot/device_roles.yaml — remove the role line
    sed -i "/^  ${DEV_NAME}:/d" ssot/device_roles.yaml
    ok "Removed ${DEV_NAME} from ssot/device_roles.yaml"

    # ssot/protected-resources.yaml — remove the interface block (Python for safety)
    .venv/bin/python3 - "$DEV_NAME" <<'PYEOF'
import sys, re, pathlib

name = sys.argv[1]
path = pathlib.Path("ssot/protected-resources.yaml")
text = path.read_text()

pattern = rf'\n  - device: {re.escape(name)}\n(?:    [^\n]*\n)*'
new_text = re.sub(pattern, '', text)
path.write_text(new_text)
print(f"  Removed {name} from ssot/protected-resources.yaml")
PYEOF

    ok "${DEV_NAME} removed from all SSOT files"
    warn "Also remove ${DEV_NAME} from the device table in skills/netpulse/SKILL.md and re-sync the skill."
}

# ── Connectivity check for all devices ───────────────────────────────────────

check_all() {
    echo ""
    info "Checking TCP port-22 reachability for all SSH-enabled devices..."
    DEVICE_NAMES=$(grep "name:" inventory/devices.yaml | awk '{print $NF}')
    for DEV in $DEVICE_NAMES; do
        if .venv/bin/python3 -m app.main --intent show_version --device "$DEV" --check 2>/dev/null; then
            ok "Reachable:   $DEV"
        else
            warn "Unreachable: $DEV"
        fi
    done
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

case "$CHOICE" in
    1) add_device ;;
    2) remove_device ;;
    3) check_all ;;
    4) info "Bye."; exit 0 ;;
    *) warn "Invalid choice. Exiting."; exit 1 ;;
esac

echo ""
list_devices

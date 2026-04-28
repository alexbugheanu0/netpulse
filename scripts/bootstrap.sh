#!/usr/bin/env bash
# bootstrap.sh - clone NetPulse and hand off to the interactive setup wizard.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/alexbugheanu0/netpulse/main/scripts/bootstrap.sh | bash
#
# Optional:
#   NETPULSE_DIR="$HOME/netpulse-project" NETPULSE_REPO_URL="https://..." bash scripts/bootstrap.sh

set -euo pipefail

NETPULSE_REPO_URL="${NETPULSE_REPO_URL:-https://github.com/alexbugheanu0/netpulse.git}"
NETPULSE_DIR="${NETPULSE_DIR:-$HOME/netpulse-project}"

info() { printf '[--]  %s\n' "$*"; }
ok() { printf '[OK]  %s\n' "$*"; }
err() { printf '[ERROR] %s\n' "$*" >&2; }

run_as_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        err "Missing sudo; install required packages manually and re-run."
        exit 1
    fi
}

install_missing_packages() {
    missing=()
    for cmd in git python3; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing+=("$cmd")
        fi
    done

    if [ "${#missing[@]}" -eq 0 ]; then
        return
    fi

    if ! command -v apt-get >/dev/null 2>&1; then
        err "Missing required command(s): ${missing[*]}"
        err "Install them manually, then re-run this bootstrap script."
        exit 1
    fi

    info "Installing missing package(s): ${missing[*]}"
    run_as_root apt-get update -qq
    run_as_root apt-get install -y -qq "${missing[@]}"
}

install_missing_packages

if [ -d "$NETPULSE_DIR/.git" ]; then
    ok "Using existing NetPulse checkout: $NETPULSE_DIR"
elif [ -e "$NETPULSE_DIR" ]; then
    err "Target path exists but is not a git checkout: $NETPULSE_DIR"
    err "Set NETPULSE_DIR to a different path or move the existing directory."
    exit 1
else
    info "Cloning NetPulse into $NETPULSE_DIR"
    git clone "$NETPULSE_REPO_URL" "$NETPULSE_DIR"
fi

cd "$NETPULSE_DIR"

if [ ! -f "scripts/setup.sh" ]; then
    err "scripts/setup.sh was not found in $NETPULSE_DIR"
    exit 1
fi

ok "Starting NetPulse setup wizard"
exec bash scripts/setup.sh "$@"

# NetPulse — Installation and Run Guide

## Quick install (Ubuntu / Debian)

Run a single command from the project root and the wizard handles everything:

```bash
bash scripts/setup.sh
```

It will: install system packages, create the Python venv, prompt for SSH
credentials (passwords hidden), walk you through adding your network devices,
run the test suite, and optionally set up OpenClaw for Telegram/WhatsApp/Discord.

To add or remove devices after the initial setup:

```bash
bash scripts/add-device.sh
```

---

## Manual installation

Step-by-step procedure for setting up NetPulse on a Linux or macOS machine,
using it from the CLI, and connecting it to OpenClaw for natural language access
from Telegram, WhatsApp, or Discord.

---

## Requirements

| Requirement | Minimum | Notes |
|---|---|---|
| Python | 3.11+ | 3.12 recommended |
| SSH access | port 22 | To at least one Cisco switch |
| Node.js | 22.14+ | Only needed for OpenClaw integration |
| Git | any | To clone the project |

---

## Part 1 — Install NetPulse

### Step 1 — Clone the project

```bash
git clone <your-repo-url> netpulse-project
cd netpulse-project
```

If you already have the folder, just `cd` into it.

---

### Step 2 — Create the Python virtual environment

```bash
python3 -m venv .venv
```

Activate it (you must do this every time you open a new terminal):

```bash
# Linux / macOS
source .venv/bin/activate

# Windows (Command Prompt)
.venv\Scripts\activate.bat

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

Your prompt will show `(.venv)` when the environment is active.

---

### Step 3 — Install Python dependencies

```bash
pip install -r requirements.txt
```

Dependencies installed:
- `netmiko` — SSH to Cisco devices
- `pydantic` — request/response validation
- `pyyaml` — inventory and SSOT file loading
- `rich` — terminal output formatting
- `python-dotenv` — credential loading from `.env`
- `pytest` — test suite

---

### Step 4 — Configure SSH credentials

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```env
NETPULSE_USERNAME=admin
NETPULSE_PASSWORD=your_ssh_password
NETPULSE_SECRET=your_enable_secret   # leave blank if not using enable
NETPULSE_SSH_TIMEOUT=30
NETPULSE_SSH_PORT=22
```

> `.env` is in `.gitignore` — it is never committed to version control.

---

### Step 5 — Configure your device inventory

Open `inventory/devices.yaml` and replace the placeholder IPs with your real devices:

```yaml
devices:
  - name: sw-core-01
    hostname: sw-core-01
    ip: 192.168.100.11        # <-- replace with real IP
    platform: cisco_ios       # cisco_ios / cisco_xe / cisco_nxos
    role: core
    ssh_enabled: true
    snmp_enabled: false
```

Supported Netmiko platform values: `cisco_ios`, `cisco_xe`, `cisco_nxos`, `cisco_iosxr`.

> Device names must be hyphenated with a numeric suffix: `sw-core-01`, `rtr-edge-02`.
> The `role` field is used for `--role` targeting (e.g. `--role access`).

When adding a new device here, also update:
- `ssot/device_roles.yaml` — add the role mapping for the new device
- `ssot/protected-resources.yaml` — add the device's trunk uplink interfaces under `protected_interfaces`

---

### Step 6 — Verify everything works

Run the test suite (no live devices needed):

```bash
pytest tests/ -v
```

All 177 tests should pass. If any fail, check that:
- The virtual environment is activated (`source .venv/bin/activate`)
- Dependencies installed without errors (`pip install -r requirements.txt`)

---

### Step 7 — Test connectivity before running jobs

```bash
python3 -m app.main --intent show_version --device sw-core-01 --check
```

The `--check` flag runs a TCP port-22 reachability test without opening an SSH session.
If it passes, drop `--check` to run the real command:

```bash
python3 -m app.main --intent show_version --device sw-core-01
```

---

## Part 2 — Use NetPulse from the CLI

### Natural language mode

```bash
python3 -m app.main "show vlans on sw-core-01"
python3 -m app.main "show errors on sw-core-01"
python3 -m app.main "who is the root bridge on sw-core-01"
python3 -m app.main "show arp table on sw-core-01"
python3 -m app.main "show etherchannel on sw-dist-01"
python3 -m app.main "any port security violations on sw-acc-01"
python3 -m app.main "what does the log say on sw-core-01"
python3 -m app.main "what is the route to 10.10.0.0 on sw-core-01"
python3 -m app.main "health check all switches"
python3 -m app.main "backup config from sw-acc-02"
python3 -m app.main "drift check all switches"
```

### Structured flags mode (always unambiguous)

```bash
# Single device
python3 -m app.main --intent show_vlans          --device sw-core-01
python3 -m app.main --intent show_errors         --device sw-core-01
python3 -m app.main --intent show_spanning_tree  --device sw-core-01
python3 -m app.main --intent show_cdp            --device sw-dist-01
python3 -m app.main --intent show_mac            --device sw-acc-01
python3 -m app.main --intent show_route          --device sw-core-01
python3 -m app.main --intent show_arp            --device sw-core-01
python3 -m app.main --intent show_etherchannel   --device sw-dist-01
python3 -m app.main --intent show_port_security  --device sw-acc-01
python3 -m app.main --intent show_logging        --device sw-core-01
python3 -m app.main --intent show_version        --device sw-core-01
python3 -m app.main --intent backup_config       --device sw-acc-02
python3 -m app.main --intent ping                --device sw-core-01 --target 10.0.0.1

# All devices
python3 -m app.main --intent health_check
python3 -m app.main --intent show_errors

# Role-based targeting
python3 -m app.main --intent show_errors         --role access
python3 -m app.main --intent drift_check         --role core

# SSOT audit
python3 -m app.main --intent audit_vlans   --device sw-core-01
python3 -m app.main --intent audit_trunks  --device sw-dist-01
python3 -m app.main --intent drift_check   --scope all
```

### Useful flags

| Flag | Description |
|---|---|
| `--check` | TCP port-22 reachability test before SSH |
| `--dry-run` | Show what would run — no SSH connections opened |
| `--filter <str>` | Only print output lines containing this string |
| `--format json` | Machine-readable JSON output |
| `--format csv` | CSV output (uses parsed_data when available) |
| `--role <role>` | Target all devices with that role |
| `--target <ip>` | Destination IP for `--intent ping` |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | All jobs succeeded |
| `1` | Startup error (bad flags, bad inventory, validation failure) |
| `2` | One or more jobs failed at runtime |

---

## Part 3 — Use the JSON adapter (OpenClaw / scripting)

The adapter accepts a JSON payload and returns a JSON response. No Rich formatting.

```bash
# Single device
python3 -m app.openclaw_adapter --json '{"intent":"show_vlans","device":"sw-core-01","scope":"single"}'

# All devices
python3 -m app.openclaw_adapter --json '{"intent":"health_check","scope":"all"}'

# Via the shell wrapper (handles venv automatically)
./scripts/run_openclaw_netpulse.sh '{"intent":"show_route","device":"sw-core-01","scope":"single"}'

# Via stdin
echo '{"intent":"show_logging","device":"sw-core-01","scope":"single"}' | ./scripts/run_openclaw_netpulse.sh
```

Valid scope values: `single` (requires `device`), `all`, `role` (requires `role`).

---

## Part 4 — Connect to OpenClaw (natural language from phone)

OpenClaw is a local AI assistant that connects to Telegram/WhatsApp/Discord.
Once set up, you can ask questions about your switches from your phone.

### Step 1 — Install Node.js 22+

```bash
# Install nvm (Node version manager)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc

# Install and activate Node 22
nvm install 22
nvm use 22
nvm alias default 22

# Verify
node --version    # should show v22.x.x
npm --version     # should show 10.x.x
```

---

### Step 2 — Install OpenClaw

```bash
curl -fsSL https://openclaw.ai/install.sh | bash
```

---

### Step 3 — Run the onboarding wizard

Open a fresh terminal (so nvm is on PATH) and run:

```bash
openclaw onboard --install-daemon
```

The wizard will ask you to:
1. Choose a model provider — **Anthropic (Claude)** or **OpenAI (GPT-4o)** recommended
2. Paste your API key
3. Confirm starting the gateway as a background daemon (say yes)

Verify the gateway started:

```bash
openclaw gateway status      # should show "running"
openclaw dashboard           # opens http://127.0.0.1:18789 in your browser
```

Send a test message in the dashboard chat. If you get an AI reply, the core works.

---

### Step 4 — Create a Telegram bot

1. Open Telegram on your phone
2. Start a chat with `@BotFather`
3. Send `/newbot` and follow the prompts (give the bot any name)
4. Copy the token BotFather gives you (format: `1234567890:ABCdef...`)

Register it with OpenClaw:

```bash
openclaw channels add telegram --token "YOUR_TOKEN_HERE"
```

Send your new bot a message from your phone — you should get an AI reply in the dashboard.

Full Telegram setup guide: https://docs.openclaw.ai/channels/telegram

---

### Step 5 — Install the NetPulse skill

The skill file teaches OpenClaw when and how to call NetPulse.

```bash
cp -r /home/alex/netpulse-project/skills/netpulse ~/.openclaw/skills/
```

Verify it loaded:

```bash
openclaw skills list | grep netpulse
```

> Skills are loaded at session start. Start a new OpenClaw session after this step.

---

### Step 6 — Set SSH credentials for OpenClaw

The `.env` file at the project root already has your credentials and the adapter
loads them automatically. No extra step needed if `.env` is populated.

If you prefer to store credentials in OpenClaw's secrets store instead:

```bash
openclaw secrets set NETPULSE_USERNAME admin
openclaw secrets set NETPULSE_PASSWORD yourpassword
```

---

### Step 7 — Test end to end from Telegram

Start a new chat session with your bot and send:

```
what vlans are on sw-core-01?
```

> **First run:** OpenClaw will ask you to approve the `exec` tool for the netpulse skill.
> Approve it — this is a one-time prompt.

If it works, try these:

```
show errors on sw-acc-01
who is the root bridge on sw-core-01?
is the LACP bundle on sw-dist-01 healthy?
any port security violations on the access switches?
what does the log say on sw-core-01?
what is the route to 10.0.0.0/8 on sw-core-01?
run a drift check on all switches
backup config from sw-acc-02
health check all switches
```

---

## Part 5 — Day-to-day operations

### Start / stop the OpenClaw gateway

```bash
# Start (uses nvm automatically)
./scripts/start-openclaw.sh

# Check status
./scripts/start-openclaw.sh --status

# Stop
./scripts/start-openclaw.sh --stop
```

Or use systemd if you enabled the daemon during onboarding:

```bash
openclaw gateway start
openclaw gateway stop
openclaw gateway status
```

### Run the tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

### Check NetPulse logs

```bash
# Live tail
tail -f output/logs/netpulse.log

# Only OpenClaw adapter lines
grep "netpulse.openclaw" output/logs/netpulse.log | tail -50

# Only errors and warnings
grep -E "(WARNING|ERROR)" output/logs/netpulse.log | tail -20
```

### Add a new device

Follow all four steps — skipping any of them will cause drift check failures or
incorrect agent behaviour for write intents on the new device.

**Step 1 — Add the device to `inventory/devices.yaml`**

```yaml
- name: sw-acc-03
  hostname: sw-acc-03
  ip: 192.168.100.15
  platform: cisco_ios
  role: access
  ssh_enabled: true
  snmp_enabled: false
```

**Step 2 — Add the role mapping to `ssot/device_roles.yaml`**

```yaml
devices:
  sw-acc-03: access
```

**Step 3 — Add the device's uplink interfaces to `ssot/protected-resources.yaml`**

Under `protected_interfaces`, add an entry for the new device's trunk uplink(s):

```yaml
protected_interfaces:
  - device: sw-acc-03
    interfaces: ["Gi1/0/1"]
    reason: "Uplink to distribution layer"
```

This ensures the agent always asks for approval before shutting down or
reconfiguring trunk ports on the new device.

**Step 4 — Update the skill and re-sync**

Add the new device to the device table in `skills/netpulse/SKILL.md`, then
push the updated skill to OpenClaw:

```bash
cp -r skills/netpulse ~/.openclaw/skills/
```

---

## Troubleshooting

### "No module named 'app'"

You are running `python3 app/main.py` instead of `python3 -m app.main`.
Always use the `-m` flag from the project root:

```bash
cd /home/alex/netpulse-project
python3 -m app.main --intent show_version --device sw-core-01
```

### "Authentication failed"

Check `NETPULSE_USERNAME` and `NETPULSE_PASSWORD` in `.env`.
Test manually:

```bash
ssh admin@192.168.100.11
```

If manual SSH works but NetPulse fails, verify the variable names match exactly.

### "Unreachable or slow — connection timed out"

```bash
# TCP reachability test
python3 -m app.main --intent show_version --device sw-core-01 --check
```

If the check fails: confirm the IP in `inventory/devices.yaml`, check port 22 is open,
and check for ACLs blocking SSH from this host.

### "Device 'X' not found in inventory"

The device name must match `inventory/devices.yaml` exactly (case-sensitive).

```bash
grep 'name:' inventory/devices.yaml
```

### OpenClaw skill not loading

```bash
openclaw skills list | grep netpulse
```

If missing: confirm the skill was copied to `~/.openclaw/skills/netpulse/SKILL.md`
and restart OpenClaw (`openclaw gateway restart`).

### Virtual environment not active

Look for `(.venv)` at the start of your shell prompt.
If missing, run `source .venv/bin/activate` from the project root.

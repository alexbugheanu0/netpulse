# NetPulse

SSH execution backend for [OpenClaw](https://openclaw.ai). Ask natural language
questions about your Cisco switches from Telegram, WhatsApp, or Discord — NetPulse
handles the SSH, parsing, and structured responses.

Install the included skill (`skills/netpulse/SKILL.md`) and the agent does the rest.

---

## Supported intents

### Show / operational

| Intent              | Command run on device              |
|---------------------|------------------------------------|
| `show_interfaces`   | `show interfaces status`           |
| `show_vlans`        | `show vlan brief`                  |
| `show_trunks`       | `show interfaces trunk`            |
| `show_version`      | `show version`                     |
| `show_errors`       | `show interfaces` (error counters) |
| `show_cdp`          | `show cdp neighbors detail`        |
| `show_mac`          | `show mac address-table`           |
| `show_spanning_tree`| `show spanning-tree`               |
| `ping`              | `ping <target> repeat 5`           |
| `backup_config`     | `show running-config` → file       |
| `diff_backup`       | diff two most recent backups       |
| `health_check`      | version + interfaces + vlans       |

### SSOT audit

| Intent         | What it does                                              |
|----------------|-----------------------------------------------------------|
| `audit_vlans`  | Compare device VLANs against `ssot/vlans.yaml`            |
| `audit_trunks` | Compare trunk allowed VLANs against `ssot/trunks.yaml`    |
| `device_facts` | Collect platform, IOS version, uptime, port stats          |
| `drift_check`  | Combined VLAN + trunk audit + device-role check            |

All audit intents are read-only. They run `show` commands and compare the
output against the SSOT files you maintain — they never modify device config.

---

## Quick start

```bash
# 1. Clone and enter the project
git clone <repo-url> netpulse-project
cd netpulse-project

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure SSH credentials
cp .env.example .env
# Edit .env — at minimum set:
#   NETPULSE_USERNAME=admin
#   NETPULSE_PASSWORD=yourpassword

# 5. Set your device IPs
# Edit inventory/devices.yaml — replace the placeholder IPs with real ones

# 6. (Optional) Verify connectivity before running jobs
python3 -m app.main --intent show_vlans --device sw-core-01 --check
```

The `--check` flag runs a TCP port-22 reachability test before opening SSH.
If connectivity is confirmed, drop `--check` and run the real job.

---

## .env

```env
NETPULSE_USERNAME=admin
NETPULSE_PASSWORD=your_ssh_password
NETPULSE_SECRET=your_enable_secret   # optional; omit if not using enable
NETPULSE_SSH_TIMEOUT=30
NETPULSE_SSH_PORT=22
```

Credentials are never stored in YAML or committed to version control.
`.env` is in `.gitignore`.

---

## inventory/devices.yaml

```yaml
devices:
  - name: sw-core-01
    hostname: sw-core-01
    ip: 192.168.100.11
    platform: cisco_ios        # Netmiko device_type
    role: core
    ssh_enabled: true
    snmp_enabled: false
```

Supported platforms follow Netmiko naming: `cisco_ios`, `cisco_xe`,
`cisco_nxos`, etc. The `role` field is used for `--role` targeting.

---

## ssot/ — SSOT baseline files

Three YAML files define what the network *should* look like.
Edit them to match your lab or production baseline.

```
ssot/
├── vlans.yaml         # expected VLANs per role (core / distribution / access)
├── trunks.yaml        # expected allowed VLANs on trunk ports, per role
└── device_roles.yaml  # expected role for each named device
```

**`ssot/vlans.yaml`** — example entry:

```yaml
roles:
  access:
    - {id: "1",   name: default}
    - {id: "10",  name: MGMT}
    - {id: "20",  name: SERVERS}
    - {id: "30",  name: USERS}
    - {id: "100", name: VOICE}
devices: {}   # optional per-device overrides
```

**`ssot/trunks.yaml`** — example entry:

```yaml
roles:
  access:
    allowed_vlans: [1, 10, 20, 30, 100]
    native_vlan: 1
devices: {}
```

**`ssot/device_roles.yaml`** — example entry:

```yaml
devices:
  sw-core-01: core
  sw-dist-01: distribution
  sw-acc-01:  access
```

The `devices:` overrides in each file take precedence over role-level defaults,
letting you express per-device exceptions without touching the shared baseline.

---

## Developer CLI (`app/main.py`)

Use the CLI for setup verification, scripting, automation, and `diff_backup`
(not exposed via OpenClaw). For everything else, just ask OpenClaw.

### Structured flags

```bash
# Single device
python3 -m app.main --intent show_vlans          --device sw-core-01
python3 -m app.main --intent show_errors         --device sw-core-01
python3 -m app.main --intent show_cdp            --device sw-dist-01
python3 -m app.main --intent show_mac            --device sw-acc-01
python3 -m app.main --intent show_spanning_tree  --device sw-core-01
python3 -m app.main --intent ping                --device sw-core-01 --target 10.0.0.1
python3 -m app.main --intent backup_config       --device sw-acc-02
python3 -m app.main --intent diff_backup         --device sw-core-01

# All devices (omit --device)
python3 -m app.main --intent health_check
python3 -m app.main --intent show_errors

# Role-based targeting
python3 -m app.main --intent show_errors  --role access
python3 -m app.main --intent health_check --role core

# SSOT audit (structured flags)
python3 -m app.main --intent audit_vlans   --device sw-core-01
python3 -m app.main --intent audit_trunks  --device sw-dist-01
python3 -m app.main --intent device_facts  --device sw-acc-01
python3 -m app.main --intent drift_check   --device sw-core-01
python3 -m app.main --intent audit_vlans   --scope all
python3 -m app.main --intent drift_check   --role access
```

### Flags

| Flag | Description |
|---|---|
| `--role <role>` | Target all SSH-enabled devices with that role |
| `--target <ip>` | Ping destination IP (required for `--intent ping`) |
| `--filter <str>` | Only show output lines containing this string |
| `--format json` | Output results as JSON array (machine-readable) |
| `--format csv` | Output results as CSV (uses `parsed_data` if available) |
| `--dry-run` | Show what would run without opening SSH connections |
| `--check` | TCP port-22 reachability check before running jobs |

```bash
# Examples
python3 -m app.main --intent show_errors  --device sw-core-01 --filter Gi1/0/1
python3 -m app.main --intent health_check --format json > results.json
python3 -m app.main --intent show_vlans   --role access --format csv
python3 -m app.main --intent health_check --dry-run
python3 -m app.main --intent show_vlans   --device sw-core-01 --check
```

### Exit codes

| Code | Meaning |
|------|---------|
| `0`  | All jobs succeeded |
| `1`  | Startup error (bad inventory / bad flags / validation failure) |
| `2`  | One or more jobs failed at runtime |

---

## Running tests

```bash
# From project root with venv active
pytest tests/ -v
```

146 tests — no live devices required. Covers intent parsing, parsers,
inventory loading, request validation, audit comparison logic, and the
OpenClaw adapter.

---

## OpenClaw integration

NetPulse ships with a native [OpenClaw](https://openclaw.ai) skill. Once installed,
you can ask your AI assistant questions like *"what vlans are on sw-core-01?"* or
*"run a drift check on all access switches"* from Telegram, WhatsApp, or Discord —
and get a real answer from your switches.

### How it works

OpenClaw reads `skills/netpulse/SKILL.md` at session start. When the user asks a
network question, the agent builds a JSON payload and calls `app/openclaw_adapter.py`
via the `exec` tool. The adapter validates the intent, looks up the device in
inventory, runs the SSH job, and returns clean JSON. The agent presents the
`results[].summary` field in chat.

### Install the skill

```bash
# Option A — copy to the shared OpenClaw skills folder
cp -r skills/netpulse ~/.openclaw/skills/

# Option B — add this project's skills/ dir to openclaw.json
openclaw config set skills.load.extraDirs '["/home/alex/netpulse-project/skills"]'
```

### Store credentials in OpenClaw

```bash
openclaw secrets set NETPULSE_USERNAME admin
openclaw secrets set NETPULSE_PASSWORD yourpassword
```

Or use a `.env` file at the project root (see the `.env` section above).

### Verify the skill loaded

```bash
openclaw skills list | grep netpulse
```

### Test the adapter directly

```bash
# Valid request — shows what OpenClaw would receive
python3 -m app.openclaw_adapter --json '{"intent": "show_vlans", "device": "sw-core-01", "scope": "single"}'

# All devices
python3 -m app.openclaw_adapter --json '{"intent": "health_check", "scope": "all"}'

# Via the shell wrapper (handles venv automatically)
./scripts/run_openclaw_netpulse.sh '{"intent": "show_version", "device": "sw-core-01", "scope": "single"}'

# Via stdin
echo '{"intent": "audit_vlans", "device": "sw-core-01", "scope": "single"}' | ./scripts/run_openclaw_netpulse.sh
```

Allowed intents via OpenClaw: `show_interfaces`, `show_vlans`, `show_trunks`,
`show_version`, `show_errors`, `show_cdp`, `show_mac`, `show_spanning_tree`,
`show_route`, `show_arp`, `show_etherchannel`, `show_port_security`, `show_logging`,
`backup_config`, `health_check`, `ping`, `audit_vlans`, `audit_trunks`,
`device_facts`, `drift_check`.

See [`OPENCLAW_INTEGRATION.md`](OPENCLAW_INTEGRATION.md) for the full integration
guide and [`skills/netpulse/SKILL.md`](skills/netpulse/SKILL.md) for per-intent
payload reference.

---

## Backup file format

Config backups are written to `output/backups/`:

```
sw-core-01_20260415_143022.cfg
```

Format: `<device-name>_YYYYMMDD_HHMMSS.cfg`

Use `diff_backup` to compare the two most recent backups for a device.

---

## Extending NetPulse

### Add a new intent

1. Add the value to `IntentType` in `app/models.py`.
2. Add keyword patterns to `INTENT_PATTERNS` in `app/intents.py`.
3. Create `app/jobs/your_new_job.py` with a `run(device) -> JobResult` function.
4. Register it in `JOB_MAP` and `COMMAND_PREVIEW` in `app/executor.py` / `app/main.py`.
5. To expose it via OpenClaw: add it to `OPENCLAW_ALLOWED_INTENTS` in `app/openclaw_adapter.py`
   and update the intent table in `skills/netpulse/SKILL.md`.

### Add a device platform

Update the device entry in `devices.yaml` with the correct Netmiko
`platform` value (`cisco_xe`, `cisco_nxos`, etc.). No code changes needed.

### Upgrade to TextFSM parsing

In `app/parsers.py`, replace any line-by-line parser with:

```python
from ntc_templates.parse import parse_output
parsed = parse_output(platform="cisco_ios", command="show vlan brief", data=raw)
```

---

## Project structure

```
netpulse/
├── app/
│   ├── main.py               # CLI entry point — arg parsing, dispatch, output
│   ├── intents.py            # NL query → IntentRequest (keyword/regex router)
│   ├── validators.py         # Safety checks before any SSH connection opens
│   ├── executor.py           # Shared job dispatch engine (CLI + OpenClaw)
│   ├── inventory.py          # Loads devices.yaml → Device objects
│   ├── ssh_client.py         # Netmiko SSH wrapper — runs pre-approved commands
│   ├── parsers.py            # Raw CLI output → structured dicts
│   ├── audit.py              # SSOT comparison logic (pure Python, no SSH)
│   ├── ssot.py               # SSOT file loader (ssot/*.yaml → typed objects)
│   ├── formatter.py          # Rich terminal output + JSON/CSV output
│   ├── summarizer.py         # One-line chat summaries for OpenClaw
│   ├── openclaw_adapter.py   # OpenClaw integration entry point
│   ├── models.py             # Pydantic models: Device, IntentRequest, JobResult,
│   │                         #   AuditStatus, AuditFinding, AuditResult
│   ├── config.py             # Paths and env var constants
│   ├── logger.py             # Logging setup (file + stderr)
│   ├── snmp_client.py        # SNMP scaffold (v1 placeholder)
│   └── jobs/
│       ├── show_interfaces.py
│       ├── show_vlans.py
│       ├── show_trunks.py
│       ├── show_version.py
│       ├── show_errors.py
│       ├── show_cdp.py
│       ├── show_mac.py
│       ├── show_spanning_tree.py
│       ├── ping.py
│       ├── backup_config.py
│       ├── diff_backup.py
│       ├── health_check.py
│       ├── audit_vlans.py    # VLAN SSOT audit
│       ├── audit_trunks.py   # Trunk SSOT audit
│       ├── device_facts.py   # Collect device facts (no comparison)
│       └── drift_check.py    # Combined VLAN + trunk + role audit
├── inventory/
│   └── devices.yaml
├── ssot/
│   ├── vlans.yaml            # Expected VLANs per role
│   ├── trunks.yaml           # Expected trunk allowed VLANs per role
│   └── device_roles.yaml     # Expected role per device
├── output/
│   ├── backups/              # Config backup files
│   └── logs/                 # netpulse.log
├── skills/
│   └── netpulse/
│       └── SKILL.md                # OpenClaw skill — teaches agent how to call NetPulse
├── scripts/
│   └── run_openclaw_netpulse.sh    # Shell wrapper — handles venv, called by exec tool
├── tests/
│   ├── test_intents.py
│   ├── test_inventory.py
│   ├── test_parsers.py
│   ├── test_validators.py
│   ├── test_audit.py         # Audit comparison logic + parser helpers
│   └── test_openclaw_adapter.py
├── .env.example
├── OPENCLAW_INTEGRATION.md   # Full OpenClaw integration guide
├── requirements.txt
└── README.md
```

---

## Future integration points (TODO markers in source)

| Tag | Location(s) | What it enables |
|---|---|---|
| `TODO (approval workflow)` | `openclaw_adapter.py` | Confirmation prompt before `backup_config` or future write actions |
| `TODO (SNMP enrichment)` | `models.py`, `inventory.py`, `snmp_client.py` | SNMP-based reachability and counter enrichment |
| `TODO (config diff mode)` | `parsers.py` | Normalised config parsing for structured line-by-line diffs |
| `TODO (Ansible execution path)` | `openclaw_adapter.py` | Route approved write intents to Ansible instead of SSH |

---

## Design constraints (v1)

- No database
- No web frontend
- No Docker
- No async framework
- No API server
- No LLM API calls
- No autonomous remediation
- No free-form CLI forwarded to devices

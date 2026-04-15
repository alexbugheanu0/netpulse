# NetPulse

A simple, daily-use network operations copilot for Cisco switches.

NetPulse lets a network engineer type natural language requests and
automatically runs the right show commands or config backups over SSH.
It is intentionally small, safe, and easy to extend — not a framework.

---

## Why it exists

Most network automation tools are either too complex for daily use, or
require an LLM API for every query. NetPulse sits in the middle:
deterministic keyword routing for safety, SSH for reliability, and
Rich for readable output. It is designed to become the execution
backend for [OpenClaw](https://github.com) in a future release.

---

## Supported intents (v1)

| Intent            | What it runs                   |
|-------------------|-------------------------------|
| `show_interfaces` | `show interfaces status`      |
| `show_vlans`      | `show vlan brief`             |
| `show_trunks`     | `show interfaces trunk`       |
| `show_version`    | `show version`                |
| `backup_config`   | `show running-config` → file  |
| `health_check`    | version + interfaces + vlans  |

---

## Folder structure

```
netpulse/
├── app/
│   ├── main.py          # CLI entry point
│   ├── inventory.py     # Loads devices.yaml
│   ├── intents.py       # NL → IntentRequest router
│   ├── validators.py    # Request safety checks
│   ├── ssh_client.py    # Netmiko SSH wrapper
│   ├── snmp_client.py   # SNMP scaffold (v1 placeholder)
│   ├── parsers.py       # Raw output parsers
│   ├── config.py        # Env vars and paths
│   ├── models.py        # Pydantic models
│   ├── logger.py        # Logging setup
│   ├── formatter.py     # Rich CLI output
│   └── jobs/
│       ├── show_interfaces.py
│       ├── show_vlans.py
│       ├── show_trunks.py
│       ├── show_version.py
│       ├── backup_config.py
│       └── health_check.py
├── inventory/
│   └── devices.yaml     # Device list (no credentials)
├── output/
│   ├── backups/         # Config backup files
│   └── logs/            # netpulse.log
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

---

## Installation

```bash
# 1. Clone or create the project folder
cd netpulse-project

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up your environment file
cp .env.example .env
# Edit .env with your lab SSH credentials

# 5. Update the inventory
# Edit inventory/devices.yaml with real device IPs
```

---

## .env setup

```env
NETPULSE_USERNAME=admin
NETPULSE_PASSWORD=your_ssh_password
NETPULSE_SECRET=your_enable_secret
NETPULSE_SSH_TIMEOUT=30
NETPULSE_SSH_PORT=22
```

Credentials are read from `.env` only. They are never stored in YAML
or committed to version control. Add `.env` to your `.gitignore`.

---

## Example inventory (inventory/devices.yaml)

```yaml
devices:
  - name: sw-core-01
    hostname: sw-core-01.lab.local
    ip: 192.168.1.1
    platform: cisco_ios
    role: core
    ssh_enabled: true
    snmp_enabled: false
```

Supported platforms follow Netmiko naming: `cisco_ios`, `cisco_xe`, etc.

---

## Example commands

```bash
# Natural language — single device
python3 app/main.py "show trunk status on sw-dist-01"
python3 app/main.py "show vlans on sw-core-01"
python3 app/main.py "backup config from sw-acc-02"

# Natural language — all devices
python3 app/main.py "health check all switches"
python3 app/main.py "show version on all switches"

# Structured flags (bypasses NL parser)
python3 app/main.py --intent show_trunks --device sw-dist-01
python3 app/main.py --intent health_check
```

---

## Running tests

```bash
# From project root with venv active
pytest tests/ -v
```

No devices are needed to run the tests — they cover intent parsing,
inventory loading, and validation only (no SSH).

---

## How to extend it

### Add a new intent

1. Add the new value to `IntentType` in `app/models.py`.
2. Add keyword patterns to `INTENT_PATTERNS` in `app/intents.py`.
3. Create `app/jobs/your_new_job.py` with a `run(device) -> JobResult` function.
4. Register it in `JOB_MAP` in `app/main.py`.

### Add a new device platform

Update the device entry in `devices.yaml` with the correct Netmiko
`platform` value (e.g. `cisco_xe`, `cisco_nxos`). No other changes needed.

### Switch to TextFSM parsing

In `app/parsers.py`, replace the line-by-line logic with:

```python
from ntc_templates.parse import parse_output
parsed = parse_output(platform="cisco_ios", command="show vlan brief", data=raw)
```

---

## Future OpenClaw integration

NetPulse is designed to be called as an execution backend by OpenClaw.
Search for `TODO (OpenClaw integration)` comments in the source for
the planned integration points:

- `app/intents.py` — expose `parse_intent()` as a tool call
- `app/jobs/health_check.py` — feed `parsed_data` to OpenClaw for NL summaries
- `app/models.py` — `IntentRequest` and `JobResult` are already JSON-serialisable
- `app/snmp_client.py` — SNMP polling to enrich OpenClaw context

---

## Design constraints (v1)

- No database
- No web frontend
- No Docker
- No async framework
- No API server
- No GUI
- No LLM API calls
- No autonomous remediation
- No free-form CLI accepted from user input

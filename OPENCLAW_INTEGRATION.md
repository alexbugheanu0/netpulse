# NetPulse + OpenClaw Integration

[OpenClaw](https://openclaw.ai) is a personal AI assistant that runs locally (Node.js / npm),
connects to Telegram, WhatsApp, Discord, Signal, and iMessage, and extends the LLM agent with
a **Skills** plugin system.

NetPulse integrates with OpenClaw as a **native skill**. The skill file (`skills/netpulse/SKILL.md`)
teaches the LLM agent when to call NetPulse and how to build valid JSON payloads. OpenClaw invokes
NetPulse via its built-in `exec` tool — the agent runs a shell command and gets back clean JSON.

No API server, no custom webhook, no database. The agent reads SKILL.md and calls the adapter as a
subprocess.

---

## How it works

```
User message (Telegram / WhatsApp / Discord)
         │
         ▼
OpenClaw LLM agent
  (reads skills/netpulse/SKILL.md at session start)
         │  decides intent, device, scope
         ▼
exec tool
  cd /path/to/netpulse-project
  python3 -m app.openclaw_adapter --json '{"intent":"...","device":"...","scope":"..."}'
         │
         ▼
app/openclaw_adapter.py
  (schema validation → allowlist → inventory lookup → executor)
         │
         ▼
SSH to Cisco device
         │
         ▼
JSON response → summary → chat reply
```

All execution is read-only. The adapter enforces an explicit intent allowlist and never lets any
string from OpenClaw reach the device SSH session directly.

---

## Installation

### 1. Install NetPulse dependencies

```bash
cd /home/alex/netpulse-project
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set SSH credentials

**Option A — `.env` file (simpler for a single-machine setup)**

```bash
cp .env.example .env
# Edit .env and fill in:
#   NETPULSE_USERNAME=admin
#   NETPULSE_PASSWORD=yourpassword
```

**Option B — OpenClaw secrets store (keeps credentials out of the filesystem)**

```bash
openclaw secrets set NETPULSE_USERNAME admin
openclaw secrets set NETPULSE_PASSWORD yourpassword
```

When stored via OpenClaw secrets, the variables are injected into the environment
before `exec` runs, so `app/openclaw_adapter.py` picks them up automatically via
`python-dotenv` / `os.environ`.

### 3. Install the skill

**Option A — copy to the shared OpenClaw skills folder**

```bash
cp -r /home/alex/netpulse-project/skills/netpulse ~/.openclaw/skills/
```

**Option B — add the project skills directory to `openclaw.json`**

```bash
openclaw config set skills.load.extraDirs '["/home/alex/netpulse-project/skills"]'
```

### 4. Verify the skill loaded

```bash
openclaw skills list | grep netpulse
```

You should see `netpulse` in the list. If not, restart OpenClaw after copying the skill.

### 5. Update the device path in the skill

Open `skills/netpulse/SKILL.md` and confirm the `cd` path in the "How to call NetPulse"
section matches your actual project location:

```
cd /home/alex/netpulse-project && source .venv/bin/activate && ...
```

---

## Testing

### Unit tests (no SSH required)

```bash
source .venv/bin/activate
pytest tests/ -v
```

### Adapter smoke tests (no live device required)

```bash
source .venv/bin/activate

# Unknown device — should return JSON error
python3 -m app.openclaw_adapter --json '{"intent":"show_vlans","device":"sw-nonexistent","scope":"single"}'

# Disallowed intent — should return JSON error
python3 -m app.openclaw_adapter --json '{"intent":"ping","device":"sw-core-01","scope":"single"}'

# Schema error (missing intent) — should return JSON error
python3 -m app.openclaw_adapter --json '{"device":"sw-core-01"}'
```

### Test via the wrapper script

```bash
./scripts/run_openclaw_netpulse.sh '{"intent":"show_vlans","device":"sw-core-01","scope":"single"}'
```

### Live test from OpenClaw chat

Start a new OpenClaw session and send:

```
what vlans are on sw-core-01?
```

OpenClaw should load the netpulse skill, build the correct payload, run the adapter, and
reply with a VLAN summary.

> **Exec approval note:** The first time OpenClaw uses the `exec` tool you may see a prompt asking
> you to approve execution of shell commands by this skill. Grant approval for the netpulse skill
> to allow it to call the adapter.

---

## Allowed intents

### Operational show intents — L2

| Intent | Command run | Key fields returned |
|---|---|---|
| `show_interfaces` | `show interfaces status` | port, status, vlan, duplex, speed |
| `show_vlans` | `show vlan brief` | vlan_id, name, status |
| `show_trunks` | `show interfaces trunk` | port, mode, encap, native_vlan, vlans_allowed |
| `show_errors` | `show interfaces` | port, input_errors, crc, output_errors, resets |
| `show_cdp` | `show cdp neighbors detail` | device_id, ip, platform, local_port, remote_port |
| `show_mac` | `show mac address-table` | vlan, mac, type, port |
| `show_spanning_tree` | `show spanning-tree` | vlan, port, role, state (FWD/BLK/LIS/LRN), cost |
| `show_etherchannel` | `show etherchannel summary` | group, protocol, flags, member_ports with flags |
| `show_port_security` | `show port-security` | interface, max_mac, current_mac, violations, action |

### Operational show intents — L3 and diagnostics

| Intent | Command run | Key fields returned |
|---|---|---|
| `show_version` | `show version` | software, uptime, hardware, serial |
| `show_route` | `show ip route` | protocol, prefix, mask, admin_distance, metric, next_hop, interface |
| `show_arp` | `show ip arp` | protocol, ip, age, mac, type, interface |
| `show_logging` | `show logging` | timestamp, facility, severity_code, mnemonic, message (last 20) |
| `backup_config` | `show running-config` | Saved to `output/backups/` |
| `health_check` | version + interfaces + vlans | Combined health snapshot |
| `ping` | `ping <target> repeat 5` | success_rate, sent, received, min_ms, avg_ms, max_ms |

### SSOT audit intents

| Intent | SSOT source | Notes |
|---|---|---|
| `audit_vlans` | `ssot/vlans.yaml` | Compare device VLANs against expected baseline |
| `audit_trunks` | `ssot/trunks.yaml` | Compare trunk allowed VLANs against expected baseline |
| `device_facts` | — | Platform, IOS, uptime, port stats — no comparison |
| `drift_check` | both SSOT files + `ssot/device_roles.yaml` | Combined VLAN + trunk + role drift |

---

## Request / response format

### Request schema

```json
{
  "intent":    "<intent name>",
  "device":    "<device name from inventory/devices.yaml>",
  "scope":     "single | all | role",
  "role":      "<role name — required when scope=role>",
  "raw_query": "<original user message — optional, for logging>"
}
```

### Scope rules

| scope | device | role | Behaviour |
|---|---|---|---|
| `single` | required | — | One named device |
| `all` | omit | — | All SSH-enabled devices in inventory |
| `role` | omit | required | All SSH-enabled devices with that role |

### Response schema

```json
{
  "success": true,
  "intent":  "show_vlans",
  "scope":   "single",
  "error":   null,
  "results": [
    {
      "device":      "sw-core-01",
      "success":     true,
      "summary":     "SW-CORE-01: 6 VLAN(s) — 1, 10, 20, 30, 100, 200.",
      "parsed_data": { ... },
      "elapsed_ms":  312.5,
      "error":       null
    }
  ]
}
```

**Present `results[].summary` in chat** — it is already formatted for human reading.

---

## Example requests and responses

### show_vlans — single device

**Request:**
```json
{"intent":"show_vlans","device":"sw-core-01","scope":"single"}
```

**Response:**
```json
{
  "success": true,
  "intent":  "show_vlans",
  "scope":   "single",
  "error":   null,
  "results": [
    {
      "device":      "sw-core-01",
      "success":     true,
      "summary":     "SW-CORE-01: 6 VLAN(s) — 1, 10, 20, 30, 100, 200.",
      "parsed_data": [
        {"vlan_id": "1",   "name": "default"},
        {"vlan_id": "10",  "name": "MGMT"},
        {"vlan_id": "20",  "name": "SERVERS"},
        {"vlan_id": "30",  "name": "USERS"},
        {"vlan_id": "100", "name": "NATIVE"},
        {"vlan_id": "200", "name": "VOICE"}
      ],
      "elapsed_ms": 312.5,
      "error": null
    }
  ]
}
```

---

### health_check — all devices

**Request:**
```json
{"intent":"health_check","scope":"all"}
```

**Response:**
```json
{
  "success": true,
  "intent":  "health_check",
  "scope":   "all",
  "error":   null,
  "results": [
    {
      "device":  "sw-core-01",
      "success": true,
      "summary": "SW-CORE-01: IOS 15.2(4)E7, up 42 days — 12/24 ports connected, 6 VLANs.",
      "elapsed_ms": 640.0,
      "error": null
    },
    {
      "device":  "sw-dist-01",
      "success": true,
      "summary": "SW-DIST-01: IOS 15.2(4)E7, up 15 days — 8/24 ports connected, 4 VLANs.",
      "elapsed_ms": 580.0,
      "error": null
    }
  ]
}
```

---

### audit_vlans — compliant

**Request:**
```json
{"intent":"audit_vlans","device":"sw-core-01","scope":"single"}
```

**Response:**
```json
{
  "success": true,
  "intent":  "audit_vlans",
  "scope":   "single",
  "error":   null,
  "results": [
    {
      "device":  "sw-core-01",
      "success": true,
      "summary": "SW-CORE-01: VLAN baseline compliant — 6 VLAN(s) match.",
      "parsed_data": {
        "status":      "compliant",
        "findings":    [],
        "summary":     "SW-CORE-01: VLAN baseline compliant — 6 VLAN(s) match.",
        "warnings":    [],
        "next_action": "No action required."
      },
      "elapsed_ms": 310.0,
      "error": null
    }
  ]
}
```

---

### audit_vlans — drift detected

**Response (VLAN 30 missing, VLAN 999 extra):**
```json
{
  "success": true,
  "intent":  "audit_vlans",
  "scope":   "single",
  "error":   null,
  "results": [
    {
      "device":  "sw-dist-01",
      "success": true,
      "summary": "SW-DIST-01: VLAN drift — missing: 30; extra: 999.",
      "parsed_data": {
        "status":  "missing",
        "findings": [
          {"status": "missing", "field": "vlan_id", "expected": "30",  "actual": null,
           "message": "VLAN 30 (USERS) missing from device"},
          {"status": "extra",   "field": "vlan_id", "expected": null,  "actual": "999",
           "message": "VLAN 999 (ROGUE) present on device but not in baseline"}
        ],
        "summary":     "SW-DIST-01: VLAN drift — missing: 30; extra: 999.",
        "warnings":    ["VLAN 30 (USERS) missing from device", "VLAN 999 (ROGUE) present on device but not in baseline"],
        "next_action": "Review VLANs listed as MISSING or EXTRA. Add missing VLANs or update ssot/vlans.yaml."
      },
      "elapsed_ms": 310.0,
      "error": null
    }
  ]
}
```

---

### audit_trunks — trunk drift

**Response (trunk port missing VLAN 30):**
```json
{
  "success": true,
  "intent":  "audit_trunks",
  "scope":   "single",
  "error":   null,
  "results": [
    {
      "device":  "sw-dist-01",
      "success": true,
      "summary": "SW-DIST-01: Trunk drift — Gi1/0/1: missing allowed VLANs [30]. Expected: [1, 10, 20, 30, 100]. Actual: [1, 10, 20, 100].",
      "parsed_data": {
        "status":  "missing",
        "findings": [
          {
            "status":   "missing",
            "field":    "allowed_vlans",
            "expected": [1, 10, 20, 30, 100],
            "actual":   [1, 10, 20, 100],
            "message":  "Gi1/0/1: missing allowed VLANs [30]. Expected: [1, 10, 20, 30, 100]. Actual: [1, 10, 20, 100]."
          }
        ],
        "warnings":    ["Gi1/0/1: missing allowed VLANs [30]..."],
        "next_action": "Review trunk ports listed above. Update 'switchport trunk allowed vlan' to match ssot/trunks.yaml."
      },
      "elapsed_ms": 280.0,
      "error": null
    }
  ]
}
```

---

### drift_check — all devices

**Request:**
```json
{"intent":"drift_check","scope":"all","raw_query":"drift check all switches"}
```

**Response (one device passing, one failing):**
```json
{
  "success": false,
  "intent":  "drift_check",
  "scope":   "all",
  "error":   null,
  "results": [
    {
      "device":  "sw-core-01",
      "success": true,
      "summary": "SW-CORE-01: Drift check clean — VLANs, trunks, and device role all compliant.",
      "elapsed_ms": 890.0,
      "error": null
    },
    {
      "device":  "sw-dist-01",
      "success": false,
      "summary": "SW-DIST-01: Drift detected — VLAN 30 missing; trunk Gi1/0/1 missing VLAN 30.",
      "elapsed_ms": 860.0,
      "error": null
    }
  ]
}
```

---

### device_facts — single device

**Request:**
```json
{"intent":"device_facts","device":"sw-core-01","scope":"single"}
```

**Response:**
```json
{
  "success": true,
  "intent":  "device_facts",
  "scope":   "single",
  "error":   null,
  "results": [
    {
      "device":  "sw-core-01",
      "success": true,
      "summary": "SW-CORE-01: Cisco WS-C3750X-24P, IOS 15.2(4)E7, up 42 days — 12/24 ports connected.",
      "parsed_data": {
        "platform": "WS-C3750X-24P",
        "ios_version": "15.2(4)E7",
        "uptime": "42 days, 3 hours",
        "total_ports": 24,
        "connected_ports": 12,
        "disabled_ports": 2
      },
      "elapsed_ms": 450.0,
      "error": null
    }
  ]
}
```

---

### Error — unknown device

**Request:**
```json
{"intent":"show_vlans","device":"sw-fake-99","scope":"single"}
```

**Response:**
```json
{
  "success": false,
  "intent":  "show_vlans",
  "scope":   "single",
  "error":   "Device 'sw-fake-99' not found in inventory.",
  "results": []
}
```

---

### Error — intent not permitted

**Request:**
```json
{"intent":"ping","device":"sw-core-01","scope":"single"}
```

**Response:**
```json
{
  "success": false,
  "intent":  "ping",
  "scope":   "single",
  "error":   "'ping' is not permitted via OpenClaw. Allowed: audit_trunks, audit_vlans, backup_config, device_facts, drift_check, health_check, show_interfaces, show_trunks, show_vlans, show_version.",
  "results": []
}
```

---

## Safety guidelines

### OpenClaw must NOT:
- Pass raw user text directly as `intent`
- Generate Cisco CLI commands and pass them via any field
- Call `ssh_client.py` or any job module directly
- Set `intent` to a value not in the allowed list
- Pass credentials or IPs as part of the payload

### OpenClaw must:
- Classify the user request into one of the approved intents first
- Pass `raw_query` for audit logging only — it is never executed
- Use `device` names that match exactly what is in `inventory/devices.yaml`
- Treat `results[].summary` as the chat-safe output

### Why OpenClaw must not generate raw device commands

Every command NetPulse runs on a device is a hardcoded constant in a job module
(e.g. `COMMAND = "show vlan brief"` in `app/jobs/show_vlans.py`). No string from
any external source — user message, OpenClaw response, or environment variable —
ever reaches the device SSH session. This is a deliberate safety constraint.

If OpenClaw were allowed to pass raw CLI strings, a prompt injection or
misconfiguration could execute `no vlan 1` or `reload` on production switches.
The intent allowlist and job dispatch model prevent this entirely.

---

## Adding a new intent safely

1. Build and test the new job via the CLI first:
   ```bash
   python3 -m app.main --intent your_new_intent --device sw-core-01
   ```

2. Verify the job is read-only (or get explicit approval for write operations).

3. Add it to `OPENCLAW_ALLOWED_INTENTS` in `app/openclaw_adapter.py`.

4. Add a summary branch in `app/summarizer.py` for the new intent.

5. Write a test in `tests/test_openclaw_adapter.py` that mocks execution.

6. Update the allowed intents table in `skills/netpulse/SKILL.md`.

7. Document the new intent in this file.

---

## Troubleshooting

### "Invalid JSON input"

The payload sent to the adapter is not valid JSON.

```bash
# Test with a known-good payload first
python3 -m app.openclaw_adapter --json '{"intent":"show_vlans","device":"sw-core-01","scope":"single"}'
```

Common causes: unescaped double-quotes inside a string, trailing comma after
the last field, single-quoted JSON (JSON requires double quotes).

---

### "Device 'X' not found in inventory"

The `device` field does not match any entry in `inventory/devices.yaml`.
Device names are **case-sensitive** and must be exact.

```bash
# List all device names
grep -E '^\s+name:' inventory/devices.yaml
```

If the device exists but has a different name than expected, update either
`devices.yaml` or the OpenClaw payload — never guess a name.

---

### "Intent 'X' is not a recognised NetPulse intent" / "not permitted via OpenClaw"

Two separate cases:

| Error | Meaning |
|---|---|
| `not a recognised NetPulse intent` | The string is not a valid `IntentType` at all |
| `not permitted via OpenClaw` | Valid intent but not in the OpenClaw allowlist |

To add an intent to the allowlist, edit `OPENCLAW_ALLOWED_INTENTS` in
`app/openclaw_adapter.py` — but only after building and testing it via the CLI
first (see the "Adding a new intent safely" section above).

---

### Environment variables missing

If `NETPULSE_USERNAME` or `NETPULSE_PASSWORD` are empty, SSH connections will fail
immediately on the first login attempt.

```bash
# Check variables are loaded
source .venv/bin/activate
python3 -c "from app.config import SSH_USERNAME, SSH_PASSWORD; print(repr(SSH_USERNAME), repr(SSH_PASSWORD))"
```

If they print as empty strings, check:
1. `.env` file exists at the project root (copy from `.env.example`).
2. Variable names match exactly: `NETPULSE_USERNAME`, `NETPULSE_PASSWORD`.
3. No extra spaces around the `=` sign in the `.env` file.

Alternatively, store credentials in the OpenClaw secrets store:
```bash
openclaw secrets set NETPULSE_USERNAME admin
openclaw secrets set NETPULSE_PASSWORD yourpassword
```

---

### SSH authentication failure

**Symptom in summary:** `SW-CORE-01: Authentication failed — check NETPULSE_USERNAME / NETPULSE_PASSWORD in .env.`

**Symptom in result.error:** contains `Authentication` or `auth`

Steps:
1. Verify the username and password are correct with a manual SSH test:
   ```bash
   ssh admin@192.168.100.11
   ```
2. Check whether the switch requires an enable secret (`NETPULSE_SECRET` in `.env`).
3. Confirm the switch allows SSH from this host (check SSH access-class ACL).

---

### SSH timeout

**Symptom in summary:** `SW-CORE-01: Unreachable or slow — connection timed out.`

**Symptom in result.error:** contains `timed out` or `timeout`

Steps:
1. Confirm the device IP in `inventory/devices.yaml` is correct.
2. Test reachability from this host:
   ```bash
   python3 -m app.main --intent show_version --device sw-core-01 --check
   ```
   The `--check` flag runs a TCP port-22 test before opening SSH.
3. Check for a firewall or ACL blocking port 22 between this host and the device.
4. If the device is slow, increase `NETPULSE_SSH_TIMEOUT` in `.env` (default: 30s).

---

### Skill not loading in OpenClaw

If `openclaw skills list` does not show `netpulse`:

1. Confirm the `SKILL.md` exists at `~/.openclaw/skills/netpulse/SKILL.md` or that
   `skills.load.extraDirs` includes the project's `skills/` folder.
2. Restart OpenClaw after adding the skill — skills are read at session start.
3. Check OpenClaw logs for YAML parse errors in the skill frontmatter.

---

### Checking the logs

All adapter activity is written to `output/logs/netpulse.log`
under the logger name `netpulse.openclaw`. Warnings and errors also go to stderr.

```bash
# Follow live log output during a call
tail -f output/logs/netpulse.log

# Show only OpenClaw log lines
grep "netpulse.openclaw" output/logs/netpulse.log | tail -50

# Show only failures
grep -E "(WARNING|ERROR)" output/logs/netpulse.log | tail -20
```

Each successful request logs: intent, scope, device, per-device result (OK / FAILED),
and total elapsed milliseconds.

---

## Future integration points

These are marked as TODO comments in the source code.

| TODO tag | Location | What it enables |
|---|---|---|
| `TODO (approval workflow)` | `openclaw_adapter.py` | Confirmation prompt before `backup_config` (or future write actions) |
| `TODO (SNMP enrichment)` | `openclaw_adapter.py`, `models.py`, `inventory.py` | Pre-flight SNMP reachability and counter data |
| `TODO (diff mode)` | `openclaw_adapter.py`, `parsers.py` | Add `diff_backup` to allowlist for post-change audits |
| `TODO (Ansible execution path)` | `openclaw_adapter.py` | Route approved write intents to Ansible instead of SSH |

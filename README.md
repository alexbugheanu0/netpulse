# NetPulse

**Talk to your Cisco switches from chat.** NetPulse is the SSH layer behind [OpenClaw](https://openclaw.ai): you ask in plain language (Telegram, WhatsApp, Discord, or similar), and it runs the right `show` commands, parses the output, and answers with a short summary—no copy-pasting into a terminal.

---

## Start here

| If you want to… | Do this |
|-------------------|---------|
| **Get running fast** | Run `bash scripts/setup.sh` after cloning (Ubuntu/Debian). It sets up Python, `.env`, and can wire OpenClaw. |
| **Wire chat to your lab** | Install the skill from `skills/netpulse/` into OpenClaw, set `NETPULSE_*` secrets, then ask questions like “what VLANs are on sw-core-01?”. |
| **Script or automate** | Use `python3 -m app.main` with `--intent` and `--device` (see [Developer CLI](#developer-cli-appmainpy)). |
| **Change device config** | Writes are **single-device only**, gated by policy in `ssot/` and (in chat) explicit confirmation. There is no “run arbitrary CLI” path. |

**Important:** Credentials live in `.env` only—never in `inventory/` or git. The app never sends raw user text to SSH; only predefined intents and validated parameters reach the devices.

---

## What NetPulse actually does

1. Loads your devices from `inventory/devices.yaml`.
2. Maps each request to a **fixed** command (e.g. `show vlan brief` for `show_vlans`)—no free-form Cisco CLI.
3. Connects over SSH (Netmiko), parses output into structured data, and returns one-line summaries for chat or JSON for scripts.

That keeps behavior predictable and auditable. For deep detail on OpenClaw wiring, see [`OPENCLAW_INTEGRATION.md`](OPENCLAW_INTEGRATION.md) and [`skills/netpulse/SKILL.md`](skills/netpulse/SKILL.md).

---

## Supported intents

### Show / operational

| Intent | On the device |
|--------|----------------|
| `show_interfaces` | `show interfaces status` |
| `show_vlans` | `show vlan brief` |
| `show_trunks` | `show interfaces trunk` |
| `show_version` | `show version` |
| `show_errors` | `show interfaces` (error counters) |
| `show_cdp` | `show cdp neighbors detail` |
| `show_mac` | `show mac address-table` |
| `show_spanning_tree` | `show spanning-tree` |
| `ping` | `ping <target> repeat 5` |
| `backup_config` | `show running-config` → file under `output/backups/` |
| `diff_backup` | Diff two most recent backups |
| `health_check` | Version + interfaces + VLANs (one SSH session) |

Additional read intents (routing, ARP, EtherChannel, port security, logging, etc.) are documented in [`skills/netpulse/SKILL.md`](skills/netpulse/SKILL.md) and the OpenClaw allowlist in `app/openclaw_adapter.py`—same pattern: one intent maps to one approved command shape.

### SSOT audit (read-only)

| Intent | Purpose |
|--------|---------|
| `audit_vlans` | Compare live VLANs to `ssot/vlans.yaml` |
| `audit_trunks` | Compare trunks to `ssot/trunks.yaml` |
| `device_facts` | Snapshot: platform, IOS, uptime, ports |
| `drift_check` | Combined VLAN + trunk + role check |

Audits only **read** the switch and compare to your YAML baselines—they never push config by themselves.

---

## Quick start

### Option A — Automated (recommended on Ubuntu / Debian)

```bash
git clone https://github.com/alexbugheanu0/netpulse.git netpulse-project
cd netpulse-project
bash scripts/setup.sh
```

The script installs dependencies, creates the venv, helps you set SSH credentials, and can add devices. Later, add or remove devices with:

```bash
bash scripts/add-device.sh
```

### Option B — Manual

```bash
git clone https://github.com/alexbugheanu0/netpulse.git netpulse-project
cd netpulse-project
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # edit NETPULSE_USERNAME / NETPULSE_PASSWORD
# Edit inventory/devices.yaml with real IPs
```

Optional reachability check (TCP port 22 only—**does not** run the intent afterward):

```bash
python3 -m app.main --intent show_vlans --device sw-core-01 --check
```

Drop `--check` when you want the real job to run.

---

## Environment (`.env`)

Copy [`.env.example`](.env.example) to `.env` and fill in your lab values. At minimum:

- **`NETPULSE_USERNAME` / `NETPULSE_PASSWORD`** — SSH login  
- **`NETPULSE_SECRET`** — enable password, if your workflow needs `enable`  
- **`NETPULSE_SSH_TIMEOUT`** — default **15** seconds (tune per `.env.example` comments)  
- **`NETPULSE_SSH_PORT`** — usually `22`  
- **`NETPULSE_SSH_WORKERS`** — concurrency cap for multi-device scopes  

`.env` is gitignored; do not commit it.

---

## Inventory (`inventory/devices.yaml`)

Each device needs a name, IP, Netmiko `platform` (e.g. `cisco_ios`), `role`, and `ssh_enabled`. Example:

```yaml
devices:
  - name: sw-core-01
    hostname: sw-core-01
    ip: 192.168.100.11
    platform: cisco_ios
    role: core
    ssh_enabled: true
```

Roles matter when you use `--role` or `scope=role` from OpenClaw. Full field list and samples stay in the repo’s `inventory/` file.

---

## SSOT folder (`ssot/`)

These YAML files describe **what you expect** on the network and **what changes are allowed**:

| File | Role |
|------|------|
| `vlans.yaml` | Expected VLANs per role |
| `trunks.yaml` | Expected trunk / allowed VLANs |
| `device_roles.yaml` | Which device should be which role |
| `change-policy.yaml` | When the agent may auto-approve vs must ask vs must refuse |
| `protected-resources.yaml` | VLANs, devices, and interfaces that are always sensitive |

The agent (and validators for write intents) use these for governance before `add_vlan`, `remove_vlan`, or interface changes. Edit the files under `ssot/` to match your environment; see inline comments there for structure.

---

## Developer CLI (`app/main.py`)

Use this for scripts, CI, or quick checks. Chat users normally go through OpenClaw instead.

**Single device**

```bash
python3 -m app.main --intent show_vlans --device sw-core-01
python3 -m app.main --intent ping --device sw-core-01 --target 10.0.0.1
python3 -m app.main --intent backup_config --device sw-acc-02
```

**All devices or by role**

```bash
python3 -m app.main --intent health_check
python3 -m app.main --intent show_errors --role access
```

**Useful flags**

| Flag | Meaning |
|------|---------|
| `--scope all` | All SSH-enabled devices |
| `--role <name>` | Only devices with that role |
| `--target <ip>` | Ping destination (required for `ping`) |
| `--filter <str>` | Narrow text output |
| `--format json` / `csv` | Machine-readable output |
| `--dry-run` | Show what would run, no SSH |
| `--check` | TCP reachability on port 22 only, then **exit** (no intent execution) |

**Exit codes:** `0` = all jobs OK, `1` = bad args/validation, `2` = runtime job failure.

---

## Tests

```bash
pytest tests/ -v
```

There are **250** unit tests (no live switches required): intents, parsers, inventory, validation, audits, OpenClaw adapter, and SSH helpers. Run `pytest tests/ --collect-only -q` to confirm the current count.

---

## OpenClaw integration

1. Copy or register `skills/netpulse/` so OpenClaw loads [`SKILL.md`](skills/netpulse/SKILL.md).  
2. Provide the same env vars as `.env` (e.g. `openclaw secrets set …` or a project `.env`).  
3. Call the adapter directly to debug:

```bash
python3 -m app.openclaw_adapter --json '{"intent": "show_vlans", "device": "sw-core-01", "scope": "single"}'
./scripts/run_openclaw_netpulse.sh '{"intent": "show_version", "device": "sw-core-01", "scope": "single"}'
```

Full intent list and payloads: **[`OPENCLAW_INTEGRATION.md`](OPENCLAW_INTEGRATION.md)** and **`skills/netpulse/SKILL.md`**.

---

## Config backups

Backups land in `output/backups/` as:

`<device-name>_YYYYMMDD_HHMMSS.cfg`

Use `diff_backup` to compare the two newest files for a device.

---

## Extending NetPulse

1. Add an `IntentType` in `app/models.py`.  
2. Add patterns in `app/intents.py` (for natural language) if needed.  
3. Add `app/jobs/<name>.py` with `run(device) -> JobResult`.  
4. Register in `app/executor.py` (and CLI previews in `app/main.py` if you use them).  
5. For OpenClaw: allowlist in `app/openclaw_adapter.py` and document in `skills/netpulse/SKILL.md`.

New platform: set the right Netmiko `device_type` in `devices.yaml`—often no code change.

---

## Project layout (short)

```
app/              CLI, executor, SSH, parsers, OpenClaw adapter, validators
inventory/        devices.yaml
ssot/             Baseline and policy YAML
skills/netpulse/  OpenClaw skill
scripts/          setup.sh, OpenClaw wrapper, add-device
tests/            Unit tests
output/           backups/, logs/ (generated; gitignored paths)
```

---

## Design choices (v1)

- No database, no bundled web UI, no Docker requirement  
- No API server and no LLM calls inside NetPulse itself  
- No autonomous remediation loops  
- **No** passing arbitrary CLI strings to devices—only structured intents  

---

## Roadmap hints (see `TODO` in source)

| Area | Notes |
|------|--------|
| SNMP | Scaffold exists; enrichment not wired end-to-end |
| Config diff | Richer parsing for line-by-line diffs |
| Ansible | Optional path for approved changes instead of direct SSH |

Policy and protected resources for writes are enforced in code and YAML; see `ssot/` and `app/validators.py`.

# NetPulse

NetPulse is an AI-safe execution control plane for **read-only Cisco switch
operations**. It accepts structured requests or OpenClaw chat intents, reads
only enrolled switches, and stores plan and audit evidence for each request.

## Safety Boundary

NetPulse is intentionally restricted:

- Only SSH-enabled devices listed in `inventory/devices.yaml` may be contacted.
- An allowed status or audit check with no named target runs only across those
  enrolled, SSH-enabled inventory switches.
- Only fixed read commands are allowed.
- Configuration changes, arbitrary CLI, directed probes such as `ping`, and
  non-network operations are blocked.
- NetPulse never enters enable or configuration mode.
- Use a switch-side **read-only SSH account** and leave `NETPULSE_SECRET` unset.

```text
intent -> plan -> risk check -> inventory/read-only check -> execute -> audit
```

## Quick Start

### Option A - Setup Wizard

```bash
git clone https://github.com/alexbugheanu0/netpulse.git netpulse-project
cd netpulse-project
bash scripts/setup.sh
```

The setup wizard installs dependencies, creates the venv, helps you set SSH
credentials, and can add devices. Later, add or remove devices with:

```bash
bash scripts/add-device.sh
```

### Option B - Manual Setup

```bash
git clone https://github.com/alexbugheanu0/netpulse.git netpulse-project
cd netpulse-project
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with the read-only SSH username and password, then update
`inventory/devices.yaml` with the switches NetPulse is allowed to read.

## Credentials

Example `.env` configuration:

```dotenv
NETPULSE_USERNAME=netpulse_readonly
NETPULSE_PASSWORD=your_ssh_password_here
NETPULSE_SSH_TIMEOUT=15
NETPULSE_SSH_PORT=22
NETPULSE_SSH_WORKERS=10
```

Do not set `NETPULSE_SECRET`. Store credentials only in `.env` or an approved
secret store; never commit them to git.

## Enroll Switches

`inventory/devices.yaml` is the access allowlist. Remove placeholder or unowned
entries before use, and add only switches NetPulse may access.

```yaml
devices:
  - name: sw-core-01
    hostname: sw-core-01
    ip: 192.168.100.11
    platform: cisco_ios
    role: core
    ssh_enabled: true
```

To manage entries interactively:

```bash
bash scripts/add-device.sh
```

## Common Reads

Activate the environment before using the CLI:

```bash
source .venv/bin/activate
```

Read a single switch:

```bash
python3 -m app.main --intent show_vlans --device sw-core-01
python3 -m app.main --intent show_version --device sw-core-01
python3 -m app.main --intent show_errors --device sw-core-01
python3 -m app.main --intent diagnose_endpoint --device sw-acc-01 --endpoint 10.0.0.25
```

Read groups of enrolled switches:

```bash
python3 -m app.main "health check"
python3 -m app.main "show interface errors"
python3 -m app.main "audit vlans"
python3 -m app.main --intent health_check --scope all
python3 -m app.main --intent show_errors --role access
```

Run baselines and local backup checks:

```bash
python3 -m app.main --intent audit_vlans --device sw-core-01
python3 -m app.main --intent drift_check --device sw-core-01
python3 -m app.main --intent backup_config --device sw-core-01
python3 -m app.main --intent diff_backup --device sw-core-01
```

Targetless status reads and audits default to all enrolled, SSH-enabled
inventory switches. `backup_config`, `diff_backup`, and `diagnose_endpoint`
require an explicit device or scope.

Preview a request or test SSH reachability without running a read job:

```bash
python3 -m app.main --intent show_vlans --device sw-core-01 --dry-run
python3 -m app.main --intent show_vlans --device sw-core-01 --check
```

`--check` probes TCP port 22 only for SSH-enabled enrolled switches.

## Supported Operations

| Category | Intents |
|---|---|
| Switch state | `show_interfaces`, `show_vlans`, `show_trunks`, `show_version`, `show_errors` |
| Network tables | `show_cdp`, `show_mac`, `show_spanning_tree`, `show_route`, `show_arp`, `show_etherchannel`, `show_port_security`, `show_logging` |
| Diagnostics | `health_check`, `device_facts`, `diagnose_endpoint` |
| Baseline checks | `audit_vlans`, `audit_trunks`, `drift_check` |
| Local evidence | `backup_config`, `diff_backup` |

`ping` and all device configuration intents are blocked.

## OpenClaw

Telegram should be routed to a dedicated NetPulse OpenClaw agent whose
workspace is this repository. This makes an unqualified question such as
`what is the status of my devices?` run a health check only against enrolled,
SSH-enabled inventory switches, rather than checking OpenClaw host nodes.

```bash
openclaw agents add netpulse --non-interactive --workspace /home/alex/netpulse-project --bind telegram
openclaw agents list --bindings
openclaw skills list --agent netpulse
openclaw gateway restart
```

The setup wizard configures this routing automatically. To call the wrapper
directly with a structured read request:

```bash
./scripts/run_openclaw_netpulse.sh '{"intent":"show_vlans","device":"sw-core-01","scope":"single","response_mode":"telegram"}'
./scripts/run_openclaw_netpulse.sh '{"intent":"health_check","response_mode":"telegram"}'
```

In the second example, the omitted target is resolved to all enrolled,
SSH-enabled inventory switches. It cannot expand beyond inventory.

For payload schemas and chat integration details, see
[OPENCLAW_INTEGRATION.md](OPENCLAW_INTEGRATION.md) and
[skills/netpulse/SKILL.md](skills/netpulse/SKILL.md).

## Baselines And Evidence

Files under `ssot/` describe the expected VLAN, trunk, and role state of
enrolled switches. They support audit and drift checks; they do not authorize
configuration changes.

Plans are stored under `output/plans/`. Audit reports are stored under
`output/audit/YYYY-MM-DD/`. Configuration backups created by `backup_config`
are stored under `output/backups/`.

## Tests

Tests do not require live switches:

```bash
pytest tests/ -q
```

## Project Layout

```text
app/              execution, validation, adapters, parsers, safety policy
inventory/        enrolled switch allowlist
ssot/             expected-state baselines
skills/netpulse/  OpenClaw instructions
scripts/          setup and execution wrappers
tests/            unit tests
output/           generated plans, audits, logs, and backups
```

## License

Licensed under the [Apache License, Version 2.0](LICENSE). See [NOTICE](NOTICE)
for attribution information.

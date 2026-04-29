# NetPulse

NetPulse is an AI-safe execution control plane for infrastructure operations. It turns natural-language intent into structured, policy-checked, approved, verified, and auditable actions across network devices today, with a path toward compute, storage, and lab systems.

Current domain: Cisco network operations.

Architecture goal: safe AI-driven infrastructure orchestration.

Core loop:

```text
intent -> plan -> risk check -> approval -> execute -> verify -> audit
```

## Why NetPulse

AI agents are useful for operations only when execution is bounded. NetPulse keeps the agent away from arbitrary CLI and forces every request through fixed intents, typed parameters, policy checks, explicit approval gates, post-change verification, and JSON audit artifacts.

## Architecture

OpenClaw, CLI, and future integrations call the unified runner in `app/runner.py`. The runner builds an execution plan, classifies risk, checks approval state, routes to an adapter, verifies write actions, and saves an audit artifact.

The current production adapter wraps existing Cisco IOS jobs in `app/jobs/`. Mock adapters for compute, storage, and instruments live under `app/adapters/` and return deterministic data.

## Safety Model

- No arbitrary CLI execution.
- Every request maps to a fixed intent and validated parameters.
- Every request gets an execution plan before execution.
- Read-only intents run without approval.
- Write and high-risk intents require a server-side pending approval and signed receipt before execution.
- Existing SSOT and protected-resource policy remains enforced.
- Write actions get post-change verification where supported.
- Every lifecycle path writes a JSON audit artifact.

## Execution Lifecycle

1. Receive natural-language or structured request.
2. Normalize to a supported intent.
3. Generate an execution plan with steps and expected outputs.
4. Classify risk and evaluate SSOT/protected-resource policy.
5. Stop if blocked, or return an approval-required response when needed.
6. Execute through the selected adapter.
7. Verify write results.
8. Save the audit artifact and return structured proof.

## Risk Levels

- `READ_ONLY` - show, check, get, read, audit, and diagnostic intents.
- `LOW_CHANGE` - low-impact fixed changes such as `add_vlan`, subject to policy.
- `MEDIUM_CHANGE` - state-changing operations such as VLAN removal or access VLAN changes.
- `HIGH_RISK` - interface shutdown, trunk/routing/default-gateway/core-uplink style changes.
- `BLOCKED` - unknown intents, arbitrary CLI, or forbidden protected-resource actions.

## Audit Artifacts

Plans are written under `output/plans/`. Audit reports are written under `output/audit/YYYY-MM-DD/<request_id>.json` and include request metadata, plan, risk decision, approval state, prechecks, execution results, postchecks, errors, final status, and duration.

## Current Limitations

Production execution is still focused on Cisco IOS network operations. Compute, storage, and instrument adapters are mock-only. Verification is implemented for current VLAN/interface write intents and will grow as more write intents are added.

## Roadmap

See [`ROADMAP.md`](ROADMAP.md) for the phased path from safety control plane to multi-domain adapters and policy-backed infrastructure workflows.

## Start Here

| If you want to... | Do this |
|-------------------|---------|
| **Get running fast** | Run `bash scripts/setup.sh` after cloning (Ubuntu/Debian). It sets up Python, `.env`, and can wire OpenClaw. |
| **Wire chat to your lab** | Install the skill from `skills/netpulse/` into OpenClaw, set `NETPULSE_*` secrets, then ask questions like “what VLANs are on sw-core-01?”. |
| **Script or automate** | Use `python3 -m app.main` with `--intent` and `--device` (see [Developer CLI](#developer-cli-appmainpy)). |
| **Change device config** | Writes are **single-device only**, gated by risk, policy, and explicit confirmation. There is no “run arbitrary CLI” path. |

Credentials live in `.env` only, never in `inventory/` or git. The app never sends raw user text to SSH; only predefined intents and validated parameters reach devices.

---

## Quick start

### Option A — Automated (recommended on Ubuntu / Debian)

```bash
curl -fsSL https://raw.githubusercontent.com/alexbugheanu0/netpulse/main/scripts/bootstrap.sh | bash
```

The bootstrap script clones NetPulse into `~/netpulse-project` and starts the setup wizard. If you already cloned the repo, run the wizard directly:

```bash
git clone https://github.com/alexbugheanu0/netpulse.git netpulse-project
cd netpulse-project
bash scripts/setup.sh
```

The setup wizard installs dependencies, creates the venv, helps you set SSH credentials, and can add devices. Later, add or remove devices with:

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

The agent (and validators for write intents) use these for governance before `add_vlan`, `remove_vlan`, or interface changes. Write execution is two-step: the first request returns `approval_required` and saves a pending approval, then the confirmation request must reference the same `request_id` and matching parameters before NetPulse mints a signed receipt. Edit the files under `ssot/` to match your environment; see inline comments there for structure.

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

There are **288** unit tests (no live switches required): intents, parsers, inventory, validation, audits, OpenClaw adapter, approval workflow, and SSH helpers. Run `pytest tests/ --collect-only -q` to confirm the current count.

---

## OpenClaw integration

1. Copy or register `skills/netpulse/` so OpenClaw loads [`SKILL.md`](skills/netpulse/SKILL.md).  
2. Provide the same env vars as `.env` (e.g. `openclaw secrets set …` or a project `.env`).  
3. Call this repository's NetPulse OpenClaw wrapper to debug:

```bash
./scripts/run_openclaw_netpulse.sh '{"intent": "show_vlans", "device": "sw-core-01", "scope": "single", "response_mode": "telegram"}'
./scripts/run_openclaw_netpulse.sh '{"intent": "show_version", "device": "sw-core-01", "scope": "single", "response_mode": "telegram"}'
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

---

## License

License: Apache-2.0

NetPulse is licensed under the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0). See [`LICENSE`](LICENSE) for the full text and [`NOTICE`](NOTICE) for copyright attribution.

NetPulse is open source for learning, labs, and infrastructure automation research. Production use requires your own testing, security review, credential handling, and approval process.

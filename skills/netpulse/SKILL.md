---
name: netpulse
description: AI-safe execution control plane for Cisco network operations. Uses fixed intents only, generates an execution plan, classifies risk, gates approval, executes through adapters, verifies writes, and returns audit-backed proof. Arbitrary CLI is forbidden.
metadata: {"openclaw": {"requires": {"bins": ["python3"]}, "os": ["linux", "darwin"]}}
---

# NetPulse — AI-Safe Infrastructure Execution

Run structured diagnostics and approved config changes against Cisco switches via SSH.
Every request maps to a fixed intent and typed parameters. No raw CLI ever reaches
a device. NetPulse generates a plan before execution, classifies risk, requires
approval for write/high-risk actions, verifies write actions after execution, and
saves audit artifacts.

For per-intent anomaly thresholds, diagnostic chaining playbooks ("port not
passing traffic", "link keeps flapping", etc.), and full payload examples,
read [`skills/netpulse/REFERENCE.md`](REFERENCE.md) on demand. Do NOT preload
it — keep token usage low.

---

## Execution lifecycle rules

- Never execute arbitrary CLI.
- Always use a fixed intent from the allowed list.
- Generate a plan before execution.
- Classify risk before execution.
- Require approval for write or high-risk actions.
- Verify after write actions.
- Save audit artifacts.
- Return proof: plan, risk, result evidence, verification, and audit path.

Core loop:

```text
intent -> plan -> risk check -> approval -> execute -> verify -> audit
```

---

## Telegram privacy and final-only replies

Telegram must receive only the final user-facing answer. Never send interim
status such as "Working...", tool calls, command lines, stdout/stderr, JSON
payloads, plan objects, risk objects, audit objects, chain-of-thought, or
reasoning text.

Never reveal or quote environment variables, `.env` contents, OpenClaw secrets,
SSH credentials, `NETPULSE_PASSWORD`, `NETPULSE_SECRET`, device passwords, or
enable secrets. If a credential problem occurs, say only that credentials need
to be checked.

For every Telegram call:

- Set `response_mode` to `telegram`.
- Keep `verbose` as `false` unless the user explicitly asks for table detail.
- Use `query` for narrow lookups instead of asking for full tables.
- Send only `aggregate_summary` for multi-device responses.
- Send only `results[0].summary` for single-device responses.
- Do not paste NetPulse JSON into Telegram unless the user explicitly asks for
  raw JSON.

---

## Allowed intents

Read intents:

| Intent | What it returns |
|---|---|
| `show_interfaces` | Port list: status, VLAN, duplex, speed, type |
| `show_vlans` | VLAN table: id, name, status |
| `show_trunks` | Trunk ports: mode, encap, native, allowed VLANs |
| `show_version` | IOS version, uptime, platform, serial |
| `show_errors` | Per-port: input/output errors, CRC, resets |
| `show_cdp` | Neighbors: device_id, IP, platform, local/remote port |
| `show_mac` | MAC table: VLAN, MAC, type, port |
| `show_spanning_tree` | Per-VLAN STP port role/state/cost |
| `show_route` | Routes: protocol, prefix/mask, AD/metric, next-hop |
| `show_arp` | ARP cache: IP, age, MAC, type, interface |
| `show_etherchannel` | Bundles: group, protocol, flags, members |
| `show_port_security` | Per-interface: secure MACs, violations, action |
| `show_logging` | Last 20 syslog: timestamp, facility, severity, mnemonic |
| `backup_config` | Saves to `output/backups/<device>_YYYYMMDD_HHMMSS.cfg` |
| `health_check` | version + interfaces + vlans snapshot |
| `device_facts` | Platform, IOS, uptime, port ratio |
| `ping` | Success rate, min/avg/max RTT. Requires `ping_target` |
| `audit_vlans` / `audit_trunks` / `drift_check` | SSOT compliance audit |

Write intents (`scope=single` only — require approval):

| Intent | Required params |
|---|---|
| `add_vlan` | `vlan_id` (int), `vlan_name` (str), `device` |
| `remove_vlan` | `vlan_id` (int), `device` |
| `shutdown_interface` | `interface` (str), `device` |
| `no_shutdown_interface` | `interface` (str), `device` |
| `set_interface_vlan` | `interface` (str), `vlan_id` (int), `device` |

Do NOT use the netpulse skill for arbitrary CLI or any intent not in the list above.

---

## How to call NetPulse

Use this repository's NetPulse OpenClaw wrapper. Do not call any other skill or
external wrapper.

```bash
/home/alex/netpulse-project/scripts/run_openclaw_netpulse.sh 'PAYLOAD'
```

Developer-only local debug path, not for OpenClaw chat routing:

```bash
cd /home/alex/netpulse-project && source .venv/bin/activate && python3 -m app.openclaw_adapter --json 'PAYLOAD'
```

---

## Payload schema

```json
{
  "intent":      "<intent name>",
  "device":      "<device name from inventory>",
  "scope":       "single | all | role",
  "role":        "<role name — required when scope=role>",
  "ping_target": "<IPv4 — required when intent=ping>",
  "dry_run": false,
  "approval_response": "<yes|no — only on follow-up approval calls>",
  "request_id": "<optional id from caller>",
  "user": "<optional user/chat identity>",
  "approved_by": "<user who confirmed the pending request>",
  "source": "openclaw",
  "response_mode": "telegram",
  "query":       "<optional server-side filter>",
  "verbose":     false,
  "vlan_id":     0,
  "vlan_name":   "",
  "interface":   ""
}
```

### Scope rules

| scope | device | role | Behaviour |
|---|---|---|---|
| `single` | required | — | One named device |
| `all` | omit | — | All SSH-enabled devices |
| `role` | omit | required | All devices with that role |

**Prefer `scope=single` unless the user says "every/all/network-wide".**
Multi-device calls multiply token cost linearly.
If the user names a role such as core, distribution, or access, prefer
`scope=role` over `scope=all`.

For Telegram and other chat channels, set `response_mode` to `telegram`.
This keeps the adapter response compact while preserving plan and audit
artifacts on disk.

### Token-saving knobs

- **`query`** — substring/CIDR/IP filter applied server-side. Use it whenever
  the user asks about a single resource (one MAC, one IP, one interface, one
  prefix, one neighbor). The adapter returns only matching rows, usually one.
  Works on: `show_arp`, `show_mac`, `show_route`, `show_interfaces`,
  `show_errors`, `show_cdp`, `show_logging`.
- **`verbose`** — default `false`. The adapter returns `summary` plus up to
  10 sample rows of `parsed_data` and sets `parsed_data_truncated: true`,
  `parsed_data_total_rows: N`. Set `verbose: true` only when the user needs
  the full table.

### Inventory (from `inventory/devices.yaml`)

| Device | Role | IP |
|---|---|---|
| sw-core-01 | core | 192.168.100.11 |
| sw-dist-01 | distribution | 192.168.100.12 |
| sw-acc-01 | access | 192.168.100.13 |
| sw-acc-02 | access | 192.168.100.14 |

NEVER invent a device name. If the user names a device not in this table, say so.

---

## Response format

```json
{
  "success": true,
  "intent":  "show_arp",
  "scope":   "single",
  "aggregate_summary": "<one-line cross-device summary, only when len(results) > 1>",
  "error":   null,
  "results": [
    {
      "device":                 "sw-core-01",
      "success":                true,
      "summary":                "SW-CORE-01: 47 ARP entries, all resolved.",
      "parsed_data":            [ ... up to 10 rows unless verbose:true ... ],
      "parsed_data_truncated":  true,
      "parsed_data_total_rows": 47,
      "elapsed_ms":             280.4,
      "error":                  null
    }
  ]
}
```

## Reply rules

- Reply with the `summary` field ONLY. Do not add explanation, context,
  or background unless the user explicitly asks for it.
- Do NOT send "Working...", tool output, shell commands, stdout/stderr, JSON
  payloads, plan/risk/audit objects, or any chain-of-thought/reasoning text.
- Do NOT reveal `.env`, OpenClaw secrets, environment variables, passwords, or
  enable secrets. Never include `NETPULSE_PASSWORD` or `NETPULSE_SECRET` values.
- Do NOT reference previous questions or earlier conversation history.
- Do NOT suggest follow-up commands unless the user asks "what should I
  check next?" or equivalent.
- If the answer is one sentence, send one sentence. Do not pad.
- For multi-device responses use `aggregate_summary` as the entire reply.
  Expand to per-device detail only if the user asks about a specific device.
- For Telegram calls, set `response_mode: "telegram"` and keep `verbose: false`
  unless the user explicitly asks for raw table detail.

Wrong:  "Based on your earlier question about VLAN 10, I can see that..."
Right:  "SW-CORE-01: 3 VLANs — 1, 10, 20."

Wrong:  "The health check completed. Here is a summary of the results along
         with some recommendations for your network..."
Right:  "SW-CORE-01: IOS 15.2(4)E8 | 22/48 ports up | 5 VLANs."

---

## SSOT change policy — read before every write intent

Before calling the adapter for any write intent, read and evaluate:

- `ssot/change-policy.yaml` — auto_approve / require_approval / forbidden rules
- `ssot/protected-resources.yaml` — protected VLANs, devices, interfaces

Decision:
1. Matches a **forbidden** rule → refuse, do not call the adapter.
2. Targets a protected resource → approval workflow.
3. ALL **auto_approve** conditions satisfied → call adapter immediately.
4. Otherwise → approval workflow.

## Approval workflow for write intents

**Never call the adapter for a write intent without explicit user confirmation.**

1. Identify intent and parameters from the message.
2. Present the proposed action:

   > ⚠️ **Config change requested**
   > - Device: `sw-core-01`
   > - Action: Add VLAN 50 named `SERVERS2`
   > - Commands: `vlan 50` / `name SERVERS2`
   >
   > Confirm? Reply **yes** to execute or **no** to cancel.

3. Wait for the user's reply in Telegram.
4. Call the adapter only if the reply is `yes` / `y` / `confirm` or equivalent,
   using the same intent/parameters plus the original `request_id`,
   `approved_by`, and `approval_response: "yes"`.
5. If negative — abort and confirm cancellation.

Do NOT execute write intents silently. Do NOT assume confirmation from the
original request. Do NOT rely on `approval_received: true`; write execution
requires the server-side pending approval and signed receipt flow. See
REFERENCE.md examples 11–15 for the full payload shapes.

---

## Safety constraints

- NEVER invent a device name. Only use names from the inventory table.
- NEVER pass raw Cisco CLI. Use only this adapter with valid intents.
- NEVER use an intent not in the allowed list.
- NEVER skip plan generation, risk classification, verification, or audit reporting.
- For `scope=all`, omit `device`.
- For `scope=role`, set `role` to `core`, `distribution`, or `access`.
- `ping_target` is required only when `intent=ping`.
- Write intents are `scope=single` only — bulk writes are forbidden.
- NEVER execute a write or high-risk intent without explicit Telegram confirmation.
- Return the audit path and verification evidence when reporting a completed change.

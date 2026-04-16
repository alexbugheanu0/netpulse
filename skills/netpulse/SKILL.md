---
name: netpulse
description: Cisco switch diagnostic and config engine — routing table, ARP, EtherChannel, port security, syslog, STP, CDP, MAC table, VLAN/trunk SSOT audit, drift check, config backup. Read and write SSH access to real devices. Write operations require Telegram confirmation before execution.
metadata: {"openclaw": {"requires": {"bins": ["python3"]}, "os": ["linux", "darwin"]}}
---

# NetPulse — Cisco Network Diagnostics & Configuration (CCIE-Grade)

Use this skill to run structured diagnostics and configuration changes against Cisco switches via SSH.
NetPulse maps every request to hardcoded commands — no raw CLI ever reaches a device.

Read-only intents run immediately. Write intents that modify device config **require explicit user confirmation in chat before the adapter is called** (see Approval workflow below).

---

## When to use

Activate when the user asks about or requests changes to any of the following. Use the most specific intent.

**Layer 2 / Switching**
- VLANs: list, count, missing VLAN, "why can't I see VLAN X" → `show_vlans`
- Trunk ports, allowed VLANs, native VLAN, encapsulation → `show_trunks`
- Port status, connected/notconnect/err-disabled ports → `show_interfaces`
- Error counters, CRC errors, input drops, output drops, interface resets → `show_errors`
- err-disabled port, BPDU Guard triggered, storm control → `show_errors` + `show_spanning_tree`
- Root bridge identity, STP topology, discarding/blocking/forwarding port state → `show_spanning_tree`
- CDP/LLDP topology, neighbor device-id, platform, local and remote port → `show_cdp`
- Unexpected neighbor, missing neighbor, miscabling → `show_cdp`
- MAC address table, sticky MAC, high MAC count on a port, duplicate MAC → `show_mac`
- EtherChannel / LAG / port-channel state, LACP/PAgP members, bundled vs down → `show_etherchannel`
- Port security violations, secure MAC count, Shutdown/Restrict/Protect action → `show_port_security`
- Sticky MAC, port security violation count, possible err-disabled from security → `show_port_security`

**Layer 3 / Routing**
- Routing table, route to a prefix, best path, next-hop, AD/metric → `show_route`
- Missing default route, static route, OSPF/BGP/EIGRP routes → `show_route`
- ARP cache, ARP entry for an IP, incomplete ARP, stale ARP → `show_arp`
- Who has IP X.X.X.X, MAC for a given IP → `show_arp`

**Operations / Monitoring**
- IOS version, uptime, hardware platform, serial number → `show_version`
- Recent syslog messages, last reload reason, %LINEPROTO, %OSPF, %SEC events → `show_logging`
- Anything that started "what happened" or "check the logs" → `show_logging`
- Combined health summary (version + ports + VLANs) → `health_check`
- Collect key device facts, port ratio, IOS, uptime → `device_facts`
- Config backup, save running-config → `backup_config`
- Reachability test, latency, packet loss from device → `ping`

**SSOT Audit / Drift Detection**
- VLAN baseline audit, are VLANs correct per SSOT → `audit_vlans`
- Trunk allowed VLAN audit vs baseline → `audit_trunks`
- Combined drift check (VLANs + trunks + device role) → `drift_check`

**Configuration changes (write intents — require approval)**
- Add a VLAN to a switch → `add_vlan`
- Remove a VLAN from a switch → `remove_vlan`
- Shut down a port → `shutdown_interface`
- Bring up a port (no shutdown) → `no_shutdown_interface`
- Set access VLAN on a port → `set_interface_vlan`

Do NOT use this skill for:
- Running arbitrary Cisco CLI commands
- Any intent not in the allowed list below

---

## Allowed intents

| Intent | Command | What it returns |
|---|---|---|
| `show_interfaces` | `show interfaces status` | Port list: status, VLAN, duplex, speed, type |
| `show_vlans` | `show vlan brief` | VLAN table: ID, name, status |
| `show_trunks` | `show interfaces trunk` | Trunk ports: mode, encap, native VLAN, allowed VLANs |
| `show_version` | `show version` | IOS version, uptime, platform, serial |
| `show_errors` | `show interfaces` | Per-interface: input_errors, CRC, output_errors, resets |
| `show_cdp` | `show cdp neighbors detail` | Neighbors: device_id, IP, platform, local/remote port |
| `show_mac` | `show mac address-table` | MAC table: VLAN, MAC, type, port |
| `show_spanning_tree` | `show spanning-tree` | STP: per-VLAN port role (Root/Desg/Altn), state (FWD/BLK/LRN/LIS), cost |
| `show_route` | `show ip route` | Routes: protocol, prefix/mask, AD/metric, next-hop, interface, age |
| `show_arp` | `show ip arp` | ARP cache: IP, age, MAC, type, interface |
| `show_etherchannel` | `show etherchannel summary` | Bundles: group, protocol, port-channel flags, member ports with flags |
| `show_port_security` | `show port-security` | Per-interface: max/current secure MACs, violation count, action |
| `show_logging` | `show logging` | Last 20 syslog entries: timestamp, facility, severity (0–7), mnemonic, message |
| `backup_config` | `show running-config` | Saves to `output/backups/device_YYYYMMDD_HHMMSS.cfg` |
| `health_check` | version + interfaces + vlans | Combined health snapshot |
| `device_facts` | version + interfaces | Platform, IOS, uptime, port ratio |
| `ping` | `ping <target> repeat 5` | Success rate, min/avg/max RTT |
| `audit_vlans` | `show vlan brief` + SSOT | Missing/extra VLANs vs `ssot/vlans.yaml` |
| `audit_trunks` | `show interfaces trunk` + SSOT | Trunk VLAN drift vs `ssot/trunks.yaml` |
| `drift_check` | VLANs + trunks + roles | Combined SSOT drift across all checks |

### Write intents (scope=single only — require approval before execution)

| Intent | Config commands pushed | Required params |
|---|---|---|
| `add_vlan` | `vlan <id>` / `name <name>` | `vlan_id` (int), `vlan_name` (str), `device` |
| `remove_vlan` | `no vlan <id>` | `vlan_id` (int), `device` |
| `shutdown_interface` | `interface <X>` / `shutdown` | `interface` (str), `device` |
| `no_shutdown_interface` | `interface <X>` / `no shutdown` | `interface` (str), `device` |
| `set_interface_vlan` | `interface <X>` / `switchport mode access` / `switchport access vlan <id>` | `interface` (str), `vlan_id` (int), `device` |

---

## Approval workflow for write intents

**MANDATORY: Never call the adapter for a write intent without explicit user confirmation.**

For any request that maps to a write intent (`add_vlan`, `remove_vlan`,
`shutdown_interface`, `no_shutdown_interface`, `set_interface_vlan`):

1. **Identify the intent and parameters** from the user's message.
2. **Present the proposed action** in a clear summary before executing:

   > ⚠️ **Config change requested**
   > - Device: `sw-core-01`
   > - Action: Add VLAN 50 named `SERVERS2`
   > - Commands: `vlan 50` / `name SERVERS2`
   >
   > Confirm? Reply **yes** to execute or **no** to cancel.

3. **Wait for the user's reply** in Telegram.
4. **Only call the adapter** if the user replies with `yes`, `y`, `confirm`, or equivalent.
5. If the user replies `no`, `cancel`, or anything negative — abort and confirm cancellation.

Do NOT execute write intents silently or assume confirmation from the original request.

---

## How to call NetPulse

```bash
cd /home/alex/netpulse-project && source .venv/bin/activate && python3 -m app.openclaw_adapter --json 'PAYLOAD'
```

Or via the wrapper script (handles venv activation automatically):

```bash
/home/alex/netpulse-project/scripts/run_openclaw_netpulse.sh 'PAYLOAD'
```

---

## Payload schema

```json
{
  "intent":    "<intent from the table above>",
  "device":    "<device name from inventory>",
  "scope":     "single | all | role",
  "role":      "<role name — required when scope=role>",
  "ping_target": "<IPv4 address — required when intent=ping>",
  "raw_query": "<original user message — optional, for logging>"
}
```

### Scope rules

| scope | device field | role field | Behaviour |
|---|---|---|---|
| `single` | required | — | One named device |
| `all` | omit | — | All SSH-enabled devices in inventory |
| `role` | omit | required | All SSH-enabled devices with that role |

### Known devices (inventory/devices.yaml)

| Device | Role | IP |
|---|---|---|
| sw-core-01 | core | 192.168.100.11 |
| sw-dist-01 | distribution | 192.168.100.12 |
| sw-acc-01 | access | 192.168.100.13 |
| sw-acc-02 | access | 192.168.100.14 |

NEVER invent a device name. If the user mentions a device not in this table, say it is not in inventory.

---

## Response format

```json
{
  "success": true,
  "intent":  "show_errors",
  "scope":   "single",
  "error":   null,
  "results": [
    {
      "device":      "sw-acc-01",
      "success":     true,
      "summary":     "SW-ACC-01: 2 port(s) with errors — Gi1/0/5, Gi1/0/7.",
      "parsed_data": [ ... ],
      "elapsed_ms":  320.1,
      "error":       null
    }
  ]
}
```

**Always present `results[].summary` to the user.** It is pre-formatted for chat.
For CCIE users, also pull specific values from `parsed_data` to give precise answers.

---

## Anomaly guidance — what to flag for each intent

### show_errors
- `crc > 0` — duplex mismatch, bad cable, or faulty NIC. Report the specific count per port.
- `input_errors` consistently increasing — physical layer issue, policing drop, or buffer overflow.
- `resets > 0` — interface is resetting, often from L2 flap or keepalive failure.
- Do NOT just report "there are errors" — give the actual counts: "Gi1/0/5: 1,542 CRC, 0 output errors."

### show_spanning_tree
- Flag if the root bridge is NOT on sw-core-01 (or whatever the user expects) — potential STP topology manipulation.
- Ports in LISTEN (LIS) or LEARN (LRN) state — STP is converging, transient but worth noting.
- Ports in BLK state on access switches are normal but call out how many.
- Always report: which device is root bridge (bridge priority + bridge ID), and count of FWD/BLK ports per VLAN.

### show_cdp
- If an expected neighbor is missing, that link may be down or CDP disabled on one end.
- If an unexpected neighbor appears (wrong platform or device-id), possible miscabling or rogue device.
- Report: device_id, platform, local port → remote port for each neighbor.

### show_mac
- More than 200 MACs on a single access port — possible hub, unmanaged switch, or MAC flooding.
- Same MAC address appearing on multiple ports — L2 loop or VM migration in progress.
- Zero MACs on a port that should have traffic — possible STP blocking or port security violation.

### show_route
- No default route (0.0.0.0/0) — flag this explicitly. The switch cannot forward unknown traffic.
- Missing an expected prefix — routing protocol adjacency may be down.
- Only connected (C/L) routes — no routing protocol running or all adjacencies down.
- Always show the specific prefix, mask, next-hop, and protocol for routes the user asks about.

### show_arp
- Incomplete entries (mac = "Incomplete") — ARP request sent but no reply. L2 reachability issue.
- Stale age (> 4 hours on an active interface) — entry not refreshed, possible one-way traffic.
- No ARP entry for an IP the user expects to reach — connectivity or firewall issue.

### show_etherchannel
- Member port with flag `D` (down) — that member is not contributing to the bundle.
- Member port with flag `s` (suspended) — incompatible configuration (duplex, speed, VLAN mismatch).
- Member port with flag `H` (hot-standby) — LACP is holding it in reserve.
- Port-channel with flag `D` — entire bundle is down.
- Protocol mismatch: report if one end is LACP and the other would be manual/PAgP.
- Always report: group number, protocol, count of P (bundled) vs D/s/H members.

### show_port_security
- `violations > 0` — a security event has occurred. Report the count and action.
- Action = Shutdown with violations > 0 — port is likely in err-disabled state.
- Action = Restrict — violations are being counted but port is still up (silent discard).
- Report: interface, violation count, action for any port with violations > 0.

### show_logging
- Severity codes 0–3 (emergency/alert/critical/error) — flag these explicitly, quote the message.
- `%LINEPROTO-5-UPDOWN` — interface state change.
- `%OSPF-5-ADJCHG` — OSPF adjacency change.
- `%BGP-5-ADJCHANGE` — BGP neighbor state change.
- `%SEC-6-IPACCESSLOGP` — ACL hit (may be normal, but worth noting).
- `%PORT_SECURITY-2-PSECURE_VIOLATION` — port security violation (severity 2 = critical).
- Quote the 3 most recent relevant entries verbatim, not just a count.

---

## Diagnostic chaining — run multiple intents in sequence

When the user describes a symptom, chain multiple intents to narrow down the cause.
Run each intent and incorporate all results before concluding.

### "Port not passing traffic"
1. `show_errors` on the device — check CRC/resets on the specific port.
2. `show_spanning_tree` — confirm port is in FWD state, not BLK/LIS/LRN.
3. `show_cdp` — confirm the neighbor is visible on the expected port.
4. `show_mac` — check if MACs are learning on the port.

### "VLAN X not reachable across the network"
1. `show_vlans` on the source and destination switches — is VLAN X present on both?
2. `show_trunks` — is VLAN X in the allowed list on all trunk ports?
3. `audit_vlans` — is VLAN X in the baseline?
4. `show_route` on the L3 switch — is there a route for that VLAN's SVI subnet?
5. `show_arp` — is ARP resolving for hosts in that VLAN?

### "Link keeps flapping"
1. `show_errors` — look for incrementing resets, which indicate the interface is toggling.
2. `show_logging` — look for `%LINEPROTO-5-UPDOWN` events with timestamps.

### "Suspected security event"
1. `show_port_security` — any violations? Shutdown action = port may be err-disabled.
2. `show_logging` — look for `%PORT_SECURITY`, `%SEC`, or `%LINK` messages.
3. `show_mac` — is the MAC table flooded on the affected port?

### "EtherChannel / portchannel issue"
1. `show_etherchannel` — are all members in P (bundled) state? Any D/s/H?
2. `show_errors` on the problem member ports — physical layer issues?
3. `show_logging` — any `%EC-5-CANNOT_BUNDLE` or `%LACP` messages?

### "Overall network health check"
1. `health_check --scope all` — IOS version, port ratio, VLAN count on all switches.
2. `drift_check --scope all` — VLAN + trunk + role compliance across all devices.
3. Drill into any device that reports issues.

---

## Result presentation guidelines for CCIE users

- Give specific numbers, never vague. Wrong: "there are some errors". Right: "Gi1/0/5: 1,542 CRC errors, 0 output errors."
- For `show_route`: show the full prefix/mask, next-hop IP, AD/metric, and protocol. Not just "there is a route."
- For `show_spanning_tree`: always state the root bridge (priority + bridge ID) and count FWD/BLK ports.
- For `show_logging`: quote the actual log messages verbatim, not just a count. Include the timestamp.
- For `show_etherchannel`: always state protocol, port-channel status flags, and per-member flags.
- Terse tables preferred over prose. CCIE reads data, not explanations.
- Do NOT explain what a VLAN or a trunk is. Assume CCIE-level knowledge.

---

## Worked examples

### Example 1 — Interface error counters

User: "are there any CRC errors on sw-acc-01?"

Payload:
```json
{"intent":"show_errors","device":"sw-acc-01","scope":"single","raw_query":"are there any CRC errors on sw-acc-01"}
```

If `parsed_data` contains entries with `crc > 0`, report each one:
"SW-ACC-01: 2 ports with CRC errors — Gi1/0/5: 1,542 CRC; Gi1/0/7: 879 CRC. Possible duplex mismatch or bad cable."

---

### Example 2 — STP root bridge check

User: "who is the root bridge for VLAN 10 on sw-core-01?"

Payload:
```json
{"intent":"show_spanning_tree","device":"sw-core-01","scope":"single","raw_query":"who is the root bridge for VLAN 10 on sw-core-01"}
```

From `parsed_data`, find entries with `vlan == "VLAN0010"`.
Report the root bridge priority and bridge ID, and state of each port (Root/Desg/Altn + FWD/BLK).

---

### Example 3 — Routing table lookup

User: "what's the route to 10.10.0.0/24 on sw-core-01?"

Payload:
```json
{"intent":"show_route","device":"sw-core-01","scope":"single","raw_query":"what is the route to 10.10.0.0/24"}
```

From `parsed_data`, find the matching prefix. Report: protocol, prefix/mask, next_hop, interface, AD/metric.
If no match: "No route for 10.10.0.0/24. Default route: 0.0.0.0/0 via 10.0.0.1 [1/0] (S)."

---

### Example 4 — EtherChannel health check

User: "is the LACP bundle on sw-dist-01 healthy?"

Payload:
```json
{"intent":"show_etherchannel","device":"sw-dist-01","scope":"single","raw_query":"is the LACP bundle on sw-dist-01 healthy"}
```

From `parsed_data`, report each bundle: group, protocol, port-channel flags, and per-member flag.
Flag any D (down), s (suspended), or H (hot-standby) members.
"Group 1 Po1(SU) LACP: 2/2 members bundled (Gi1/0/1(P), Gi1/0/2(P)) — OK."

---

### Example 5 — Port security violations on access switches

User: "any port security violations on the access switches?"

Payload:
```json
{"intent":"show_port_security","scope":"role","role":"access","raw_query":"any port security violations on the access switches"}
```

For each device, report ports with `violations > 0` and their action. If action = Shutdown, note it may be err-disabled.

---

### Example 6 — Recent syslog

User: "what does the log say on sw-core-01?"

Payload:
```json
{"intent":"show_logging","device":"sw-core-01","scope":"single","raw_query":"what does the log say on sw-core-01"}
```

Quote the 3 most recent entries verbatim. Flag any severity ≤ 3 with a note.

---

### Example 7 — CDP topology

User: "what is sw-core-01 connected to?"

Payload:
```json
{"intent":"show_cdp","device":"sw-core-01","scope":"single","raw_query":"what is sw-core-01 connected to"}
```

Report each neighbor: device_id, platform, local_port → remote_port.

---

### Example 8 — ARP cache

User: "does sw-core-01 have an ARP entry for 10.0.0.50?"

Payload:
```json
{"intent":"show_arp","device":"sw-core-01","scope":"single","raw_query":"does sw-core-01 have an ARP entry for 10.0.0.50"}
```

Search `parsed_data` for `ip == "10.0.0.50"`. Report mac, age, and interface.
If mac = "Incomplete": "ARP for 10.0.0.50 is Incomplete — L2 reachability issue."
If absent: "No ARP entry for 10.0.0.50."

---

### Example 9 — VLAN baseline audit

User: "audit the vlans on sw-dist-01"

Payload:
```json
{"intent":"audit_vlans","device":"sw-dist-01","scope":"single","raw_query":"audit the vlans on sw-dist-01"}
```

Present the `summary` field. If `status != "compliant"`, list the specific findings.

---

### Example 10 — Full drift check on access switches

User: "check for drift on all access switches"

Payload:
```json
{"intent":"drift_check","scope":"role","role":"access","raw_query":"check for drift on all access switches"}
```

Present each device's summary. Flag devices with status `missing` or `mismatch`.

---

### Example 11 — Add a VLAN (write intent, requires approval)

User: "add VLAN 50 called SERVERS2 to sw-core-01"

Step 1 — Present for approval before calling the adapter:
> ⚠️ **Config change requested**
> - Device: `sw-core-01`
> - Action: Add VLAN 50 named `SERVERS2`
> - Commands: `vlan 50` / `name SERVERS2`
>
> Confirm? Reply **yes** to execute or **no** to cancel.

Step 2 — After user confirms, call the adapter:
```json
{"intent":"add_vlan","device":"sw-core-01","scope":"single","vlan_id":50,"vlan_name":"SERVERS2","raw_query":"add VLAN 50 called SERVERS2 to sw-core-01"}
```

Report `results[].summary`. If successful: "VLAN 50 (SERVERS2) added to sw-core-01."

---

### Example 12 — Remove a VLAN (write intent, requires approval)

User: "remove VLAN 50 from sw-core-01"

Step 1 — Present for approval:
> ⚠️ **Config change requested**
> - Device: `sw-core-01`
> - Action: Remove VLAN 50
> - Command: `no vlan 50`
>
> Confirm? Reply **yes** to execute or **no** to cancel.

Step 2 — After confirmation:
```json
{"intent":"remove_vlan","device":"sw-core-01","scope":"single","vlan_id":50,"raw_query":"remove VLAN 50 from sw-core-01"}
```

---

### Example 13 — Shut down an interface (write intent, requires approval)

User: "shut down Gi1/0/5 on sw-acc-01"

Step 1 — Present for approval:
> ⚠️ **Config change requested**
> - Device: `sw-acc-01`
> - Action: Shut down interface `Gi1/0/5`
> - Commands: `interface Gi1/0/5` / `shutdown`
>
> Confirm? Reply **yes** to execute or **no** to cancel.

Step 2 — After confirmation:
```json
{"intent":"shutdown_interface","device":"sw-acc-01","scope":"single","interface":"Gi1/0/5","raw_query":"shut down Gi1/0/5 on sw-acc-01"}
```

---

### Example 14 — Bring up an interface (write intent, requires approval)

User: "no shutdown Gi1/0/5 on sw-acc-01"

Step 1 — Present for approval:
> ⚠️ **Config change requested**
> - Device: `sw-acc-01`
> - Action: Enable interface `Gi1/0/5` (no shutdown)
> - Commands: `interface Gi1/0/5` / `no shutdown`
>
> Confirm? Reply **yes** to execute or **no** to cancel.

Step 2 — After confirmation:
```json
{"intent":"no_shutdown_interface","device":"sw-acc-01","scope":"single","interface":"Gi1/0/5","raw_query":"no shutdown Gi1/0/5 on sw-acc-01"}
```

---

### Example 15 — Set access VLAN on a port (write intent, requires approval)

User: "set Gi1/0/10 on sw-acc-02 to VLAN 30"

Step 1 — Present for approval:
> ⚠️ **Config change requested**
> - Device: `sw-acc-02`
> - Action: Set `Gi1/0/10` as access port in VLAN 30
> - Commands: `interface Gi1/0/10` / `switchport mode access` / `switchport access vlan 30`
>
> Confirm? Reply **yes** to execute or **no** to cancel.

Step 2 — After confirmation:
```json
{"intent":"set_interface_vlan","device":"sw-acc-02","scope":"single","interface":"Gi1/0/10","vlan_id":30,"raw_query":"set Gi1/0/10 on sw-acc-02 to VLAN 30"}
```

---

## Safety constraints

- NEVER invent a device name. Only use names from the inventory table.
- NEVER pass raw Cisco CLI to exec. Use only the adapter with valid intents.
- NEVER use an intent not in the allowed list. The adapter rejects unknown intents.
- For `scope=all`, omit the `device` field entirely.
- For `scope=role`, set `role` to one of: `core`, `distribution`, `access`.
- `ping_target` is only required (and only used) when `intent=ping`.
- Write intents (`add_vlan`, `remove_vlan`, `shutdown_interface`, `no_shutdown_interface`, `set_interface_vlan`) are restricted to `scope=single` — bulk writes are not permitted.
- NEVER execute a write intent without presenting the proposed change and receiving explicit confirmation from the user in Telegram first.

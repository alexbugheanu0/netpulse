# NetPulse — AI Agent for Network Troubleshooting

## Vision

NetPulse is a self-hosted AI agent that helps network engineers troubleshoot infrastructure using natural language. Engineers interact with it through their existing chat tools (Slack, Teams, Discord, Telegram) and the agent reasons over device state, logs, and topology to diagnose problems — proposing or executing remediation actions only when a human approves.

---

## Core Principles

- **Self-hosted first** — company data (configs, IPs, topology) never leaves the premises
- **Read-only by default** — the agent observes and diagnoses; write actions require explicit approval
- **Model-agnostic** — swap between Claude, GPT, or a local Ollama model without changing skills
- **Multi-vendor** — abstracts over Cisco, Juniper, Arista, Palo Alto CLI differences
- **Chat-native** — lives in the tools engineers already use, no new UI to learn

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Chat Platforms                    │
│         Slack · Teams · Discord · Telegram          │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│              OpenClaw Agent Runtime                 │
│   ReAct Loop: Goal → Plan → Act → Observe → Repeat  │
│   Persistent Memory · Skill Execution · Audit Log   │
└──────┬─────────────────────────────────┬────────────┘
       │                                 │
┌──────▼──────┐                 ┌────────▼────────────┐
│  LLM Layer  │                 │   Network Skills    │
│  (pluggable)│                 │  SSH · SNMP · REST  │
│  Claude     │                 │  Log Parser         │
│  GPT-4o     │                 │  Topology Mapper    │
│  Ollama     │                 │  Runbook RAG        │
└─────────────┘                 └────────┬────────────┘
                                         │
                                ┌────────▼────────────┐
                                │  Network Devices    │
                                │  Routers · Switches │
                                │  Firewalls · WLCs   │
                                └─────────────────────┘
```

### 3-Layer Stack

| Layer | Components |
|-------|-----------|
| **Execution** | OpenClaw Gateway, skill runner, shell/SSH access |
| **Memory & Context** | SOUL.md (agent persona), MEMORY.md (network topology, known issues), incident history |
| **Skills** | Network-specific plugins listed below |

---

## Network Skills (Planned)

| Skill | Description | Access Level |
|-------|-------------|-------------|
| `device-inventory` | Lookup devices by name, IP, site, or role | Read |
| `interface-check` | Run `show interface`, parse drops/errors/CRC | Read |
| `bgp-neighbor-check` | Verify BGP peer state, flag idle/down sessions | Read |
| `ospf-check` | Check OSPF adjacency, cost, and route table | Read |
| `ping-traceroute` | Connectivity testing from agent host | Read |
| `log-analyzer` | Pull and summarize recent syslog events | Read |
| `snmp-poller` | Poll OIDs for CPU, memory, interface counters | Read |
| `topology-mapper` | Ingest LLDP/CDP to build and query a topology graph | Read |
| `runbook-rag` | Answer questions from company runbooks / KB docs | Read |
| `config-diff` | Compare running vs. saved or last-known-good config | Read |
| `interface-bounce` | Shut/no-shut an interface — requires human approval | **Write** |
| `bgp-clear` | Clear a BGP session — requires human approval | **Write** |

All write-capable skills display a confirmation prompt in chat before execution. Nothing destructive runs without a human typing "confirm" in the thread.

---

## Phased Delivery Plan

### Phase 1 — Validation & PoC (Weeks 1–2)

- [ ] Install OpenClaw and connect to Slack (or Discord for testing)
- [ ] Verify local LLM works via Ollama (fully air-gapped path)
- [ ] Assess Microsoft Teams channel support (community plugin or custom adapter)
- [ ] Build one trivial skill: `ping-check` (run `ping` via shell, return parsed output)
- [ ] Evaluate multi-engineer shared channel experience

### Phase 2 — Core Troubleshooting Skills (Weeks 3–6)

- [ ] Build `device-inventory` skill with YAML-based device config
- [ ] Build `ssh-readonly` skill wrapper (Netmiko under the hood, command allowlist enforced)
- [ ] Build `interface-check`, `bgp-neighbor-check`, `log-analyzer`
- [ ] Multi-vendor abstraction layer (IOS, NX-OS, JunOS, EOS output parsers)
- [ ] Structured output — agent returns formatted tables, not raw CLI blobs

### Phase 3 — Memory & Knowledge Base (Weeks 7–8)

- [ ] Seed MEMORY.md with network topology, device roles, site info
- [ ] Ingest company runbooks / KB articles for RAG-based answers
- [ ] Incident memory: agent recalls "this same BGP flap happened on R1 last Tuesday"
- [ ] `topology-mapper` skill using LLDP/CDP data

### Phase 4 — Safety & Enterprise Hardening (Weeks 9–11)

- [ ] Command allowlist: skills reject anything not on the approved list
- [ ] Write-action approval workflow in chat (propose → confirm → execute)
- [ ] Full audit log: timestamp, engineer, device, command, output, approval
- [ ] Credential management: integrate with HashiCorp Vault or environment secrets
- [ ] Teams adapter: build or validate connector for Microsoft Teams
- [ ] RBAC: junior vs. senior engineer permission tiers

### Phase 5 — Packaging & Distribution (Weeks 12–14)

- [ ] Docker Compose bundle: OpenClaw + Ollama + NetPulse skills, `docker compose up` install
- [ ] Guided setup CLI: "Add your devices" → "Connect your LLM" → "Connect your chat platform"
- [ ] Helm chart for Kubernetes deployment
- [ ] Documentation: installation guide, skill reference, security model
- [ ] Version pinning strategy for OpenClaw stability in production

---

## Technology Stack

| Component | Choice | Notes |
|-----------|--------|-------|
| Agent Runtime | OpenClaw | Self-hosted, skill ecosystem, 20+ chat channels |
| LLM | Configurable | Claude / GPT-4o (cloud) or Ollama + Mistral/Llama (on-prem) |
| Network Library | Netmiko + NAPALM | Multi-vendor SSH abstraction |
| Knowledge Store | ChromaDB / Qdrant | RAG over runbooks and topology docs |
| Secrets | HashiCorp Vault | SSH keys, SNMP strings, API tokens |
| Packaging | Docker Compose + Helm | Easy self-hosted deployment |
| Chat | Slack, Teams, Discord, Telegram | Via OpenClaw channel connectors |

---

## Security Model

| Concern | Mitigation |
|---------|-----------|
| Network credentials in plaintext | All secrets via Vault or environment variables only |
| Agent running destructive commands | Read-only by default; write commands require in-chat approval |
| Data leaving the network | On-prem LLM option (Ollama); no cloud API required |
| Audit compliance | Every agent action logged with actor, timestamp, and output |
| OpenClaw version stability | Pin to tested versions; separate staging environment |
| Privilege escalation | Skills enforce role-based command allowlists |

---

## Open Questions

1. **Teams support** — Does OpenClaw have a Teams channel adapter, or does one need to be built?
2. **Shared vs. per-engineer instances** — One shared agent in a NOC channel, or one per engineer?
3. **LLM choice for production** — Claude API vs. fully local Ollama for air-gapped environments?
4. **Alerting integration** — Should the agent proactively start troubleshooting on a PagerDuty/Zabbix alert, or only respond to engineer prompts?
5. **Target vendors** — Which vendors/OS types to support first (Cisco IOS/NX-OS, Juniper JunOS, Arista EOS)?

---

## Repository Structure (Target)

```
netpulse/
├── skills/                  # OpenClaw skill definitions
│   ├── device-inventory/
│   ├── interface-check/
│   ├── bgp-neighbor-check/
│   ├── log-analyzer/
│   └── ...
├── parsers/                 # Vendor-specific CLI output parsers
│   ├── cisco_ios.py
│   ├── junos.py
│   └── arista_eos.py
├── memory/
│   ├── SOUL.md              # Agent persona and behavior rules
│   └── MEMORY.md            # Network topology and known devices
├── config/
│   └── devices.yaml         # Device inventory template
├── docker-compose.yml       # One-command deployment
├── docs/
│   ├── installation.md
│   ├── skills.md
│   └── security.md
└── README.md
```

---

*Last updated: April 2026*

# Genesis-Style NetPulse Demo

This demo shows NetPulse as an AI-safe execution control plane without requiring real Cisco devices or lab systems.

Run it from the repository root:

```bash
python demos/genesis_style/run_demo.py
```

The simulated request is:

> Prepare the lab environment for simulation job demo-001.

The demo generates a structured execution plan, classifies risk, runs deterministic mock checks for network, compute, storage, and instrument readiness, verifies the environment, and writes a JSON audit artifact under `output/audit/`.

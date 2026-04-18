# Install UX Review

**Date:** 2026-04-18
**Scope:** `scripts/setup.sh`, `scripts/add-device.sh`, `scripts/run_openclaw_netpulse.sh`, `scripts/start-openclaw.sh`, `README.md` Quick start, `INSTALL.md`
**Goal under review:** *"Easy to install — ideally two steps."*

---

## 1. Static analysis findings

### 1.1 Syntax check (`bash -n`)

| File | Result |
|---|---|
| `scripts/setup.sh` | PASS |
| `scripts/add-device.sh` | PASS |
| `scripts/run_openclaw_netpulse.sh` | PASS |
| `scripts/start-openclaw.sh` | PASS |

### 1.2 ShellCheck (v0.10.0, default + `-S style`)

| File | Findings |
|---|---|
| `scripts/setup.sh` | 1 × SC2015 (info) — line 225 |
| `scripts/add-device.sh` | 0 |
| `scripts/run_openclaw_netpulse.sh` | 0 |
| `scripts/start-openclaw.sh` | 0 |

**SC2015 detail** — `scripts/setup.sh:225`

```bash
[ "$DEVICES_ADDED" -gt 0 ] && ok "$DEVICES_ADDED device(s) configured" || info "No new devices added"
```

The `A && B || C` idiom is not a true if/else. In this case it is functionally
safe because `ok` always exits 0, but the pattern is fragile and should be an
explicit `if/then/else`. The summary block at lines 322–324 uses the same
pattern with line-continuation backslashes (not flagged by ShellCheck but worth
the same fix).

### 1.3 Other observations (not flagged by tooling)

1. **Bash-4 dependency.** The script uses `${VAR,,}` lowercase expansion
   (`setup.sh:96, 215, 221, 265, 267`). This needs bash 4+. Ubuntu and Debian
   ship bash 5.x, so on-target this is fine. macOS's `/bin/bash` is 3.2 and
   would silently mis-evaluate — but the script exits at line 44 on non-`apt`
   systems before reaching these lines.

2. **GNU-specific flag usage.** `tail -"$DEVICES_ADDED"` at `setup.sh:234`
   works on GNU coreutils but is not portable. `tail -n "$DEVICES_ADDED"` is
   the POSIX form.

3. **Workspace artefact.** `.tools/shellcheck` (downloaded for this review)
   is not in `.gitignore`. Either delete after review or add `.tools/` to
   `.gitignore`.

---

## 2. Install UX assessment

### 2.1 What the user actually types today (Option A)

```bash
git clone <repo-url> netpulse-project
cd netpulse-project
bash scripts/setup.sh
```

**Commands typed: 3.** The README frames this as "2 steps" (clone + run),
which is a reasonable description, but the wizard itself is interactive and
asks ~10 questions:

1. Overwrite `.env`? (if one already exists)
2. SSH username
3. SSH password (hidden)
4. Enable secret (hidden)
5. SSH port
6. SSH timeout
7. Add a network device? → name / IP / role / platform (loop)
8. Install OpenClaw? → provider / API key / onboarding wizard

That is the minimum you can ask for in a networking tool — SSH credentials and
device IPs have to come from somewhere — but it is not "zero-touch."

### 2.2 Gaps between current state and a true 2-step promise

| Gap | Today | Impact |
|---|---|---|
| **macOS / RHEL / Fedora support** | `setup.sh` hard-exits at line 44 with *"requires apt"* | Non-Ubuntu/Debian users must use the 6-step manual path |
| **Single-command bootstrap** | Must `git clone` → `cd` → `bash scripts/setup.sh` | No `curl \| bash` one-liner like nvm/rustup/openclaw |
| **Unattended/CI install** | Every prompt is interactive | Cannot drive from Ansible / cloud-init / Packer |
| **"No devices yet" path** | User must still answer `n` to at least one prompt | Harmless friction, but extra keystroke |

### 2.3 What a genuine 2-step install looks like

**Target — one command:**

```bash
curl -fsSL https://raw.githubusercontent.com/<owner>/netpulse/main/scripts/bootstrap.sh | bash
```

A `bootstrap.sh` would `git clone` to `~/netpulse-project`, `cd` into it,
and `exec scripts/setup.sh`. Same UX as `nvm`/`rustup`/`openclaw` installers.

**Stretch — zero-touch mode:**

```bash
NETPULSE_USERNAME=admin NETPULSE_PASSWORD=xxx \
    bash scripts/setup.sh --non-interactive --devices path/to/devices.yaml
```

---

## 3. Recommendations

Ordered by impact-per-effort. Each item is self-contained — none depend on
any other.

### R1 — Fix SC2015 (trivial, do always)

Replace the two `A && B || C` patterns with explicit `if/then/else`. Silences
ShellCheck cleanly and removes a known fragile idiom. **~5 minutes.**

### R2 — Add `scripts/bootstrap.sh` for one-liner install (highest ROI)

A ~20-line script that:

1. Verifies `git` and `python3` exist (installs them on Debian/Ubuntu if not).
2. Clones the repo to `${NETPULSE_DIR:-$HOME/netpulse-project}`.
3. `exec`s `scripts/setup.sh` from inside it.

Published install command becomes:

```bash
curl -fsSL https://raw.githubusercontent.com/<owner>/netpulse/main/scripts/bootstrap.sh | bash
```

That is the genuine 2-step promise: **one curl command → answer prompts**.
**~30 minutes.**

### R3 — Add macOS support to `setup.sh` (broadens reach)

At the top of Step 1, detect the OS:

- If `apt-get` available → current path
- Else if `brew` available → `brew install python@3.12 git`
- Else → print a clear error with a link to manual install steps

Also require bash ≥ 4 on macOS (or swap `${VAR,,}` for a portable
`tr '[:upper:]' '[:lower:]'` helper). **~60 minutes.**

### R4 — Add `--non-interactive` / `--yes` flag (optional, only if anyone runs this from IaC)

Accept answers via env vars instead of prompts:

```
NETPULSE_USERNAME, NETPULSE_PASSWORD, NETPULSE_SECRET,
NETPULSE_SSH_PORT, NETPULSE_SSH_TIMEOUT,
NETPULSE_DEVICES_FILE (path to pre-written devices.yaml),
NETPULSE_INSTALL_OPENCLAW=true|false
```

If `--non-interactive` is passed and a required env var is missing, exit with
a clear error listing what's missing. Skip the "add device" loop when
`NETPULSE_DEVICES_FILE` is set — copy that file straight into place.
**~90 minutes.**

### R5 — Minor polish

- Replace `tail -"$N"` with `tail -n "$N"` in `setup.sh:234`.
- Add `.tools/` to `.gitignore` (or delete the folder before committing).
- In the summary block (`setup.sh:322–324`), same `A && B || C` fix as R1.

**~10 minutes.**

---

## 4. Suggested execution order

If the goal is "genuinely 2-step install across Linux and macOS":

1. **R1** (clean lint, 5 min)
2. **R2** (one-liner bootstrap, 30 min) — biggest UX win
3. **R3** (macOS support, 60 min) — biggest reach win
4. **R5** (polish, 10 min)
5. **R4** (only if IaC/CI use case is real)

After R1 + R2 + R3 the published install instructions become:

```bash
# Any Linux (apt) or macOS (brew):
curl -fsSL https://raw.githubusercontent.com/<owner>/netpulse/main/scripts/bootstrap.sh | bash
```

That is a true one-command install. The interactive prompts for SSH
credentials and device inventory remain — and they should, because there is
no safe automatic answer for those.

---

## 5. What is already good

Worth naming so these don't get broken in future refactors:

- `set -euo pipefail` on both `setup.sh` and `add-device.sh`.
- Password prompts use `read -rsp` (hidden input).
- `.env` is written with `chmod 600`.
- The wizard is idempotent — safe to re-run after a partial install.
- Each wizard step tracks a boolean and prints a final summary with `[OK]` /
  `[!!]` status per stage.
- Existing `.env` is detected and skipped (with confirm-to-overwrite).
- Existing devices are listed before asking whether to add more.
- ShellCheck + `bash -n` are both near-clean (1 finding total across 4 files).
- Tests are run as part of install, so a broken environment is caught
  immediately instead of at first real use.

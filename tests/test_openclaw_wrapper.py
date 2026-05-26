"""Regression tests for the OpenClaw shell wrapper."""

import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_missing_credentials_return_safe_generic_error(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    wrapper = scripts_dir / "run_openclaw_netpulse.sh"
    shutil.copy2(ROOT / "scripts" / "run_openclaw_netpulse.sh", wrapper)

    python = tmp_path / ".venv" / "bin" / "python3"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\nexit 0\n", encoding="ascii")
    python.chmod(0o700)

    result = subprocess.run(
        [str(wrapper), '{"intent":"health_check"}'],
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert payload["error"] == (
        "Read-only switch credentials are unavailable. Check the configured credentials."
    )
    assert ".env" not in result.stdout
    assert "NETPULSE_" not in result.stdout

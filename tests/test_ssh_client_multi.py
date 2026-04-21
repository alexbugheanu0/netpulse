"""Tests for ssh_client.run_commands() — single-session multi-command execution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from app.models import Device


DEVICE = Device(
    name="sw-test-01",
    hostname="sw-test-01",
    ip="10.0.0.1",
    platform="cisco_ios",
    role="access",
    ssh_enabled=True,
)

COMMANDS = ["show version", "show interfaces status", "show vlan brief"]


def _make_conn_mock(outputs: dict[str, str] | None = None) -> MagicMock:
    """Return a mock ConnectHandler instance whose send_command echoes the command."""
    conn = MagicMock()
    if outputs:
        conn.send_command.side_effect = lambda cmd, **kw: outputs.get(cmd, "")
    else:
        conn.send_command.side_effect = lambda cmd, **kw: f"output-of-{cmd}"
    return conn


class TestRunCommandsReturnsDict:
    def test_returns_dict_keyed_by_command(self):
        """Each command in the input list must appear as a key in the result."""
        conn = _make_conn_mock()

        with (
            patch("app.ssh_client.SSH_USERNAME", "admin"),
            patch("app.ssh_client.SSH_PASSWORD", "pass"),
            patch("app.ssh_client.SSH_SECRET", ""),
            patch("app.ssh_client.ConnectHandler") as mock_ch,
        ):
            mock_ch.return_value.__enter__ = lambda s: conn
            mock_ch.return_value.__exit__ = MagicMock(return_value=False)

            from app.ssh_client import run_commands

            result = run_commands(DEVICE, COMMANDS)

        assert set(result.keys()) == set(COMMANDS)

    def test_values_are_strings(self):
        """All values in the returned dict must be strings."""
        conn = _make_conn_mock()

        with (
            patch("app.ssh_client.SSH_USERNAME", "admin"),
            patch("app.ssh_client.SSH_PASSWORD", "pass"),
            patch("app.ssh_client.SSH_SECRET", ""),
            patch("app.ssh_client.ConnectHandler") as mock_ch,
        ):
            mock_ch.return_value.__enter__ = lambda s: conn
            mock_ch.return_value.__exit__ = MagicMock(return_value=False)

            from app.ssh_client import run_commands

            result = run_commands(DEVICE, COMMANDS)

        for key, val in result.items():
            assert isinstance(val, str), f"Expected str for {key!r}, got {type(val)}"

    def test_correct_output_per_command(self):
        """send_command output must be stored under the matching command key."""
        outputs = {
            "show version": "Cisco IOS 15.2",
            "show interfaces status": "Gi0/1  connected",
        }
        cmds = list(outputs.keys())
        conn = _make_conn_mock(outputs)

        with (
            patch("app.ssh_client.SSH_USERNAME", "admin"),
            patch("app.ssh_client.SSH_PASSWORD", "pass"),
            patch("app.ssh_client.SSH_SECRET", ""),
            patch("app.ssh_client.ConnectHandler") as mock_ch,
        ):
            mock_ch.return_value.__enter__ = lambda s: conn
            mock_ch.return_value.__exit__ = MagicMock(return_value=False)

            from app.ssh_client import run_commands

            result = run_commands(DEVICE, cmds)

        assert result["show version"] == "Cisco IOS 15.2"
        assert result["show interfaces status"] == "Gi0/1  connected"


class TestRunCommandsOpensOneConnection:
    def test_opens_only_one_connection_for_three_commands(self):
        """ConnectHandler must be instantiated exactly once regardless of command count."""
        conn = _make_conn_mock()

        with (
            patch("app.ssh_client.SSH_USERNAME", "admin"),
            patch("app.ssh_client.SSH_PASSWORD", "pass"),
            patch("app.ssh_client.SSH_SECRET", ""),
            patch("app.ssh_client.ConnectHandler") as mock_ch,
        ):
            mock_ch.return_value.__enter__ = lambda s: conn
            mock_ch.return_value.__exit__ = MagicMock(return_value=False)

            from app.ssh_client import run_commands

            run_commands(DEVICE, COMMANDS)

        assert mock_ch.call_count == 1, (
            f"Expected 1 ConnectHandler call, got {mock_ch.call_count}"
        )

    def test_send_command_called_once_per_command(self):
        """send_command must be called exactly len(commands) times within that session."""
        conn = _make_conn_mock()

        with (
            patch("app.ssh_client.SSH_USERNAME", "admin"),
            patch("app.ssh_client.SSH_PASSWORD", "pass"),
            patch("app.ssh_client.SSH_SECRET", ""),
            patch("app.ssh_client.ConnectHandler") as mock_ch,
        ):
            mock_ch.return_value.__enter__ = lambda s: conn
            mock_ch.return_value.__exit__ = MagicMock(return_value=False)

            from app.ssh_client import run_commands

            run_commands(DEVICE, COMMANDS)

        assert conn.send_command.call_count == len(COMMANDS)


class TestRunCommandsEnableBehaviour:
    def test_enable_called_when_secret_set(self):
        """conn.enable() must be invoked when SSH_SECRET is non-empty."""
        conn = _make_conn_mock()

        with (
            patch("app.ssh_client.SSH_USERNAME", "admin"),
            patch("app.ssh_client.SSH_PASSWORD", "pass"),
            patch("app.ssh_client.SSH_SECRET", "secret"),
            patch("app.ssh_client.ConnectHandler") as mock_ch,
        ):
            mock_ch.return_value.__enter__ = lambda s: conn
            mock_ch.return_value.__exit__ = MagicMock(return_value=False)

            from app.ssh_client import run_commands

            run_commands(DEVICE, COMMANDS)

        conn.enable.assert_called_once()

    def test_enable_not_called_when_no_secret(self):
        """conn.enable() must NOT be called when SSH_SECRET is an empty string."""
        conn = _make_conn_mock()

        with (
            patch("app.ssh_client.SSH_USERNAME", "admin"),
            patch("app.ssh_client.SSH_PASSWORD", "pass"),
            patch("app.ssh_client.SSH_SECRET", ""),
            patch("app.ssh_client.ConnectHandler") as mock_ch,
        ):
            mock_ch.return_value.__enter__ = lambda s: conn
            mock_ch.return_value.__exit__ = MagicMock(return_value=False)

            from app.ssh_client import run_commands

            run_commands(DEVICE, COMMANDS)

        conn.enable.assert_not_called()

"""Unit tests for inventory loading and lookup."""

import pytest
import yaml

from app.inventory import get_all_devices, get_device, load_inventory

SAMPLE_INVENTORY = {
    "devices": [
        {
            "name": "sw-core-01",
            "hostname": "sw-core-01.lab.local",
            "ip": "192.168.1.1",
            "platform": "cisco_ios",
            "role": "core",
            "ssh_enabled": True,
            "snmp_enabled": False,
        },
        {
            "name": "sw-acc-01",
            "hostname": "sw-acc-01.lab.local",
            "ip": "192.168.1.10",
            "platform": "cisco_ios",
            "role": "access",
            "ssh_enabled": False,
            "snmp_enabled": False,
        },
    ]
}


@pytest.fixture
def inventory_file(tmp_path):
    path = tmp_path / "devices.yaml"
    path.write_text(yaml.dump(SAMPLE_INVENTORY))
    return path


def test_load_inventory_returns_all_devices(inventory_file):
    inv = load_inventory(inventory_file)
    assert len(inv) == 2
    assert "sw-core-01" in inv
    assert "sw-acc-01" in inv


def test_load_inventory_device_fields(inventory_file):
    inv = load_inventory(inventory_file)
    device = inv["sw-core-01"]
    assert device.ip == "192.168.1.1"
    assert device.platform == "cisco_ios"
    assert device.ssh_enabled is True


def test_load_inventory_missing_file():
    with pytest.raises(FileNotFoundError):
        load_inventory("/nonexistent/path/devices.yaml")


def test_get_device_found(inventory_file):
    inv = load_inventory(inventory_file)
    device = get_device("sw-core-01", inv)
    assert device.name == "sw-core-01"


def test_get_device_not_found(inventory_file):
    inv = load_inventory(inventory_file)
    with pytest.raises(ValueError, match="not found"):
        get_device("sw-missing-99", inv)


def test_get_all_devices_returns_list(inventory_file):
    inv = load_inventory(inventory_file)
    devices = get_all_devices(inv)
    assert isinstance(devices, list)
    # Only sw-core-01 has ssh_enabled=True; sw-acc-01 is filtered out.
    assert len(devices) == 1
    assert devices[0].name == "sw-core-01"


def test_get_all_devices_excludes_ssh_disabled(inventory_file):
    """get_all_devices() must not include devices with ssh_enabled=False."""
    inv = load_inventory(inventory_file)
    devices = get_all_devices(inv)
    assert all(d.ssh_enabled for d in devices)
    disabled_names = {name for name, d in inv.items() if not d.ssh_enabled}
    returned_names = {d.name for d in devices}
    assert disabled_names.isdisjoint(returned_names)


def test_load_inventory_duplicate_name_logs_warning(tmp_path, caplog):
    """Duplicate device names emit a warning and the second entry wins."""
    import logging
    dup = {
        "devices": [
            {"name": "sw-core-01", "hostname": "h1", "ip": "10.0.0.1",
             "platform": "cisco_ios", "role": "core", "ssh_enabled": True},
            {"name": "sw-core-01", "hostname": "h2", "ip": "10.0.0.2",
             "platform": "cisco_ios", "role": "core", "ssh_enabled": True},
        ]
    }
    path = tmp_path / "devices.yaml"
    path.write_text(yaml.dump(dup))
    import yaml as _yaml
    path.write_text(_yaml.dump(dup))

    with caplog.at_level(logging.WARNING, logger="app.inventory"):
        inv = load_inventory(path)

    assert "Duplicate device name" in caplog.text
    assert "sw-core-01" in caplog.text
    # Second entry (ip 10.0.0.2) should have overwritten the first.
    assert inv["sw-core-01"].ip == "10.0.0.2"


def test_load_inventory_empty_file_returns_empty_dict(tmp_path):
    """An empty YAML file must return an empty inventory dict, not raise."""
    path = tmp_path / "devices.yaml"
    path.write_text("")
    inv = load_inventory(path)
    assert inv == {}

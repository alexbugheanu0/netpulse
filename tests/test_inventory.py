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
    assert len(devices) == 2

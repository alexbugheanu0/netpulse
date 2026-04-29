"""Unit tests for endpoint diagnosis."""

from unittest.mock import patch

from app.jobs.diagnose_endpoint import run
from app.models import Device
from app.summarizer import summarize


DEVICE = Device(
    name="sw-acc-01",
    hostname="sw-acc-01.lab.local",
    ip="192.168.1.10",
    platform="cisco_ios",
    role="access",
    ssh_enabled=True,
)

ARP_OUTPUT = """\
Protocol  Address          Age (min)  Hardware Addr   Type   Interface
Internet  10.0.0.25              2   aabb.cc00.0101  ARPA   Vlan20
"""

MAC_OUTPUT = """\
          Mac Address Table
-------------------------------------------
Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
  20    aabb.cc00.0101    DYNAMIC     Gi0/3
"""

INTERFACES_STATUS = """\
Port      Name               Status       Vlan       Duplex  Speed Type
Gi0/3     endpoint           connected    20         a-full  a-100 10/100/1000BaseTX
"""

INTERFACES_CLEAN = """\
GigabitEthernet0/3 is up, line protocol is up (connected)
     0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored
     0 output errors, 0 collisions, 0 interface resets
"""

INTERFACES_ERRORS = """\
GigabitEthernet0/3 is up, line protocol is up (connected)
     47 input errors, 12 CRC, 0 frame, 0 overrun, 0 ignored
     3 output errors, 0 collisions, 2 interface resets
"""

PORT_SECURITY = """\
Secure Port  MaxSecureAddr  CurrentAddr  SecurityViolation  Security Action
---------------------------------------------------------------------------
Gi0/3        2              1            0                  Restrict
"""

STP_OUTPUT = """\
VLAN0020
Interface           Role Sts Cost      Prio.Nbr Type
------------------- ---- --- --------- -------- --------------------------------
Gi0/3               Desg FWD 4         128.3    P2p
"""


def _run_with_outputs(overrides=None):
    outputs = {
        "show ip arp": ARP_OUTPUT,
        "show mac address-table": MAC_OUTPUT,
        "show interfaces status": INTERFACES_STATUS,
        "show interfaces": INTERFACES_CLEAN,
        "show port-security": PORT_SECURITY,
        "show spanning-tree": STP_OUTPUT,
    }
    outputs.update(overrides or {})

    with patch("app.jobs.diagnose_endpoint.run_command", side_effect=lambda _device, command: outputs[command]):
        return run(DEVICE, "10.0.0.25")


def test_diagnose_endpoint_correlates_clean_endpoint():
    result = _run_with_outputs()

    assert result.success is True
    data = result.parsed_data
    assert data["resolved_mac"] == "aabb.cc00.0101"
    assert data["access_port"] == "Gi0/3"
    assert data["vlan"] == "20"
    assert "No obvious fault" in data["likely_cause"]


def test_diagnose_endpoint_flags_interface_errors():
    result = _run_with_outputs({"show interfaces": INTERFACES_ERRORS})

    assert result.success is True
    data = result.parsed_data
    assert "Physical layer" in data["likely_cause"]
    assert data["confidence"] == "high"
    assert data["evidence"]["interface_errors"]["crc"] == 12


def test_diagnose_endpoint_summary_is_chat_ready():
    result = _run_with_outputs({"show interfaces": INTERFACES_ERRORS})

    summary = summarize(result)

    assert "SW-ACC-01" in summary
    assert "10.0.0.25 -> Gi0/3 / VLAN 20" in summary
    assert "\n" not in summary

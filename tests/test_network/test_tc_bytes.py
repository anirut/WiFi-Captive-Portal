import pytest
from unittest.mock import patch, MagicMock

TC_STATS_OUTPUT = b"""
class htb 1:466 parent 1: prio 0 rate 10Mbit ceil 10Mbit burst 1600b cburst 1600b
 Sent 52428800 bytes 40960 pkt (dropped 0, overlimits 0 requeues 0)
 rate 0bit 0pps backlog 0b 0p requeues 0
"""

def _mock_run(stdout=b"", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m

def test_get_bytes_returns_download_from_wan(monkeypatch):
    """get_bytes reads bytes_down from WAN_INTERFACE class matching IP."""
    import app.network.tc as tc_mod
    monkeypatch.setattr("app.core.config.settings.WAN_INTERFACE", "eth0")
    with patch("app.network.tc.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(stdout=TC_STATS_OUTPUT)
        # IP 192.168.1.210 → class ID 1:466 (1*256+210=466)
        up, down = tc_mod.get_bytes("192.168.1.210")
    assert down == 52428800

def test_get_bytes_returns_zero_when_class_not_found():
    """get_bytes returns (0,0) when no matching class exists."""
    import app.network.tc as tc_mod
    with patch("app.network.tc.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(stdout=b"qdisc htb 1: root refcnt 2\n")
        up, down = tc_mod.get_bytes("192.168.1.1")
    assert up == 0
    assert down == 0

def test_apply_bandwidth_limit_adds_ifb_commands_when_up_kbps_nonzero():
    """apply_bandwidth_limit generates ifb0 commands when up_kbps > 0."""
    import app.network.tc as tc_mod
    with patch("app.network.tc._run") as mock_run:
        tc_mod.apply_bandwidth_limit("192.168.1.5", up_kbps=1024, down_kbps=2048, wan_if="eth0")
    calls = [" ".join(c.args[0]) for c in mock_run.call_args_list]
    ifb_calls = [c for c in calls if "ifb0" in c]
    assert len(ifb_calls) >= 2  # class add + filter add on ifb0

def test_apply_bandwidth_limit_skips_ifb_when_up_kbps_zero():
    """apply_bandwidth_limit skips ifb0 when up_kbps == 0."""
    import app.network.tc as tc_mod
    with patch("app.network.tc._run") as mock_run:
        tc_mod.apply_bandwidth_limit("192.168.1.5", up_kbps=0, down_kbps=2048, wan_if="eth0")
    calls = [" ".join(c.args[0]) for c in mock_run.call_args_list]
    ifb_calls = [c for c in calls if "ifb0" in c]
    assert len(ifb_calls) == 0

def test_remove_bandwidth_limit_removes_ifb_when_up_kbps_nonzero():
    """remove_bandwidth_limit deletes ifb0 class when up_kbps > 0."""
    import app.network.tc as tc_mod
    with patch("app.network.tc._run") as mock_run:
        tc_mod.remove_bandwidth_limit("192.168.1.5", up_kbps=1024, wan_if="eth0")
    calls = [" ".join(c.args[0]) for c in mock_run.call_args_list]
    ifb_calls = [c for c in calls if "ifb0" in c]
    assert len(ifb_calls) >= 2  # filter del + class del

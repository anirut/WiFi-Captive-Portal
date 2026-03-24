import pytest
import subprocess
from unittest.mock import patch, MagicMock, mock_open


def _make_config(**kwargs):
    """Build a minimal mock DhcpConfig object."""
    cfg = MagicMock()
    cfg.enabled = kwargs.get("enabled", True)
    cfg.interface = kwargs.get("interface", "wlan0")
    cfg.gateway_ip = kwargs.get("gateway_ip", "192.168.0.1")
    cfg.subnet = kwargs.get("subnet", "192.168.0.0/22")
    cfg.dhcp_range_start = kwargs.get("dhcp_range_start", "192.168.0.10")
    cfg.dhcp_range_end = kwargs.get("dhcp_range_end", "192.168.3.250")
    cfg.lease_time = kwargs.get("lease_time", "8h")
    cfg.dns_upstream_1 = kwargs.get("dns_upstream_1", "8.8.8.8")
    cfg.dns_upstream_2 = kwargs.get("dns_upstream_2", "8.8.4.4")
    cfg.dns_mode = MagicMock()
    cfg.dns_mode.value = kwargs.get("dns_mode", "redirect")
    cfg.log_queries = kwargs.get("log_queries", False)
    return cfg


def test_write_config_redirect_mode():
    cfg = _make_config(dns_mode="redirect", log_queries=True)
    m = mock_open()
    with patch("builtins.open", m):
        from app.network.dnsmasq import write_config
        write_config(cfg)
    written = "".join(call.args[0] for call in m().write.call_args_list)
    assert "address=/#/192.168.0.1" in written
    assert "address=/logout/192.168.0.1" in written
    assert "255.255.252.0" in written  # netmask derived from /22
    assert "log-dhcp" in written
    assert "log-queries" in written


def test_write_config_forward_mode():
    cfg = _make_config(dns_mode="forward")
    m = mock_open()
    with patch("builtins.open", m):
        from app.network.dnsmasq import write_config
        write_config(cfg)
    written = "".join(call.args[0] for call in m().write.call_args_list)
    assert "address=/#/" not in written
    assert "address=/logout/192.168.0.1" in written  # logout always present
    assert "server=8.8.8.8" in written


def test_write_config_disabled_mode():
    cfg = _make_config(enabled=False)
    with patch("builtins.open", mock_open()) as m, \
         patch("app.network.dnsmasq.subprocess.run") as mock_run:
        from app.network.dnsmasq import write_config
        write_config(cfg)
    # No file should be written
    m.assert_not_called()
    # systemctl stop dnsmasq should be called
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "stop" in args
    assert "dnsmasq" in args


def test_get_leases_parses_correctly():
    lease_line = "1711036800 aa:bb:cc:dd:ee:ff 192.168.0.42 iPhone-guest *\n"
    with patch("builtins.open", mock_open(read_data=lease_line)):
        from app.network.dnsmasq import get_leases
        leases = get_leases()
    assert len(leases) == 1
    assert leases[0]["mac"] == "aa:bb:cc:dd:ee:ff"
    assert leases[0]["ip"] == "192.168.0.42"
    assert leases[0]["hostname"] == "iPhone-guest"
    assert "expires_at" in leases[0]


def test_get_leases_returns_empty_when_no_file():
    with patch("builtins.open", side_effect=FileNotFoundError):
        from app.network.dnsmasq import get_leases
        leases = get_leases()
    assert leases == []


def test_get_status_returns_dict():
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch("app.network.dnsmasq.subprocess.run", return_value=mock_result), \
         patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data="line1\nline2\n")):
        from app.network.dnsmasq import get_status
        status = get_status()
    assert "running" in status
    assert "lease_count" in status
    assert "config_file_exists" in status
    assert status["running"] is True
    assert status["config_file_exists"] is True

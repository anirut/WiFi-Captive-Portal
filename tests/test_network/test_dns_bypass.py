import pytest
from unittest.mock import patch, call, MagicMock
import subprocess


def test_add_dns_bypass_runs_two_iptables_rules():
    # Must patch the module-local subprocess reference (CLAUDE.md convention)
    with patch("app.network.iptables.subprocess.run") as mock_run:
        from app.network.iptables import add_dns_bypass
        add_dns_bypass("192.168.0.42")
    assert mock_run.call_count == 2
    calls = [str(c) for c in mock_run.call_args_list]
    assert any("udp" in c and "DNAT" in c and "8.8.8.8" in c for c in calls)
    assert any("tcp" in c and "DNAT" in c and "8.8.8.8" in c for c in calls)


def test_remove_dns_bypass_runs_two_iptables_rules():
    with patch("app.network.iptables.subprocess.run") as mock_run:
        from app.network.iptables import remove_dns_bypass
        remove_dns_bypass("192.168.0.42")
    assert mock_run.call_count == 2
    calls = [str(c) for c in mock_run.call_args_list]
    assert any("-D" in c and "udp" in c for c in calls)
    assert any("-D" in c and "tcp" in c for c in calls)


def test_remove_dns_bypass_does_not_raise_on_missing_rule():
    # remove_dns_bypass uses check=False — returns non-zero returncode without raising
    mock_result = MagicMock()
    mock_result.returncode = 1
    with patch("app.network.iptables.subprocess.run", return_value=mock_result):
        from app.network.iptables import remove_dns_bypass
        # Should not raise even with non-zero returncode
        remove_dns_bypass("192.168.0.42")

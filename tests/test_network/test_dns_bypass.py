import pytest
from unittest.mock import patch, MagicMock


def test_add_dns_bypass_calls_nftables():
    """Test that add_dns_bypass calls nftables with correct IP."""
    with patch("app.network.nftables.NftablesManager._run") as mock_run:
        from app.network.nftables import NftablesManager
        NftablesManager.add_dns_bypass("192.168.0.42")
    assert mock_run.call_count == 1
    call_args = str(mock_run.call_args)
    assert "192.168.0.42" in call_args
    assert "dns_bypass" in call_args


def test_remove_dns_bypass_calls_nftables():
    """Test that remove_dns_bypass calls nftables delete."""
    with patch("app.network.nftables.subprocess.run") as mock_run:
        from app.network.nftables import NftablesManager
        NftablesManager.remove_dns_bypass("192.168.0.42")
    assert mock_run.call_count == 1
    call_args = str(mock_run.call_args)
    assert "delete" in call_args
    assert "192.168.0.42" in call_args
    assert "dns_bypass" in call_args


def test_remove_dns_bypass_does_not_raise_on_missing_rule():
    """remove_dns_bypass uses check=False — returns non-zero returncode without raising."""
    mock_result = MagicMock()
    mock_result.returncode = 1
    with patch("app.network.nftables.subprocess.run", return_value=mock_result):
        from app.network.nftables import NftablesManager
        # Should not raise even with non-zero returncode
        NftablesManager.remove_dns_bypass("192.168.0.42")

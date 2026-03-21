"""
Tests for nftables.py module.
"""
import subprocess
import pytest
from unittest.mock import patch, MagicMock

from app.network.nftables import NftablesManager


class TestNftablesManager:
    """Test NftablesManager class."""

    @patch("app.network.nftables.subprocess.run")
    def test_add_to_whitelist_calls_nft(self, mock_run):
        """Test add_to_whitelist calls nft with correct args."""
        NftablesManager.add_to_whitelist("192.168.1.100")

        mock_run.assert_called_once_with(
            ["nft", "add", "element", "inet captive_portal", "whitelist", "{ 192.168.1.100 }"],
            check=True, capture_output=True, text=True
        )

    @patch("app.network.nftables.subprocess.run")
    def test_remove_from_whitelist_uses_check_false(self, mock_run):
        """Test remove_from_whitelist uses check=False for graceful handling."""
        NftablesManager.remove_from_whitelist("192.168.1.100")

        # Should not raise even if element doesn't exist
        mock_run.assert_called()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs.get("check") is False

    @patch("app.network.nftables.subprocess.run")
    def test_is_whitelisted_returns_true_when_present(self, mock_run):
        """Test is_whitelisted returns True when IP is in set."""
        mock_run.return_value = MagicMock(returncode=0)

        result = NftablesManager.is_whitelisted("192.168.1.100")

        assert result is True

    @patch("app.network.nftables.subprocess.run")
    def test_is_whitelisted_returns_false_when_absent(self, mock_run):
        """Test is_whitelisted returns False when IP is not in set."""
        mock_run.return_value = MagicMock(returncode=1)

        result = NftablesManager.is_whitelisted("192.168.1.100")

        assert result is False

    @patch("app.network.nftables.subprocess.run")
    def test_add_dns_bypass_calls_nft(self, mock_run):
        """Test add_dns_bypass calls nft with correct args."""
        NftablesManager.add_dns_bypass("192.168.1.100")

        mock_run.assert_called_once_with(
            ["nft", "add", "element", "inet captive_portal", "dns_bypass", "{ 192.168.1.100 }"],
            check=True, capture_output=True, text=True
        )

    @patch("app.network.nftables.subprocess.run")
    def test_remove_dns_bypass_calls_nft_with_check_false(self, mock_run):
        """Test remove_dns_bypass calls nft with correct args and check=False."""
        NftablesManager.remove_dns_bypass("192.168.1.100")

        mock_run.assert_called_once_with(
            ["nft", "delete", "element", "inet captive_portal", "dns_bypass", "{ 192.168.1.100 }"],
            check=False, capture_output=True
        )

    @patch("app.network.nftables.subprocess.run")
    def test_create_session_rules_calls_both(self, mock_run):
        """Test create_session_rules adds to both sets."""
        NftablesManager.create_session_rules("192.168.1.100")

        # Should call nft twice (whitelist + dns_bypass)
        assert mock_run.call_count == 2

    @patch("app.network.nftables.subprocess.run")
    def test_remove_session_rules_calls_both(self, mock_run):
        """Test remove_session_rules removes from both sets."""
        NftablesManager.remove_session_rules("192.168.1.100")

        # Should call nft twice
        assert mock_run.call_count == 2

    @patch("app.network.nftables.subprocess.run")
    def test_add_to_whitelist_raises_on_error(self, mock_run):
        """Test add_to_whitelist raises on subprocess error."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "nft", stderr="error")

        with pytest.raises(subprocess.CalledProcessError):
            NftablesManager.add_to_whitelist("192.168.1.100")

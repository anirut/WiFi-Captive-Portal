"""
Tests for nftables.py module.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestNftablesManager:
    """Test NftablesManager class."""

    @patch("app.network.nftables.subprocess.run")
    def test_add_to_whitelist_calls_nft(self, mock_run):
        """Test add_to_whitelist calls nft with correct args."""
        from app.network.nftables import NftablesManager

        NftablesManager.add_to_whitelist("192.168.1.100")

        mock_run.assert_called_once()
        cmd = " ".join(mock_run.call_args[0][0])
        assert "nft" in cmd
        assert "add" in cmd
        assert "whitelist" in cmd
        assert "192.168.1.100" in cmd

    @patch("app.network.nftables.subprocess.run")
    def test_remove_from_whitelist_uses_check_false(self, mock_run):
        """Test remove_from_whitelist uses check=False for graceful handling."""
        from app.network.nftables import NftablesManager

        NftablesManager.remove_from_whitelist("192.168.1.100")

        # Should not raise even if element doesn't exist
        mock_run.assert_called()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs.get("check") is False

    @patch("app.network.nftables.subprocess.run")
    def test_is_whitelisted_returns_true_when_present(self, mock_run):
        """Test is_whitelisted returns True when IP is in set."""
        from app.network.nftables import NftablesManager

        mock_run.return_value = MagicMock(returncode=0)

        result = NftablesManager.is_whitelisted("192.168.1.100")

        assert result is True

    @patch("app.network.nftables.subprocess.run")
    def test_is_whitelisted_returns_false_when_absent(self, mock_run):
        """Test is_whitelisted returns False when IP is not in set."""
        from app.network.nftables import NftablesManager

        mock_run.return_value = MagicMock(returncode=1)

        result = NftablesManager.is_whitelisted("192.168.1.100")

        assert result is False

    @patch("app.network.nftables.subprocess.run")
    def test_add_dns_bypass_calls_nft(self, mock_run):
        """Test add_dns_bypass calls nft with correct args."""
        from app.network.nftables import NftablesManager

        NftablesManager.add_dns_bypass("192.168.1.100")

        cmd = " ".join(mock_run.call_args[0][0])
        assert "dns_bypass" in cmd

    @patch("app.network.nftables.subprocess.run")
    def test_create_session_rules_calls_both(self, mock_run):
        """Test create_session_rules adds to both sets."""
        from app.network.nftables import NftablesManager

        NftablesManager.create_session_rules("192.168.1.100")

        # Should call nft twice (whitelist + dns_bypass)
        assert mock_run.call_count == 2

    @patch("app.network.nftables.subprocess.run")
    def test_remove_session_rules_calls_both(self, mock_run):
        """Test remove_session_rules removes from both sets."""
        from app.network.nftables import NftablesManager

        NftablesManager.remove_session_rules("192.168.1.100")

        # Should call nft twice
        assert mock_run.call_count == 2

    @patch("app.network.nftables.subprocess.run")
    def test_add_to_whitelist_raises_on_error(self, mock_run):
        """Test add_to_whitelist raises on subprocess error."""
        from app.network.nftables import NftablesManager
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "nft", stderr="error")

        with pytest.raises(subprocess.CalledProcessError):
            NftablesManager.add_to_whitelist("192.168.1.100")

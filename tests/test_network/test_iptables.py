from unittest.mock import patch
from app.network.iptables import add_whitelist, remove_whitelist, is_whitelisted

def test_add_whitelist_runs_correct_command():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        add_whitelist("192.168.1.45")
        mock_run.assert_called_once_with(
            ["iptables", "-I", "FORWARD", "-s", "192.168.1.45", "-j", "ACCEPT"],
            check=True, capture_output=True
        )

def test_remove_whitelist_runs_correct_command():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        remove_whitelist("192.168.1.45")
        mock_run.assert_called_once_with(
            ["iptables", "-D", "FORWARD", "-s", "192.168.1.45", "-j", "ACCEPT"],
            check=True, capture_output=True
        )

def test_is_whitelisted_true():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        assert is_whitelisted("192.168.1.45") is True

def test_is_whitelisted_false():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        assert is_whitelisted("192.168.1.45") is False

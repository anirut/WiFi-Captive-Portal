import subprocess
from unittest.mock import patch
from app.network.iptables import add_whitelist, remove_whitelist, is_whitelisted

def test_add_whitelist_runs_correct_command():
    with patch("app.network.iptables.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        add_whitelist("192.168.1.45")
        mock_run.assert_called_once_with(
            ["iptables", "-I", "FORWARD", "-s", "192.168.1.45", "-j", "ACCEPT"],
            check=True, capture_output=True
        )

def test_remove_whitelist_runs_correct_command():
    with patch("app.network.iptables.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        remove_whitelist("192.168.1.45")
        mock_run.assert_called_once_with(
            ["iptables", "-D", "FORWARD", "-s", "192.168.1.45", "-j", "ACCEPT"],
            check=True, capture_output=True
        )

def test_is_whitelisted_true():
    with patch("app.network.iptables.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        assert is_whitelisted("192.168.1.45") is True

def test_is_whitelisted_false():
    with patch("app.network.iptables.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        assert is_whitelisted("192.168.1.45") is False

def test_add_whitelist_reraises_on_failure():
    error = subprocess.CalledProcessError(1, "iptables", stderr=b"iptables: Bad rule")
    with patch("app.network.iptables.subprocess.run", side_effect=error):
        try:
            add_whitelist("192.168.1.45")
            assert False, "Expected CalledProcessError to be raised"
        except subprocess.CalledProcessError as e:
            assert e is error

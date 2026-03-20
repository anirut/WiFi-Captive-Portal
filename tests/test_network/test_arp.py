from unittest.mock import patch, mock_open
from app.network.arp import get_mac_for_ip

ARP_TABLE = """\
IP address       HW type     Flags       HW address            Mask     Device
192.168.1.45     0x1         0x2         aa:bb:cc:dd:ee:ff     *        wlan0
192.168.1.46     0x1         0x0         00:00:00:00:00:00     *        wlan0
"""

def test_get_mac_for_known_ip():
    with patch("builtins.open", mock_open(read_data=ARP_TABLE)):
        assert get_mac_for_ip("192.168.1.45") == "aa:bb:cc:dd:ee:ff"

def test_get_mac_incomplete_entry_returns_none():
    with patch("builtins.open", mock_open(read_data=ARP_TABLE)):
        assert get_mac_for_ip("192.168.1.46") is None

def test_get_mac_unknown_ip_returns_none():
    with patch("builtins.open", mock_open(read_data=ARP_TABLE)):
        assert get_mac_for_ip("192.168.1.99") is None

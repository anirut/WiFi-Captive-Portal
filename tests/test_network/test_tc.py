from unittest.mock import patch, call
from app.network.tc import apply_bandwidth_limit, remove_bandwidth_limit, _ip_to_class_id

def test_ip_to_class_id():
    # class_id = int(parts[2])*256 + int(parts[3])
    assert _ip_to_class_id("192.168.1.45") == f"1:{1*256+45}"   # 1:301
    assert _ip_to_class_id("192.168.0.1") == f"1:{0*256+1}"      # 1:1
    assert _ip_to_class_id("192.168.2.100") == f"1:{2*256+100}"  # 1:612

def test_apply_bandwidth_limit_calls_tc():
    with patch("app.network.tc.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        apply_bandwidth_limit("192.168.1.45", up_kbps=10240, down_kbps=51200, wan_if="eth0")
        assert mock_run.call_count >= 2  # at least class add + filter add

def test_remove_bandwidth_limit_calls_tc():
    with patch("app.network.tc.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        remove_bandwidth_limit("192.168.1.45", wan_if="eth0")
        assert mock_run.call_count == 2

def test_zero_kbps_skips_tc():
    with patch("app.network.tc.subprocess.run") as mock_run:
        apply_bandwidth_limit("192.168.1.45", up_kbps=0, down_kbps=0, wan_if="eth0")
        mock_run.assert_not_called()

def get_mac_for_ip(ip: str) -> str | None:
    """Read MAC from ARP table. Returns None if not found or entry incomplete."""
    try:
        with open("/proc/net/arp") as f:
            for line in f.readlines()[1:]:  # skip header
                parts = line.split()
                if len(parts) >= 4 and parts[0] == ip:
                    flags = int(parts[2], 16)
                    if flags & 0x2:  # complete entry
                        mac = parts[3]
                        return mac if mac != "00:00:00:00:00:00" else None
    except OSError:
        pass
    return None

"""
Runtime host/IP detection for ALLOWED_HOSTS and hostname resolution.

The machine's LAN IP can change (DHCP), so we discover the current local
IPv4 addresses at startup instead of hardcoding an IP that may go stale.
"""
import socket


def get_local_ips():
    """Return the machine's current non-loopback IPv4 addresses."""
    ips = set()

    # 1) Try the robust trick: connect a UDP socket to a public address
    #    (no packets are actually sent) to learn the primary outbound IP.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                ips.add(ip)
        finally:
            s.close()
    except Exception:
        pass

    # 2) Enumerate all interfaces as a fallback / to catch secondary NICs.
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass

    # 3) Use the hostname resolution directly (covers various setups).
    try:
        hostname_ip = socket.gethostbyname(socket.gethostname())
        if hostname_ip and not hostname_ip.startswith("127."):
            ips.add(hostname_ip)
    except Exception:
        pass

    return sorted(ips)


def build_allowed_hosts(configured):
    """
    Merge env-configured hosts (from ALLOWED_HOSTS) with the current
    local IPs so the backend is reachable at the machine's live address
    without hardcoding an ever-changing IP.
    """
    allowed = set(h.strip() for h in configured if h and h.strip())
    allowed.update(get_local_ips())
    # Always allow localhost for local tooling.
    allowed.update({"localhost", "127.0.0.1"})
    return sorted(allowed)

"""
Local Network Scanner — Finds Windows PCs on the LAN.
Uses ARP, SMB, and ICMP to discover devices.
"""

import subprocess
import socket
import struct
import ipaddress
import concurrent.futures
import time
import os


def get_local_ip():
    """Get the local IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.1.100"


def get_network_range(local_ip=None, cidr=None):
    """Get the local network range as a list of IPs."""
    if local_ip is None:
        local_ip = get_local_ip()

    if cidr:
        network = ipaddress.IPv4Network(cidr, strict=False)
    else:
        network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)

    return [str(ip) for ip in network.hosts()]


def ping_host(ip, timeout=1):
    """Ping a single host. Returns True if reachable."""
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["ping", "-n", "1", "-w", str(timeout * 1000), ip],
                capture_output=True,
                timeout=timeout + 2,
            )
        else:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", str(timeout), ip],
                capture_output=True,
                timeout=timeout + 2,
            )
        return result.returncode == 0
    except Exception:
        return False


def check_smb(ip, port=445, timeout=2):
    """Check if SMB port is open (indicates Windows machine)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def get_hostname(ip, timeout=2):
    """Try to resolve hostname from IP."""
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname.split(".")[0]
    except Exception:
        return None


def get_mac_address(ip):
    """Get MAC address from ARP table."""
    try:
        if os.name == "nt":
            output = subprocess.check_output(
                ["arp", "-a", ip], stderr=subprocess.DEVNULL
            ).decode("cp1252", errors="replace")
            for line in output.split("\n"):
                if ip in line:
                    parts = line.split()
                    for part in parts:
                        if ":" in part and len(part) == 17:
                            return part.upper()
        else:
            output = subprocess.check_output(
                ["arp", "-n", ip], stderr=subprocess.DEVNULL
            ).decode("utf-8", errors="replace")
            for line in output.split("\n"):
                if ip in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        return parts[2].upper()
    except Exception:
        pass
    return "unknown"


def scan_network(cidr=None, max_workers=50, timeout=2):
    """
    Scan the local network for Windows PCs.
    Returns list of discovered devices.
    """
    local_ip = get_local_ip()
    all_ips = get_network_range(local_ip, cidr)

    print(f"[*] Scanning {len(all_ips)} IPs on {local_ip}/24 network...")

    discovered = []

    # Phase 1: Ping sweep
    print("[*] Phase 1: Ping sweep...")
    alive_ips = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(ping_host, ip, timeout): ip for ip in all_ips}
        for future in concurrent.futures.as_completed(futures):
            ip = futures[future]
            if future.result():
                alive_ips.append(ip)

    print(f"[+] {len(alive_ips)} hosts alive")

    # Phase 2: Check SMB (Windows indicator)
    print("[*] Phase 2: Checking for Windows (SMB port 445)...")
    windows_ips = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(check_smb, ip, timeout=timeout): ip for ip in alive_ips
        }
        for future in concurrent.futures.as_completed(futures):
            ip = futures[future]
            if future.result():
                windows_ips.append(ip)

    print(f"[+] {len(windows_ips)} Windows machines found")

    # Phase 3: Resolve hostnames and MAC addresses
    print("[*] Phase 3: Resolving hostnames and MAC addresses...")
    for ip in windows_ips:
        hostname = get_hostname(ip)
        mac = get_mac_address(ip)
        discovered.append(
            {
                "ip": ip,
                "hostname": hostname or "unknown",
                "mac": mac,
                "smb_open": True,
                "status": "online",
            }
        )

    # Also include server itself
    server_hostname = socket.gethostname()
    discovered.insert(
        0,
        {
            "ip": local_ip,
            "hostname": server_hostname,
            "mac": get_mac_address(local_ip),
            "smb_open": True,
            "status": "online (this server)",
        },
    )

    return discovered


def scan_and_print(cidr=None):
    """Scan network and print results in a table."""
    results = scan_network(cidr)

    print("\n" + "=" * 70)
    print(f"  {'IP':<16} {'Hostname':<20} {'MAC':<18} {'Status'}")
    print("=" * 70)
    for d in results:
        print(f"  {d['ip']:<16} {d['hostname']:<20} {d['mac']:<18} {d['status']}")
    print("=" * 70)
    print(f"\nTotal Windows PCs found: {len(results) - 1}")

    return results


if __name__ == "__main__":
    import sys

    cidr = sys.argv[1] if len(sys.argv) > 1 else None
    scan_and_print(cidr)

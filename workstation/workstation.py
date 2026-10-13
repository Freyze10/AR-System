import getpass
import socket

import psutil


def get_real_mac():
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for interface, addr_list in addrs.items():
        if interface not in stats or not stats[interface].isup:
            continue

        for addr in addr_list:
            if addr.family == psutil.AF_LINK:
                mac = addr.address
                if mac and mac != "00:00:00:00:00:00":
                    # Skip VMware / VirtualBox virtual adapters
                    if not mac.lower().replace('-', ':').startswith(("00:50:56", "00:0c:29", "00:05:69")):
                        return mac.replace('-', ':')
    return None


def get_ethernet_ip():
    """IPv4 address of the physical Ethernet adapter."""
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for interface, addr_list in addrs.items():
        if interface not in stats or not stats[interface].isup:
            continue
        if "ethernet" in interface.lower():
            for addr in addr_list:
                if addr.family == socket.AF_INET:
                    return addr.address

    # Fallback: any active IPv4 that is not loopback or Tailscale (100.x.x.x)
    for interface, addr_list in addrs.items():
        if interface not in stats or not stats[interface].isup:
            continue
        for addr in addr_list:
            if addr.family == socket.AF_INET:
                ip = addr.address
                if not ip.startswith("127.") and not ip.startswith("100."):
                    return ip
    return None


def get_workstation_info():
    try:
        h = socket.gethostname()
    except Exception:
        h = None

    return {"h": h, "i": get_ethernet_ip(), "m": get_real_mac()}
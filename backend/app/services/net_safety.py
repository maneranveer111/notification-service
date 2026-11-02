import ipaddress
import socket
from app.config import get_settings


def assert_public_host(host: str) -> None:
    """
    Ensure the given host resolves exclusively to public, routable IP addresses.
    Rejects private, loopback, link-local, multicast, reserved, or unspecified addresses
    unless settings.allow_private_smtp_hosts is True.
    """
    settings = get_settings()
    if settings.allow_private_smtp_hosts:
        return

    if not host or not host.strip():
        raise ValueError("Host cannot be empty")

    clean_host = host.strip()

    try:
        # socket.getaddrinfo(host, port, family, type, proto, flags)
        addr_info = socket.getaddrinfo(clean_host, None)
    except Exception as e:
        raise ValueError(f"Could not resolve host '{clean_host}': {e}")

    if not addr_info:
        raise ValueError(f"Could not resolve host '{clean_host}'")

    for item in addr_info:
        sockaddr = item[4]
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise ValueError(f"Invalid IP address resolved for host '{clean_host}': {ip_str}")

        # Check for IPv4 mapped IPv6 (e.g., ::ffff:127.0.0.1)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(f"Host '{clean_host}' resolves to non-public IP address: {ip}")


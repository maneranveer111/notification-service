import ipaddress
from fastapi import Request
from app.config import get_settings


def client_ip(request: Request) -> str:
    settings = get_settings()
    fallback = request.client.host if request.client else "127.0.0.1"
    trusted_count = getattr(settings, "trusted_proxy_count", 0)
    if trusted_count <= 0:
        return fallback

    xff = request.headers.get("X-Forwarded-For")
    if not xff:
        return fallback

    ips = [ip.strip() for ip in xff.split(",") if ip.strip()]
    if len(ips) < trusted_count:
        return fallback

    candidate = ips[-trusted_count]
    try:
        ipaddress.ip_address(candidate)
        return candidate
    except ValueError:
        return fallback


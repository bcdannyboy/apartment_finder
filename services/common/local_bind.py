import ipaddress
from typing import Iterable, Optional
from urllib.parse import urlparse


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class LocalBindError(ValueError):
    pass


def ensure_local_bind(host: str) -> None:
    if host not in LOCAL_HOSTS:
        raise LocalBindError(
            f"Local-only binding required; received host={host!r}"
        )


def ensure_local_url(
    url: str,
    *,
    allowed_hosts: Optional[Iterable[str]] = None,
    allow_private_ips: bool = False,
) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise LocalBindError(f"Local-only URL required; received url={url!r}")
    allowed = set(allowed_hosts or [])
    if host in LOCAL_HOSTS or host in allowed:
        return
    try:
        ip_addr = ipaddress.ip_address(host)
    except ValueError:
        ip_addr = None
    if ip_addr:
        if ip_addr.is_loopback:
            return
        if allow_private_ips and ip_addr.is_private:
            return
    raise LocalBindError(
        f"Local-only URL required; received host={host!r}"
    )

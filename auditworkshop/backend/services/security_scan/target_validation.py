"""SSRF protection shared by all server-side security scan probes."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeTargetError(ValueError):
    """Raised when a scan target could reach a non-public network."""


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return ip.is_global and not any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


def validate_public_host(host: str) -> tuple[str, ...]:
    """Resolve *host* and reject it unless every result is globally routable."""
    clean = (host or "").strip().rstrip(".").lower()
    if not clean or clean == "localhost" or clean.endswith((".localhost", ".local", ".internal")):
        raise UnsafeTargetError("Lokale oder interne Zieladressen sind nicht erlaubt.")
    try:
        infos = socket.getaddrinfo(clean, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeTargetError("Der Zielhost konnte nicht öffentlich aufgelöst werden.") from exc
    addresses = tuple(sorted({info[4][0] for info in infos}))
    if not addresses or not all(_is_public(address) for address in addresses):
        raise UnsafeTargetError("Private, lokale oder reservierte Zielnetze sind nicht erlaubt.")
    return addresses


def validate_public_url(raw_url: str) -> tuple[str, str, int]:
    """Validate scheme, credentials, host, port and resolved addresses."""
    parsed = urlparse((raw_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeTargetError("Nur vollständige öffentliche HTTP/HTTPS-URLs sind erlaubt.")
    if parsed.username or parsed.password:
        raise UnsafeTargetError("Zugangsdaten in der Ziel-URL sind nicht erlaubt.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeTargetError("Der Zielport ist ungültig.") from exc
    if port not in {80, 443}:
        raise UnsafeTargetError("Sicherheitsprüfungen sind nur auf Port 80 oder 443 erlaubt.")
    validate_public_host(parsed.hostname)
    return parsed.scheme, parsed.hostname, port

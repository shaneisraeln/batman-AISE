"""SSRF guard for user-supplied upstream model URLs.

BATMAN lets a tenant register the URL of their own deployed ML API so BATMAN can
proxy inference to it. That URL is attacker-controlled input: without validation
a tenant could point it at ``http://127.0.0.1``, the cloud metadata endpoint
``http://169.254.169.254``, or an RFC1918 internal service and turn BATMAN into
a Server-Side Request Forgery pivot.

This module validates an upstream URL before it is stored or used:

  - scheme must be http or https (no file://, gopher://, ftp://, ...)
  - the host must resolve to at least one address, and NONE of the resolved
    addresses may be loopback / private / link-local / reserved / multicast /
    unspecified. This blocks the literal IPs *and* DNS names that resolve to
    them (DNS-rebinding-at-config-time).

Escape hatch: in local development / docker-compose the protected model often
*is* on a private network (e.g. the bundled ml-service). Setting
``BATMAN_ALLOW_PRIVATE_UPSTREAM=1`` disables the private-range block. It is OFF
by default, so production is safe unless an operator explicitly opts in.

This is an MVP-appropriate mitigation. It is intentionally not a full egress
firewall: it does not defend against TOCTOU DNS rebinding between validation and
the actual request, or redirects to private hosts. Those are documented as
residual risks; a hardened deployment should also restrict egress at the network
layer.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse


class UpstreamURLError(ValueError):
    """Raised when an upstream URL is malformed or points at a blocked address."""


_ALLOWED_SCHEMES = {"http", "https"}


def _allow_private() -> bool:
    return os.getenv("BATMAN_ALLOW_PRIVATE_UPSTREAM", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    """True if the address is one we must never let an upstream URL reach."""
    return (
        ip.is_loopback        # 127.0.0.0/8, ::1
        or ip.is_private      # 10/8, 172.16/12, 192.168/16, fc00::/7, ...
        or ip.is_link_local   # 169.254.0.0/16 (incl. 169.254.169.254 metadata), fe80::/10
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified  # 0.0.0.0, ::
    )


def validate_upstream_url(url: str) -> None:
    """Validate a user-supplied upstream URL. Raises UpstreamURLError if unsafe.

    Returns None on success.
    """
    if not url or not isinstance(url, str):
        raise UpstreamURLError("upstream_url_required")

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise UpstreamURLError("upstream_url_scheme_must_be_http_or_https")

    host = parsed.hostname
    if not host:
        raise UpstreamURLError("upstream_url_missing_host")

    allow_private = _allow_private()

    # If the host is already a literal IP, check it directly (no DNS).
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if not allow_private and _is_blocked_ip(literal):
            raise UpstreamURLError("upstream_url_points_to_blocked_address")
        return

    # Obvious loopback aliases that may not resolve in every environment.
    lowered = host.lower()
    if not allow_private and (lowered == "localhost" or lowered.endswith(".localhost")):
        raise UpstreamURLError("upstream_url_points_to_blocked_address")

    # Resolve the DNS name and check every returned address.
    try:
        infos = socket.getaddrinfo(host, parsed.port or None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        # Cannot resolve. When the private-range guard is active we fail closed:
        # a legitimate public upstream must be resolvable. (Local/dev flows that
        # use fake hostnames set BATMAN_ALLOW_PRIVATE_UPSTREAM=1.)
        if allow_private:
            return
        raise UpstreamURLError("upstream_url_host_unresolvable")

    if allow_private:
        return

    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            raise UpstreamURLError("upstream_url_points_to_blocked_address")

"""The AI stays home: what counts as a local Ollama server and a local model.

Allowed servers are on this machine (loopback) or the private network: the LAN ranges and
Tailscale's. A host name is judged by every address it resolves to, so a name that points
anywhere else is refused. Cloud models (Ollama runs them on ollama.com) are refused by name
here and by the ``remote_host`` Ollama reports for them (in the adapter).
"""

import ipaddress
import socket
from collections.abc import Callable

from photo_assistant.ports.ai import AIUnreachableError

Resolve = Callable[[str], list[str]]

_LOCAL_NETWORKS = tuple(
    ipaddress.ip_network(n)
    for n in (
        "127.0.0.0/8",
        "::1/128",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",  # Tailscale
        "fd7a:115c:a1e0::/48",  # Tailscale
    )
)


class NotLocalError(AIUnreachableError):
    """The AI server or model is not on this machine or the private network. A server fault,
    not a photo's: background jobs retry later instead of giving up on photos or albums."""


def system_resolve(host: str) -> list[str]:
    """Every address ``host`` resolves to; OSError when it does not resolve."""
    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]).split("%")[0] for info in infos})


def is_local_address(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return any(address in network for network in _LOCAL_NETWORKS)


def check_host(host: str, resolve: Resolve) -> None:
    """NotLocalError unless ``host`` (an address or a name) is local; OSError when a name
    does not resolve."""
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        addresses = resolve(host)
    outside = [ip for ip in addresses if not is_local_address(ip)]
    if outside or not addresses:
        raise NotLocalError(
            f"the AI server {host} is at {', '.join(outside) or 'no address'}: only this "
            "machine and the private network (LAN, Tailscale) are allowed"
        )


def is_cloud_model(name: str) -> bool:
    """``model:cloud``, ``model:tag-cloud`` and ``model:tag:cloud`` run on ollama.com
    (Ollama's own rule, internal/modelref). A colon followed by a path is a registry port."""
    _, colon, tag = name.strip().lower().rpartition(":")
    if not colon or "/" in tag:
        return False
    return tag == "cloud" or tag.endswith("-cloud")

import ipaddress

from slowapi import Limiter
from slowapi.util import get_remote_address


def client_key(request) -> str:
    """The rate-limit bucket of a request: its client IP, except that an IPv6
    client is bucketed by its /64. A single home connection usually gets a
    whole /64, so keying on the full address let one attacker rotate through
    billions of addresses and never hit a limit."""
    address = get_remote_address(request)
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if ip.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return address


limiter = Limiter(key_func=client_key)

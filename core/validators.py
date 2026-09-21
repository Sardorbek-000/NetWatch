"""our input validators working across netwatch

Every function returns True/False and never raises, so callers can use them
directly: `if not is_valid_ip(value): ...`
"""

import ipaddress
import re

# Six hex pairs separated by ':' or '-' (Windows' `arp -a` prints dashes).
# The backreference \1 forces one separator style per address, so mixed
# forms like 'aa:bb-cc:dd-ee:ff' are rejected.
_MAC_RE = re.compile(r"[0-9A-Fa-f]{2}([:-])(?:[0-9A-Fa-f]{2}\1){4}[0-9A-Fa-f]{2}")


def is_valid_ip(value):
    """True if `value` is a dotted-quad IPv4 address string, e.g. '192.168.1.10'.
    """
    if not isinstance(value, str):
        return False
    try:
        ipaddress.IPv4Address(value)
    except ValueError:
        return False
    return True


def is_valid_mac(value):
    """True if `value` is a MAC address like 'aa:bb:cc:dd:ee:ff' or 'AA-BB-CC-DD-EE-FF'."""
    if not isinstance(value, str):
        return False
    return _MAC_RE.fullmatch(value) is not None


def is_valid_ip_range(value, strict=False):
    """True if `value` is an IPv4 CIDR range like '192.168.1.0/24'.

    A prefix length is required, so a bare IP is not a range.
    With strict=False (default), '192.168.1.5/24' is accepted because the
    host bits are ignored; pass strict=True to reject it.
    """
    if not isinstance(value, str) or "/" not in value:
        return False
    if not value.rpartition("/")[2].isdigit():
        return False
    try:
        ipaddress.IPv4Network(value, strict=strict)
    except ValueError:
        return False
    return True

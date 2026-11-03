"""Structured network identifiers; retain original offsets for obfuscated email."""
import ipaddress
import re

from app.detection.recognizers.common import entity

_AT = r"(?:\[\s*at\s*\]|\(\s*at\s*\)|%40)"
_DOT = r"(?:\.|\[\s*dot\s*\]|\(\s*dot\s*\)|%2e)"
_LABEL = r"[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?"
_EMAIL = re.compile(
    rf"(?<![\w.+\-])[a-z0-9][a-z0-9._+\-]{{0,63}}\s*{_AT}\s*"
    rf"{_LABEL}(?:\s*{_DOT}\s*{_LABEL}){{0,5}}\s*{_DOT}\s*[a-z]{{2,24}}(?![\w\-])", re.I,
)
_IPV6 = re.compile(r"(?<![\w:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![\w:])", re.I)


def detect_network(text: str) -> list:
    found = [entity(text, m.start(), m.end(), "EMAIL") for m in _EMAIL.finditer(text)]
    for match in _IPV6.finditer(text):
        try:
            ipaddress.IPv6Address(match.group())
        except ValueError:
            continue
        found.append(entity(text, match.start(), match.end(), "IP_ADDRESS"))
    return found

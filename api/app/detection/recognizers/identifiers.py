"""Structured identifiers the DB regex set did not cover (or covered too narrowly).

Why: the benchmark showed 0% recall for IP addresses and court case numbers, 66% for plates,
and usernames typed PERSON; these have precise shapes or cues, so code rules are cheap and exact.
What: IPv4/IPv6 (validated with ipaddress), court case numbers (R.G., N.R.G., ruolo generale,
procedimento/causa n.), Italian plates (spaced/hyphenated; lowercase only after "targa"),
paper ID cards with a space, health-card numbers, claim/policy numbers, usernames and handles.
Test: "login da 10.1.2.3" -> IP_ADDRESS; "R.G. n. 1234/2025" -> PRACTICE_ID "1234/2025";
"L. 431/1998" -> nothing; "targa ly388zm" -> TARGA.
"""
from __future__ import annotations

import ipaddress
import re

from app.detection.entities import PiiEntity
from app.detection.recognizers.common import entity

_NUM = r"(?i:(?:n(?:r|um)?\.?|n°|numero)\s*)"
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.]|\.\d)")
_IPV6 = re.compile(r"(?<![\w:.])(?=[0-9A-Fa-f:]*:[0-9A-Fa-f]*:)[0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7}(?![\w:])")
_VERSION_CUE = re.compile(r"(?i)(?:\bv|versione|version|release|build)\s*\.?\s*$")
_CASE = re.compile(
    rf"(?:(?<![\w.])(?i:N\.?\s?R\.?\s?G\.?(?:\s?N\.?\s?R\.?)?|R\.?\s?G\.?(?:\s?(?:N\.?\s?R\.?|A\.?\s?C\.?|L\.?|E\.?))?"
    rf"|ruolo\s+generale|proc(?:edimento|\.)(?:\s+(?:penale|civile|pen\.|civ\.))?|causa(?:\s+civile)?"
    rf"|fascicolo|decreto\s+ingiuntivo|ricorso|pratica|sentenza)(?:\s+(?i:iscritt[ao]\s+al))?\s*{_NUM}?\s*:?\s*"
    rf"(?:{_NUM}\s*)?(?P<v>\d{{1,7}}\s?/\s?(?:19|20)?\d{{2}})(?![\d/])"
    rf"|(?i:\bn\.)\s*(?P<v2>\d{{1,7}}/(?:19|20)\d{{2}})\s*(?i:R\.?\s?G\.?|N\.?\s?R\.?\s?G))"
)
# Italian plates since 1994 never use I, O, Q, U
_PL = "[A-HJ-NPR-TV-Z]"
_PLATE = re.compile(rf"(?<![\w\-])({_PL}{{2}}[ \-]?\d{{3}}[ \-]?{_PL}{{2}})(?![\w\-])")
_PLATE_CUE = re.compile(
    rf"(?i:\btarg(?:a|ato|ata|he)|\bplate|\bveicolo)\s*(?:{_NUM})?:?\s*(?P<v>[A-Za-z]{{2}}[ \-]?\d{{3}}[ \-]?[A-Za-z]{{1,2}}"
    rf"|[A-Za-z]{{2}}[ \-]?\d{{5,6}})(?![\w\-])"
)
_ID_CARD = re.compile(rf"(?i:carta\s+d.identit[àa](?:\s+cartacea)?|\bC\.\s?I\.)\s*{_NUM}?:?\s*(?P<v>[A-Z]{{2}}\s\d{{7}})\b")
_HEALTH_CARD = re.compile(r"(?<!\d)(80380\d{15})(?!\d)")
_POLICY = re.compile(
    rf"(?i:\bsinistro|\bpolizza(?:\s+(?:vita|auto|rca|casa|n))?|\bcontratto\s+assicurativo|\bpratica\s+assicurativa)"
    rf"\s*{_NUM}?:?\s*(?P<v>(?=[A-Z0-9./\-]*\d{{4}})[A-Z0-9][A-Z0-9./\-]{{3,24}}[A-Z0-9])(?![\w/])"
)
_USER_CUE = re.compile(
    r"(?i:\b(?:username|user\s*name|nome\s+utente|user\s*id|userid|login|nickname|handle|account))"
    r"(?P<sep>\s*(?:è|e'|:|=)\s*|\s+)[\"']?(?P<v>[A-Za-z0-9][A-Za-z0-9._\-]{1,38}[A-Za-z0-9])"
)
_HANDLE = re.compile(r"(?<![\w.@])@([A-Za-z0-9_](?:[A-Za-z0-9_.]{1,28}[A-Za-z0-9_])?)\b")
_NOT_USERNAMES = frozenset({"ok", "ko", "fallito", "failed", "riuscito", "success", "error", "errore", "attempt",
                            "page", "pagina", "form", "the", "per", "non", "con", "del", "della"})


def _ip(text: str) -> list[PiiEntity]:
    found = []
    for pattern in (_IPV4, _IPV6):
        for m in pattern.finditer(text):
            try:
                ipaddress.ip_address(m.group())
            except ValueError:
                continue
            if pattern is _IPV4 and _VERSION_CUE.search(text[max(0, m.start() - 12):m.start()]):
                continue
            found.append(entity(text, m.start(), m.end(), "IP_ADDRESS"))
    return found


def _username(text: str) -> list[PiiEntity]:
    found = []
    for m in _USER_CUE.finditer(text):
        value = m["v"]
        explicit = m["sep"].strip() != ""
        if value.lower() in _NOT_USERNAMES or not (explicit or re.search(r"[\d._]", value)):
            continue
        found.append(entity(text, m.start("v"), m.end("v"), "USERNAME"))
    found += [entity(text, m.start(1), m.end(1), "USERNAME") for m in _HANDLE.finditer(text)]
    return found


def detect_identifiers(text: str) -> list[PiiEntity]:
    """Why/What: see module docstring. Test: see module docstring."""
    found = _ip(text) + _username(text)
    for m in _CASE.finditer(text):
        group = "v" if m["v"] else "v2"
        found.append(entity(text, m.start(group), m.end(group), "PRACTICE_ID"))
    found += [entity(text, m.start(1), m.end(1), "TARGA") for m in _PLATE.finditer(text)]
    found += [entity(text, m.start("v"), m.end("v"), "TARGA") for m in _PLATE_CUE.finditer(text)]
    found += [entity(text, m.start("v"), m.end("v"), "IDENTITY_CARD") for m in _ID_CARD.finditer(text)]
    found += [entity(text, m.start(1), m.end(1), "HEALTH_CARD") for m in _HEALTH_CARD.finditer(text)]
    found += [entity(text, m.start("v"), m.end("v"), "POLICY_NUMBER") for m in _POLICY.finditer(text)]
    return found

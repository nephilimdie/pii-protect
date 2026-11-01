"""Key-aware detection for JSON and key=value text (logs, payloads, exports).

Why: in logs and JSON the key names the value's meaning ("tax_code", "ip", "user") far more
reliably than any NER model; the logs_json genre was our weakest (F1 68.4).
What: finds "key": "value" pairs and key=value / key: value tokens, normalises the key
(lowercase, separators -> "_", last dotted segment) and emits the mapped PII type for the
value after a light per-type sanity check (an IP must parse, a phone needs 6+ digits...).
Test: '{"full_name":"Thi Lan Nguyen","ip":"76.182.195.80"}' -> PERSON + IP_ADDRESS;
'"request_id":"649..."' -> nothing.
"""
from __future__ import annotations

import ipaddress
import re

from app.detection.entities import PiiEntity
from app.detection.recognizers.common import entity, parse_date

_KEYS: dict[str, tuple[str, ...]] = {
    "PERSON": ("name", "fullname", "full_name", "firstname", "first_name", "lastname", "last_name", "surname",
               "nome", "cognome", "nominativo", "customer_name", "holder", "intestatario", "display_name",
               "contact_name", "given_name", "family_name"),
    "EMAIL": ("email", "mail", "e_mail", "pec", "email_address"),
    "PHONE": ("phone", "telephone", "tel", "telefono", "mobile", "cell", "cellulare", "phone_number", "msisdn"),
    "FISCAL_CODE": ("cf", "codice_fiscale", "codicefiscale", "tax_code", "taxcode", "fiscal_code"),
    "IBAN": ("iban",),
    "ADDRESS": ("address", "indirizzo", "street", "residenza", "domicilio", "address_line", "addr"),
    "USERNAME": ("user", "username", "user_name", "login", "uid", "nickname", "handle", "utente", "account"),
    "IP_ADDRESS": ("ip", "ip_address", "ipaddr", "client_ip", "remote_ip", "remote_addr", "src_ip", "source_ip",
                   "x_forwarded_for"),
    "DATE_BORN": ("dob", "birth_date", "birthdate", "date_of_birth", "data_nascita", "data_di_nascita", "birthday"),
    "CITY_BORN": ("birth_place", "place_of_birth", "luogo_nascita", "comune_nascita", "luogo_di_nascita"),
    "VAT_NUMBER": ("piva", "p_iva", "partita_iva", "vat", "vat_number"),
    "TARGA": ("plate", "targa", "license_plate"),
}
_TYPE_BY_KEY = {key: pii_type for pii_type, keys in _KEYS.items() for key in keys}
_JSON_PAIR = re.compile(r'"(?P<k>[A-Za-z_][\w\-.]{0,40})"\s*:\s*"(?P<v>[^"\\\n]{1,200})"')
_KV_PAIR = re.compile(r"(?<![\w.\-])(?P<k>[A-Za-z_][\w\-.]{0,40})\s*=\s*(?P<q>[\"']?)(?P<v>[^\s\"',;&|)\]}]{1,200})(?P=q)")
_SUBJECT_PREFIXES = frozenset({"user", "customer", "client", "cliente", "contact", "billing", "shipping", "owner"})
_EMPTY = frozenset({"", "null", "none", "nil", "n/a", "-", "true", "false", "undefined", "anonymous", "unknown"})


def _plausible(pii_type: str, value: str) -> bool:
    v = value.strip()
    if v.lower() in _EMPTY:
        return False
    if pii_type == "IP_ADDRESS":
        try:
            ipaddress.ip_address(v)
            return True
        except ValueError:
            return False
    if pii_type == "EMAIL":
        return "@" in v
    if pii_type == "PHONE":
        return len(re.sub(r"\D", "", v)) >= 6
    if pii_type == "DATE_BORN":
        return parse_date(v[:10]) is not None or parse_date(v) is not None
    if pii_type in ("PERSON", "CITY_BORN", "ADDRESS"):
        return bool(re.search(r"[A-Za-zÀ-ÿ]{2}", v))
    return len(v) >= 2


def _type_for(key: str) -> str | None:
    norm = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    if norm in _TYPE_BY_KEY:
        return _TYPE_BY_KEY[norm]
    # "customer_email", "billing_address": a subject prefix in front of a known key
    prefix, _, rest = norm.partition("_")
    return _TYPE_BY_KEY.get(rest) if prefix in _SUBJECT_PREFIXES else None


def detect_key_values(text: str) -> list[PiiEntity]:
    """Why/What: see module docstring. Test: see module docstring."""
    found: list[PiiEntity] = []
    for pattern in (_JSON_PAIR, _KV_PAIR):
        for m in pattern.finditer(text):
            pii_type = _type_for(m["k"].rsplit(".", 1)[-1])
            if pii_type and _plausible(pii_type, m["v"]):
                start, end = m.start("v"), m.end("v")
                # trim surrounding whitespace so the span is exactly the value
                while start < end and text[start].isspace():
                    start += 1
                while end > start and text[end - 1].isspace():
                    end -= 1
                found.append(entity(text, start, end, pii_type))
    return found

"""Synthetic Italian professional documents run through the regex layer + policy filter.

All names, codes and numbers below are invented; CF / P.IVA / IBAN values are
synthetic but carry valid check characters so the checksum gates accept them.
"""

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.detection.entity_merger import EntityMerger
from app.detection.layers.regex_layer import ItalianRegexDetector
from app.routers.entity_filter import filter_detected_entities

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _migration(name: str):
    spec = importlib.util.spec_from_file_location(f"migration_{name}", next(_VERSIONS.glob(f"{name}_*.py")))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M057 = _migration("057")
M017 = _migration("017")
M016 = _migration("016")
POLICIES = {p["domain"]: p for p in M057.POLICIES}

# Seeded patterns these presets reuse, as found in a fresh `alembic upgrade head` database
# (002/009/016/017), minus legacy PIVA (consolidated into VAT_NUMBER by 057).
_LEGACY = [
    (p["pii_type"], p["pattern"], p["flags"], p["capture_group"])
    for p in _migration("002").DEFAULT_PATTERNS if p["pii_type"] not in {"PIVA", "PHONE"}
] + [
    ("PHONE", r"(?<!\d)(?:\+39\s*|0039\s*)?(?:0\d[\s./\-]?\d{7,8}|0\d{2,3}[\s./\-]?\d{6}|3\d{2}[\s.\-]?\d{6,7})(?!\d)", "", 0),
    ("PASSPORT", r"\b[A-Z]{2}\d{7}\b", "", 0),
    ("POLICY_NUMBER", M017.POLICY_PATTERN, "IGNORECASE", 1),
    ("POLICY_NUMBER", M017.CLAIM_PATTERN, "IGNORECASE|DOTALL", 1),
    *[(t, p, f, g) for t, p, f, g, _ in M016.NEW_PATTERNS if t == "IDENTITY_CARD"],
]
DETECTOR = ItalianRegexDetector([
    SimpleNamespace(pii_type=t, pattern=p, flags=f, capture_group=g)
    for t, p, f, g in _LEGACY + [row[:4] for row in M057.PATTERNS]
])


def _protected(text: str, domain: str) -> set[tuple[str, str]]:
    policy = POLICIES[domain]
    merged = EntityMerger().merge(DETECTOR.detect(text), text)
    kept = filter_detected_entities(merged, keep_types=set(policy["keep"]), protect_types=set(policy["protect"]))
    return {(e.pii_type, e.text) for e in kept}


def _assert_preserved(text: str, domain: str, *fragments: str) -> None:
    protected_texts = [value for _, value in _protected(text, domain)]
    for fragment in fragments:
        assert fragment in text
        assert not any(fragment in value or value in fragment for value in protected_texts), fragment


HR_TEXT = (
    "Cedolino di marzo 2026 emesso il 31/03/2026. Il dipendente Mario Rossi, matricola 004512, "
    "codice fiscale RSSMRA80A01H501U, residente in via Garibaldi 12, 20121 Milano, "
    "tel. 333 1234567, email mario.rossi@example.it. Accredito su IBAN IT60 X054 2811 1010 0000 0123 456. "
    "Matricola INPS 1234567890, PAT INAIL 98765432/01. Assenza per malattia dal 02/03/2026 al 06/03/2026; "
    "trattenuta sindacale CGIL di € 12,50. Retribuzione lorda € 2.350,00 ai sensi dell'art. 2099 c.c."
)

TAX_TEXT = (
    "Studio Bianchi - dichiarazione presentata il 15/09/2026, protocollo telematico 26091512345678901-000123. "
    "Contribuente Laura Bianchi, C.F. BNCLRA85T45F205L, P.IVA 07940180156, domicilio fiscale "
    "corso Vittorio Emanuele 45, 10121 Torino. Avviso di accertamento n. TMB012345678/2026, "
    "cartella di pagamento 068 2026 0012345678 000. Rimborso su IBAN IT57Y0306909606100000063123. "
    "Imposta dovuta € 4.812,33 ai sensi dell'art. 36-bis del D.P.R. 600/1973."
)

REAL_ESTATE_TEXT = (
    "Atto di compravendita del 10/05/2026. Venditore Giuseppe Verdi, codice fiscale VRDGPP75C12L219Z, "
    "carta d'identità CA12345AB, patente di guida U1A23B45CD. Immobile censito al catasto fabbricati "
    "foglio 12, particella 345, subalterno 7, prezzo € 185.000,00. Passaporto YA1234567. Polizza n. 2026/00123456, "
    "sinistro n. 451234567 relativo al veicolo targato AB 123 CD. Indennizzo su IBAN "
    "DE89 3704 0044 0532 0130 00 ai sensi dell'art. 1892 c.c."
)


def test_hr_payroll_protects_identity_social_security_and_art9_data():
    found = _protected(HR_TEXT, "hr_payroll")
    expected = {
        ("PERSON", "Mario Rossi"),
        ("EMPLOYEE_ID", "004512"),
        ("FISCAL_CODE", "RSSMRA80A01H501U"),
        ("EMAIL", "mario.rossi@example.it"),
        ("IBAN", "IT60 X054 2811 1010 0000 0123 456"),
        ("SOCIAL_SECURITY_ID", "1234567890"),
        ("SOCIAL_SECURITY_ID", "98765432/01"),
        ("HEALTH_DATA", "Assenza per malattia"),
        ("UNION_MEMBERSHIP", "trattenuta sindacale CGIL"),
    }
    assert expected <= found, expected - found
    assert any(t == "ADDRESS" and "Garibaldi 12" in v for t, v in found)
    assert any(t == "PHONE" and "1234567" in v for t, v in found)
    _assert_preserved(HR_TEXT, "hr_payroll", "31/03/2026", "€ 2.350,00", "€ 12,50", "art. 2099")


def test_tax_accounting_protects_taxpayer_ids_and_keeps_amounts():
    found = _protected(TAX_TEXT, "tax_accounting")
    expected = {
        ("PERSON", "Laura Bianchi"),
        ("FISCAL_CODE", "BNCLRA85T45F205L"),
        ("VAT_NUMBER", "07940180156"),
        ("IBAN", "IT57Y0306909606100000063123"),
        ("TAX_DOCUMENT_ID", "26091512345678901-000123"),
        ("TAX_DOCUMENT_ID", "TMB012345678/2026"),
        ("TAX_DOCUMENT_ID", "068 2026 0012345678 000"),
    }
    assert expected <= found, expected - found
    assert any(t == "ADDRESS" and "Vittorio Emanuele 45" in v for t, v in found)
    _assert_preserved(TAX_TEXT, "tax_accounting", "15/09/2026", "€ 4.812,33", "art. 36-bis", "600/1973")


def test_real_estate_insurance_protects_documents_cadastre_and_policies():
    found = _protected(REAL_ESTATE_TEXT, "real_estate_insurance")
    expected = {
        ("PERSON", "Giuseppe Verdi"),
        ("FISCAL_CODE", "VRDGPP75C12L219Z"),
        ("IDENTITY_CARD", "CA12345AB"),
        ("DRIVER_LICENSE", "U1A23B45CD"),
        ("PASSPORT", "YA1234567"),
        ("CADASTRAL_REF", "foglio 12, particella 345, subalterno 7"),
        ("POLICY_NUMBER", "2026/00123456"),
        ("POLICY_NUMBER", "451234567"),
        ("TARGA", "AB 123 CD"),
        ("IBAN", "DE89 3704 0044 0532 0130 00"),
    }
    assert expected <= found, expected - found
    _assert_preserved(REAL_ESTATE_TEXT, "real_estate_insurance", "10/05/2026", "€ 185.000,00", "art. 1892")


@pytest.mark.parametrize("text", [HR_TEXT, TAX_TEXT, REAL_ESTATE_TEXT])
def test_generic_professional_covers_every_specialised_preset(text):
    generic = _protected(text, "generic_professional")
    for domain in ("hr_payroll", "tax_accounting", "real_estate_insurance"):
        assert _protected(text, domain) <= generic, domain


def test_generic_professional_is_a_superset_of_specialised_protect_lists():
    generic = set(POLICIES["generic_professional"]["protect"])
    for domain in ("hr_payroll", "tax_accounting", "real_estate_insurance"):
        assert set(POLICIES[domain]["protect"]) <= generic, domain
        assert not set(POLICIES[domain]["protect"]) & set(POLICIES[domain]["keep"]), domain


def test_checksum_gates_drop_lookalike_codes():
    text = (
        "Riferimento RSSMRA80A01H5LMA, P.IVA 01234567890, IBAN IT60 X054 2811 1010 0000 0123 457, "
        "conto DE89 3704 0044 0532 0130 01, codice IT01234567890, protocollo 2026/123 del 01/02/2026, art. 13 GDPR."
    )
    # Shape-only legacy patterns (002: 16-char CF without omocodia, compact IT IBAN) are left
    # unchanged for recall; the checksum gates cover the broadened shapes added in 057.
    found = _protected(text, "generic_professional")
    assert not {t for t, _ in found} & {"FISCAL_CODE", "VAT_NUMBER", "IBAN"}, found


def test_labels_are_required_for_ambiguous_numbers():
    text = "Il totale di 1234567890 euro e la pratica 98765432/01 del 2026, foglio di calcolo 12."
    assert _protected(text, "generic_professional") == set()


def test_date_born_rule_matches_birth_context_only():
    rule = re.compile(M057.DATE_BORN_RULE["context_pattern"])
    assert rule.search("Mario Rossi, nato a Reggio Emilia (RE) il ")
    assert rule.search("data di nascita: ")
    assert rule.search("nata il ")
    assert not rule.search("documento emesso il ")


@pytest.mark.parametrize(("text", "value"), [
    ("protocollo n. 2026/AE/000123 del 01/02/2026", "2026/AE/000123"),
    ("Prot. n. 0012345/2026", "0012345/2026"),
    ("prot. 4521-B", "4521-B"),
    ("n. protocollo AGE.DP-MI.123456", "AGE.DP-MI.123456"),
    ("numero di protocollo: 98765432.", "98765432"),
    ("Protocollo nr. 2026-000789", "2026-000789"),
])
def test_free_form_protocol_numbers_need_a_label(text, value):
    assert ("TAX_DOCUMENT_ID", value) in _protected(text, "tax_accounting")


@pytest.mark.parametrize("text", [
    "protocollo 2026 del ministero",
    "prot. n. 2026, art. 2043 c.c.",
    "protocollo n. 1.234 e prot. 1.234,56",
    "protocollo d'intesa ai sensi del D.Lgs. 196/2003",
    "protocollo art. 2043 c.c.",
    "protocollo COVID-19 e prot. 123",
    "il numero 2026/AE/000123 senza etichetta",
])
def test_free_form_protocol_rejects_years_amounts_and_law_refs(text):
    assert not {v for t, v in _protected(text, "tax_accounting") if t == "TAX_DOCUMENT_ID"}

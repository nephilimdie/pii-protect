"""Per-layer runtime configuration: defaults and schema used by engine + API."""
from __future__ import annotations

PRESIDIO_TYPES = [
    "PERSON", "EMAIL", "PHONE", "DATE", "IBAN", "FISCAL_CODE",
    "CREDIT_CARD", "PASSPORT", "DRIVER_LICENSE", "IDENTITY_CARD", "URL",
]
PRESIDIO_TYPES_WITH_LOCATION = PRESIDIO_TYPES + ["LOCATION"]

PRIVACY_FILTER_TYPES = [
    "ACCOUNT_NUMBER", "ADDRESS", "DATE", "EMAIL", "PERSON", "PHONE", "URL", "SECRET",
]

AI4PRIVACY_TYPES = [
    "PERSON", "EMAIL", "PHONE", "PASSWORD", "USERNAME", "CREDIT_CARD",
    "CVV", "SSN", "PIN", "IBAN", "BIC", "CRYPTO_ADDRESS", "IP_ADDRESS",
    "DATE_OF_BIRTH", "MASKED_NUMBER", "ACCOUNT_NUMBER",
]

from app.detection.layers.rizzo_layer import TYPES as RIZZO_TYPES

# code -> (display name, description): one source for startup rows, readiness and the scoped-config collection
LAYER_META: dict[str, tuple[str, str]] = {
    "regex": ("Regex", "Deterministic database and built-in regular-expression detection"),
    "presidio": ("Presidio/spaCy", "NER and recognizer-based detection through Presidio and spaCy"),
    "privacy_filter": ("Privacy Filter", "ONNX privacy-filter model for broad PII detection"),
    "ai4privacy": ("AI4Privacy", "Transformer layer with wider PII category coverage"),
    "rizzo": ("Rizzo-PII", "Optional Italian mmBERT PII model. Requires installed weights and platform activation; "
                           "evaluate recall, false positives and memory before enabling."),
}

DEFAULTS: dict[str, dict] = {
    "presidio": {
        "min_score":        0.65,
        "location_enabled": False,
        "enabled_types":    PRESIDIO_TYPES,
    },
    "privacy_filter": {
        "min_score":     0.70,
        "min_chars":     0,
        "enabled_types": PRIVACY_FILTER_TYPES,
    },
    "ai4privacy": {
        "min_score":     0.70,
        "min_chars":     0,
        "enabled_types": AI4PRIVACY_TYPES,
    },
    "rizzo": {
        "min_score":     0.50,
        "enabled_types": RIZZO_TYPES,
    },
}

ALL_LAYERS = list(DEFAULTS.keys())

# What each layer exposes as configurable — used by API schema + UI
SCHEMA: dict[str, list[str]] = {
    "presidio":       ["min_score", "location_enabled", "enabled_types"],
    "privacy_filter": ["min_score", "min_chars", "enabled_types"],
    "ai4privacy":     ["min_score", "min_chars", "enabled_types"],
    "rizzo":          ["min_score", "enabled_types"],
}

# All known type codes per layer (for UI multiselect options)
ALL_TYPES: dict[str, list[str]] = {
    "presidio":       PRESIDIO_TYPES_WITH_LOCATION,
    "privacy_filter": PRIVACY_FILTER_TYPES,
    "ai4privacy":     AI4PRIVACY_TYPES,
    "rizzo":          RIZZO_TYPES,
}


def merge(base: dict, override: dict) -> dict:
    """Shallow merge: override wins on any present key."""
    return {**base, **{k: v for k, v in override.items() if k in base}}


def effective(layer: str, tenant_row: dict | None, global_row: dict | None) -> dict:
    """Return effective config: defaults → global override → tenant override."""
    cfg = dict(DEFAULTS.get(layer, {}))
    if global_row:
        cfg = merge(cfg, global_row)
    if tenant_row:
        cfg = merge(cfg, tenant_row)
    return cfg

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

DEFAULTS: dict[str, dict] = {
    "presidio": {
        "min_score":        0.65,
        "location_enabled": False,
        "enabled_types":    PRESIDIO_TYPES,
    },
    "privacy_filter": {
        "min_score":     0.70,
        "min_chars":     200,
        "enabled_types": PRIVACY_FILTER_TYPES,
    },
    "ai4privacy": {
        "min_score":     0.70,
        "min_chars":     200,
        "enabled_types": AI4PRIVACY_TYPES,
    },
}

ALL_LAYERS = list(DEFAULTS.keys())

# What each layer exposes as configurable — used by API schema + UI
SCHEMA: dict[str, list[str]] = {
    "presidio":       ["min_score", "location_enabled", "enabled_types"],
    "privacy_filter": ["min_score", "min_chars", "enabled_types"],
    "ai4privacy":     ["min_score", "min_chars", "enabled_types"],
}

# All known type codes per layer (for UI multiselect options)
ALL_TYPES: dict[str, list[str]] = {
    "presidio":       PRESIDIO_TYPES_WITH_LOCATION,
    "privacy_filter": PRIVACY_FILTER_TYPES,
    "ai4privacy":     AI4PRIVACY_TYPES,
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

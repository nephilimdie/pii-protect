import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException

COLLECTIONS = {
    "regex-patterns",
    "denylist",
    "context-words",
    "reclassification",
    "detection-layers",
    "pii-types",
    "domain-policies",
    "context-types",
}

BASE_QUERIES = {
    "regex-patterns": "SELECT id, pii_type, pattern, flags, capture_group, description, enabled, created_at, updated_at FROM regex_patterns ORDER BY pii_type, created_at",
    "denylist": "SELECT id, pii_type, value, match_type, description, enabled, created_at, updated_at FROM entity_denylist ORDER BY pii_type, value",
    "context-words": "SELECT id, entity_type, word, description, enabled, created_at FROM presidio_context ORDER BY entity_type, word",
    "reclassification": "SELECT id, from_type, to_type, context_pattern, entity_pattern, context_window, description, enabled, created_at FROM reclassification_rules ORDER BY from_type, created_at",
    "detection-layers": None,  # built from settings by detection_layers_query()
    "pii-types": "SELECT code, category, display_name, default_action, faker_strategy, reversible, enabled, description FROM pii_type_registry ORDER BY category, code",
    "domain-policies": "SELECT domain, display_name, default_mode, version, protect_types, keep_types, surrogate_types, remove_types, block_types, confidence_thresholds, allowlist, visible_to_clients, description, enabled, updated_at FROM domain_policies WHERE tenant_id IS NULL ORDER BY domain",
    "context-types": "SELECT code, display_name, domain, default_mode, detection_layers, description, visible_to_clients, enabled, version, created_at FROM context_types WHERE tenant_id IS NULL ORDER BY code",
}


def ensure_collection(collection: str) -> None:
    if collection not in COLLECTIONS:
        raise HTTPException(status_code=404, detail="unknown_collection")


def detection_layers_query() -> str:
    """Why: the scoped-config view of the layers must match what the engine actually loads and gates.
    What: SELECT over VALUES rows (code, display_name, description, enabled, protection_levels) from LAYER_META + settings.
    Test: "rizzo" and "'maximum'" appear in detection_layers_query() with default settings.
    """
    from app.config import settings
    from app.detection.layer_config import LAYER_META

    def q(v: str) -> str:
        return "'" + v.replace("'", "''") + "'"
    rows = ",".join(
        f"({q(code)}, {q(name)}, {q(desc)}, {'true' if settings.layer_enabled(code) else 'false'}, "
        f"ARRAY[{','.join(q(lv) for lv in settings.layer_levels(code))}]::text[])"
        for code, (name, desc) in LAYER_META.items())
    return f"SELECT * FROM (VALUES {rows}) AS detection_layers(code, display_name, description, enabled, protection_levels)"


def item_key(collection: str, row: dict[str, Any]) -> str:
    if collection == "regex-patterns":
        return str(row.get("id") or stable_hash(row, ("pii_type", "pattern")))
    if collection == "denylist":
        return str(row.get("id") or stable_hash(row, ("pii_type", "match_type", "value")))
    if collection == "context-words":
        return str(row.get("id") or stable_hash(row, ("entity_type", "word")))
    if collection == "reclassification":
        return str(row.get("id") or stable_hash(row, ("from_type", "to_type", "context_pattern", "entity_pattern")))
    if collection == "detection-layers":
        return str(row.get("code"))
    if collection == "pii-types":
        return str(row.get("code"))
    if collection == "domain-policies":
        return str(row.get("domain"))
    if collection == "context-types":
        return str(row.get("code"))

    return hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()


def normalize(row: dict[str, Any]) -> dict[str, Any]:
    output = dict(row)
    for key, value in list(output.items()):
        if isinstance(value, uuid.UUID):
            output[key] = str(value)
            continue
        if isinstance(value, datetime):
            output[key] = value.isoformat()
            continue
        if isinstance(value, str) and (key.endswith("_types") or key == "visible_to_clients"):
            output[key] = parse_list(value)
    return output


def parse_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def stable_hash(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    raw = "|".join(str(row.get(key) or "") for key in keys)
    return hashlib.sha256(raw.encode()).hexdigest()

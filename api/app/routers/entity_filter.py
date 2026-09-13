from __future__ import annotations


def filter_detected_entities(
    entities: list,
    keep_types: set[str] | None = None,
    protect_types: set[str] | None = None,
    always_include_types: set[str] | None = None,
    remove_types: set[str] | None = None,
    confidence_thresholds: dict[str, float] | None = None,
    allowlist: dict[str, list[str]] | None = None,
) -> list:
    keep = keep_types or set()
    include_always = (always_include_types or set()) | (remove_types or set())
    filtered = []
    for entity in entities:
        threshold = (confidence_thresholds or {}).get(entity.pii_type)
        if threshold is not None and entity.score < float(threshold):
            continue
        allowed = (allowlist or {}).get(entity.pii_type, [])
        if any(entity.text.casefold().strip() == str(value).casefold().strip() for value in allowed):
            continue
        if entity.pii_type in keep:
            continue
        if (
            protect_types is not None
            and entity.pii_type not in protect_types
            and entity.pii_type not in include_always
        ):
            continue
        filtered.append(entity)
    return filtered

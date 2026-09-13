from __future__ import annotations

from app.detection.entities import MappingEntry


def apply_replacements(
    text: str,
    entities: list,
    mode: str,
    replacement_map: dict[str, str] | None,
    remove_types: set[str] | None = None,
) -> tuple[str, list[MappingEntry]]:
    from app.detection.token_generator import TokenGenerator

    generator = TokenGenerator()
    remove = remove_types or set()
    stable_map: dict[str, str] = {}
    for entity in entities:
        key = entity.text.lower().strip()
        if key in stable_map:
            continue
        if entity.pii_type in remove:
            stable_map[key] = ""
        elif replacement_map and key in replacement_map:
            stable_map[key] = replacement_map[key]
        else:
            stable_map[key] = generator.next_token(entity.pii_type)

    mappings: list[MappingEntry] = []
    result = text
    for entity in reversed(entities):
        key = entity.text.lower().strip()
        token = stable_map[key]
        result = result[:entity.start] + token + result[entity.end:]
        mappings.append(MappingEntry(
            token=token, original=entity.text, pii_type=entity.pii_type,
            start=entity.start, end=entity.end, score=entity.score,
        ))
    return result, mappings

from dataclasses import replace

from app.detection.entities import PiiEntity

_MAX_MERGE_GAP = 5


class EntityMerger:
    @staticmethod
    def _replace_clipped(deduped: list[PiiEntity], winner: PiiEntity, text: str) -> None:
        """Why: dropping a loser that starts before the winner leaks its leading part
        ("Mario Rossi, C.F. RSSM..." losing to a regex FISCAL_CODE left "Mario Rossi" in clear).
        What: replaces deduped[-1] with winner, keeping the loser's part before winner.start (trimmed).
        Test: PERSON 0-30 vs regex FISCAL_CODE 18-30 -> [PERSON 0-11, FISCAL_CODE 18-30].
        """
        loser = deduped[-1]
        head = text[loser.start:winner.start].rstrip(" \t,;:.-") if text else ""
        if head.strip():
            deduped[-1] = replace(loser, end=loser.start + len(head), text=head)
            deduped.append(winner)
        else:
            deduped[-1] = winner

    def merge(self, entities: list[PiiEntity], text: str = "") -> list[PiiEntity]:
        if not entities:
            return []
        sorted_entities = sorted(entities, key=lambda e: (e.start, -e.score))

        # Pass 1: resolve overlaps
        # If one entity fully contains the other, prefer the wider span.
        # Otherwise keep the higher-score entity.
        deduped: list[PiiEntity] = []
        for entity in sorted_entities:
            if not deduped:
                deduped.append(entity)
                continue
            last = deduped[-1]
            if entity.start < last.end:
                same_span = entity.start == last.start and entity.end == last.end
                last_contains_entity = last.start <= entity.start and entity.end <= last.end
                entity_contains_last = entity.start <= last.start and last.end <= entity.end

                # Regex (deterministic) always beats ML layers on any overlap
                if entity.source == "regex" and last.source != "regex":
                    self._replace_clipped(deduped, entity, text)
                elif last.source == "regex" and entity.source != "regex":
                    pass  # keep last (regex/deterministic)
                elif same_span:
                    if entity.score > last.score:
                        deduped[-1] = entity
                elif entity_contains_last:
                    deduped[-1] = entity  # wider span wins
                elif not last_contains_entity and entity.score > last.score:
                    self._replace_clipped(deduped, entity, text)  # partial overlap: higher score wins
                continue
            deduped.append(entity)

        # Pass 2: merge adjacent same-type entities separated by whitespace/punctuation (no newlines)
        merged: list[PiiEntity] = []
        for entity in deduped:
            if not merged:
                merged.append(entity)
                continue
            last = merged[-1]
            gap = entity.start - last.end
            gap_text = text[last.end:entity.start] if text else ""
            if last.pii_type == entity.pii_type and 0 < gap <= _MAX_MERGE_GAP and "\n" not in gap_text:
                merged[-1] = PiiEntity(
                    start=last.start,
                    end=entity.end,
                    pii_type=last.pii_type,
                    text=text[last.start:entity.end] if text else f"{last.text} {entity.text}",
                    score=max(last.score, entity.score),
                )
                continue
            merged.append(entity)
        return merged

from app.detection.entities import MappingEntry


class PiiDeanonymizer:
    def deanonymize(self, text: str, mappings: list[MappingEntry]) -> str:
        token_map = {m.token: m.original for m in mappings}
        result = text
        for token, original in token_map.items():
            result = result.replace(token, original)
        return result

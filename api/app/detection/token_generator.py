class TokenGenerator:
    def __init__(self):
        self._counters: dict[str, int] = {}

    def generate(self, pii_type: str, counter: int) -> str:
        return f"[{pii_type}_{counter}]"

    def next_token(self, pii_type: str) -> str:
        self._counters[pii_type] = self._counters.get(pii_type, 0) + 1
        return self.generate(pii_type, self._counters[pii_type])

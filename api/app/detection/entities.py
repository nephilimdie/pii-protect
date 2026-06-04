from dataclasses import dataclass


@dataclass(frozen=True)
class PiiEntity:
    start: int
    end: int
    pii_type: str
    text: str
    score: float


@dataclass
class MappingEntry:
    token: str
    original: str
    pii_type: str
    start: int = 0
    end: int = 0
    score: float = 1.0


@dataclass
class AnonymizationResult:
    anonymized_text: str
    mappings: list

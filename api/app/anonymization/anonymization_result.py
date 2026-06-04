from dataclasses import dataclass


@dataclass
class AnonymizationResult:
    anonymized_text: str
    mappings: list

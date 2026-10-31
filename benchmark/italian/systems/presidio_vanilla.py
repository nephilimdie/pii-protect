"""Vanilla Microsoft Presidio (default recognizers) with the Italian spaCy model.

Why: baseline for "what a local tool gets from Presidio out of the box" in Italian.
What: AnalyzerEngine with spaCy it_core_news_lg, supported_languages=["it"], default
predefined recognizers and default score threshold; every returned span counts as masked
(the default presidio-anonymizer operator replaces all analyzer results).
Test: run inside the engine image (has presidio + it_core_news_lg):
  python presidio_vanilla.py /bench/dataset/it_pii_v1.jsonl /out/presidio_vanilla.json
"""
import sys

from importlib.metadata import version
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

from common import load_docs, run_system

nlp = NlpEngineProvider(nlp_configuration={
    "nlp_engine_name": "spacy", "models": [{"lang_code": "it", "model_name": "it_core_news_lg"}]}).create_engine()
analyzer = AnalyzerEngine(nlp_engine=nlp, supported_languages=["it"])
recognizers = sorted({r.name for r in analyzer.get_recognizers(language="it")})


def detect(text):
    return [(r.entity_type, r.start, r.end) for r in analyzer.analyze(text=text, language="it")]


run_system(load_docs(sys.argv[1], int(sys.argv[3]) if len(sys.argv) > 3 else 0), detect, sys.argv[2],
           "presidio_vanilla_it", "presidio",
           {"label": "Microsoft Presidio (vanilla, it_core_news_lg)", "presidio_analyzer": version("presidio_analyzer"),
            "spacy_model": "it_core_news_lg 3.7.0", "recognizers_it": recognizers})

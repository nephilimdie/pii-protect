"""Rizzo-PII (MIT, Italian mmBERT model + checksum regex) through its own analyze().

Why: the only open-source, locally runnable, Italian-specific anonymizer we found with code
and weights under a license that allows testing (MIT).
What: imports the upstream app module unchanged (PII_MODEL_DIR = pinned weights), calls
app.analyze(text, excluded) and rebuilds offsets from its segments. Two configs:
  default  -> the app's default excluded tags (AGE, GENDER)
  pii_only -> also excludes AMOUNT and ORG via the app's own documented setting
Test: run in the engine image with /rizzo (repo checkout) and the weights mounted:
  python rizzo_pii.py /bench/dataset/it_pii_v1.jsonl /out default
"""
import os
import sys

sys.path.insert(0, "/rizzo/src/app")
import app as rizzo  # noqa: E402  (loads the model at import, as the upstream app does)

from common import load_docs, run_system  # noqa: E402

CONFIGS = {"default": ["AGE", "GENDER"], "pii_only": ["AGE", "GENDER", "AMOUNT", "ORG"]}


def detector(excluded):
    def detect(text):
        res = rizzo.analyze(text, excluded=excluded, mapping_enabled=True)
        spans, pos = [], 0
        for seg in res["segments"]:
            n = len(seg["t"])
            if "label" in seg:
                spans.append((seg["label"], pos, pos + n))
            pos += n
        assert pos == len(text), "segments do not cover the text"
        return spans
    return detect


docs = load_docs(sys.argv[1], int(sys.argv[4]) if len(sys.argv) > 4 else 0)
for name in sys.argv[3].split(","):
    run_system(docs, detector(CONFIGS[name]), f"{sys.argv[2]}/rizzo_{name}.json", f"rizzo_{name}", "rizzo",
               {"label": f"Rizzo-PII 0.3B v1.5.0 ({name})", "excluded_tags": CONFIGS[name],
                "code_commit": os.environ.get("RIZZO_COMMIT", "?"), "model_revision": os.environ.get("RIZZO_REV", "?")})

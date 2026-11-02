"""Append-style document builder and PDF-text-layer noise for it_pii_heldout_v2.

Why: v1 rendered inline markup; v2 uses a different authoring approach so that both corpora do
not share a renderer's quirks. Text is appended piece by piece and every PII / look-alike span
is recorded at append time, after noise, so gold offsets are exact by construction.
What: Doc.t(text) literal, Doc.p(type, value, hard) PII, Doc.n(type, value) negative look-alike,
Doc.i(why, value) not scored; Doc.finish() -> gold record (schema of benchmark/italian).
The noise model imitates text extracted from PDFs (ligatures, NBSP, soft hyphens, curly
apostrophes, justified double spaces, court line numbers, page furniture, O/0 I/1 in codes),
unlike v1's scanner model (hyphenated breaks, B/8 confusions, accent splitting).
Test: tests/test_v2.py rebuilds the corpus and checks every span against the text.
"""
from __future__ import annotations

import random

PII_TYPES = ["PERSON", "FISCAL_CODE", "VAT_NUMBER", "IBAN", "CREDIT_CARD", "PHONE", "EMAIL", "ADDRESS",
             "DATE_OF_BIRTH", "BIRTH_PLACE", "ID_DOCUMENT", "SOCIAL_SECURITY", "EMPLOYEE_ID", "LICENSE_PLATE",
             "CADASTRAL_REF", "CASE_ID", "CONTRACT_ID", "IP_ADDRESS", "USERNAME", "INDIRECT"]
NEG_TYPES = ["LAW_REF", "MONEY", "DOC_DATE", "DOC_NUMBER", "ORG", "PUBLIC_BODY", "COMMON_WORD", "CODE"]
_CODES = {"FISCAL_CODE", "LICENSE_PLATE", "ID_DOCUMENT", "IBAN"}


class Doc:
    """Why: one object per document keeps text, spans and noise state together.
    What: append API + finish(); case='upper'/'lower' recases every piece (form typed in caps, dictation).
    Test: d=Doc(rng); d.t('a '); d.p('PERSON','Ezio'); d.finish(...)['entities'][0] == {'type':'PERSON','start':2,'end':6}."""

    def __init__(self, r: random.Random, noisy: bool = False, case: str | None = None, line_numbers: bool = False):
        self.r, self.noisy, self.case, self.line_numbers = r, noisy, case, line_numbers
        self.parts: list[str] = []
        self.off = 0
        self.ents: list[dict] = []
        self.negs: list[dict] = []
        self.ign: list[dict] = []
        self.tags: set[str] = set()
        self.line = 1

    # ---------------------------------------------------------------- noise
    def _noise(self, s: str, kind: str, typ: str = "") -> tuple[str, set[str]]:
        hard: set[str] = set()
        if self.case == "upper":
            s = s.upper()
        elif self.case == "lower":
            s = s.lower()
        if not self.noisy:
            return s, hard
        r = self.r
        out = s
        if "'" in out and r.random() < .6:
            out = out.replace("'", "’")
        for a, b in (("ffi", "ﬃ"), ("fi", "ﬁ"), ("fl", "ﬂ"), ("ff", "ﬀ")):
            if a in out and r.random() < .5:
                out = out.replace(a, b)
        if " " in out.strip() and r.random() < .25:
            chars = list(out)
            for i, ch in enumerate(chars):
                if ch == " " and 0 < i < len(chars) - 1 and r.random() < .35:
                    chars[i] = "\u00a0" if kind != "lit" or r.random() < .5 else "  "
            out = "".join(chars)
        if kind == "lit" and r.random() < .15:
            words = out.split(" ")
            for k, w in enumerate(words):
                if len(w) > 9 and w.isalpha() and r.random() < .3:
                    cut = r.randint(3, len(w) - 3)
                    words[k] = w[:cut] + "\u00ad" + w[cut:]
            out = " ".join(words)
        if kind == "pii" and typ in _CODES and r.random() < .25:
            swapped = "".join({"O": "0", "0": "O", "I": "1", "1": "I"}.get(c, c) if r.random() < .15 else c for c in out)
            if swapped != out:
                out, hard = swapped, {"noisy"}
        if out != s and kind == "pii":
            hard.add("noisy")
        return out, hard

    def _lines(self, s: str) -> str:
        if not self.line_numbers or "\n" not in s:
            return s
        pieces = s.split("\n")
        for k in range(1, len(pieces)):
            self.line += 1
            pieces[k] = f"{self.line:>3}  " + pieces[k]
        return "\n".join(pieces)

    # ---------------------------------------------------------------- append API
    def _put(self, kind: str, typ: str, val: str, hard=()) -> "Doc":
        assert val and val == val.strip(), (typ, val)
        val, extra = self._noise(val, kind, typ)
        if kind == "lit":
            val = self._lines(val)
        else:
            assert "\n" not in val, (typ, val)
            span = {"type": typ, "start": self.off, "end": self.off + len(val)}
            h = set(hard) | extra | ({"uppercase"} if self.case == "upper" and kind == "pii" else set()) | \
                ({"lowercase"} if self.case == "lower" and kind == "pii" else set())
            if kind == "pii":
                if h:
                    span["hard"] = sorted(h)
                    self.tags |= h
                self.ents.append(span)
            else:
                (self.negs if kind == "neg" else self.ign).append(span)
        self.parts.append(val)
        self.off += len(val)
        return self

    def t(self, s: str) -> "Doc":
        if not s:
            return self
        lead = len(s) - len(s.lstrip())
        trail = len(s) - len(s.rstrip())
        core = s.strip()
        if not core:
            self._raw(s)
            return self
        if lead:
            self._raw(s[:lead])
        if core:
            self._put("lit", "", core)
        if trail:
            self._raw(s[len(s) - trail:])
        return self

    def _raw(self, ws: str) -> None:
        ws = self._lines(ws)
        if self.noisy and ws == "\n" and self.r.random() < .04:
            ws = f"\nPag. {self.r.randint(1, 4)} di {self.r.randint(4, 6)}\n"
        self.parts.append(ws)
        self.off += len(ws)

    def p(self, typ: str, val: str, hard=()) -> "Doc":
        assert typ in PII_TYPES, typ
        return self._put("pii", typ, val, hard)

    def n(self, typ: str, val: str) -> "Doc":
        assert typ in NEG_TYPES, typ
        return self._put("neg", typ, val)

    def i(self, why: str, val: str) -> "Doc":
        return self._put("ign", why, val)

    def pick(self, *opts: str) -> str:
        return self.r.choice(opts)

    def finish(self, doc_id: str, genre: str, sub: str) -> dict:
        text = "".join(self.parts)
        for s in self.ents + self.negs + self.ign:
            v = text[s["start"]:s["end"]]
            assert v and v == v.strip(), (doc_id, s, v)
        tags = set(self.tags) | ({"pdf_noise"} if self.noisy else set()) | ({f"all_{self.case}"} if self.case else set())
        return {"id": doc_id, "genre": genre, "subgenre": sub, "language": "it", "text": text, "entities": self.ents,
                "negatives": self.negs, "ignore": self.ign, "tags": sorted(tags)}

"""Gold-span document builder and slot helpers for the Italian PII benchmark.

Why: offsets are only trustworthy if recorded while the text is assembled.
What: Doc builder (PII / negative / ignore spans) plus reusable slot fillers (names,
addresses, CF, dates, money...) that inject the hard-case surface variants.
Test: tests/test_italian_bench.py asserts text[start:end] == value for every span.
"""
from __future__ import annotations

import random

import itdata as D

# Gold PII types (what must be masked) and negative look-alikes (what must stay).
PII_TYPES = ["PERSON", "FISCAL_CODE", "VAT_NUMBER", "IBAN", "CREDIT_CARD", "PHONE", "EMAIL", "ADDRESS",
             "DATE_OF_BIRTH", "BIRTH_PLACE", "ID_DOCUMENT", "SOCIAL_SECURITY", "EMPLOYEE_ID",
             "LICENSE_PLATE", "CADASTRAL_REF", "CASE_ID", "CONTRACT_ID", "IP_ADDRESS", "USERNAME", "INDIRECT"]
NEG_TYPES = ["LAW_REF", "MONEY", "DOC_DATE", "DOC_NUMBER", "ORG", "PUBLIC_BODY", "COMMON_WORD", "CODE"]
_OCR_SWAP = {"0": "O", "O": "0", "1": "l", "l": "1", "5": "S", "S": "5", "e": "c", "m": "rn", "i": "í", "a": "à"}


class Doc:
    """Why: offsets are only trustworthy if recorded while the string is built.
    What: append-only builder; t() literal text (optionally OCR-noised), e()/n()/i() spans.
    Test: every entity satisfies text[start:end] == value (asserted in build()).
    """

    def __init__(self, rng: random.Random, genre: str, sub: str, ocr: bool = False) -> None:
        self.rng, self.genre, self.sub, self.ocr = rng, genre, sub, ocr
        self.parts: list[str] = []
        self.pos = 0
        self.ents: list[dict] = []
        self.negs: list[dict] = []
        self.ign: list[dict] = []
        self.tags: set[str] = {"ocr"} if ocr else set()

    def t(self, s: str) -> "Doc":
        if self.ocr:
            s = "".join(_OCR_SWAP.get(c, c) if c.isalnum() and self.rng.random() < .015 else c for c in s)
            s = s.replace(" ", "  ", 1) if self.rng.random() < .2 else s
        self.parts.append(s)
        self.pos += len(s)
        return self

    def _span(self, bucket: list, typ: str, val: str, hard: tuple[str, ...] = ()) -> "Doc":
        if self.ocr and bucket is self.ents and len(val) > 6 and self.rng.random() < .25:
            k = self.rng.randrange(1, len(val) - 1)
            ch = val[k]
            val = val[:k] + (_OCR_SWAP.get(ch, ch) if ch != " " else "\n") + val[k + 1:]
            hard = (*hard, "ocr_value")
        span = {"type": typ, "start": self.pos, "end": self.pos + len(val), "value": val}
        if hard:
            span["hard"] = sorted(set(hard))
        bucket.append(span)
        self.parts.append(val)
        self.pos += len(val)
        return self

    def e(self, typ: str, val: str, *hard: str) -> "Doc":
        assert typ in PII_TYPES, typ
        return self._span(self.ents, typ, val, hard)

    def n(self, typ: str, val: str) -> "Doc":
        assert typ in NEG_TYPES, typ
        return self._span(self.negs, typ, val)

    def i(self, val: str, why: str) -> "Doc":
        return self._span(self.ign, why, val)

    def build(self, doc_id: str) -> dict:
        text = "".join(self.parts)
        for s in self.ents + self.negs + self.ign:
            assert text[s["start"]:s["end"]] == s["value"], (doc_id, s)
            del s["value"]  # gold stores offsets only; value is recoverable from text
        hard = {h for s in self.ents for h in s.get("hard", [])}
        return {"id": doc_id, "genre": self.genre, "subgenre": self.sub, "language": "it", "text": text,
                "entities": self.ents, "negatives": self.negs, "ignore": self.ign,
                "tags": sorted(self.tags | hard)}


# ---------------------------------------------------------------- slot helpers
def name(d: Doc, p: D.Person, styles: str = "full") -> Doc:
    """Surface forms: 'Mario Rossi', 'ROSSI Mario', 'Rossi Mario', 'M. Rossi', lowercase."""
    r = d.rng.random()
    hard = ["foreign"] if p.foreign else []
    if p.first in D.AMBIGUOUS_FIRST_M + D.AMBIGUOUS_FIRST_F or p.last in D.AMBIGUOUS_SURNAMES:
        hard.append("ambiguous_word")
    if styles == "chat" and r < .45:
        return d.e("PERSON", (p.full if r < .25 else p.first).lower(), "lowercase", *hard)
    if r < .55:
        return d.e("PERSON", p.full, *hard)
    if r < .70:
        return d.e("PERSON", f"{p.last.upper()} {p.first}", "uppercase_surname", *hard)
    if r < .82:
        return d.e("PERSON", f"{p.last} {p.first}", "surname_first", *hard)
    if r < .92:
        return d.e("PERSON", f"{p.first[0]}. {p.last}", "initial", *hard)
    return d.e("PERSON", p.full.lower(), "lowercase", *hard)


def title(d: Doc, p: D.Person) -> Doc:
    return d.t(d.rng.choice(["il sig. " if p.gender == "M" else "la sig.ra ", "", "", "il Sig. " if p.gender == "M"
                             else "la Sig.ra ", "Dott. " if p.gender == "M" else "Dott.ssa "]))


def dob(d: Doc, p: D.Person) -> Doc:
    y, m, dd = p.birth
    v = d.rng.choice([f"{dd:02d}/{m:02d}/{y}", f"{dd} {D.MONTHS[m - 1]} {y}", f"{dd:02d}.{m:02d}.{y}",
                      f"{dd:02d}-{m:02d}-{y}", f"{y}-{m:02d}-{dd:02d}", f"{dd}/{m}/{str(y)[2:]}"])
    return d.e("DATE_OF_BIRTH", v)


def born(d: Doc, p: D.Person) -> Doc:
    d.t(d.rng.choice(["nato a " if p.gender == "M" else "nata a ", "n. a ", "nat" + ("o" if p.gender == "M" else "a") + " in "]))
    d.e("BIRTH_PLACE", p.birth_city, *(["foreign"] if p.foreign else []))
    d.t(d.rng.choice([" il ", " in data ", " il giorno ", " il "]))
    return dob(d, p)


def address(d: Doc, p: D.Person) -> Doc:
    city, prov, cap, _ = p.city
    kind, street = p.street.split(" ", 1)
    k = next(x for x in D.STREET_KINDS if x[0] == kind)
    num = d.rng.choice([str(d.rng.randint(1, 180)), f"{d.rng.randint(1, 90)}/{d.rng.choice('ABC')}",
                        f"n. {d.rng.randint(1, 120)}", f"{d.rng.randint(1, 60)} int. {d.rng.randint(1, 12)}"])
    r = d.rng.random()
    if r < .35:
        v, hard = f"{kind} {street} {num}, {cap} {city} ({prov})", ()
    elif r < .55:
        v, hard = f"{k[2]} {street}, {num} - {cap} {city}", ("abbreviated",)
    elif r < .70:
        v, hard = f"{kind} {street} {num}", ()
    elif r < .80:
        v, hard = f"{k[1]} {street.lower()} {num} {city.lower()}", ("lowercase",)
    elif r < .90:
        v, hard = f"{kind.upper()} {street.upper()} {num} - {cap} {city.upper()} {prov}", ("uppercase",)
    else:
        v, hard = f"{d.rng.choice(['Loc.', 'Contrada', 'Fraz.'])} {d.rng.choice(['Case Sparse', 'San Vito', 'Pian di Rose', 'Molino'])} {d.rng.randint(1, 40)}, {cap} {city}", ("rural",)
    return d.e("ADDRESS", v, *hard)


def cf(d: Doc, p: D.Person) -> Doc:
    v = p.cf if d.rng.random() < .85 else (p.cf.lower() if d.rng.random() < .5 else " ".join([p.cf[:6], p.cf[6:11], p.cf[11:]]))
    hard = ["omocodia"] if any(c.isalpha() for c in p.cf[6:8] + p.cf[9:11] + p.cf[12:15]) else []
    hard += ["lowercase"] if v.islower() else ["spaced"] if " " in v else []
    return d.e("FISCAL_CODE", v, *hard)


def iban(d: Doc) -> Doc:
    v = D.iban_it(d.rng)
    return d.e("IBAN", D.group(v), "spaced") if d.rng.random() < .4 else d.e("IBAN", v)


def money(d: Doc) -> Doc:
    v = d.rng.randint(15, 250000) + d.rng.randint(0, 99) / 100
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return d.n("MONEY", d.rng.choice([f"€ {s}", f"{s} euro", f"EUR {s}", f"{s} €"]))


def docdate(d: Doc) -> Doc:
    y, m, dd = d.rng.randint(2019, 2026), d.rng.randint(1, 12), d.rng.randint(1, 28)
    return d.n("DOC_DATE", d.rng.choice([f"{dd:02d}/{m:02d}/{y}", f"{dd} {D.MONTHS[m - 1]} {y}", f"{dd:02d}.{m:02d}.{y}"]))


def law(d: Doc) -> Doc:
    return d.n("LAW_REF", d.rng.choice(D.LAW_REFS))


def rg(d: Doc) -> Doc:
    return d.e("CASE_ID", f"{d.rng.randint(100, 25000)}/{d.rng.randint(2018, 2026)}")


def digits(d: Doc, k: int) -> str:
    return "".join(str(d.rng.randint(0, 9)) for _ in range(k))


def phone(d: Doc, p: D.Person) -> Doc:
    return d.e("PHONE", p.phone)


def email(d: Doc, p: D.Person, pec: bool = False) -> Doc:
    if pec:
        return d.e("EMAIL", p.email.split("@")[0] + "@" + d.rng.choice(D.PEC_DOMAINS), "pec")
    return d.e("EMAIL", p.email)


def company(d: Doc) -> Doc:
    return d.n("ORG", d.rng.choice(D.COMPANIES))


def body(d: Doc) -> Doc:
    return d.n("PUBLIC_BODY", d.rng.choice(D.PUBLIC_BODIES))


def P(d: Doc, **kw) -> D.Person:
    return D.person(d.rng, ambiguous=kw.get("amb", d.rng.random() < .15), foreign=kw.get("foreign", d.rng.random() < .12))



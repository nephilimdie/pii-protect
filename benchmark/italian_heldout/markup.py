"""Inline-markup document builder and OCR-like noise for the held-out corpus.

Why: hand-authored templates read like real documents only if the PII sits inside ordinary
f-strings; offsets are then derived once, after noise, so they cannot drift.
What: Ctx gives templates span markers (pii/neg/ign) and surface-form helpers; render() parses
the markers, applies optional case folding and a scanner-noise model that is deliberately
different from it_pii_v1's (hyphenated line breaks, hard wraps, B/8 G/6 Z/2 confusions, ri->n,
stray punctuation, accent splitting, page furniture), and returns one gold document.
Test: tests/test_heldout.py asserts text[start:end] == recorded value for every span.
"""
from __future__ import annotations

import random
import re

import fakedata as F

PII_TYPES = ["PERSON", "FISCAL_CODE", "VAT_NUMBER", "IBAN", "CREDIT_CARD", "PHONE", "EMAIL", "ADDRESS",
             "DATE_OF_BIRTH", "BIRTH_PLACE", "ID_DOCUMENT", "SOCIAL_SECURITY", "EMPLOYEE_ID",
             "LICENSE_PLATE", "CADASTRAL_REF", "CASE_ID", "CONTRACT_ID", "IP_ADDRESS", "USERNAME", "INDIRECT"]
NEG_TYPES = ["LAW_REF", "MONEY", "DOC_DATE", "DOC_NUMBER", "ORG", "PUBLIC_BODY", "COMMON_WORD", "CODE"]
_MARK = re.compile(r"([\x02\x04\x05])([^\x1f]*)\x1f([^\x1f\x03]*)\x1f([^\x03]*)\x03")
_KIND = {"\x02": "pii", "\x04": "neg", "\x05": "ign"}
_CONFUSE = {"B": "8", "G": "6", "Z": "2", "S": "$", "I": "|", "l": "I", "e": "é", "u": "v", "h": "b"}
_PARTICLES = ("De ", "Di ", "Del ", "Della ", "Dal ", "Lo ", "La ", "Li ", "D'", "Dell'")

LAWS = ["art. 1571 c.c.", "D.Lgs. 81/2008", "art. 2 della L. 392/1978", "Reg. (UE) 2016/679", "art. 700 c.p.c.",
        "D.P.R. 917/1986", "art. 13 GDPR", "L. 104/1992", "art. 186 C.d.S.", "D.M. 37/2008", "art. 36 Cost.",
        "art. 2087 c.c.", "art. 633 c.p.c.", "D.Lgs. 23/2015", "art. 7 L. 300/1970", "art. 1117 c.c.",
        "art. 590 c.p.", "D.L. 34/2020", "art. 2697 c.c.", "art. 4 D.Lgs. 28/2010"]
ORGS = ["Enel Energia S.p.A.", "Intesa Sanpaolo", "Poste Italiane", "Fastweb S.p.A.", "UnipolSai Assicurazioni",
        "Esselunga", "Trenitalia", "Generali Italia S.p.A.", "Iliad Italia", "Banca Sella", "Conad", "Leroy Merlin",
        "Hera Comm", "Amazon Italia Logistica S.r.l.", "Coop Alleanza 3.0", "Edison Energia", "BPER Banca",
        "Vodafone Italia", "Autostrade per l'Italia", "Acea Ato 2"]
BODIES = ["Agenzia delle Entrate", "INPS", "INAIL", "Tribunale di Verona", "Comune di Fano", "ASL Roma 2",
          "Giudice di Pace di Lecce", "Corte d'Appello di Bari", "Prefettura di Cagliari", "Questura di Trento",
          "TAR Lazio", "Ispettorato Territoriale del Lavoro di Bergamo", "Tribunale di Napoli Nord",
          "Agenzia delle Entrate - Riscossione", "Comune di Bassano del Grappa", "Camera di Commercio di Torino"]


def _m(kind: str, typ: str, val: str, hard: tuple[str, ...] = ()) -> str:
    assert val and val == val.strip() and not any(c in val for c in "\x02\x03\x04\x05\x1f"), (typ, val)
    return f"{kind}{typ}\x1f{val}\x1f{','.join(hard)}\x03"


class Ctx:
    """Why: one place for the surface-form distribution, so templates stay prose.
    What: span markers + helpers returning marked strings; ocr/case are applied in render().
    Test: render(Ctx(rng), c.pii('PERSON','Ada Neri')) has one PERSON span covering 'Ada Neri'."""

    def __init__(self, rng: random.Random, ocr: bool = False, case: str | None = None) -> None:
        self.rng, self.ocr, self.case = rng, ocr, case

    # markers
    def pii(self, typ: str, val: str, *hard: str) -> str:
        assert typ in PII_TYPES, typ
        return _m("\x02", typ, val, hard)

    def neg(self, typ: str, val: str) -> str:
        assert typ in NEG_TYPES, typ
        return _m("\x04", typ, val)

    def ign(self, why: str, val: str) -> str:
        return _m("\x05", why, val)

    def pick(self, *opts: str) -> str:
        return self.rng.choice(opts)

    def chance(self, p: float) -> bool:
        return self.rng.random() < p

    # people
    def person(self, **kw) -> F.Persona:
        return F.persona(self.rng, **kw)

    def name(self, p: F.Persona, style: str | None = None) -> str:
        """Surface forms with their own mix; style forces one (full/caps/surname_first/initial/first/surname/nick/lower)."""
        r = self.rng.random()
        style = style or ("full" if r < .42 else "surname_first" if r < .55 else "caps" if r < .65 else
                          "initial" if r < .73 else "caps_surname" if r < .83 else "lower" if r < .88 else "full")
        tags = [t for t, ok in (("foreign", p.foreign), ("ambiguous_word", p.ambiguous),
                                ("double_surname", " " in p.last and not p.last.startswith(_PARTICLES)),
                                ("particle", p.last.startswith(_PARTICLES))) if ok]
        val = {"full": p.full, "surname_first": f"{p.last} {p.first}", "caps": p.full.upper(),
               "initial": f"{p.first[0]}. {p.last}", "caps_surname": f"{p.last.upper()} {p.first}",
               "lower": p.full.lower(), "first": p.first, "surname": p.last,
               "nick": p.nickname or p.first.split()[0]}[style]
        tags += {"caps": ["uppercase"], "caps_surname": ["uppercase_surname"], "initial": ["initial"], "lower": ["lowercase"],
                 "first": ["first_name_only"], "surname": ["surname_only"], "surname_first": ["surname_first"],
                 "nick": ["nickname"] if p.nickname else ["first_name_only"]}.get(style, [])
        return self.pii("PERSON", val, *tags)

    def title(self, p: F.Persona) -> str:
        return self.pick("", "", "sig.ra " if p.female else "sig. ", "Sig.ra " if p.female else "Sig. ",
                         "dott.ssa " if p.female else "dott. ", "Avv. ", "geom. ", "ing. ")

    def cf(self, p: F.Persona) -> str:
        r = self.rng.random()
        if r < .75:
            return self.pii("FISCAL_CODE", p.cf)
        if r < .87:
            return self.pii("FISCAL_CODE", p.cf.lower(), "lowercase")
        return self.pii("FISCAL_CODE", f"{p.cf[:3]} {p.cf[3:6]} {p.cf[6:11]} {p.cf[11:]}", "spaced")

    def dob(self, p: F.Persona) -> str:
        y, m, d = p.birth
        v = self.pick(f"{d:02d}/{m:02d}/{y}", f"{d}.{m}.{y}", f"{d} {F.MONTHS[m - 1]} {y}", f"{d:02d}-{F.MONTHS[m - 1][:3].upper()}-{y}",
                      f"{y}-{m:02d}-{d:02d}", f"{d:02d}/{m:02d}/{y % 100:02d}", f"{d:02d}{m:02d}{y}")
        return self.pii("DATE_OF_BIRTH", v, *(["compact"] if v.isdigit() else []))

    def bplace(self, p: F.Persona) -> str:
        return self.pii("BIRTH_PLACE", p.birth_city.upper() if self.chance(.15) else p.birth_city, *(["foreign"] if p.foreign else []))

    def birth(self, p: F.Persona) -> str:
        """Birth phrasing deliberately not 'nato a X il D' first: date-first, key/value, parenthesised..."""
        a = "a" if p.female else "o"
        return self.pick(f"nat{a} il {self.dob(p)} a {self.bplace(p)}",
                         f"luogo e data di nascita: {self.bplace(p)}, {self.dob(p)}",
                         f"n. {self.bplace(p)} {self.dob(p)}",
                         f"nascita {self.dob(p)} ({self.bplace(p)})",
                         f"nat{a} a {self.bplace(p)} il {self.dob(p)}",
                         f"originari{a} di {self.bplace(p)}, dove è nat{a} il {self.dob(p)}")

    def addr(self, p: F.Persona, style: int | None = None) -> str:
        city, prov, cap, _ = p.city
        s, n = p.street, p.number
        k = self.rng.randrange(8) if style is None else style
        v, hard = [(f"{s} n. {n}, {cap} {city} ({prov})", ()), (f"{s}, {n} - {city}", ()), (f"{s.lower()} {n} {city.lower()}", ("lowercase",)),
                   (f"{s.upper()} {n} {cap} {city.upper()} {prov}", ("uppercase",)), (f"{city}, {s} {n}", ("city_first",)),
                   (f"{s} {n}", ()), (f"{s} {n} - {cap} - {city} ({prov})", ()), (f"{cap} {city}, {s} civ. {n}", ("city_first",))][k]
        return self.pii("ADDRESS", v, *hard)

    def phone(self, p: F.Persona) -> str:
        return self.pii("PHONE", p.phone, *(["foreign"] if p.phone.startswith("+40") else []))

    def email(self, p: F.Persona, pec: bool = False) -> str:
        if pec:
            return self.pii("EMAIL", p.email.split("@")[0] + "@" + self.pick(*F.PEC_DOM), "pec")
        if self.chance(.06):
            u, dom = p.email.split("@")
            return self.pii("EMAIL", f"{u} [at] {dom.replace('.', ' [dot] ')}", "obfuscated")
        return self.pii("EMAIL", p.email.upper() if self.chance(.05) else p.email)

    def iban(self, country: str | None = None) -> str:
        country = country or ("IT" if self.chance(.8) else self.pick("DE", "FR", "ES", "RO"))
        v = F.iban(self.rng, country)
        r = self.rng.random()
        if r < .45:
            return self.pii("IBAN", F.group4(v), "spaced", *(["foreign"] if country != "IT" else []))
        return self.pii("IBAN", v.lower() if r < .5 else v, *(["foreign"] if country != "IT" else []))

    def piva(self) -> str:
        return self.pii("VAT_NUMBER", self.pick("", "", "IT") + F.partita_iva(self.rng))

    def company_vat(self) -> str:
        return self.ign("company_vat", F.partita_iva(self.rng))

    def card(self) -> str:
        v = F.card(self.rng)
        return self.pii("CREDIT_CARD", " ".join(v[i:i + 4] for i in range(0, len(v), 4)) if self.chance(.6) else v)

    # negatives
    def money(self) -> str:
        v = F.eur(self.rng)
        return self.neg("MONEY", self.pick(f"€ {v}", f"{v} euro", f"EUR {v}", f"{v}€", f"euro {v}"))

    def ddate(self, y0: int = 2021, y1: int = 2026) -> str:
        y, m, d = self.rng.randint(y0, y1), self.rng.randint(1, 12), self.rng.randint(1, 28)
        return self.neg("DOC_DATE", self.pick(f"{d:02d}/{m:02d}/{y}", f"{d} {F.MONTHS[m - 1]} {y}", f"{y}-{m:02d}-{d:02d}", f"{d}.{m}.{y}"))

    def law(self) -> str:
        return self.neg("LAW_REF", self.pick(*LAWS))

    def org(self) -> str:
        return self.neg("ORG", self.pick(*ORGS))

    def body(self) -> str:
        return self.neg("PUBLIC_BODY", self.pick(*BODIES))

    def prot(self) -> str:
        r = self.rng
        return self.neg("DOC_NUMBER", self.pick(f"{r.randint(2021, 2026)}/{F.digits(r, 7)}", f"{F.digits(r, 6)}/U",
                                                f"{r.randint(1, 999)}/FE", f"4500{F.digits(r, 6)}", f"PG/{r.randint(2022, 2026)}/{F.digits(r, 6)}"))

    def code(self, kind: str | None = None) -> str:
        r = self.rng
        kinds = {"tributo": self.pick("1001", "1040", "3918", "3797", "1712", "4001", "6099", "8918"),
                 "ateco": f"{r.choice(['69.10.10', '43.21.01', '56.10.11', '47.11.40', '62.01.00', '86.21.00'])}",
                 "cig": "Z" + "".join(r.choice("0123456789ABCDEF") for _ in range(9)),
                 "http": str(r.choice([400, 401, 403, 404, 409, 429, 500, 502, 503, 504])),
                 "sku": f"{r.randint(10, 99)}-{r.randint(1000, 9999)}-{r.choice('ABCX')}",
                 "hash": "".join(r.choice("0123456789abcdef") for _ in range(12)),
                 "ver": f"{r.randint(1, 9)}.{r.randint(0, 30)}.{r.randint(0, 99)}",
                 "cat": self.pick("A/2", "A/3", "A/4", "C/6", "C/2"),
                 "icd": self.pick("M54.5", "S83.2", "J18.9", "I10", "E11.9")}
        return self.neg("CODE", kinds[kind or r.choice(list(kinds))])


def _ocr(rng: random.Random, s: str, entity: bool) -> tuple[str, set[str]]:
    tags: set[str] = set()
    out = []
    for ch in s:
        if ch in _CONFUSE and rng.random() < (.03 if entity else .02):
            out.append(_CONFUSE[ch])
            tags.add("ocr_value")
        elif ch in "àèùò" and rng.random() < .5:
            out.append({"à": "a'", "è": "e'", "ù": "u'", "ò": "o'"}[ch])
        else:
            out.append(ch)
    s = "".join(out).replace("ri", "n", 1) if rng.random() < .08 else "".join(out)
    words = s.split(" ")
    for i, w in enumerate(words):  # hyphenated line break inside a long word
        if len(w) > 7 and w.isalpha() and rng.random() < (.12 if entity else .05):
            k = rng.randrange(3, len(w) - 3)
            words[i] = w[:k] + "-\n" + w[k:]
            tags.add("ocr_hyphen")
    s = " ".join(words)
    if not entity and rng.random() < .1:
        s = s.replace(", ", " , ", 1).replace(". ", " . ", 1)
    return s, tags


def render(c: Ctx, markup: str, doc_id: str, genre: str, sub: str, tags: tuple[str, ...] = ()) -> dict:
    """What: markup -> {id, genre, subgenre, language, text, entities, negatives, ignore, tags}."""
    segs: list[tuple[str, str, str, tuple[str, ...]]] = []
    pos = 0
    for m in _MARK.finditer(markup):
        if m.start() > pos:
            segs.append(("lit", "", markup[pos:m.start()], ()))
        segs.append((_KIND[m.group(1)], m.group(2), m.group(3), tuple(h for h in m.group(4).split(",") if h)))
        pos = m.end()
    segs.append(("lit", "", markup[pos:], ()))
    if c.ocr and segs[0][2]:
        segs.insert(0, ("lit", "", c.pick("—— Scansione ——\n", "[pag. 1/2]\n", "Documento acquisito digitalmente\n"), ()))
    text, ents, negs, ign, all_tags = [], [], [], [], set(tags) | ({"ocr"} if c.ocr else set())
    off = 0
    for kind, typ, val, hard in segs:
        if c.case == "lower":
            val = val.lower()
        elif c.case == "upper":
            val = val.upper()
        hard = set(hard)
        if c.case and kind == "pii":
            hard.add("lowercase" if c.case == "lower" else "uppercase")
        if c.ocr:
            val, extra = _ocr(c.rng, val, kind == "pii")
            hard |= extra if kind == "pii" else set()
        if kind != "lit":
            span = {"type": typ, "start": off, "end": off + len(val), "value": val}
            if hard and kind == "pii":
                span["hard"] = sorted(hard)
                all_tags |= hard
            (ents if kind == "pii" else negs if kind == "neg" else ign).append(span)
        text.append(val)
        off += len(val)
    full = "".join(text)
    if c.ocr:  # hard wrap at ~66 columns: replaces spaces with newlines, so offsets stay valid
        chars, col = list(full), 0
        for i, ch in enumerate(chars):
            col = 0 if ch == "\n" else col + 1
            if ch == " " and col > 62 and c.rng.random() < .5:
                chars[i], col = "\n", 0
        full = "".join(chars)
    for s in ents + negs + ign:
        s["value"] = full[s["start"]:s["end"]]
        assert s["value"] and not s["value"][0].isspace() and not s["value"][-1].isspace(), (doc_id, s)
        del s["value"]
    return {"id": doc_id, "genre": genre, "subgenre": sub, "language": "it", "text": full, "entities": ents,
            "negatives": negs, "ignore": ign, "tags": sorted(all_tags)}

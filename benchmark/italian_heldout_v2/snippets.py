"""Reusable phrase snippets for the v2 genres (each appends text + gold spans to a Doc).

Why: the same identity facts (name, birth, address, codes) appear in every genre with many
surface forms; one place keeps the forms varied and the span conventions identical.
What: name(), birth(), residence(), code helpers; conventions follow benchmark/italian gold
(PERSON without title, BIRTH_PLACE = town only, ADDRESS = street..town/province, codes = value only).
Test: covered through tests/test_v2.py (span integrity on the whole corpus).
"""
from __future__ import annotations

import ident as I
from builder import Doc

TITLES = ["Sig.", "Sig.ra", "Dott.", "Dott.ssa", "Avv.", "Ing.", "Geom.", "Prof.", "Rag.", "Arch."]


def name(d: Doc, p: I.Person, style: str | None = None) -> None:
    """What: appends one PERSON span in a random (or given) surface form."""
    r = d.r
    style = style or r.choice(["fl", "fl", "fl", "LF", "Lf", "lf_comma", "init", "UPPER", "last", "first"])
    hard = set(p.hard)
    if style == "fl":
        v = p.full
    elif style == "LF":
        v, hard = f"{p.last.upper()} {p.first}", hard | {"uppercase_surname"}
    elif style == "Lf":
        v = f"{p.last} {p.first}"
    elif style == "lf_comma":
        v = f"{p.last}, {p.first}"
    elif style == "init":
        v, hard = f"{p.first[0]}. {p.last}", hard | {"initial"}
    elif style == "UPPER":
        v, hard = p.full.upper(), hard | {"uppercase"}
    elif style == "last":
        v, hard = p.last, hard | {"surname_only"}
    elif style == "lower":
        v, hard = p.full.lower(), hard | {"lowercase"}
    else:
        v, hard = p.first, hard | {"first_name_only"}
    d.p("PERSON", v, hard)


def titled(d: Doc, p: I.Person, style: str | None = None) -> None:
    d.t(d.r.choice(TITLES) + " ")
    name(d, p, style)


def birth(d: Doc, p: I.Person) -> None:
    """What: birth place + date in one of many phrasings (with and without 'nato a')."""
    r = d.r
    dt, h = I.birth_date(r, p)
    nato = "nata" if p.female else "nato"
    k = r.randrange(8)
    if k == 0:
        d.t(f", {nato} a ").p("BIRTH_PLACE", p.birth_town).t(" il ").p("DATE_OF_BIRTH", dt, h)
    elif k == 1:
        d.t(f", {nato} il ").p("DATE_OF_BIRTH", dt, h).t(" a ").p("BIRTH_PLACE", p.birth_town, {"no_cue"})
    elif k == 2:
        d.t(" (").p("BIRTH_PLACE", p.birth_town, {"no_cue"}).t(", ").p("DATE_OF_BIRTH", dt, h).t(")")
    elif k == 3:
        d.t(f", {nato} in ").p("BIRTH_PLACE", p.birth_town).t(" in data ").p("DATE_OF_BIRTH", dt, h)
    elif k == 4:
        d.t(", n. a ").p("BIRTH_PLACE", p.birth_town).t(" (" + p.birth_prov + ") il ").p("DATE_OF_BIRTH", dt, h)
    elif k == 5:
        d.t(", classe ").p("DATE_OF_BIRTH", str(p.y), {"year_only"}).t(", originari" + ("a" if p.female else "o") + " di ") \
            .p("BIRTH_PLACE", p.birth_town)
    elif k == 6:
        d.t(", luogo e data di nascita: ").p("BIRTH_PLACE", p.birth_town, {"no_cue"}).t(", ").p("DATE_OF_BIRTH", dt, h)
    else:
        d.t(f", venut{'a' if p.female else 'o'} alla luce a ").p("BIRTH_PLACE", p.birth_town).t(" il ") \
            .p("DATE_OF_BIRTH", dt, h)


def address_value(d: Doc, p: I.Person, with_town: bool = True) -> str:
    town, prov, cap, _ = p.town
    if not with_town:
        return p.street
    return d.r.choice([f"{p.street}, {cap} {town} ({prov})", f"{p.street} - {cap} {town} {prov}",
                       f"{p.street}, {town}", f"{p.street}, {cap} {town}"])


def residence(d: Doc, p: I.Person) -> None:
    lead = d.pick(", residente in ", ", res. a ", ", domiciliat" + ("a" if p.female else "o") + " in ",
                  ", con residenza in ", ", abitante in ")
    d.t(lead).p("ADDRESS", address_value(d, p))


def fiscal(d: Doc, p: I.Person) -> None:
    v, h = I.cf_form(d.r, p.cf)
    d.t(d.pick(", C.F. ", ", codice fiscale ", ", c.f. ", " - CF: ", ", cod. fisc. ")).p("FISCAL_CODE", v, h)


def mail(d: Doc, p: I.Person, obf: float = .15, pec: bool = False) -> None:
    v = I.mail_for(d.r, p.first, p.last, p.y, pec) if pec else p.email
    h: set[str] = {"pec"} if pec else set()
    if d.r.random() < obf:
        v, h2 = I.obfuscate_mail(d.r, v)
        h |= h2
    d.p("EMAIL", v, h)


def ident_doc(d: Doc) -> None:
    k = d.r.randrange(3)
    if k == 0:
        d.t(d.pick("carta d'identità n. ", "C.I. n. ", "CIE ")).p("ID_DOCUMENT", I.cie(d.r))
    elif k == 1:
        d.t(d.pick("passaporto n. ", "passaporto ")).p("ID_DOCUMENT", I.passport(d.r))
    else:
        d.t(d.pick("patente n. ", "patente di guida ")).p("ID_DOCUMENT", I.licence(d.r))


def law(d: Doc) -> None:
    d.n("LAW_REF", d.pick("art. 46 del D.P.R. 445/2000", "art. 1490 c.c.", "art. 633 c.p.c.", "L. 241/1990",
                          "art. 13 del Reg. UE 2016/679", "D.Lgs. 196/2003", "art. 2119 c.c.", "art. 7 L. 300/1970",
                          "art. 186 C.d.S.", "D.M. 37/2008", "art. 76 del D.P.R. 445/2000", "art. 2043 c.c."))


def money(d: Doc, lo: int = 15, hi: int = 250000) -> None:
    d.n("MONEY", I.eur(d.r, lo, hi))


def ddate(d: Doc) -> None:
    d.n("DOC_DATE", I.doc_date(d.r))


def prot(d: Doc) -> None:
    d.n("DOC_NUMBER", d.pick(f"{d.r.randint(100, 99999)}/{d.r.randint(2020, 2026)}", f"{I.digits(d.r, 7)}",
                             f"PG/{d.r.randint(2021, 2026)}/{I.digits(d.r, 6)}", f"{d.r.randint(1, 999)}-{d.r.choice('ABCDE')}"))

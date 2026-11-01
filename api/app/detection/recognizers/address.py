"""Full Italian postal addresses and cadastral references.

Why: the ML layers stop at the house number ("Corso Gramsci 46" of "Corso Gramsci 46 int. 9,
16121 Genova (GE)"), so CAP, city and province leaked in a third of benchmark addresses; the DB
cadastral regex missed the common "F. 102, P.lla 658, sub 1" abbreviation.
What: street type + name + house number [+ interno/scala] [+ CAP city (PROV)] as one ADDRESS;
at maximum also a street without house number and a trailing lowercase city; foglio/particella
[/sub] as CADASTRAL_REF.
Test: "residente in Corso Garibaldi 78/B, 35121 Padova (PD)." -> ADDRESS covering through "(PD)";
"F. 51, P.lla 1309, sub 15" -> CADASTRAL_REF.
"""
from __future__ import annotations

import re

from app.detection.entities import PiiEntity
from app.detection.recognizers.common import CITY, MAXIMUM, entity

_STREET = (r"(?<![\w.])(?i:via|viale|v\.le|corso|c\.so|largo|l\.go|piazza|piazzale|p\.zza|p\.za|p\.le|vicolo|vico"
           r"|strada|str\.|contrada|c\.da|localit[àa]|loc\.|borgo|lungomare|lungotevere|salita|traversa|frazione|fraz\.)")
_NAME = r"[ \t]+(?:[\w'’.]+[ \t]+){0,5}?[\w'’.]+"
_HOUSE = r"(?:,[ \t]*|[ \t]+)(?i:n\.|n°|nr\.)?[ \t]*\d{1,4}(?:[ \t]?/[ \t]?[A-Za-z0-9]{1,3}|[A-Za-z](?!\w))?"
_INNER = r"(?:[ \t]*,?[ \t]*(?i:int\.|interno|scala|sc\.|piano)[ \t]*\w{1,3})*"
_CAP_CITY = rf"(?:[ \t]*[,\-–]?[ \t]*\d{{5}}[ \t]+{CITY}(?:[ \t]*\([ \t]*[A-Z]{{2}}[ \t]*\)|[ \t]+[A-Z]{{2}}(?![\w]))?)"
_ADDRESS = re.compile(rf"{_STREET}{_NAME}{_HOUSE}{_INNER}{_CAP_CITY}?")
# maximum: a lowercase city right after the house number ("via iv novembre 20/C ancona")
_LOWER_CITY = re.compile(r"[ \t]+[a-zà-ÿ]{3,}(?=[ \t]*(?:[.,;)]|$))", re.MULTILINE)
_STREET_ONLY = re.compile(rf"{_STREET}[ \t]+(?:(?i:del|della|dei|degli|di|de)[ \t]+)?[A-ZÀ-Ý][\w'’]+(?:[ \t]+[A-ZÀ-Ý][\w'’]+){{0,3}}")
_CADASTRAL = re.compile(
    r"(?<![\w.])(?i:foglio|fg\.?|f\.)[ \t]*(?:n\.[ \t]*)?\d{1,4}[ \t,;\-]*(?i:particella|part\.|p\.lla|mappale|mapp?\.)"
    r"[ \t]*(?:n\.[ \t]*)?\d{1,5}(?:[ \t,;\-]*(?i:subalterno|sub\.?)[ \t]*(?:n\.[ \t]*)?\d{1,4})?(?!\d)"
)


def detect_addresses(text: str, level: str) -> list[PiiEntity]:
    """Why: one pass for street addresses (level-aware) and cadastral references.
    What: ADDRESS spans through CAP/city/province; CADASTRAL_REF spans; maximum adds looser forms.
    Test: detect_addresses("via iv novembre 20/C ancona", "maximum")[0].text ends with "ancona".
    """
    found = [entity(text, m.start(), m.end(), "CADASTRAL_REF") for m in _CADASTRAL.finditer(text)]
    for m in _ADDRESS.finditer(text):
        end = m.end()
        if level == MAXIMUM and (tail := _LOWER_CITY.match(text, end)):
            end = tail.end()
        found.append(entity(text, m.start(), end, "ADDRESS"))
    if level == MAXIMUM:
        found += [entity(text, m.start(), m.end(), "ADDRESS") for m in _STREET_ONLY.finditer(text)
                  if not any(e.start <= m.start() < e.end for e in found)]
    return found

"""Person names right after Italian role/label cues, in any capitalisation the cue makes safe.

Why: UPPERCASE surnames ("MARCHETTI Simona"), surname-first order and form labels
("Soggetto:", "Nome:", "Coniuge a carico:", "conducente") were the bulk of PERSON leaks; ML
models drop or split them, and capitalised-word rules without a cue would mask headings.
What: after a cue, captures 1-4 name tokens (Capitalised, UPPERCASE, initials, particles,
O'Brien / Jean-Pierre forms), cut at the first stopword. Lowercase names are accepted only after
a strong cue and when followed by a delimiter or an identity cue ("nato", "C.F.", "iban=").
Test: "Soggetto: COPPOLA DANIELA nato a LECCE" -> PERSON "COPPOLA DANIELA";
"Il Contratto Standard resta valido" -> nothing.
"""
from __future__ import annotations

import re

from app.detection.entities import PiiEntity
from app.detection.recognizers.common import entity

# Words that are never (part of) a person name in these positions: titles, labels, headings,
# legal/administrative vocabulary and pronouns. Shared with the precision filter.
STOPWORDS = frozenset("""
il lo la i gli le un una uno di del della dei degli delle da dal dalla e ed o a ad al alla in nel nella con su per tra fra
lei lui egli ella voi noi loro sua suo mio mia suoi sue
sig sigg sig.ra sigra signor signora signore dott dott.ssa dottssa dr prof avv avvocato ing geom rag arch notaio spett spettabile
egregio egregia gentile gentilissimo gentilissima caro cara cordiali distinti saluti grazie buongiorno buonasera salve
oggetto data luogo nome cognome denominazione soggetto firma firmato codice fiscale cf c.f p.iva iva tel telefono cell email
mail pec via viale piazza corso largo indirizzo residente domiciliato nato nata n nr numero pratica sinistro polizza
tribunale corte giudice sentenza decreto ricorso procura liti atto citazione motivi decisione fatto diritto premesso
considerato ritenuto visto pqm p.q.m rg r.g attore convenuto convenuta ricorrente resistente parte parti teste testimone
fattura cedente cessionario destinatario mittente busta paga cedolino rimborso recapito veicolo targa conducente
contratto locazione locatore conduttore conduttrice proprieta proprietà immobile catasto foglio particella subalterno
agenzia entrate inps inail comune regione provincia ministero questura prefettura ufficio direzione sezione erario
spa srl snc sas società azienda studio banca assicurazione compagnia
lavoratore lavoratrice dipendente contribuente coniuge carico beneficiario intestatario cliente paziente utente
retribuzione superminimo contributi contributo trattenute trattenuta competenze competenza detrazioni detrazione
imponibile irpef netto lordo lorda straordinari straordinario ferie permessi tfr tredicesima quattordicesima
matricola qualifica livello mansione ccnl totale accredito voci voce
canone deposito cauzionale cauzione durata rata rate art articolo clausola rinnovo recesso spese condominiali premesse
importo saldo scadenza allegato allegati pagina
ciao perfetto certo ok okay bene
gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre
lunedi martedi mercoledi giovedi venerdi sabato domenica
""".split())

_CAP = r"[A-ZÀ-Ý][a-zà-ÿ]+(?:['’\-][A-ZÀ-Ýa-zà-ÿ][a-zà-ÿ]+)?"
_UP = r"[A-ZÀ-Ý]{2,}(?:['’\-][A-ZÀ-Ý]{2,})?"
_INITIAL = r"[A-Z]\."
_PARTICLE = r"(?:[Dd][aeiu]|[Dd]el(?:la|lo)?|[Dd]al|[Ll][ao]|[Vv]an|[Vv]on|[Dd]er|[Bb]en|[Ee]l|[Aa]l|[Bb]in|[Aa]bu|[Mm]c)"
_TOKEN = rf"(?:{_CAP}|{_UP}|{_INITIAL})"
_NAME = rf"{_TOKEN}(?:[ ](?:{_PARTICLE}[ ])?(?:{_CAP}|{_UP})){{0,3}}"
_LOWER_NAME = r"[a-zà-ÿ][a-zà-ÿ'’]+(?:[ ][a-zà-ÿ][a-zà-ÿ'’]+){1,2}"

# Cues that need a colon after them (labels) vs. cues that read naturally before a name.
LABEL_CUES = (r"soggetto|nome|cognome(?:\s*,?\s*(?:e\s+)?(?:nome|denominazione))?|denominazione|contribuente"
               r"|coniuge(?:\s+a\s+carico)?|cedente|cessionario|destinatario|firma(?:to)?|per|assegnato|assegnata"
               r"|beneficiari[oa](?:\s+designat[oa])?|intestatari[oa]|lavorat(?:ore|rice)|paziente|cliente|assicurat[oa]"
               r"|contraente|dipendente|richiedente|delegat[oa]|referente|titolare|nominativo")
_NATURAL_CUES = (r"il/la|il\s+sottoscritto|la\s+sottoscritta|sottoscritt[oa](?:/[ao])?|conducente|al(?:la)?\s+dipendente"
                 r"|contro|promossa\s+da|promosso\s+da|(?:il|la)\s+teste|(?:il|la)\s+collega|(?:mio|mia)\s+inquilin[oa]"
                 r"|(?:il\s+)?mio\s+capo|cv\s+di|customer|gentile(?:\s+(?:sig(?:\.|nor[ae]?)|cliente|dott\.?(?:ssa)?))?"
                 r"|egregi[oa](?:\s+(?:sig\.|signor[ae]?|dott\.?(?:ssa)?|avv\.))?|(?:dall?['’]\s?)?avv\.|avvocato|dott\.(?:ssa)?"
                 r"|dott(?:ssa|oressa|or)?|sig\.(?:ra)?|signor[ae]?|prof\.(?:ssa)?|geom\.|ing\.|rag\.|notaio|giudice")
_CUE = re.compile(rf"(?i:(?<![\w])(?:(?P<label>{LABEL_CUES})\s*:|(?P<natural>{_NATURAL_CUES})))[ \t]*\n?[ \t]*")
_NAME_AT = re.compile(_NAME)
_LOWER_AT = re.compile(_LOWER_NAME)
_LOWER_FOLLOW = re.compile(r"\s*(?:[,(<\n;]|$|-\s|(?i:nat[oa]\b|n\.\s+a\b|c\.\s?f\.|cf\b|codice\s+fiscale|\w+=))")
_STRONG_LOWER = re.compile(r"(?i)customer|cv\s+di|contro|il/la|sottoscritt|conducente|dipendente|cliente|assegnat")


def _trim(text: str, start: int, end: int) -> int:
    """Cut the captured name at the first stopword token; returns the new end (== start if none left)."""
    pos = start
    for m in re.finditer(r"\S+", text[start:end]):
        if m.group().lower().strip(".,:;'’") in STOPWORDS:
            break
        pos = start + m.end()
    return pos


def detect_persons(text: str) -> list[PiiEntity]:
    """Why/What: see module docstring. Test: see module docstring."""
    found: list[PiiEntity] = []
    for cue in _CUE.finditer(text):
        at = cue.end()
        if m := _NAME_AT.match(text, at):
            end = _trim(text, at, m.end())
            single = " " not in text[at:end].strip()
            if end > at and (not single or cue["label"] or re.fullmatch(_UP, text[at:end])):
                found.append(entity(text, at, end, "PERSON", 0.95))
            continue
        if _STRONG_LOWER.match(cue.group().strip()) and (m := _LOWER_AT.match(text, at)):
            end = _trim(text, at, m.end())
            if end > at and " " in text[at:end] and _LOWER_FOLLOW.match(text, end):
                found.append(entity(text, at, end, "PERSON", 0.9))
    return found

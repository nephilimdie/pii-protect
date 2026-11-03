"""PII-free near-miss genres for it_pii_heldout_v2 (every masked span here is a false positive).

Why: measures over-masking on text that looks like personal data but identifies nobody living:
textbook placeholders (Tizio, Caio, Sempronio), case-law citations, eponymous places and
institutions, historical figures, product/tech codes, statistics, public tenders, sports/weather.
What: one function per sub-genre; NEGATIVE lists (sub-genre, fn, count, noise p, case p).
Test: tests/test_v2.py asserts these documents have no PII spans.
"""
from __future__ import annotations

import ident as I
from builder import Doc

PLACEHOLDER = ["Tizio", "Caio", "Sempronio", "Mevio", "Filano"]
EPONYMS = ["Via Giuseppe Garibaldi", "Piazza Giacomo Matteotti", "Liceo Scientifico Enrico Fermi",
           "Ospedale Antonio Cardarelli", "Stadio Diego Armando Maradona", "Aeroporto Leonardo da Vinci",
           "Istituto Tecnico Guglielmo Marconi", "Teatro Gioachino Rossini", "Corso Vittorio Emanuele II",
           "Viale Alcide De Gasperi", "Policlinico Agostino Gemelli", "Ponte Giovanni da Verrazzano",
           "Scuola Primaria Maria Montessori", "Biblioteca Natalia Ginzburg"]
HISTORY = [("Alessandro Manzoni", "Milano", "1785"), ("Grazia Deledda", "Nuoro", "1871"),
           ("Giacomo Leopardi", "Recanati", "1798"), ("Eleonora Duse", "Vigevano", "1858"),
           ("Luigi Pirandello", "Agrigento", "1867"), ("Maria Montessori", "Chiaravalle", "1870"),
           ("Gabriele D'Annunzio", "Pescara", "1863"), ("Enrico Fermi", "Roma", "1901"),
           ("Giuseppe Verdi", "Busseto", "1813"), ("Anna Kuliscioff", "Moskaja", "1855")]
TEAMS = ["Atalanta", "Udinese", "Sassuolo", "Lecce", "Cagliari", "Cremonese", "Pisa", "Venezia"]


def dottrina(d: Doc) -> None:
    r = d.r
    a, b, c = r.sample(PLACEHOLDER, 3)
    d.t("Esempio " + str(r.randint(1, 40)) + ". ").n("COMMON_WORD", a)
    d.t(" vende a ").n("COMMON_WORD", b)
    d.t(" un fondo rustico per ")
    d.n("MONEY", I.eur(r, 5000, 90000))
    d.t("; successivamente ").n("COMMON_WORD", a)
    d.t(" aliena il medesimo bene a ").n("COMMON_WORD", c)
    d.t(", che trascrive per primo. Ai sensi dell'")
    d.n("LAW_REF", r.choice(["art. 2644 c.c.", "art. 1155 c.c.", "art. 2643 c.c."]))
    d.t(" prevale ").n("COMMON_WORD", c)
    d.t(", salvo il risarcimento del danno a favore di ").n("COMMON_WORD", b)
    d.t(r.choice([" (cfr. ", " (si veda "])).n("LAW_REF", r.choice(["Cass. civ., sez. II, 12 giugno 2019, n. 15738", "Cass. n. 9325/2011"]))
    d.t(").\nNota: il signor ").n("COMMON_WORD", "Rossi").t(" dell'esempio classico è un nome di fantasia; le parti sono indicate come A e B.\n")


def massime(d: Doc) -> None:
    r = d.r
    for _ in range(r.randint(2, 3)):
        d.n("LAW_REF", f"Cass. {r.choice(['civ.', 'pen.', 'lav.'])}, sez. {r.choice(['I', 'II', 'III', 'V', 'VI-3'])}, "
                       f"{r.randint(1, 28)} {r.choice(I.MONTHS)} {r.randint(2005, 2025)}, n. {r.randint(1000, 39999)}")
        d.t(" - " + r.choice(["In tema di locazione, il conduttore che ", "In materia di licenziamento, il datore che ",
                              "Ai fini della responsabilità ex ", "In tema di circolazione stradale, il proprietario che "]))
        if d.parts[-1].endswith("ex"):
            d.n("LAW_REF", "art. 2051 c.c.")
            d.t(", il custode che ")
        d.t(r.choice(["omette la manutenzione risponde dei danni", "non prova il caso fortuito è responsabile",
                      "agisce oltre il termine decade dall'azione"]) + " (conf. ")
        d.n("LAW_REF", f"Cass. n. {r.randint(1000, 30000)}/{r.randint(2000, 2020)}")
        d.t("; contra ")
        d.n("LAW_REF", f"Trib. {r.choice(I.TOWNS)[0]}, {r.randint(1, 28)}.{r.randint(1, 12)}.{r.randint(2015, 2024)}")
        d.t(").\n")


def toponomastica(d: Doc) -> None:
    r = d.r
    a, b = r.sample(EPONYMS, 2)
    d.n("PUBLIC_BODY", "Comune di " + r.choice(I.TOWNS)[0])
    d.t(" - Avviso alla cittadinanza\nDal ")
    d.n("DOC_DATE", I.doc_date(r))
    d.t(" " + r.choice(["è istituito il divieto di sosta in ", "saranno chiusi al traffico i tratti di ", "inizieranno i lavori in "]))
    d.n("COMMON_WORD", a)
    d.t(r.choice([" e nelle vie limitrofe all'", " fino all'incrocio con ", " e davanti al "]))
    d.n("COMMON_WORD", b)
    d.t(". Ordinanza n. ").n("DOC_NUMBER", f"{r.randint(1, 400)}/{r.randint(2024, 2026)}")
    d.t(". Per informazioni rivolgersi all'URP, ").n("PUBLIC_BODY", "Polizia Locale")
    d.t(", numero verde ").n("CODE", "800 " + I.digits(r, 3) + " " + I.digits(r, 3))
    d.t(".\n")


def storia(d: Doc) -> None:
    r = d.r
    nm, town, y = r.choice(HISTORY)
    d.t("Scheda didattica - ")
    d.n("COMMON_WORD", nm)
    d.t(" nacque a ")
    d.n("COMMON_WORD", town)
    d.t(" nel ").n("DOC_DATE", y)
    d.t(" e " + r.choice(["è ricordat* come una delle figure più influenti del suo tempo.".replace("*", "o"),
                          "la sua opera è studiata in tutte le scuole.", "a lei/lui sono intitolate strade e istituti."]))
    d.t(" Nel ").n("DOC_DATE", str(int(y) + r.randint(20, 50)))
    d.t(" " + r.choice(["pubblicò la sua opera più nota", "ricevette un importante riconoscimento", "si trasferì all'estero"]) +
        ". Oggi il ").n("COMMON_WORD", r.choice(EPONYMS))
    d.t(" ne porta il nome.\n")


def catalogo(d: Doc) -> None:
    r = d.r
    d.t("CATALOGO RICAMBI " + str(r.randint(2024, 2026)) + "\nCodice        Descrizione                   Prezzo\n")
    for _ in range(r.randint(4, 7)):
        d.n("CODE", r.choice([f"{''.join(r.choice('ABCDEFGHKLMNPRSTVZ') for _ in range(3))}-{I.digits(r, 5)}",
                              f"{I.digits(r, 4)}.{I.digits(r, 3)}.{I.digits(r, 2)}", f"SKU{I.digits(r, 8)}",
                              "".join(r.choice("ABCDEFGHLMNPRSTVZ") for _ in range(6)) + I.digits(r, 2) + r.choice("ABCDE") + I.digits(r, 2)]))
        d.t("   " + r.choice(["Filtro olio", "Pastiglie freno", "Cinghia distribuzione", "Termostato", "Guarnizione testata"]) + "   ")
        d.n("MONEY", I.eur(r, 5, 400))
        d.t("\n")
    d.t("Firmware centralina v").n("CODE", f"{r.randint(1, 9)}.{r.randint(0, 9)}.{r.randint(0, 99)}.{r.randint(100, 999)}")
    d.t(" - lotto ").n("CODE", f"L{I.digits(r, 6)}")
    d.t("\n")


def statistiche(d: Doc) -> None:
    r = d.r
    d.n("PUBLIC_BODY", r.choice(["ISTAT", "Banca d'Italia", "Regione " + r.choice(["Umbria", "Puglia", "Veneto", "Sardegna"])]))
    d.t(" - nota del ").n("DOC_DATE", I.doc_date(r))
    d.t("\nNel " + str(r.randint(2019, 2025)) + " la spesa media mensile delle famiglie è stata di ")
    d.n("MONEY", I.eur(r, 1800, 3200))
    d.t(" (+" + str(r.randint(1, 9)) + "," + str(r.randint(0, 9)) + "%). Le famiglie residenti a ")
    d.n("COMMON_WORD", r.choice(I.TOWNS)[0])
    d.t(" erano " + f"{r.randint(10, 400)}.{r.randint(100, 999)}" + "; il reddito mediano ")
    d.n("MONEY", I.eur(r, 15000, 32000))
    d.t(". Fonte: indagine campionaria, tavola ").n("DOC_NUMBER", f"{r.randint(1, 20)}.{r.randint(1, 9)}")
    d.t(".\n")


def gara(d: Doc) -> None:
    r = d.r
    d.n("PUBLIC_BODY", "Comune di " + r.choice(I.TOWNS)[0])
    d.t(" - Determinazione dirigenziale n. ").n("DOC_NUMBER", f"{r.randint(1, 2000)}/{r.randint(2024, 2026)}")
    d.t("\nOggetto: affidamento del servizio di " + r.choice(["manutenzione del verde", "refezione scolastica", "pulizia uffici"]) +
        " - CIG ").n("CODE", "".join(r.choice("0123456789ABCDEF") for _ in range(10)))
    d.t(" - CUP ").n("CODE", r.choice("ABCDEFGHJ") + I.digits(r, 2) + r.choice("ABCDEFGHJ") + I.digits(r, 11))
    d.t("\nImporto a base d'asta ")
    d.n("MONEY", I.eur(r, 20000, 900000))
    d.t(", ai sensi del ").n("LAW_REF", "D.Lgs. 36/2023")
    d.t(". Aggiudicataria: ").n("ORG", r.choice(["Verde Pubblico Soc. Coop.", "Ristorazione Collettiva S.p.A.", "Multiservizi Adriatica S.r.l."]))
    d.t(", P.IVA ").i("company_vat", I.piva(r))
    d.t(". Il RUP è il Responsabile del Settore Lavori Pubblici.\n")


def sport_meteo(d: Doc) -> None:
    r = d.r
    a, b = r.sample(TEAMS, 2)
    if r.random() < .5:
        d.n("ORG", a)
        d.t(f"-{b} {r.randint(0, 4)}-{r.randint(0, 4)}: ")
        d.t(r.choice(["partita equilibrata fino al ", "gol decisivo al ", "espulsione al "]) + str(r.randint(10, 90)) +
            "', biglietti a ")
        d.n("MONEY", I.eur(r, 15, 90))
        d.t(". Prossimo turno il ").n("DOC_DATE", I.doc_date(r))
        d.t(".\n")
    else:
        d.t("Previsioni per ").n("COMMON_WORD", r.choice(I.TOWNS)[0])
        d.t(" del ").n("DOC_DATE", I.doc_date(r))
        d.t(": " + r.choice(["pioggia in mattinata, schiarite dal pomeriggio", "sereno, minime 4 °C", "venti forti da maestrale"]) +
            ". Allerta " + r.choice(["gialla", "arancione"]) + " ").n("PUBLIC_BODY", "Protezione Civile")
        d.t(" n. ").n("DOC_NUMBER", f"{r.randint(1, 99)}/{r.randint(2025, 2026)}")
        d.t(".\n")


NEGATIVE = {"negative": [("dottrina_placeholder", dottrina, 14, .1, 0), ("massime", massime, 14, .15, 0),
                         ("toponomastica", toponomastica, 14, 0, .1), ("storia", storia, 12, 0, 0),
                         ("catalogo_codici", catalogo, 14, 0, 0), ("statistiche", statistiche, 12, 0, 0),
                         ("gara_appalto", gara, 12, .1, 0), ("sport_meteo", sport_meteo, 8, 0, 0)]}

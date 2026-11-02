"""Hand-authored near-miss documents with NO personal data: everything annotated must stay visible.

Why: a detector tuned for recall shows its cost on text full of things that look like PII but
identify nobody (eponymous streets and hospitals, words that are also first names, laws named
after ministers, case-law citations, bank codes of public bodies, version strings shaped like IPs).
What: functions Ctx -> markup with only negative / ignore spans. COMMON_WORD covers name-like words
and eponymous places used in a public, non-identifying sense; ORG covers named institutions.
Test: tests/test_heldout.py asserts negative documents carry no PII spans.
"""
from __future__ import annotations

import fakedata as F
from markup import Ctx

EPONYMS = ["Ospedale Sandro Pertini", "Aeroporto Marco Polo", "Liceo Galileo Galilei", "Stadio Diego Armando Maradona",
           "Policlinico Agostino Gemelli", "Istituto Enrico Fermi", "Teatro Carlo Felice", "Fondazione Giorgio Cini",
           "Aeroporto Falcone e Borsellino", "Università Luigi Bocconi"]
STREETS = ["via Giuseppe Garibaldi", "piazza Aldo Moro", "corso Vittorio Emanuele II", "viale Giacomo Matteotti",
           "via Alessandro Manzoni", "largo Enrico Berlinguer", "piazza Giuseppe Mazzini", "via Dante Alighieri"]
NAMED_LAWS = ["legge Fornero", "riforma Cartabia", "legge Biagi", "decreto Cura Italia", "legge Merlin", "Jobs Act",
              "decreto Bersani", "legge Basaglia"]
WORDS = [("rosa", "una rosa dei venti disegnata sul pavimento"), ("speranza", "con la speranza di chiudere entro l'estate"),
         ("serena", "una giornata serena e senza vento"), ("vittoria", "la vittoria in appello del Comune"),
         ("bianca", "una parete bianca da ritinteggiare"), ("Leone", "il Leone d'oro alla Mostra di Venezia"),
         ("gentile", "il personale è stato gentile e rapido"), ("ferro", "una ringhiera in ferro battuto"),
         ("monti", "i monti Sibillini innevati"), ("porta", "la porta tagliafuoco del garage"),
         ("gallo", "il gallo del campanile restaurato"), ("piccolo", "un piccolo intervento di manutenzione"),
         ("Felice", "Buon Natale e Felice Anno Nuovo"), ("celeste", "il nastro celeste per il fiocco nascita")]


def delibera(c: Ctx) -> str:
    return (f"{c.body()}\nDETERMINAZIONE DIRIGENZIALE n. {c.prot()} del {c.ddate()}\n"
            f"OGGETTO: affidamento diretto del servizio di {c.pick('manutenzione del verde', 'pulizia uffici', 'trasporto scolastico')} "
            f"- CIG {c.code('cig')} - CUP {c.neg('CODE', 'J' + F.digits(c.rng, 2) + 'B' + F.digits(c.rng, 11))}\n"
            f"IL DIRIGENTE\nvisto l'{c.law()}; visto il {c.law()}; richiamata la delibera di Giunta n. {c.prot()} del {c.ddate()};\n"
            f"DETERMINA\ndi affidare il servizio a {c.org()} (P.IVA {c.company_vat()}) per un importo di {c.money()} oltre IVA;\n"
            f"di imputare la spesa al capitolo {c.neg('CODE', F.digits(c.rng, 4) + '/' + F.digits(c.rng, 2))} del bilancio {c.rng.randint(2024, 2026)};\n"
            f"di pubblicare il presente atto all'Albo pretorio ai sensi del {c.law()}.\n")


def eponimi(c: Ctx) -> str:
    return (f"{c.pick('VIABILITÀ', 'Notizie dal territorio', 'Comunicato stampa')} - {c.ddate()}\n"
            f"Da lunedì {c.neg('COMMON_WORD', c.pick(*STREETS))} sarà chiusa al traffico tra {c.neg('COMMON_WORD', c.pick(*STREETS))} "
            f"e {c.neg('COMMON_WORD', c.pick(*STREETS))} per i lavori di {c.org()}. Le navette per l'{c.neg('ORG', c.pick(*EPONYMS))} "
            f"partiranno da {c.neg('COMMON_WORD', c.pick(*STREETS))}. L'investimento complessivo è di {c.money()}, "
            f"finanziato dal {c.pick('PNRR', 'Fondo sviluppo e coesione')} ({c.law()}).\n"
            f"Info: {c.neg('ORG', c.pick('URP', 'Ufficio Mobilità', 'Numero Verde'))} {c.neg('CODE', '800 ' + F.digits(c.rng, 3) + ' ' + F.digits(c.rng, 3))}.\n")


def parole(c: Ctx) -> str:
    picks = c.rng.sample(WORDS, 3)
    body = " ".join(f"{phrase.split(w, 1)[0]}{c.neg('COMMON_WORD', w)}{phrase.split(w, 1)[1]}." for w, phrase in picks)
    return (f"Relazione di sopralluogo del {c.ddate()} - pratica {c.prot()}\n{body[0].upper() + body[1:]} "
            f"Si ricorda che, dopo la {c.neg('LAW_REF', c.pick(*NAMED_LAWS))}, la spesa ({c.money()}) è detraibile ex {c.law()}.\n")


def codici(c: Ctx) -> str:
    return (f"{c.org()} - Documento di trasporto n. {c.prot()} del {c.ddate()}\n"
            f"Articolo {c.code('sku')}  router {c.pick('AX3000', 'VR-1100')} firmware {c.neg('CODE', f'{c.rng.randint(1, 12)}.{c.rng.randint(0, 9)}.{c.rng.randint(0, 9)}.{c.rng.randint(10, 250)}')}"
            f"  S/N {c.neg('CODE', 'SN' + F.digits(c.rng, 10))}  qtà {c.rng.randint(1, 40)}  {c.money()}\n"
            f"Articolo {c.code('sku')}  manuale ISBN {c.neg('CODE', '978-88-' + F.digits(c.rng, 2) + '-' + F.digits(c.rng, 5) + '-' + F.digits(c.rng, 1))}  {c.money()}\n"
            f"Codice ATECO del cedente {c.code('ateco')}; pagamento a 60 gg d.f.f.m. su IBAN {c.ign('company_iban', F.iban(c.rng))}; "
            f"BIC {c.neg('CODE', c.pick('BCITITMM', 'UNCRITMM', 'BPMOIT22XXX'))}\n"
            f"Totale imponibile {c.money()} - IVA 22% {c.money()} - rif. ordine {c.prot()}\n")


def storia(c: Ctx) -> str:
    return (f"Scheda didattica - {c.pick('Storia', 'Educazione civica')}\n"
            f"L'Italia unita è nata il {c.neg('DOC_DATE', '17 marzo 1861')}; la Repubblica è nata con il referendum del {c.neg('DOC_DATE', '2 giugno 1946')}. "
            f"La Costituzione è entrata in vigore il {c.neg('DOC_DATE', '1° gennaio 1948')} ({c.neg('LAW_REF', 'art. 139 Cost.')}).\n"
            f"Esercizio: calcola quanti anni sono passati fino al {c.ddate()} e confronta con la {c.neg('LAW_REF', c.pick(*NAMED_LAWS))}. "
            f"Scadenza consegna: {c.ddate(2026, 2026)}. Aula {c.neg('CODE', c.pick('B12', 'A3', 'Lab 2'))}, {c.neg('ORG', c.pick(*EPONYMS))}.\n")


def massima(c: Ctx) -> str:
    sec = c.pick("I", "II", "III", "lav.", "VI")
    return (f"{c.neg('PUBLIC_BODY', 'Cass. civ.')}, sez. {sec}, {c.ddate(2015, 2025)}, n. {c.neg('DOC_NUMBER', str(c.rng.randint(1000, 35000)))}\n"
            f"In tema di {c.pick('locazione', 'responsabilità medica', 'licenziamento disciplinare')}, qualora {c.neg('COMMON_WORD', 'Tizio')} "
            f"abbia ceduto a {c.neg('COMMON_WORD', 'Caio')} il credito verso {c.neg('ORG', c.pick('Alfa S.r.l.', 'Beta S.p.A.'))}, "
            f"l'onere della prova grava sul cessionario ai sensi dell'{c.law()}. Conf. {c.neg('PUBLIC_BODY', c.pick(*['Trib. Milano', 'App. Roma', 'Trib. Bari']))} "
            f"{c.ddate(2015, 2024)}. Valore della lite: {c.money()}.\n")


def tech_log(c: Ctx) -> str:
    lines = []
    for _ in range(c.rng.randint(4, 8)):
        t = f"2025-{c.rng.randint(1, 12):02d}-{c.rng.randint(1, 28):02d} {c.rng.randint(0, 23):02d}:{c.rng.randint(0, 59):02d}:{c.rng.randint(0, 59):02d}"
        lines.append(c.pick(
            f"{t} INFO  scheduler job={c.code('hash')} finished in {c.rng.randint(10, 9000)}ms status={c.code('http')}",
            f"{t} WARN  cache miss ratio {c.rng.randint(1, 60)}% on node {c.ign('internal_ip', f'10.0.{c.rng.randint(0, 9)}.{c.rng.randint(2, 250)}')}",
            f"{t} INFO  deployed build {c.code('ver')} commit {c.code('hash')}",
            f"{t} ERROR upstream {c.org()} returned {c.code('http')} after {c.rng.randint(1, 30)}s (retry {c.rng.randint(1, 5)}/5)"))
    return "\n".join(lines) + "\n"


NEGATIVE = {"negative": [("delibera", delibera, 15, .3), ("eponimi", eponimi, 15, 0), ("parole", parole, 15, 0),
                         ("codici", codici, 15, .2), ("storia", storia, 12, 0), ("massima", massima, 14, 0),
                         ("tech_log", tech_log, 14, 0)]}

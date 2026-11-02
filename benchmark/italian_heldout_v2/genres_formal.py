"""Formal genres for it_pii_heldout_v2: notarial deeds, public-administration forms, court documents.

Why: v1 covered PEC, verbali, atti di citazione and labour ricorsi; v2 uses different paperwork.
What: one function per sub-genre, each fills a Doc; FORMAL lists (sub-genre, fn, count, noise p, case p).
Test: tests/test_v2.py (rebuild + span integrity).
"""
from __future__ import annotations

import ident as I
import snippets as S
from builder import Doc

ORGS = ["Banca Popolare del Cassinate S.p.A.", "Credito Valtellinese Soc. Coop.", "Edilsud Costruzioni S.r.l.",
        "Agenzia Immobiliare Il Portico S.a.s.", "Officine Meccaniche Brembo-Valle S.r.l.", "Cooperativa Sociale La Spiga",
        "Assicurazioni Generali Italia S.p.A.", "Termoidraulica Fratelli Zanetti S.n.c.", "Studio Associato Delta"]
BODIES = ["Comune di {t}", "Agenzia delle Entrate - Ufficio Provinciale di {t}", "Tribunale di {t}",
          "Giudice di Pace di {t}", "ASL di {t}", "Prefettura di {t}", "INPS - Sede di {t}", "Questura di {t}"]


def body(d: Doc) -> None:
    d.n("PUBLIC_BODY", d.pick(*BODIES).format(t=d.r.choice(I.TOWNS)[0]))


def org(d: Doc) -> None:
    d.n("ORG", d.pick(*ORGS))


def rogito(d: Doc) -> None:
    r = d.r
    seller, buyer, notary = I.person(r), I.person(r), I.person(r, 0)
    d.t(f"REPERTORIO N. {r.randint(1000, 60000)}          RACCOLTA N. {r.randint(1000, 30000)}\n\n")
    d.t("COMPRAVENDITA IMMOBILIARE\nREPUBBLICA ITALIANA\n\nL'anno duemila" + r.choice(["ventitré", "ventiquattro", "venticinque"]) +
        ", il giorno " + r.choice(["dodici", "tre", "ventuno", "nove"]) + " del mese di " + r.choice(I.MONTHS) + ", in ")
    d.t(r.choice(I.TOWNS)[0] + ", nel mio studio.\nAvanti a me, ")
    S.name(d, notary, "fl")
    d.t(", Notaio in " + r.choice(I.TOWNS)[0] + ", iscritto nel Ruolo del Distretto Notarile, sono presenti i signori:\n- ")
    S.name(d, seller, r.choice(["fl", "LF"]))
    S.birth(d, seller)
    S.residence(d, seller)
    S.fiscal(d, seller)
    d.t(", che dichiara di essere " + r.choice(["celibe", "coniugato in regime di separazione dei beni", "vedovo", "nubile"]) + ";\n- ")
    S.name(d, buyer, r.choice(["fl", "LF", "Lf"]))
    S.birth(d, buyer)
    S.residence(d, buyer)
    S.fiscal(d, buyer)
    d.t(".\nDetti comparenti, della cui identità personale io Notaio sono certo, convengono quanto segue.\n")
    d.t("Art. 1 - Il venditore vende al compratore, che accetta, la piena proprietà dell'unità immobiliare sita in ")
    d.p("ADDRESS", S.address_value(d, I.person(r)))
    d.t(", censita al Catasto Fabbricati di " + r.choice(I.TOWNS)[0] + " al ")
    fg, part, sub = r.randint(1, 90), r.randint(10, 2500), r.randint(1, 40)
    d.p("CADASTRAL_REF", r.choice([f"foglio {fg}, particella {part}, subalterno {sub}", f"fg. {fg} mapp. {part} sub. {sub}",
                                   f"Foglio {fg} Part. {part} Sub {sub}"]))
    d.t(", categoria A/" + str(r.randint(2, 7)) + ".\nArt. 2 - Il prezzo è convenuto in ")
    S.money(d, 60000, 480000)
    d.t(", pagato mediante bonifico dal conto IBAN ")
    v, h = I.iban_form(r, I.iban(r))
    d.p("IBAN", v, h)
    d.t(" ai sensi dell'")
    d.n("LAW_REF", "art. 35, comma 22, del D.L. 223/2006")
    d.t(".\nArt. 3 - Le parti dichiarano che la vendita non è stata conclusa con l'intervento di mediatori.\n\nF.to ")
    S.name(d, seller, "fl")
    d.t("\nF.to ")
    S.name(d, buyer, "fl")
    d.t("\nF.to ")
    S.name(d, notary, "last")
    d.t(" Notaio\n")


def autocert(d: Doc) -> None:
    r = d.r
    p = I.person(r)
    d.t("DICHIARAZIONE SOSTITUTIVA DI CERTIFICAZIONE\n(")
    S.law(d)
    d.t(")\n\nIl/La sottoscritto/a ")
    S.name(d, p, r.choice(["fl", "LF", "UPPER"]))
    S.birth(d, p)
    S.residence(d, p)
    S.fiscal(d, p)
    d.t(", tel. ").p("PHONE", p.phone)
    d.t(",\nconsapevole delle sanzioni penali previste dall'")
    d.n("LAW_REF", "art. 76 del D.P.R. 445/2000")
    d.t(" per le ipotesi di falsità in atti e dichiarazioni mendaci,\nDICHIARA\n")
    for _ in range(r.randint(2, 3)):
        k = r.randrange(5)
        if k == 0:
            d.t("[X] di essere residente nel Comune di " + p.town[0] + ";\n")
        elif k == 1:
            fam = I.person(r)
            d.t("[X] che la propria famiglia anagrafica è composta, oltre al dichiarante, da: ")
            S.name(d, fam, "fl")
            S.birth(d, fam)
            d.t(" (" + r.choice(["coniuge", "figlio", "figlia", "convivente"]) + ");\n")
        elif k == 2:
            d.t("[X] di essere in possesso del titolo di studio di " + r.choice(["laurea magistrale", "diploma di geometra", "licenza media"]) + ";\n")
        elif k == 3:
            d.t("[X] di essere titolare di partita IVA n. ").p("VAT_NUMBER", I.piva(r)).t(" (ditta individuale);\n")
        else:
            d.t("[X] che il reddito ISEE del nucleo è pari a ")
            S.money(d, 3000, 40000)
            d.t(";\n")
    d.t("\nLuogo e data: " + p.town[0] + ", ")
    S.ddate(d)
    d.t("\nIl dichiarante ")
    S.name(d, p, r.choice(["fl", "init"]))
    d.t("\nSi allega copia del documento: ")
    S.ident_doc(d)
    d.t("\n")


def accesso_atti(d: Doc) -> None:
    r = d.r
    p = I.person(r)
    d.t("Al ")
    body(d)
    d.t("\nUfficio Protocollo\n\nOGGETTO: Istanza di accesso agli atti amministrativi ai sensi della ")
    d.n("LAW_REF", "L. 241/1990")
    d.t("\n\nIo sottoscritt" + ("a" if p.female else "o") + " ")
    S.name(d, p)
    S.fiscal(d, p)
    S.residence(d, p)
    d.t(", recapito ").p("PHONE", p.phone).t(", e-mail ")
    S.mail(d, p, .2)
    d.t(",\nin qualità di " + r.choice(["proprietario confinante", "controinteressato", "diretto interessato", "erede"]) +
        ", chiedo di prendere visione ed estrarre copia della pratica edilizia prot. n. ")
    S.prot(d)
    d.t(" del ")
    S.ddate(d)
    d.t(" relativa all'immobile di ")
    S.name(d, I.person(r), r.choice(["fl", "Lf", "last"]))
    d.t(" sito in ").p("ADDRESS", S.address_value(d, I.person(r)))
    d.t(".\nMotivazione: " + r.choice(["tutela in giudizio di un interesse giuridicamente rilevante.",
                                       "verifica della conformità urbanistica di una sopraelevazione.",
                                       "contestazione di una sanzione amministrativa."]) + "\nDiritti di segreteria: ")
    S.money(d, 5, 60)
    d.t("\n\nDistinti saluti\n")
    S.name(d, p, r.choice(["fl", "UPPER", "init"]))
    d.t("\n")


def cert_anagrafe(d: Doc) -> None:
    r = d.r
    head = I.person(r)
    d.t("")
    body(d)
    d.t("\nSERVIZI DEMOGRAFICI\nCERTIFICATO DI STATO DI FAMIGLIA\n\nSi certifica che, dalle risultanze anagrafiche, la famiglia residente in ")
    d.p("ADDRESS", S.address_value(d, head))
    d.t(" è così composta:\n\n")
    d.t("N. | COGNOME E NOME | LUOGO DI NASCITA | DATA DI NASCITA | RAPPORTO\n")
    members = [head] + [I.person(r, .1) for _ in range(r.randint(1, 3))]
    for k, m in enumerate(members, 1):
        dt, h = I.birth_date(r, m)
        d.t(f"{k} | ").p("PERSON", f"{m.last.upper()} {m.first.upper()}", m.hard | {"uppercase", "table_cell"})
        d.t(" | ").p("BIRTH_PLACE", m.birth_town.upper(), {"no_cue", "table_cell", "uppercase"})
        d.t(" | ").p("DATE_OF_BIRTH", dt, h | {"table_cell"})
        d.t(" | " + ("INTESTATARIO SCHEDA" if k == 1 else r.choice(["CONIUGE", "FIGLIO/A", "SUOCERO/A", "CONVIVENTE"])) + "\n")
    d.t("\nSi rilascia in carta libera per gli usi consentiti dalla legge. " + head.town[0] + ", ")
    S.ddate(d)
    d.t("\nL'Ufficiale d'Anagrafe\n")
    S.name(d, I.person(r, 0), r.choice(["init", "fl"]))
    d.t("\n")


def decreto(d: Doc) -> None:
    r = d.r
    cred, debt, lawyer, judge = I.person(r), I.person(r), I.person(r, 0), I.person(r, 0)
    d.n("PUBLIC_BODY", "TRIBUNALE ORDINARIO DI " + r.choice(I.TOWNS)[0].upper())
    d.t("\nSezione " + r.choice(["I", "II", "III"]) + " Civile\n")
    d.p("CASE_ID", r.choice([f"R.G. n. {r.randint(100, 9999)}/{r.randint(2023, 2026)}", f"N. {r.randint(100, 9999)}/{r.randint(2023, 2026)} R.G.",
                             f"RG {r.randint(100, 9999)}/{r.randint(23, 26)}"]))
    d.t("\n\nDECRETO INGIUNTIVO\n(")
    d.n("LAW_REF", "artt. 633 e ss. c.p.c.")
    d.t(")\n\nIl Giudice, ")
    S.titled(d, judge, r.choice(["fl", "init"]))
    d.t(",\nletto il ricorso depositato da ")
    S.name(d, cred, r.choice(["fl", "UPPER"]))
    S.fiscal(d, cred)
    d.t(", rappresentat" + ("a" if cred.female else "o") + " e difes" + ("a" if cred.female else "o") + " dall'")
    S.titled(d, lawyer, "fl")
    d.t(" (PEC ")
    S.mail(d, lawyer, 0, pec=True)
    d.t("),\nnei confronti di ")
    S.name(d, debt, r.choice(["fl", "LF", "UPPER"]))
    S.birth(d, debt)
    S.residence(d, debt)
    d.t(";\nritenuta la propria competenza e la sussistenza del credito documentato dalle fatture n. ")
    S.prot(d)
    d.t(",\nINGIUNGE\na ")
    S.name(d, debt, r.choice(["last", "fl"]))
    d.t(" di pagare, entro quaranta giorni dalla notifica, la somma di ")
    S.money(d, 1500, 90000)
    d.t(" oltre interessi e spese, liquidate in ")
    S.money(d, 300, 4000)
    d.t(".\n" + r.choice(I.TOWNS)[0] + ", ")
    S.ddate(d)
    d.t("\nIl Giudice\n")
    S.name(d, judge, "init")
    d.t("\n")


def sentenza(d: Doc) -> None:
    r = d.r
    a, b, wit = I.person(r), I.person(r), I.person(r)
    d.t("REPUBBLICA ITALIANA\nIN NOME DEL POPOLO ITALIANO\n")
    d.n("PUBLIC_BODY", "Tribunale di " + r.choice(I.TOWNS)[0])
    d.t(" - sentenza n. ")
    S.prot(d)
    d.t("\nnella causa civile iscritta al ")
    d.p("CASE_ID", f"n. {r.randint(100, 9999)}/{r.randint(2019, 2025)} R.G.")
    d.t(" promossa da\n")
    S.name(d, a, r.choice(["UPPER", "LF", "fl"]))
    S.fiscal(d, a)
    d.t(" - attore -\ncontro\n")
    S.name(d, b, r.choice(["UPPER", "LF", "fl"]))
    d.t(" - convenut" + ("a" if b.female else "o") + " contumace -\n\nSVOLGIMENTO DEL PROCESSO\nCon atto di citazione notificato il ")
    S.ddate(d)
    d.t(" l'attore esponeva che in data ")
    S.ddate(d)
    d.t(", mentre percorreva " + r.choice(["a piedi", "in bicicletta", "alla guida della propria autovettura targata"]))
    if "targata" in d.parts[-1]:
        d.t(" ").p("LICENSE_PLATE", I.plate(r))
    d.t(" ")
    d.p("ADDRESS", S.address_value(d, I.person(r), r.random() < .5))
    d.t(", veniva " + r.choice(["investito", "urtato", "travolto"]) + " dal veicolo condotto dalla convenuta.\n")
    d.t("La teste ")
    S.name(d, wit, r.choice(["fl", "Lf"]))
    d.t(", sentita all'udienza del ")
    S.ddate(d)
    d.t(", confermava la dinamica. Il CTU quantificava il danno biologico nel " + str(r.randint(3, 25)) + "%.\n")
    d.t("Richiamato l'orientamento di ")
    d.n("LAW_REF", r.choice(["Cass. civ., sez. III, n. 7513/2018", "Cass. SS.UU. n. 26972/2008", "Cass. n. 28989/2019"]))
    d.t(",\nP.Q.M.\ncondanna ")
    S.name(d, b, "last")
    d.t(" al pagamento in favore di ")
    S.name(d, a, r.choice(["last", "fl"]))
    d.t(" della somma di ")
    S.money(d, 4000, 150000)
    d.t(".\n")


def conciliazione(d: Doc) -> None:
    r = d.r
    w, rep, uni = I.person(r), I.person(r, 0), I.person(r, 0)
    d.t("VERBALE DI CONCILIAZIONE IN SEDE SINDACALE\n(")
    d.n("LAW_REF", r.choice(["artt. 410 e 411 c.p.c.", "art. 2113 c.c."]))
    d.t(")\n\nIl giorno ")
    S.ddate(d)
    d.t(", presso la sede " + r.choice(["CGIL", "CISL", "UIL", "UGL"]) + " di " + r.choice(I.TOWNS)[0] + ", sono comparsi:\n")
    d.t("- ")
    S.name(d, w, r.choice(["fl", "LF"]))
    S.birth(d, w)
    S.fiscal(d, w)
    d.t(", matricola ").p("EMPLOYEE_ID", r.choice([I.digits(r, 6), "MAT-" + I.digits(r, 5), I.digits(r, 4) + "/" + r.choice("ABC")]))
    d.t(", assistit" + ("a" if w.female else "o") + " dal rappresentante sindacale ")
    S.name(d, uni, r.choice(["fl", "init"]))
    d.t(";\n- la società ")
    org(d)
    d.t(", in persona del procuratore ")
    S.name(d, rep, "fl")
    d.t(".\nLe parti concordano la risoluzione consensuale del rapporto con decorrenza ")
    S.ddate(d)
    d.t(" e il pagamento di un incentivo all'esodo di ")
    S.money(d, 5000, 80000)
    d.t(" lordi, da accreditare sull'IBAN ")
    v, h = I.iban_form(r, I.iban(r))
    d.p("IBAN", v, h)
    d.t(".\nLetto, confermato e sottoscritto.\n")


FORMAL = {"formal": [("rogito", rogito, 16, .2, 0), ("autocertificazione", autocert, 16, .12, .15),
                     ("accesso_atti", accesso_atti, 13, .1, 0), ("stato_famiglia", cert_anagrafe, 11, .15, 0),
                     ("decreto_ingiuntivo", decreto, 13, .2, 0), ("sentenza", sentenza, 13, .25, 0),
                     ("conciliazione", conciliazione, 11, .1, 0)]}

"""Informal and machine-readable genres for it_pii_heldout_v2.

Why: v1 had WhatsApp, mixed IT/EN mail and Slack, CRM CSV, server logs, JSON payloads and pasted
spreadsheets; v2 uses dictation transcripts, quoted mail threads, SMS/Telegram, forum posts,
issue trackers, FatturaPA XML, vCard/iCal, SQL dumps, YAML/INI configs, fixed-width and markdown tables.
What: one function per sub-genre; DIGITAL lists (sub-genre, fn, count, noise p, case p).
Test: tests/test_v2.py.
"""
from __future__ import annotations

import ident as I
import snippets as S
from builder import Doc
from genres_formal import org

SPOKEN_N = ["zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove"]


def dettatura(d: Doc) -> None:
    """Speech-to-text dictation: lowercase, little punctuation, some digits spoken."""
    r = d.r
    p, q = I.person(r), I.person(r)
    d.t("[trascrizione automatica nota vocale " + f"{r.randint(0, 9)}:{r.randint(10, 59)}" + "]\n")
    d.t(r.choice(["allora", "dunque", "ok"]) + " " + r.choice(["nota per la pratica", "promemoria", "appunto per lo studio"]) + " del cliente ")
    S.name(d, p, "lower")
    d.t(" " + r.choice(["che è nato a", "nato a"]) + " ")
    d.p("BIRTH_PLACE", p.birth_town.lower(), {"lowercase"})
    d.t(" il ")
    d.p("DATE_OF_BIRTH", f"{p.d} {I.MONTHS[p.m - 1]} {p.y}", {"lowercase", "spoken"})
    d.t(" abita in ")
    d.p("ADDRESS", f"{p.street.lower()} a {p.town[0].lower()}", {"lowercase", "spoken"})
    d.t(" il numero di telefono è ")
    digits = p.phone.replace(" ", "").replace("+39", "").replace("/", "").replace(".", "").replace("-", "").replace("(", "").replace(")", "")[-10:]
    if r.random() < .5:
        d.p("PHONE", " ".join(SPOKEN_N[int(c)] for c in digits[:3]) + " " + digits[3:], {"spoken"})
    else:
        d.p("PHONE", " ".join(digits[i:i + 3] for i in range(0, len(digits), 3)), {"spoken"})
    d.t(" " + r.choice(["e la mail", "mail"]) + " è ")
    local, dom = p.email.split("@")
    d.p("EMAIL", f"{local} chiocciola {dom.replace('.', ' punto ')}", {"spoken", "obfuscated"})
    d.t(" " + r.choice(["poi", "inoltre"]) + " dice che il vicino ")
    S.name(d, q, "lower")
    d.t(" gli deve ancora " + str(r.randint(200, 9000)) + " euro " + r.choice(["per i lavori al tetto", "del prestito", "di affitto"]) +
        " " + r.choice(["richiamarlo lunedì", "preparare la diffida", "sentire l'avvocato"]) + "\n")


def mail_thread(d: Doc) -> None:
    r = d.r
    a, b = I.person(r), I.person(r)
    d.t("Da: ")
    S.name(d, a, "fl")
    d.t(" <")
    S.mail(d, a, 0)
    d.t(">\nA: ")
    S.mail(d, b, 0)
    d.t("\nOggetto: R: " + r.choice(["preventivo ristrutturazione", "documenti per il mutuo", "disdetta contratto", "visita di controllo"]) +
        "\n\n" + r.choice(["Ciao ", "Buongiorno ", "Gentile "]))
    S.name(d, b, "first")
    d.t(",\n" + r.choice(["ti giro i dati che mi hai chiesto.", "eccomi con le informazioni mancanti.", "come d'accordo al telefono."]) +
        " Il mio codice fiscale è ")
    v, h = I.cf_form(r, a.cf)
    d.p("FISCAL_CODE", v, h)
    d.t(" e il nuovo numero è ").p("PHONE", a.phone)
    d.t(".\nPer favore non usare più l'indirizzo vecchio, scrivimi a ")
    S.mail(d, a, .5)
    d.t(".\n\nGrazie, ")
    S.name(d, a, r.choice(["first", "init"]))
    d.t("\n\nIl giorno ")
    S.ddate(d)
    d.t(", ")
    S.name(d, b, "fl")
    d.t(" ha scritto:\n> " + r.choice(["Mi servirebbero anche l'indirizzo", "Puoi mandarmi la residenza"]) + " e una copia del documento.\n> Il bonifico va fatto a ")
    org(d)
    d.t(".\n> \n> --\n> ")
    S.name(d, b, "fl")
    d.t("\n> Cell. ").p("PHONE", b.phone)
    d.t("\n\nP.S. residenza: ").p("ADDRESS", S.address_value(d, a))
    d.t(" - documento ")
    S.ident_doc(d)
    d.t("\n")


def sms(d: Doc) -> None:
    r = d.r
    a, b = I.person(r, .3), I.person(r, .3)
    d.t(f"Telegram - chat con {r.choice(['Mamma', 'Lavoro', 'Condominio', 'Calcetto'])}\n")
    t = r.randint(7, 21)
    d.t(f"[{t}:{r.randint(10, 59)}] ")
    S.name(d, a, r.choice(["first", "fl"]))
    d.t(": ciao sono ")
    S.name(d, a, r.choice(["first", "lower"]))
    d.t(" ho cambiato numero, salva questo ").p("PHONE", a.phone)
    d.t("\n" + f"[{t}:{r.randint(10, 59)}] ")
    S.name(d, b, "first")
    d.t(": ok! mi mandi anche l'iban per la quota? 😊\n" + f"[{t + 1}:{r.randint(10, 59)}] ")
    S.name(d, a, "first")
    d.t(": ")
    v, h = I.iban_form(r, I.iban(r))
    d.p("IBAN", v.lower() if r.random() < .2 else v, h)
    d.t(" intestato a " + r.choice(["me", "mio marito ", "mia moglie "]))
    if not d.parts[-1].endswith("me"):
        S.name(d, I.person(r), r.choice(["fl", "lower"]))
    d.t("\n" + f"[{t + 1}:{r.randint(10, 59)}] ")
    S.name(d, b, "first")
    d.t(": perfetto. ah il mio insta è ").p("USERNAME", "@" + I._slug(b.first) + r.choice(["_", ".", ""]) + I._slug(b.last)[:5] + str(r.randint(1, 99)))
    d.t(" e ci vediamo da me in ").p("ADDRESS", b.street.lower() if r.random() < .4 else b.street)
    d.t(" sabato\n")


def forum(d: Doc) -> None:
    r = d.r
    p = I.person(r)
    nick = r.choice(["", "the_", "x"]) + I._slug(p.first)[:4] + str(r.randint(70, 99))
    d.t("Forum Condominio Web > Sezione " + r.choice(["Liti tra vicini", "Spese condominiali", "Locazioni"]) + "\nUtente: ")
    d.p("USERNAME", nick)
    d.t(" | iscritto dal " + str(r.randint(2009, 2022)) + "\n\n" + r.choice(["Salve a tutti", "Buonasera", "Ciao ragazzi"]) +
        ", vi scrivo perché l'amministratore ")
    S.name(d, I.person(r), r.choice(["fl", "last", "init"]))
    d.t(" " + r.choice(["non ci convoca l'assemblea da due anni", "ha addebitato a me i lavori dell'ascensore",
                        "non risponde alle PEC"]) + ". Abito in ")
    d.p("ADDRESS", S.address_value(d, p, r.random() < .5))
    d.t(" e il problema riguarda anche la signora del piano di sopra, ")
    S.name(d, I.person(r), r.choice(["fl", "Lf"]))
    d.t(", che ha " + r.choice(["87 anni", "un figlio disabile", "appena subito un intervento"]) + ".\nSe qualcuno vuole contattarmi in privato: ")
    S.mail(d, p, .6)
    d.t("\nGrazie\n" + r.choice(["--", "__"]) + "\n")
    S.name(d, p, r.choice(["first", "fl"]))
    d.t("\n")


def ticket(d: Doc) -> None:
    r = d.r
    u, agent = I.person(r, .3), I.person(r, 0)
    d.t(f"[SUP-{r.randint(1000, 9999)}] " + r.choice(["Cannot login after password reset", "Account bloccato", "Fattura con dati errati",
                                                     "Data export request (GDPR art. 15)"]) + "\nReporter: ")
    S.mail(d, u, 0)
    d.t("\nAssignee: ").p("USERNAME", I._slug(agent.first) + "." + I._slug(agent.last))
    d.t("\nPriority: " + r.choice(["High", "Medium", "Low"]) + "\n\nDescription:\nHi team, customer ")
    S.name(d, u, r.choice(["fl", "Lf"]))
    d.t(" (user id ").p("USERNAME", r.choice([I._slug(u.first)[0] + I._slug(u.last) + str(u.y % 100), "u" + I.digits(r, 7)]))
    d.t(") called from ").p("PHONE", u.phone)
    d.t(". " + r.choice(["Last successful login from IP ", "Suspicious access from ", "Session came from "]))
    v6 = r.random() < .45
    d.p("IP_ADDRESS", I.ipv6(r) if v6 else I.ipv4(r), {"ipv6"} if v6 else ())
    d.t(" on ")
    S.ddate(d)
    d.t(".\nIl cliente dice che l'indirizzo di fatturazione corretto è ").p("ADDRESS", S.address_value(d, u))
    d.t(" e chiede di aggiornare la P.IVA in ").p("VAT_NUMBER", I.piva(r))
    d.t(".\n\nStack: AuthError at login.py:212 (build ").n("CODE", f"{r.randint(1, 9)}.{r.randint(0, 30)}.{r.randint(0, 99)}")
    d.t(")\n")


def fattura_xml(d: Doc) -> None:
    r = d.r
    p = I.person(r, .1)
    d.t('<?xml version="1.0" encoding="UTF-8"?>\n<p:FatturaElettronica versione="FPR12">\n <FatturaElettronicaHeader>\n  <CedentePrestatore>\n   <DatiAnagrafici>\n    <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>')
    d.p("VAT_NUMBER", I.piva(r))
    d.t("</IdCodice></IdFiscaleIVA>\n    <CodiceFiscale>").p("FISCAL_CODE", p.cf)
    d.t("</CodiceFiscale>\n    <Anagrafica><Nome>").p("PERSON", p.first, p.hard | {"first_name_only", "key_value"})
    d.t("</Nome><Cognome>").p("PERSON", p.last, p.hard | {"surname_only", "key_value"})
    d.t("</Cognome></Anagrafica>\n   </DatiAnagrafici>\n   <Sede><Indirizzo>").p("ADDRESS", p.street)
    d.t("</Indirizzo><CAP>" + p.town[2] + "</CAP><Comune>" + p.town[0] + "</Comune><Provincia>" + p.town[1] +
        "</Provincia><Nazione>IT</Nazione></Sede>\n   <Contatti><Telefono>")
    d.p("PHONE", p.phone.replace(" ", ""))
    d.t("</Telefono><Email>").p("EMAIL", p.email)
    d.t("</Email></Contatti>\n  </CedentePrestatore>\n  <CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>")
    d.i("company_vat", I.piva(r))
    d.t("</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>")
    org(d)
    d.t("</Denominazione></Anagrafica></DatiAnagrafici></CessionarioCommittente>\n </FatturaElettronicaHeader>\n <FatturaElettronicaBody>\n  <DatiGeneraliDocumento><Data>")
    d.n("DOC_DATE", f"{r.randint(2023, 2026)}-{r.randint(1, 12):02d}-{r.randint(1, 28):02d}")
    d.t("</Data><Numero>").n("DOC_NUMBER", f"{r.randint(1, 300)}/{r.choice(['A', 'FE', 'PA'])}")
    d.t("</Numero><ImportoTotaleDocumento>").n("MONEY", f"{r.randint(50, 9000)}.{r.randint(0, 99):02d}")
    d.t("</ImportoTotaleDocumento></DatiGeneraliDocumento>\n  <DatiPagamento><IBAN>").p("IBAN", I.iban(r))
    d.t("</IBAN></DatiPagamento>\n </FatturaElettronicaBody>\n</p:FatturaElettronica>\n")


def vcard(d: Doc) -> None:
    r = d.r
    p = I.person(r, .25)
    if r.random() < .6:
        d.t("BEGIN:VCARD\nVERSION:3.0\nN:").p("PERSON", p.last, p.hard | {"surname_only", "key_value"}).t(";")
        d.p("PERSON", p.first, p.hard | {"first_name_only", "key_value"})
        d.t(";;;\nFN:").p("PERSON", p.full, p.hard)
        d.t("\nTEL;TYPE=CELL:").p("PHONE", p.phone)
        d.t("\nEMAIL;TYPE=INTERNET:").p("EMAIL", p.email)
        d.t("\nADR;TYPE=HOME:;;").p("ADDRESS", f"{p.street};{p.town[0]};{p.town[1]};{p.town[2]}", {"key_value"})
        d.t(";Italia\nBDAY:").p("DATE_OF_BIRTH", f"{p.y}{p.m:02d}{p.d:02d}", {"iso_date"})
        d.t("\nNOTE:cliente dal " + str(r.randint(2010, 2024)) + "\nEND:VCARD\n")
    else:
        d.t("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:")
        d.n("DOC_DATE", f"{r.randint(2025, 2026)}{r.randint(1, 12):02d}{r.randint(1, 28):02d}T{r.randint(8, 18):02d}0000")
        d.t("\nSUMMARY:" + r.choice(["Visita ", "Colloquio ", "Udienza "]))
        S.name(d, p, "fl")
        d.t("\nLOCATION:").p("ADDRESS", S.address_value(d, p))
        d.t("\nATTENDEE;CN=")
        S.name(d, I.person(r), "fl")
        d.t(":mailto:")
        S.mail(d, I.person(r), 0)
        d.t("\nDESCRIPTION:portare referti e tessera sanitaria. Cell. ").p("PHONE", p.phone)
        d.t("\nEND:VEVENT\nEND:VCALENDAR\n")


def sql_dump(d: Doc) -> None:
    r = d.r
    d.t("-- dump tabella clienti " + I.doc_date(r) + "\nINSERT INTO clienti (id, cognome, nome, cf, nato_a, nato_il, email, iban) VALUES\n")
    n = r.randint(3, 5)
    for k in range(n):
        p = I.person(r, .2)
        d.t(f"({r.randint(100, 99999)}, '").p("PERSON", p.last.replace("'", "''"), p.hard | {"surname_only", "table_cell"})
        d.t("', '").p("PERSON", p.first, p.hard | {"first_name_only", "table_cell"})
        d.t("', '").p("FISCAL_CODE", p.cf)
        d.t("', '").p("BIRTH_PLACE", p.birth_town.replace("'", "''"), {"no_cue", "table_cell"})
        d.t("', '").p("DATE_OF_BIRTH", f"{p.y}-{p.m:02d}-{p.d:02d}", {"iso_date", "table_cell"})
        d.t("', '").p("EMAIL", p.email)
        d.t("', ")
        if r.random() < .3:
            d.t("NULL")
        else:
            d.t("'").p("IBAN", I.iban(r)).t("'")
        d.t(")" + (",\n" if k < n - 1 else ";\n"))


def config(d: Doc) -> None:
    r = d.r
    p = I.person(r, .1)
    if r.random() < .5:
        d.t("# deploy.yaml - ambiente staging\nservice:\n  name: billing-api\n  version: ").n("CODE", f"{r.randint(1, 4)}.{r.randint(0, 9)}.{r.randint(0, 30)}")
        d.t("\n  owner: ").p("EMAIL", p.email)
        d.t("\n  oncall_phone: \"").p("PHONE", p.phone)
        d.t("\"\ndatabase:\n  host: ").p("IP_ADDRESS", I.ipv4(r))
        d.t("\n  user: ").p("USERNAME", I._slug(p.first)[0] + I._slug(p.last))
        d.t("\nallowlist:\n  - ").p("IP_ADDRESS", I.ipv6(r), {"ipv6"})
        d.t("\n  - ").i("internal_ip", f"10.{r.randint(0, 255)}.{r.randint(0, 255)}.{r.randint(1, 254)}")
        d.t("\n# referente: ")
        S.name(d, p, "fl")
        d.t("\n")
    else:
        d.t("[utente]\nnome = ").p("PERSON", p.full, p.hard)
        d.t("\nlogin = ").p("USERNAME", I._slug(p.last) + I.digits(r, 2))
        d.t("\nemail = ").p("EMAIL", p.email)
        d.t("\n\n[rete]\nip_pubblico = ").p("IP_ADDRESS", I.ipv4(r))
        d.t("\nip6 = ").p("IP_ADDRESS", I.ipv6(r), {"ipv6"})
        d.t("\ngateway = ").i("internal_ip", f"192.168.{r.randint(0, 9)}.1")
        d.t("\ntimeout = " + str(r.randint(5, 120)) + "\n")


def fixed_width(d: Doc) -> None:
    r = d.r
    d.t("ANAGRAFE ASSISTITI - ESTRAZIONE " + I.doc_date(r) + "\nCOGNOME             NOME           SESSO DATA NASC.  COMUNE NASCITA       COD.FISCALE\n")
    for _ in range(r.randint(3, 6)):
        p = I.person(r, .15)
        dt = f"{p.d:02d}{I.MON3[p.m - 1]}{p.y}" if r.random() < .4 else f"{p.d:02d}/{p.m:02d}/{p.y}"
        d.p("PERSON", p.last.upper(), p.hard | {"surname_only", "uppercase", "table_cell"})
        d.t(" " * max(1, 20 - len(p.last))).p("PERSON", p.first.upper(), p.hard | {"first_name_only", "uppercase", "table_cell"})
        d.t(" " * max(1, 15 - len(p.first)) + ("F" if p.female else "M") + "     ")
        d.p("DATE_OF_BIRTH", dt, {"table_cell"} | ({"month_abbrev"} if not dt[2] == "/" else set()))
        d.t(" " * max(1, 12 - len(dt))).p("BIRTH_PLACE", p.birth_town.upper(), {"no_cue", "uppercase", "table_cell"})
        d.t(" " * max(1, 21 - len(p.birth_town))).p("FISCAL_CODE", p.cf)
        d.t("\n")


def md_table(d: Doc) -> None:
    r = d.r
    d.t("## " + r.choice(["Turni reparto", "Elenco volontari", "Partecipanti corso sicurezza", "Inquilini stabile"]) + "\n\n")
    cols = r.choice([("Nome", "Matricola", "Telefono"), ("Partecipante", "Email", "Badge"), ("Nominativo", "Cellulare", "Targa auto")])
    d.t("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n")
    for _ in range(r.randint(3, 6)):
        p = I.person(r, .2)
        d.t("| ")
        S.name(d, p, r.choice(["fl", "Lf", "UPPER", "init"]))
        for c in cols[1:]:
            d.t(" | ")
            if c in ("Matricola", "Badge"):
                d.p("EMPLOYEE_ID", r.choice([I.digits(r, 5), "B" + I.digits(r, 4), I.digits(r, 3) + "-" + I.digits(r, 3)]), {"table_cell"})
            elif c in ("Telefono", "Cellulare"):
                d.p("PHONE", p.phone, {"table_cell"})
            elif c == "Email":
                d.p("EMAIL", p.email, {"table_cell"})
            else:
                d.p("LICENSE_PLATE", I.plate(r), {"table_cell"})
        d.t(" |\n")


DIGITAL = {"informal": [("dettatura", dettatura, 13, 0, 0), ("mail_thread", mail_thread, 15, .05, 0),
                        ("telegram", sms, 13, 0, 0), ("forum", forum, 11, 0, 0), ("ticket", ticket, 11, 0, 0)],
           "structured": [("fattura_xml", fattura_xml, 12, 0, 0), ("vcard_ical", vcard, 11, 0, 0),
                          ("sql_dump", sql_dump, 10, 0, 0), ("config", config, 9, 0, 0),
                          ("fixed_width", fixed_width, 10, 0, 0), ("markdown_table", md_table, 11, 0, 0)]}

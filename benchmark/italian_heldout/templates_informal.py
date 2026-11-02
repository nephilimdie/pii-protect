"""Hand-authored templates: chats, CRM exports, logs, JSON APIs, spreadsheets, mixed IT/EN mail,
free-text letters and helpdesk tickets.

Why: much PII reaches an anonymizer as machine output or casual typing, where labels are column
headers, JSON keys or nothing at all.
What: functions Ctx -> markup string; low() lowercases a marked fragment (values included).
Test: tests/test_heldout.py renders every template for several seeds and checks span integrity.
"""
from __future__ import annotations

import fakedata as F
from markup import _MARK, Ctx
from templates_formal import indirect


def low(s: str) -> str:
    """What: lowercase literal text and span values (not span types) of a marked fragment."""
    out, pos = [], 0
    for m in _MARK.finditer(s):
        out.append(s[pos:m.start()].lower())
        hard = ",".join(sorted(set(filter(None, m.group(4).split(","))) | {"lowercase"})) if m.group(1) == "\x02" else m.group(4)
        out.append(f"{m.group(1)}{m.group(2)}\x1f{m.group(3).lower()}\x1f{hard}\x03")
        pos = m.end()
    return "".join(out) + s[pos:].lower()


def whatsapp(c: Ctx) -> str:
    a, b = c.person(foreign=.3), c.person()
    d = f"{c.rng.randint(1, 28):02d}/{c.rng.randint(1, 12):02d}/{c.rng.randint(23, 26)}"
    ts = lambda: f"[{d}, {c.rng.randint(7, 23):02d}:{c.rng.randint(0, 59):02d}:{c.rng.randint(0, 59):02d}]"  # noqa: E731
    na, nb = c.name(a, c.pick("nick", "first", "full")), c.name(b, c.pick("nick", "first", "full"))
    msgs = [f"{ts()} {na}: {low(c.pick('ciao! ', 'ehi ', 'buongiorno ') + 'mi mandi i dati per il contratto?')}",
            f"{ts()} {nb}: {low('allora: ' + c.name(b, 'full') + ' cf ' + c.cf(b))}",
            f"{ts()} {nb}: {low('nato il ' + c.dob(b) + ' a ' + c.bplace(b))}",
            f"{ts()} {nb}: {low('abito in ' + c.addr(b, c.pick(2, 5, 1)))} {c.pick('🏠', '', '')}",
            f"{ts()} {na}: {c.pick('perfetto', 'ok grazie', 'top')}. e l'iban x il rimborso?",
            f"{ts()} {nb}: {c.iban('IT')}",
            f"{ts()} {na}: {low('se serve chiamami al ' + c.phone(a) + ' dopo le 18')}",
            f"{ts()} {nb}: {c.pick('ah dimenticavo, la mail è ' + c.email(b), 'scrivimi anche su ' + c.email(b))}",
            f"{ts()} {na}: {c.pick('ok passo da te sabato', 'ti giro tutto a ' + c.name(c.person(), 'nick') + ' che fa la pratica', 'grazie mille!!')}",
            f"{ts()} {nb}: <Media omessi>"]
    k = c.rng.randint(5, len(msgs))
    return "\n".join(msgs[:k]) + "\n"


def crm_csv(c: Ctx) -> str:
    sep = c.pick(";", ",", "\t")
    q = (lambda s: f'"{s}"') if sep == "," else (lambda s: s)
    hdr = sep.join(["id", "nome", "cognome", "email", "telefono", "indirizzo", "data_nascita", "codice_fiscale", "note", "fatturato"])
    rows = []
    for i in range(c.rng.randint(3, 7)):
        p = c.person()
        caps = c.chance(.3)
        first = c.pii("PERSON", p.first.upper() if caps else p.first, "first_name_only", *(["uppercase"] if caps else []))
        last = c.pii("PERSON", p.last.upper() if caps else p.last, "surname_only", *(["uppercase"] if caps else []))
        note = c.pick("cliente storico", f"richiamare {c.ddate()}", f"referente: {c.name(c.person(), 'surname')}", "", "NO marketing",
                      f"moglie di {c.name(c.person(), 'full')}", f"ex {c.org()}")
        rows.append(sep.join([c.neg("DOC_NUMBER", f"C{F.digits(c.rng, 6)}"), q(first), q(last), c.email(p), c.phone(p),
                              q(c.addr(p, c.pick(5, 1, 0))), c.dob(p), c.cf(p), q(note) if note else "", c.money()]))
    return f"# export {c.org()} CRM {c.ddate()}\n{hdr}\n" + "\n".join(rows) + "\n"


def server_log(c: Ctx) -> str:
    out = []
    for _ in range(c.rng.randint(4, 9)):
        p = c.person()
        t = f"2025-{c.rng.randint(1, 12):02d}-{c.rng.randint(1, 28):02d}T{c.rng.randint(0, 23):02d}:{c.rng.randint(0, 59):02d}:{c.rng.randint(0, 59):02d}Z"
        user = F._plain(p.first).lower()[0] + "." + F._plain(p.last).lower()
        k = c.rng.randrange(6)
        if k == 0:
            out.append(f"{c.pii('IP_ADDRESS', F.ip(c.rng))} - {c.pii('USERNAME', user)} [{t}] \"GET /api/v2/clienti?email="
                       f"{c.pii('EMAIL', p.email.replace('@', '%40'), 'urlencoded')} HTTP/1.1\" {c.code('http')} {c.rng.randint(200, 9000)}")
        elif k == 1:
            out.append(f"{t} INFO  auth.LoginService - login ok user={c.pii('USERNAME', user + str(c.rng.randint(1, 99)))} "
                       f"src={c.pii('IP_ADDRESS', F.ip(c.rng))} req={c.code('hash')}")
        elif k == 2:
            out.append(f"{t} WARN  billing - card declined for {c.name(p, 'full')} pan={c.card()} amount={c.money()}")
        elif k == 3:
            out.append(f"{t} DEBUG anagrafe.sync payload cf={c.cf(p)} nome=\"{c.name(p, 'caps')}\" tel={c.phone(p)} v{c.code('ver')}")
        elif k == 4:
            out.append(f"{t} ERROR mailer - SMTP 550 rejected recipient <{c.email(p)}> (job {c.code('hash')})")
        else:
            out.append(f"{t} INFO  shipping - consegna a {c.addr(p, c.pick(1, 0))} per ordine {c.prot()} corriere {c.org()}")
    return "\n".join(out) + "\n"


def json_api(c: Ctx) -> str:
    p = c.person()
    y, m, d = p.birth
    ind = "\n  " if c.chance(.6) else ""
    return ("{" + ind + f'"requestId": "{c.code("hash")}",' + ind + f'"customer": {{"firstName": "{c.name(p, "first")}", '
            f'"lastName": "{c.name(p, "surname")}", "taxCode": "{c.cf(p)}", "birthDate": "{c.pii("DATE_OF_BIRTH", f"{y}-{m:02d}-{d:02d}")}", '
            f'"birthPlace": "{c.bplace(p)}",' + ind + f'"address": {{"street": "{c.pii("ADDRESS", p.street + " " + p.number)}", '
            f'"zip": "{p.city[2]}", "city": "{p.city[0]}"}}, "mobile": "{c.phone(p)}", "email": "{c.email(p)}"}},' + ind
            + f'"payment": {{"method": "SEPA", "iban": "{c.iban()}", "amount": "{c.money()}"}},' + ind
            + f'"device": {{"ip": "{c.pii("IP_ADDRESS", F.ip(c.rng))}", "ua": "Mozilla/5.0", "appVersion": "{c.code("ver")}"}},' + ind
            + f'"loyaltyCard": "{c.pii("CONTRACT_ID", "FID" + F.digits(c.rng, 10))}", "createdAt": "{c.ddate()}"' + ("\n" if ind else "") + "}\n")


def spreadsheet(c: Ctx) -> str:
    sep = c.pick("\t", " | ")
    head = sep.join(["Cognome", "Nome", "Reparto", "Matricola", "IBAN", "Targa auto aziendale", "Netto"])
    rows = []
    for _ in range(c.rng.randint(3, 8)):
        p = c.person()
        rows.append(sep.join([c.name(p, "surname"), c.name(p, "first"), c.pick("Logistica", "Amministrazione", "Vendite", "R&D"),
                              c.pii("EMPLOYEE_ID", c.pick(F.digits(c.rng, 5), "E" + F.digits(c.rng, 4))), c.iban(),
                              c.pii("LICENSE_PLATE", F.plate(c.rng)) if c.chance(.5) else "-", c.money()]))
    return f"Foglio1 - Riepilogo {c.pick(*F.MONTHS)} ({c.org()})\n{head}\n" + "\n".join(rows) + f"\nTotale{sep}{sep}{sep}{sep}{sep}{sep}{c.money()}\n"


def mixed_en(c: Ctx) -> str:
    p, q = c.person(), c.person()
    if c.chance(.5):
        return (f"Subject: {c.pick('Escalation', 'KYC check', 'Refund request')} - customer {c.name(p, 'caps_surname')}\n\n"
                f"Hi {c.name(q, 'first')},\nthe customer called again today. Details below (please don't forward outside the team):\n"
                f"- Name: {c.name(p)}\n- Tax code (codice fiscale): {c.cf(p)}\n- DOB: {c.dob(p)}, born in {c.bplace(p)}\n"
                f"- Lives at {c.addr(p, c.pick(0, 1, 4))}\n- Mobile {c.phone(p)}, e-mail {c.email(p)}\n"
                f"She says the {c.money()} refund was sent to the wrong account; the correct IBAN is {c.iban()}.\n"
                f"Per la normativa ({c.law()}) dobbiamo rispondere entro 30 giorni. Ticket {c.prot()}.\nThanks,\n{c.name(q, 'initial')}\n")
    return (f"#ops-italia  {c.name(q, 'nick')}: guys the import for {c.org()} failed again\n"
            f"#ops-italia  {c.name(p, c.pick('first', 'nick'))}: which record?\n"
            f"#ops-italia  {c.name(q, 'nick')}: the one for {c.name(c.person())}, user {c.pii('USERNAME', '@' + F._plain(p.last).lower() + str(c.rng.randint(1, 99)))}, "
            f"logged in from {c.pii('IP_ADDRESS', F.ip(c.rng))}\n"
            f"#ops-italia  {c.name(p, 'first')}: ah ok, è quella col passaporto {c.pii('ID_DOCUMENT', F.passport(c.rng))} scaduto. "
            f"I'll fix it after the {c.code('ver')} deploy\n")


def narrativa(c: Ctx) -> str:
    p, x = c.person(), c.person()
    k = c.rng.randrange(3)
    if k == 0:
        return (f"Gentile redazione,\nmi chiamo {c.name(p, 'full')} e vi scrivo da {p.city[0]}. Da mesi {c.org()} mi addebita bollette che non mi spettano "
                f"({c.money()} solo a {c.pick(*F.MONTHS)}). Ho chiamato decine di volte dal mio {c.phone(p)} senza risposta. "
                f"Il contratto è il {c.pii('CONTRACT_ID', 'IT001E' + F.digits(c.rng, 8))} e l'intestatario era mio padre, {c.name(x, 'full')}, "
                f"mancato lo scorso anno. Abito in {c.addr(p, 5)}, se volete venire a vedere i documenti.\n{c.name(p, 'first')}\n")
    if k == 1:
        return (f"Segnalazione whistleblowing n. {c.prot()} del {c.ddate()}\n"
                f"Descrivo i fatti: {indirect(c)} riceve da tempo pagamenti in contanti dal fornitore. "
                f"Ho visto più volte {c.name(x, 'surname_first')} consegnare buste nel parcheggio, con l'auto {c.pii('LICENSE_PLATE', F.plate(c.rng))}. "
                f"Non indico il mio nome; potete rispondermi a {c.email(p)}.\n")
    return (f"Esposto a: {c.body()}\n{'La sottoscritta' if p.female else 'Il sottoscritto'}, {c.title(p)}{c.name(p)}, {c.birth(p)}, espone quanto segue. "
            f"Il vicino {c.name(x, 'surname')}, che vive sopra di me in {c.addr(x, 5)}, da {c.rng.randint(2, 14)} mesi "
            f"{c.pick('accumula rifiuti sul balcone', 'tiene musica ad alto volume di notte', 'ha occupato il mio posto auto')}. "
            f"Allego le foto e la diffida del {c.ddate()}. Recapito: {c.phone(p)}.\n")


def ticket(c: Ctx) -> str:
    p, op = c.person(), c.person()
    return (f"[Helpdesk] Ticket #{c.neg('DOC_NUMBER', F.digits(c.rng, 6))} - {c.pick('Accesso negato', 'Cambio IBAN', 'Reset password', 'Errore 502')}\n"
            f"Aperto da: {c.name(p)} <{c.email(p)}>   Utente: {c.pii('USERNAME', c.pick(F._plain(p.first).lower() + '.' + F._plain(p.last).lower(), F._plain(p.last).lower()[:6] + F.digits(c.rng, 2)))}\n"
            f"Priorità: {c.pick('alta', 'media')}  Stato: aperto  Creato: {c.ddate()}\n\n"
            f"{low(c.pick('salve, ', 'buongiorno, ') + 'non riesco ad entrare nel portale da ieri. ')}"
            f"{c.pick('il mio indirizzo IP è ' + c.pii('IP_ADDRESS', F.ip(c.rng)), 'il codice errore è ' + c.code('http'))}. "
            f"{c.pick('vi lascio il cell ' + c.phone(p), 'codice cliente ' + c.pii('CONTRACT_ID', 'CL-' + F.digits(c.rng, 7)), 'il cf è ' + c.cf(p))}.\n\n"
            f"--- Risposta operatore ({c.name(op, 'first')}) ---\nGentile {c.name(p, c.pick('surname', 'full'))}, abbiamo reimpostato l'accesso. "
            f"{c.pick('Il nuovo IBAN ' + c.iban() + ' è stato registrato.', 'La invitiamo a non condividere le credenziali.')}\n")


INFORMAL = {
    "chat": [("whatsapp", whatsapp, 24, 0), ("mixed_en", mixed_en, 20, 0)],
    "structured": [("crm_csv", crm_csv, 16, 0), ("server_log", server_log, 18, 0), ("json_api", json_api, 18, 0),
                   ("spreadsheet", spreadsheet, 14, 0)],
    "free_text": [("narrativa", narrativa, 24, 0), ("ticket", ticket, 18, 0)],
}

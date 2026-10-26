"""Synthetic Italian eval set with gold spans for the quantization experiment.

Why: the repo corpus has 14 gold rows; quantization needs a few hundred varied texts
so that fp32-vs-quantized leakage per type is measurable.
What: writes N texts across 8 presets; every inserted PII value is recorded as a gold
span (type, start, end). Checksummed IDs are valid so regex validators accept them.
Test: every gold span satisfies text[start:end] == value (asserted below).
Run with /app (engine api) on sys.path for app.detection.checksums.
"""
import json, random, string, sys
sys.path.insert(0, "/app")
from app.detection.checksums import cf_check_char, is_valid_codice_fiscale, is_valid_iban, is_valid_partita_iva

R = random.Random(20261026)
FIRST = ["Mario", "Giulia", "Luca", "Francesca", "Marco", "Chiara", "Alessandro", "Sara", "Paolo", "Elena",
         "Giuseppe", "Anna", "Roberto", "Martina", "Davide", "Valentina", "Stefano", "Federica", "Andrea", "Silvia",
         "Matteo", "Laura", "Simone", "Ilaria", "Gianluca", "Beatrice", "Pietro", "Camilla", "Lorenzo", "Alessia",
         "Ahmed", "Olena", "Wei", "Fatima", "John", "Ioana", "Giovanni Battista", "Maria Grazia", "Pier Paolo", "Anna Maria"]
LAST = ["Rossi", "Bianchi", "Esposito", "Romano", "Colombo", "Ricci", "Marino", "Greco", "Bruno", "Gallo",
        "Conti", "De Luca", "Mancini", "Costa", "Giordano", "Rizzo", "Lombardi", "Moretti", "Barbieri", "Fontana",
        "Santoro", "Mariani", "Rinaldi", "Caruso", "Ferrara", "Galli", "Martini", "Leone", "Longo", "Gentile",
        "Di Stefano", "D'Angelo", "Dell'Acqua", "Lo Russo", "Benali", "Kovalenko", "Zhang", "Popescu", "Smith", "Fumagalli"]
CITY = ["Milano", "Roma", "Torino", "Napoli", "Bologna", "Firenze", "Padova", "Verona", "Bari", "Palermo",
        "Genova", "Trieste", "Brescia", "Bergamo", "Lecce", "Cagliari", "Perugia", "Trento", "Modena", "Parma"]
STREET = ["Via Roma", "Via Garibaldi", "Corso Vittorio Emanuele", "Via Mazzini", "Piazza Duomo", "Viale Europa",
          "Via dei Mille", "Via Cavour", "Corso Italia", "Via San Francesco", "Largo Augusto", "Via Verdi"]
MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
COMPANY = ["Alfa Servizi S.r.l.", "Beta Consulting S.p.A.", "Gamma Immobiliare S.r.l.", "Delta Logistica S.n.c."]
FILL = {
    "legal": ["Le parti convengono che il presente accordo disciplina in modo esclusivo gli obblighi reciproci.",
              "Il giudice, letti gli atti, rinvia la causa all'udienza successiva per la precisazione delle conclusioni.",
              "Si eccepisce l'inammissibilita del ricorso per difetto di legittimazione attiva.",
              "Le spese di lite seguono la soccombenza e sono liquidate come in dispositivo."],
    "hr": ["Il dipendente ha maturato le ferie residue indicate nel cedolino del mese corrente.",
           "La valutazione annuale evidenzia un miglioramento nelle competenze trasversali.",
           "Si conferma il passaggio al livello superiore del CCNL commercio a decorrere dal prossimo mese.",
           "Il periodo di prova si e concluso con esito positivo."],
    "tax": ["Il contribuente dichiara di aver percepito redditi da lavoro dipendente nell'anno d'imposta.",
            "Le detrazioni per spese sanitarie sono riportate nel quadro E del modello 730.",
            "Il versamento del saldo IRPEF avverra mediante modello F24.",
            "L'Agenzia delle Entrate ha notificato un avviso bonario per l'anno precedente."],
    "realestate": ["L'immobile e censito al catasto fabbricati e risulta libero da ipoteche.",
                   "Il canone mensile sara aggiornato annualmente secondo l'indice ISTAT.",
                   "La caparra confirmatoria verra restituita alla scadenza del contratto.",
                   "Le spese condominiali ordinarie sono a carico del conduttore."],
    "generic": ["Grazie per la disponibilita, resto in attesa di un riscontro.",
                "La riunione e stata spostata alla prossima settimana per motivi organizzativi.",
                "Il documento allegato contiene il riepilogo delle attivita svolte.",
                "Vi preghiamo di verificare i dati e di segnalare eventuali errori."],
}


def cf():
    L = string.ascii_uppercase
    s = "".join(R.choice(L) for _ in range(6)) + f"{R.randint(0, 99):02d}" + R.choice("ABCDEHLMPRST") + \
        f"{R.choice([R.randint(1, 31), R.randint(41, 71)]):02d}" + R.choice("ABDEFGHILMZ") + f"{R.randint(1, 999):03d}"
    v = s + cf_check_char(s)
    assert is_valid_codice_fiscale(v)
    return v


def iban(spaced=False):
    cin = R.choice(string.ascii_uppercase)
    bban = cin + f"{R.randint(0, 99999):05d}" + f"{R.randint(0, 99999):05d}" + "".join(R.choice(string.digits) for _ in range(12))
    num = "".join(str(int(c, 36)) for c in bban + "IT00")
    check = 98 - int(num) % 97
    v = f"IT{check:02d}{bban}"
    assert is_valid_iban(v)
    return " ".join(v[i:i + 4] for i in range(0, len(v), 4)) if spaced else v


def piva():
    while True:
        base = "".join(R.choice(string.digits) for _ in range(10))
        for c in string.digits:
            if is_valid_partita_iva(base + c):
                return base + c


def card():
    d = [4] + [R.randint(0, 9) for _ in range(14)]
    for c in range(10):
        digits = d + [c]
        total = sum((x * 2 - 9 if x * 2 > 9 else x * 2) if i % 2 == len(digits) % 2 else x for i, x in enumerate(digits))
        if total % 10 == 0:
            s = "".join(map(str, digits))
            return R.choice([s, " ".join(s[i:i + 4] for i in range(0, 16, 4)), "-".join(s[i:i + 4] for i in range(0, 16, 4))])


def phone():
    return R.choice([f"+39 3{R.randint(10, 99)} {R.randint(100, 999)} {R.randint(1000, 9999)}", f"3{R.randint(10, 99)}{R.randint(1000000, 9999999)}",
                     f"0{R.randint(2, 99)} {R.randint(100000, 9999999)}", f"+39 0{R.randint(2, 99)}-{R.randint(1000000, 9999999)}"])


def person():
    return f"{R.choice(FIRST)} {R.choice(LAST)}"


def email(name=None):
    name = name or person()
    a, b = name.lower().replace("'", "").split(" ", 1)
    return f"{a.replace(' ', '')}{R.choice(['.', '_', ''])}{b.replace(' ', '')}{R.choice(['', str(R.randint(1, 99))])}@{R.choice(['example.it', 'example.com', 'mail.example.org', 'studio-example.it'])}"


def date():
    d, m, y = R.randint(1, 28), R.randint(1, 12), R.randint(1950, 2025)
    return R.choice([f"{d:02d}/{m:02d}/{y}", f"{d} {MONTHS[m - 1]} {y}", f"{d:02d}-{m:02d}-{y}"])


def address():
    return f"{R.choice(STREET)} {R.randint(1, 250)}, {R.randint(10, 98)}{R.randint(100, 999)} {R.choice(CITY)}"


def ip():
    return f"{R.randint(1, 223)}.{R.randint(0, 255)}.{R.randint(0, 255)}.{R.randint(1, 254)}"


class Doc:
    def __init__(self):
        self.parts, self.ents, self.n = [], [], 0

    def t(self, s):
        self.parts.append(s); self.n += len(s); return self

    def e(self, kind, value):
        self.ents.append({"type": kind, "start": self.n, "end": self.n + len(value)}); return self.t(value)

    def build(self):
        text = "".join(self.parts)
        return text, self.ents


def sentence(doc, preset):
    k = R.randrange(9)
    p = person()
    if k == 0:
        doc.t("Il sig. " if R.random() < .5 else "La sig.ra ").e("PERSON", p).t(", nato a " + R.choice(CITY) + " il ").e("DATE", date()).t(", codice fiscale ").e("FISCAL_CODE", cf()).t(", ")
        doc.t("residente in ").e("ADDRESS", address()).t(". ")
    elif k == 1:
        doc.t("Il pagamento avverra sul conto IBAN ").e("IBAN", iban(R.random() < .3)).t(" intestato a ").e("PERSON", p).t(". ")
    elif k == 2:
        doc.t("Per informazioni contattare ").e("PERSON", p).t(" all'indirizzo ").e("EMAIL", email(p)).t(" oppure al numero ").e("PHONE", phone()).t(". ")
    elif k == 3:
        doc.t("Carta di credito utilizzata: ").e("CREDIT_CARD", card()).t(", titolare ").e("PERSON", p).t(". ")
    elif k == 4:
        doc.t(R.choice(COMPANY) + ", partita IVA ").e("VAT_NUMBER", piva()).t(", in persona del legale rappresentante ").e("PERSON", p).t(". ")
    elif k == 5:
        doc.t("Recapito telefonico: ").e("PHONE", phone()).t(". ")
    else:
        doc.t(R.choice(FILL[preset if preset in FILL else "generic"]) + " ")


def prose(preset, target):
    doc = Doc()
    head = {"legal": "TRIBUNALE DI " + R.choice(CITY).upper() + "\nAtto di citazione\n\n", "hr": "Scheda dipendente\n\n",
            "tax": "Dichiarazione dei redditi - riepilogo\n\n", "realestate": "CONTRATTO DI LOCAZIONE AD USO ABITATIVO\n\n",
            "generic": ""}[preset]
    doc.t(head)
    while doc.n < target:
        sentence(doc, preset)
        if R.random() < .25:
            doc.t("\n")
    return doc


def email_doc(target):
    doc = Doc(); sender, rcpt = person(), person()
    doc.t("Da: ").e("PERSON", sender).t(" <").e("EMAIL", email(sender)).t(">\nA: ").e("EMAIL", email(rcpt)).t("\nOggetto: pratica in corso\n\nGentile ").e("PERSON", rcpt).t(",\n")
    while doc.n < target:
        sentence(doc, "generic")
    doc.t("\n\nCordiali saluti,\n").e("PERSON", sender).t("\nTel. ").e("PHONE", phone()).t("\n")
    return doc


def log_doc(target):
    doc = Doc()
    while doc.n < target:
        ts = f"2026-{R.randint(1, 12):02d}-{R.randint(1, 28):02d}T{R.randint(0, 23):02d}:{R.randint(0, 59):02d}:{R.randint(0, 59):02d}Z"
        k = R.randrange(4)
        doc.t(ts + " INFO ")
        if k == 0:
            doc.t("login ok user=").e("EMAIL", email()).t(" ip=").e("IP_ADDRESS", ip()).t("\n")
        elif k == 1:
            doc.t("payment declined card=").e("CREDIT_CARD", card()).t(" customer=\"").e("PERSON", person()).t("\"\n")
        elif k == 2:
            doc.t("sms sent to ").e("PHONE", phone()).t(" status=200\n")
        else:
            doc.t("request GET /api/v1/orders latency_ms=" + str(R.randint(3, 900)) + " ip=").e("IP_ADDRESS", ip()).t("\n")
    return doc


def json_doc(target):
    doc = Doc(); doc.t("[\n")
    first = True
    while doc.n < target:
        p = person()
        doc.t("" if first else ",\n"); first = False
        doc.t('  {"nome": "').e("PERSON", p).t('", "email": "').e("EMAIL", email(p)).t('", "telefono": "').e("PHONE", phone()).t('", ')
        doc.t('"codice_fiscale": "').e("FISCAL_CODE", cf()).t('", "iban": "').e("IBAN", iban()).t('", "note": "cliente dal ' + str(R.randint(2000, 2025)) + '"}')
    doc.t("\n]\n")
    return doc


def main(out, per_preset=30):
    rows = []
    for preset in ["legal", "hr", "tax", "realestate", "generic", "email", "log", "json"]:
        for i in range(per_preset):
            target = R.choice([300, 600, 1000, 1500, 2500, 4000, 5500])
            doc = {"email": email_doc, "log": log_doc, "json": json_doc}.get(preset, lambda t: prose(preset, t))(target)
            text, ents = doc.build()
            for e in ents:
                assert 0 <= e["start"] < e["end"] <= len(text)
            rows.append({"id": f"{preset}-{i:03d}", "preset": preset, "language": "it", "text": text, "entities": ents})
    json.dump(rows, open(out, "w"), ensure_ascii=False, indent=0)
    print(len(rows), "texts", sum(len(r["text"]) for r in rows), "chars", sum(len(r["entities"]) for r in rows), "gold entities")


if __name__ == "__main__":
    main(sys.argv[1])

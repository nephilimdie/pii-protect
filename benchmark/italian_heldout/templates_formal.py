"""Hand-authored templates: formal Italian documents (PEC, verbali, atti, ricorsi, payroll, CU, F24,
leases, appraisals, medical reports).

Why: real paperwork mixes labelled fields, run-on legal prose and column layouts; each template
here was written from the author's memory of such documents, not from it_pii_v1 or engine rules.
What: functions Ctx -> markup string; randomness only through c.rng (deterministic per seed).
Test: tests/test_heldout.py renders every template for several seeds and checks span integrity.
"""
from __future__ import annotations

import fakedata as F
from markup import Ctx


def indirect(c: Ctx) -> str:
    """Quasi-identifying descriptions that single out one person without naming them."""
    town = c.rng.choice(F.COMUNI)[0]
    return c.pii("INDIRECT", c.pick(
        f"l'unico farmacista di {town}", f"la vedova dell'ex sindaco di {town}", f"il primario di ortopedia dell'ospedale di {town}",
        "l'inquilina del terzo piano, quella con il pastore tedesco", "il magazziniere che a marzo ha avuto l'infarto sul muletto",
        f"il parroco di {town}", f"l'allenatore della squadra under 14 di {town}", "la candidata trentaquattrenne con invalidità al 75%",
        "il socio di minoranza che ha denunciato l'amministratore", f"la maestra della 3ª B della primaria di {town}",
        "l'unico dipendente in part-time del reparto verniciatura", f"il titolare della tabaccheria in piazza a {town}"))


def pec_email(c: Ctx) -> str:
    a, b = c.person(), c.person()
    return (f"Da: {c.email(a, pec=True)}\nA: {c.neg('ORG', c.pick('protocollo@pec.comune.fano.pu.it', 'ufficio.contenzioso@pec.inps.gov.it'))}\n"
            f"Data: {c.ddate()} {c.rng.randint(8, 19)}:{c.rng.randint(10, 59)}\n"
            f"Oggetto: {c.pick('Istanza di accesso agli atti', 'Riscontro Vs. nota', 'Diffida ad adempiere', 'Trasmissione documentazione')} - prot. {c.prot()}\n\n"
            f"{c.pick('Spett.le Ufficio,', 'Buongiorno,', 'Alla c.a. del Responsabile del procedimento,')}\n"
            f"{c.pick('la/il sottoscritta/o', 'il sottoscritto' if not a.female else 'la sottoscritta', 'scrive')} {c.name(a)}, "
            f"{c.birth(a)}, C.F. {c.cf(a)}, {c.pick('residente in', 'domiciliata/o in', 'con residenza anagrafica in')} {c.addr(a)}, "
            f"in qualità di {c.pick('erede di', 'delegata/o da', 'procuratore di')} {c.name(b)} ({c.pick('cod. fisc.', 'CF', 'codice fiscale')} {c.cf(b)}),\n"
            f"chiede {c.pick('copia del fascicolo', 'la rettifica della posizione', 'lo sgravio della cartella')} ai sensi dell'{c.law()}.\n"
            f"Per comunicazioni: tel. {c.phone(a)}{c.pick('', ' (ore pasti)', ' - whatsapp')}.\n"
            f"Allegati: documento di identità ({c.pick('CIE', 'carta d’identità elettronica')} n. {c.pii('ID_DOCUMENT', F.cie(c.rng))}).\n\n"
            f"Distinti saluti\n{c.name(a, 'caps')}\n"
            f"--\nQuesto messaggio è stato inviato tramite posta elettronica certificata da {c.org()}.\n")


def verbale(c: Ctx) -> str:
    if c.chance(.5):  # verbale di assemblea condominiale
        amm, p1, p2, p3 = (c.person() for _ in range(4))
        return (f"VERBALE DI ASSEMBLEA {c.pick('ORDINARIA', 'STRAORDINARIA')} DEL CONDOMINIO \"{c.pick('Residenza Le Querce', 'Palazzo Aurora', 'Il Gelso')}\"\n"
                f"In data {c.ddate()}, alle ore 18:30, presso {c.pick('la sala riunioni dello studio', 'l’androne della scala B', 'il locale caldaia')}, "
                f"si è riunita l'assemblea regolarmente convocata ex {c.law()}.\n"
                f"Presiede {c.title(p1)}{c.name(p1)}; segretario {c.name(amm)}, amministratore ({c.pick('P.IVA', 'partita iva')} {c.piva()}).\n"
                f"Presenti: {c.name(p1, 'surname_first')} (int. 3, {c.rng.randint(40, 120)} millesimi), {c.name(p2)} (delega a {c.name(p3, 'initial')}), "
                f"{indirect(c)}.\n"
                f"Punto 1. Il condomino {c.name(p2, 'surname')} lamenta infiltrazioni dal lastrico; il tecnico quantifica la spesa in {c.money()}.\n"
                f"Punto 2. Morosità: l'unità di {c.name(p3)} risulta debitrice di {c.money()}; si dà mandato per il decreto ingiuntivo.\n"
                f"Il verbale viene chiuso alle ore 20:10.\n")
    ag, tr = c.person(), c.person()
    return (f"{c.neg('PUBLIC_BODY', c.pick('Polizia Locale di Vasto', 'Comando Polizia Municipale di Bra', 'Polizia Locale Unione Bassa Romagna'))}\n"
            f"VERBALE DI ACCERTAMENTO n. {c.prot()} del {c.ddate()}\n"
            f"Il giorno indicato alle ore {c.rng.randint(0, 23):02d}:{c.rng.randint(0, 59):02d} in {c.pick('via', 'loc.', 'S.P.')} {c.pick('Roma', 'delle Fornaci', '22 km 4+300')} "
            f"l'agente matr. {c.pii('EMPLOYEE_ID', str(c.rng.randint(100, 999)))} ha accertato che il veicolo {c.pick('autovettura', 'motociclo', 'furgone')} "
            f"targa {c.pii('LICENSE_PLATE', c.pick(F.plate(c.rng), F.plate(c.rng).lower(), ' '.join([(t := F.plate(c.rng))[:2], t[2:5], t[5:]])))} "
            f"condotto da {c.name(tr)}, {c.birth(tr)}, residente {c.addr(tr)}, patente n. {c.pii('ID_DOCUMENT', F.patente(c.rng))}, "
            f"violava l'{c.law()}.\nSanzione: {c.money()}. Decurtazione punti: {c.rng.randint(2, 10)}.\n"
            f"Il trasgressore {c.pick('dichiara: «non mi ero accorto del semaforo»', 'non rilascia dichiarazioni', 'chiede copia del verbale')}.\n"
            f"Firma dell'agente ____ Firma del trasgressore ____\n")


def atto_citazione(c: Ctx) -> str:
    att, conv, avv = c.person(), c.person(), c.person()
    rg = f"{c.rng.randint(150, 19999)}/{c.rng.randint(2022, 2026)}"
    return (f"{c.neg('PUBLIC_BODY', c.pick('TRIBUNALE ORDINARIO DI VERONA', 'TRIBUNALE DI NAPOLI NORD', 'TRIBUNALE DI TRENTO'))}\n"
            f"ATTO DI CITAZIONE {c.pick('IN OPPOSIZIONE A DECRETO INGIUNTIVO', '', 'PER RISARCIMENTO DANNI')}\n"
            f"Per {c.name(att, c.pick('caps', 'caps_surname', 'full'))} ({c.cf(att)}), {c.birth(att)}, elettivamente domiciliat{'a' if att.female else 'o'} "
            f"presso lo studio dell'Avv. {c.name(avv)} ({c.email(avv, pec=True)}) che l{'a' if att.female else 'o'} rappresenta e difende "
            f"giusta procura in calce al presente atto\n- attore -\ncontro\n{c.name(conv)}, residente in {c.addr(conv)}, "
            f"{c.pick('C.F.', 'cod. fisc.')} {c.cf(conv)}\n- convenut{'a' if conv.female else 'o'} -\n"
            f"PREMESSO CHE\n1) con scrittura privata del {c.ddate(2018, 2023)} il{c.pick(' sig.', '')} {c.name(conv, 'surname')} "
            f"si obbligava a versare all'attore la somma di {c.money()};\n"
            f"2) nonostante la diffida del {c.ddate()} (racc. A/R n. {c.prot()}) nulla è stato corrisposto;\n"
            f"3) è stato esperito senza esito il procedimento di mediazione ex {c.law()} (proc. n. {c.pii('CASE_ID', rg)});\n"
            f"tutto ciò premesso, l'attore CITA {c.name(conv, 'caps')} a comparire all'udienza del {c.ddate(2026, 2027)} "
            f"innanzi al {c.body()}, con invito a costituirsi nel termine di legge.\n"
            f"Si dichiara che il valore della causa è di {c.money()} e il contributo unificato di {c.money()}.\n"
            f"Avv. {c.name(avv, 'initial')}\n")


def ricorso(c: Ctx) -> str:
    r = c.person()
    if c.chance(.5):
        return (f"AL GIUDICE DI PACE DI {c.pick('LECCE', 'FANO', 'TERMOLI', 'SULMONA')}\nRICORSO EX ART. 7 D.LGS. 150/2011\n"
                f"Il/La ricorrente {c.name(r)} {c.pick('(CF ', '- codice fiscale ')}{c.cf(r)}{c.pick(')', '')}, {c.birth(r)}, "
                f"residente a {c.addr(r, c.pick(4, 7, 0))}, tel. {c.phone(r)}, email {c.email(r)},\n"
                f"proprietari{'a' if r.female else 'o'} del veicolo targato {c.pii('LICENSE_PLATE', F.plate(c.rng))},\n"
                f"PROPONE RICORSO avverso il verbale n. {c.prot()} notificato il {c.ddate()} dal {c.body()}, "
                f"con cui è stata irrogata la sanzione di {c.money()} per violazione dell'{c.law()}, per i seguenti\nMOTIVI\n"
                f"Il giorno dell'accertamento il veicolo si trovava presso l'officina {c.org()}, come da fattura n. {c.prot()}.\n"
                f"Chiede la sospensione dell'efficacia esecutiva e l'annullamento del verbale.\n{c.pick('Con osservanza.', 'Salvis iuribus.')}\n"
                f"{c.pick('Luogo e data', 'Firma')}: ______ {c.name(r, 'caps')}\n")
    dat = c.person()
    return (f"TRIBUNALE DI {c.pick('BERGAMO', 'CAGLIARI', 'ANCONA')} - SEZIONE LAVORO\nRICORSO EX ART. 414 C.P.C.\n"
            f"per {c.name(r, 'surname_first')}, nat{'a' if r.female else 'o'} il {c.dob(r)}, c.f. {c.cf(r)}, "
            f"già dipendente con matricola n. {c.pii('EMPLOYEE_ID', c.pick(F.digits(c.rng, 6), 'MAT-' + F.digits(c.rng, 5)))} "
            f"(posizione INPS {c.pii('SOCIAL_SECURITY', F.digits(c.rng, 10))})\ncontro\n{c.org()} in persona del legale rappresentante p.t. "
            f"{c.name(dat)}, P.IVA {c.company_vat()}\n"
            f"FATTO\nIl ricorrente è stato assunto il {c.ddate(2012, 2019)} con mansioni di {c.pick('magazziniere', 'operaio di III livello', 'impiegata amministrativa')}. "
            f"Il {c.ddate()} riceveva lettera di licenziamento per giusta causa, contestata ex {c.law()}. "
            f"I colleghi indicano come responsabile dell'accaduto {indirect(c)}.\n"
            f"Si chiede la reintegrazione e il pagamento delle retribuzioni non percepite pari a {c.money()}.\n")


def busta_paga(c: Ctx) -> str:
    p = c.person()
    mat = c.pick(F.digits(c.rng, 5), "0" + F.digits(c.rng, 5), f"D{F.digits(c.rng, 4)}")
    lines = [f"{c.org()}   C.F./P.IVA {c.company_vat()}   Pos. INAIL {c.neg('CODE', F.digits(c.rng, 8))}",
             f"CEDOLINO PAGA - {c.pick(*F.MONTHS).upper()} {c.rng.randint(2023, 2026)}",
             f"Matricola  Cognome e nome                    Codice fiscale       Liv.  Qualifica",
             f"{c.pii('EMPLOYEE_ID', mat)}     {c.name(p, c.pick('caps', 'caps_surname', 'surname_first'))}    {c.cf(p)}     {c.rng.randint(1, 7)}°    {c.pick('Impiegato', 'Operaio', 'Quadro')}",
             f"Data assunzione: {c.rng.randint(1, 28):02d}/{c.rng.randint(1, 12):02d}/{c.rng.randint(2005, 2023)}   Data di nascita: {c.dob(p)}",
             f"Indirizzo: {c.addr(p, c.pick(3, 0, 6))}",
             f"IBAN accredito: {c.iban('IT')}",
             "VOCE                         ORE/GG     COMPETENZE      TRATTENUTE",
             f"Retribuzione ordinaria        {c.rng.randint(150, 173)},00    {c.money()}",
             f"Straordinario 25%              {c.rng.randint(1, 20)},00     {c.money()}",
             f"Contributi IVS 9,19%                                   {c.money()}",
             f"IRPEF lorda ({c.law()})                                {c.money()}",
             f"NETTO IN BUSTA                                         {c.money()}",
             f"Note: {c.pick('assegno unico gestito da INPS', 'trattenuta sindacale', 'conguaglio 730')}"]
    return "\n".join(lines) + "\n"


def cu(c: Ctx) -> str:
    p = c.person()
    y = c.rng.randint(2023, 2026)
    caps = c.chance(.6)
    last = c.name(p, "surname") if not caps else c.pii("PERSON", p.last.upper(), "surname_only", "uppercase")
    first = c.name(p, "first") if not caps else c.pii("PERSON", p.first.upper(), "first_name_only", "uppercase")
    city, prov, cap, _ = p.city
    return (f"CERTIFICAZIONE UNICA {y}\nCERTIFICAZIONE DI CUI ALL'ART. 4, COMMI 6-ter e 6-quater, DEL D.P.R. 22 LUGLIO 1998, n. 322\n"
            f"DATI RELATIVI AL SOSTITUTO D'IMPOSTA\nCodice fiscale {c.company_vat()}   Cognome o Denominazione {c.org()}\n"
            f"DATI RELATIVI AL DIPENDENTE, PENSIONATO O ALTRO PERCETTORE DELLE SOMME\n"
            f"1 Codice fiscale {c.cf(p)}\n2 Cognome {last}   3 Nome {first}   4 Sesso {'F' if p.female else 'M'}\n"
            f"5 Data di nascita {c.dob(p)}   6 Comune (o Stato estero) di nascita {c.bplace(p)}   7 Provincia {'EE' if p.foreign else c.pick('NA', 'TO', 'PG')}\n"
            f"DOMICILIO FISCALE AL 01/01/{y - 1}\n10 Comune {city.upper()}   11 Provincia {prov}   "
            f"12 Codice comune {c.neg('CODE', c.rng.choice(F.COMUNI)[3])}\n"
            f"DATI FISCALI\n1 Redditi di lavoro dipendente {c.money()}   21 Ritenute IRPEF {c.money()}\n"
            f"Data {c.ddate(y, y)}   Firma del sostituto ______\n")


def f24(c: Ctx) -> str:
    p = c.person()
    y = c.rng.randint(2022, 2025)
    rows = "\n".join(f"{c.code('tributo')}        {c.pick('0101', '0000', '0012')}    {y}       {c.money()}" for _ in range(c.rng.randint(1, 3)))
    return (f"MODELLO F24 - {c.pick('DELEGA IRREVOCABILE A', 'Delega di pagamento presso')} {c.org()}\n"
            f"CONTRIBUENTE\ncodice fiscale {c.cf(p)}\ndati anagrafici: cognome, denominazione o ragione sociale {c.name(p, 'surname')} "
            f"nome {c.name(p, 'first')}\ndata di nascita {c.dob(p)}  sesso {'F' if p.female else 'M'}  comune (o Stato estero) di nascita {c.bplace(p)}\n"
            f"domicilio fiscale: {c.addr(p, c.pick(3, 4))}\n"
            f"SEZIONE ERARIO\ncodice tributo  rateazione  anno rif.  importi a debito versati\n{rows}\n"
            f"SEZIONE IMU E ALTRI TRIBUTI LOCALI\ncodice ente {c.neg('CODE', c.rng.choice(F.COMUNI)[3])}  codice tributo {c.code('tributo')}  "
            f"importo {c.money()}\nESTREMI DEL VERSAMENTO\ndata {c.ddate()}  codice ABI {c.neg('CODE', F.digits(c.rng, 5))}  "
            f"addebito su IBAN {c.iban('IT')}\n"
            f"Descrizione: {c.pick('saldo IRPEF', 'acconto cedolare secca', 'IMU seconda casa', 'ravvedimento operoso')} "
            f"{c.pick('per conto del coniuge ' + c.name(c.person()), 'anno ' + str(y), 'ex ' + c.law())}\n")


def locazione(c: Ctx) -> str:
    loc, con = c.person(), c.person()
    city, prov, cap, _ = con.city
    return (f"CONTRATTO DI LOCAZIONE AD USO ABITATIVO ({c.pick('4+4', '3+2 a canone concordato', 'transitorio')})\n"
            f"Con la presente scrittura privata tra:\n{c.name(loc, 'caps')}, {c.birth(loc)}, codice fiscale {c.cf(loc)}, "
            f"di seguito «locatore», e\n{c.name(con)}, {c.birth(con)}, {c.pick('titolare di permesso di soggiorno n.', 'documento:', 'passaporto n.')} "
            f"{c.pii('ID_DOCUMENT', c.pick(F.passport(c.rng), F.cie(c.rng), 'RM' + F.digits(c.rng, 7)))}, C.F. {c.cf(con)}, di seguito «conduttore»,\n"
            f"si conviene quanto segue:\nArt. 1 - Il locatore concede in locazione l'unità immobiliare sita in {c.addr(con, c.pick(0, 1, 6))}, piano {c.rng.randint(1, 5)}, "
            f"censita al N.C.E.U. del Comune di {city} al {c.pii('CADASTRAL_REF', c.pick(f'foglio {c.rng.randint(1, 60)}, particella {c.rng.randint(10, 2999)}, sub. {c.rng.randint(1, 30)}', f'Fg. {c.rng.randint(1, 60)} Mapp. {c.rng.randint(10, 2999)} Sub {c.rng.randint(1, 30)}'))}, "
            f"cat. {c.code('cat')}, classe energetica {c.pick('D', 'E', 'G')}.\n"
            f"Art. 2 - Il canone annuo è convenuto in {c.money()}, da versare in rate mensili sul conto IBAN {c.iban()} intestato al locatore.\n"
            f"Art. 3 - Deposito cauzionale: {c.money()}, non imputabile in conto canoni ({c.law()}).\n"
            f"Art. 4 - Il contratto è registrato presso l'{c.body()} con codice identificativo {c.pii('CONTRACT_ID', 'T' + F.digits(c.rng, 2) + c.pick('A', 'B') + F.digits(c.rng, 12))}.\n"
            f"Recapiti conduttore: {c.phone(con)} / {c.email(con)}\nLetto, confermato e sottoscritto, {c.ddate()}.\n")


def perizia(c: Ctx) -> str:
    per, ctu = c.person(), c.person()
    if c.chance(.5):
        return (f"PERIZIA MEDICO-LEGALE\nPeriziand{'a' if per.female else 'o'}: {c.name(per, 'surname_first')} - {c.dob(per)}\n"
                f"Sinistro n. {c.pii('CONTRACT_ID', c.pick(f'{c.rng.randint(2022, 2026)}/SX/{F.digits(c.rng, 6)}', 'SIN' + F.digits(c.rng, 9)))} "
                f"- Compagnia {c.org()} - polizza {c.pii('CONTRACT_ID', F.digits(c.rng, 3) + '.' + F.digits(c.rng, 6) + '.' + F.digits(c.rng, 2))}\n"
                f"Anamnesi: {c.pick('la', 'il')} {c.pick('paziente', 'periziand' + ('a' if per.female else 'o'))} riferisce che il {c.ddate()}, mentre transitava a bordo "
                f"della propria vettura targata {c.pii('LICENSE_PLATE', F.plate(c.rng))}, veniva tamponata. Si recava al PS dell'{c.body()} "
                f"dove veniva diagnosticata distorsione del rachide cervicale ({c.code('icd')}).\n"
                f"Esame obiettivo: lieve contrattura paravertebrale. Il periziando è {indirect(c) if c.chance(.4) else 'in buone condizioni generali'}.\n"
                f"Conclusioni: invalidità temporanea parziale al 50% per 20 giorni; danno biologico permanente 2%.\n"
                f"Il medico legale, dott. {c.name(ctu)}\n")
    return (f"PERIZIA TECNICA DI STIMA\nRichiedente: {c.name(per)} ({c.cf(per)}), {c.pick('tel.', 'cell.')} {c.phone(per)}\n"
            f"Immobile: {c.addr(per, c.pick(0, 3))}\nIdentificativi catastali: {c.pii('CADASTRAL_REF', c.pick(f'F. {c.rng.randint(1, 80)} P.lla {c.rng.randint(1, 4000)} sub {c.rng.randint(1, 40)}', f'foglio {c.rng.randint(1, 80)} mappale {c.rng.randint(1, 4000)}'))}, "
            f"categoria {c.code('cat')}, rendita {c.money()}\n"
            f"Il sottoscritto {c.pick('geom.', 'arch.', 'ing.')} {c.name(ctu)}, iscritto all'albo n. {c.neg('DOC_NUMBER', str(c.rng.randint(100, 4999)))}, "
            f"effettuato il sopralluogo in data {c.ddate()} alla presenza della proprietaria {c.name(c.person(), 'first')}, "
            f"stima il più probabile valore di mercato in {c.money()}.\nRiferimenti normativi: {c.law()}; {c.law()}.\n")


def referto(c: Ctx) -> str:
    p, doc = c.person(), c.person()
    return (f"{c.body()} - {c.pick('U.O. Radiologia', 'Ambulatorio di Cardiologia', 'Pronto Soccorso')}\n"
            f"REFERTO n. {c.prot()}   del {c.ddate()}\n"
            f"Paziente: {c.name(p, c.pick('caps_surname', 'caps', 'full'))}   Sesso: {'F' if p.female else 'M'}   Nato/a il: {c.dob(p)}   a: {c.bplace(p)}\n"
            f"C.F.: {c.cf(p)}   Tessera sanitaria n. {c.pii('ID_DOCUMENT', '80380' + F.digits(c.rng, 15))}\n"
            f"Recapito: {c.addr(p, c.pick(0, 1, 5))} - {c.phone(p)}\n"
            f"Medico richiedente: dott. {c.name(doc, 'initial')}\n"
            f"Quesito: {c.pick('dolore toracico atipico', 'trauma distorsivo caviglia dx', 'controllo post-operatorio')} ({c.code('icd')})\n"
            f"Esito: {c.pick('Non si apprezzano lesioni ossee a carattere traumatico.', 'ECG: ritmo sinusale, FC 72 bpm, PR nei limiti.', 'Versamento articolare di modesta entità.')}\n"
            f"{c.pick('La paziente', 'Il paziente')} {c.pick('riferisce di lavorare come', 'è')} {indirect(c) if c.chance(.3) else 'impiegato/a'}.\n"
            f"Firmato digitalmente da {c.name(doc, 'caps_surname')} ai sensi del {c.law()}\n")


FORMAL = {  # genre: [(subgenre, template, docs, ocr probability)]
    "legal": [("pec", pec_email, 22, 0), ("verbale", verbale, 22, .3), ("atto_citazione", atto_citazione, 20, .25),
              ("ricorso", ricorso, 20, .2)],
    "hr_tax": [("busta_paga", busta_paga, 18, .3), ("cu", cu, 16, .4), ("f24", f24, 16, .3)],
    "real_estate_medical": [("locazione", locazione, 20, .25), ("perizia", perizia, 18, .25), ("referto", referto, 18, .3)],
}

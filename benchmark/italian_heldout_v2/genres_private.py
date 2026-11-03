"""Private-sector genres for it_pii_heldout_v2: insurance, health, banking, HR, school.

Why: different paperwork from v1 (which had payslips, CU, F24, leases, appraisals, medical reports).
What: one function per sub-genre; PRIVATE lists (sub-genre, fn, count, noise p, all-caps p).
Test: tests/test_v2.py.
"""
from __future__ import annotations

import ident as I
import snippets as S
from builder import Doc
from genres_formal import body, org

DIAG = ["frattura composta del radio distale", "polmonite lobare", "colecistite acuta litiasica",
        "fibrillazione atriale parossistica", "trauma distorsivo del ginocchio", "appendicite acuta"]


def sinistro(d: Doc) -> None:
    r = d.r
    a, b = I.person(r), I.person(r)
    d.t("DENUNCIA DI SINISTRO - CONSTATAZIONE AMICHEVOLE (CAI)\nCompagnia: ")
    org(d)
    d.t("\nData sinistro: ")
    S.ddate(d)
    d.t("   Ora: " + f"{r.randint(6, 22)}:{r.randint(0, 59):02d}" + "\nLuogo: ")
    d.p("ADDRESS", S.address_value(d, I.person(r), r.random() < .6))
    d.t("\n\nVEICOLO A\nContraente/Assicurato: ")
    S.name(d, a, r.choice(["LF", "UPPER", "fl"]))
    d.t("\nCod. fiscale: ")
    v, h = I.cf_form(r, a.cf)
    d.p("FISCAL_CODE", v, h)
    d.t("\nIndirizzo: ").p("ADDRESS", S.address_value(d, a))
    d.t("\nTelefono: ").p("PHONE", a.phone)
    d.t("\nTarga: ").p("LICENSE_PLATE", I.plate(r))
    d.t("   Polizza n. ").p("CONTRACT_ID", r.choice([I.digits(r, 10), f"{I.digits(r, 3)}.{I.digits(r, 6)}", "RCA" + I.digits(r, 8)]))
    d.t("\nConducente: ")
    if r.random() < .6:
        d.t("lo stesso")
    else:
        drv = I.person(r)
        S.name(d, drv, "fl")
        S.birth(d, drv)
    d.t("   Patente: ").p("ID_DOCUMENT", I.licence(r))
    d.t("\n\nVEICOLO B\nAssicurato: ")
    S.name(d, b, r.choice(["LF", "fl"]))
    d.t("   Targa: ").p("LICENSE_PLATE", I.plate(r))
    d.t("\n\nDescrizione: " + r.choice(["il veicolo B, uscendo da un parcheggio, urtava la fiancata destra del veicolo A.",
                                        "tamponamento a catena in prossimità del semaforo.",
                                        "il veicolo A non rispettava la precedenza a destra."]) + "\nDanni stimati: ")
    S.money(d, 300, 15000)
    d.t("\nTestimoni: ")
    if r.random() < .5:
        S.name(d, I.person(r), r.choice(["fl", "Lf"]))
        d.t(" tel. ").p("PHONE", I.person(r).phone)
    else:
        d.t("nessuno")
    d.t("\n")


def dimissione(d: Doc) -> None:
    r = d.r
    p, doc, gp = I.person(r), I.person(r, 0), I.person(r, 0)
    d.t("")
    body(d)
    d.t(" - Presidio Ospedaliero\nU.O.C. " + r.choice(["Medicina Interna", "Ortopedia e Traumatologia", "Chirurgia Generale", "Cardiologia"]) +
        "\n\nLETTERA DI DIMISSIONE\n\nGent.mo Collega ")
    S.titled(d, gp, r.choice(["fl", "last"]))
    d.t(",\nsi dimette in data odierna il/la paziente ")
    S.name(d, p, r.choice(["UPPER", "LF", "fl"]))
    d.t(r.choice([", nato/a il ", ", data di nascita "])).p("DATE_OF_BIRTH", I.birth_date(r, p)[0])
    d.t(", n. nosologico ").p("CONTRACT_ID", f"{r.randint(2024, 2026)}{I.digits(r, 6)}", {"nosologico"})
    d.t(", tessera sanitaria ").p("ID_DOCUMENT", "80380" + I.digits(r, 15), {"health_card"})
    d.t(",\nricoverato/a dal ")
    S.ddate(d)
    d.t(" per " + r.choice(DIAG) + ".\n\nANAMNESI: " + r.choice(["ipertensione arteriosa in terapia", "pregresso IMA",
                                                              "diabete mellito tipo 2", "nulla di rilevante"]) +
        ". Vive con " + r.choice(["la moglie", "il marito", "la figlia"]) + " ")
    S.name(d, I.person(r), "first")
    d.t(" (recapito ").p("PHONE", I.person(r).phone).t(").\n")
    d.t("TERAPIA ALLA DIMISSIONE: " + r.choice(["ramipril 5 mg 1 cp/die", "apixaban 5 mg x 2", "paracetamolo 1 g al bisogno"]) +
        ".\nControllo ambulatoriale tra 30 giorni (prenotazione CUP n. ")
    S.prot(d)
    d.t(").\n\nIl Medico\n")
    S.titled(d, doc, r.choice(["fl", "init"]))
    d.t("\n")


def ricetta(d: Doc) -> None:
    r = d.r
    p, doc = I.person(r), I.person(r, 0)
    d.t("SERVIZIO SANITARIO NAZIONALE - RICETTA ELETTRONICA\nPROMEMORIA PER L'ASSISTITO\nNRE: ")
    d.n("CODE", f"{r.randint(100, 199)}0A{I.digits(r, 10)}")
    d.t("\nCOGNOME E NOME: ")
    d.p("PERSON", f"{p.last.upper()} {p.first.upper()}", p.hard | {"uppercase"})
    d.t("\nCODICE FISCALE: ").p("FISCAL_CODE", p.cf)
    d.t("\nINDIRIZZO: ").p("ADDRESS", S.address_value(d, p).upper(), {"uppercase"})
    d.t("\nESENZIONE: " + r.choice(["NON ESENTE", "E01", "048", "013"]) + "\nPRESCRIZIONE: " +
        r.choice(["ECOGRAFIA ADDOME COMPLETO", "VISITA CARDIOLOGICA", "EMOCROMO + PCR", "RX TORACE 2P"]) +
        "\nDATA: ")
    S.ddate(d)
    d.t("\nMEDICO: ")
    d.p("PERSON", f"{doc.last.upper()} {doc.first.upper()}", {"uppercase"})
    d.t("  COD. REG. ").n("CODE", I.digits(r, 6))
    d.t("\n")


def estratto_conto(d: Doc) -> None:
    r = d.r
    p = I.person(r)
    d.t("")
    org(d)
    d.t("\nESTRATTO CONTO AL ")
    S.ddate(d)
    d.t("\nIntestatario: ")
    S.name(d, p, r.choice(["UPPER", "LF", "fl"]))
    d.t("\n").p("ADDRESS", S.address_value(d, p))
    d.t("\nIBAN: ")
    v, h = I.iban_form(r, I.iban(r))
    d.p("IBAN", v, h)
    d.t("\nCodice cliente: ").p("CONTRACT_ID", I.digits(r, 8))
    d.t("\n\nDATA       VALUTA     DESCRIZIONE                                  IMPORTO\n")
    for _ in range(r.randint(4, 7)):
        k = r.randrange(5)
        dt = f"{r.randint(1, 28):02d}/{r.randint(1, 12):02d}"
        d.t(f"{dt}      {dt}      ")
        if k == 0:
            d.t("BONIFICO A FAVORE DI ")
            d.p("PERSON", I.person(r).full.upper(), {"uppercase", "table_cell"})
        elif k == 1:
            d.t("PAGAMENTO POS CARTA ")
            c = I.card(r)
            d.p("CREDIT_CARD", " ".join(c[i:i + 4] for i in range(0, len(c), 4)) if r.random() < .5 else c, {"table_cell"})
        elif k == 2:
            d.t("ADDEBITO SDD ")
            org(d)
        elif k == 3:
            d.t("BONIFICO DA ")
            d.p("PERSON", f"{I.person(r).last.upper()} {I.person(r).first.upper()}", {"uppercase", "table_cell"})
            d.t(" IBAN ")
            d.p("IBAN", I.iban(r, r.choice(["IT", "PL", "BE", "PT", "AT"])), {"table_cell"})
        else:
            d.t("PRELIEVO ATM " + r.choice(I.TOWNS)[0].upper())
        d.t("   ")
        S.money(d, 5, 4000)
        d.t("\n")
    d.t("\nSaldo contabile finale: ")
    S.money(d, 100, 60000)
    d.t("\n")


def kyc(d: Doc) -> None:
    r = d.r
    p = I.person(r, .35)
    d.t("QUESTIONARIO ADEGUATA VERIFICA DELLA CLIENTELA (")
    d.n("LAW_REF", "D.Lgs. 231/2007")
    d.t(")\n\n1. Cognome: ").p("PERSON", p.last, p.hard | {"surname_only", "key_value"})
    d.t("\n2. Nome: ").p("PERSON", p.first, p.hard | {"first_name_only", "key_value"})
    d.t("\n3. Luogo di nascita: ").p("BIRTH_PLACE", p.birth_town, {"no_cue", "key_value"})
    d.t("\n4. Data di nascita: ").p("DATE_OF_BIRTH", I.birth_date(r, p)[0])
    d.t("\n5. Cittadinanza: " + (p.country or "italiana") + "\n6. Codice fiscale: ")
    v, h = I.cf_form(r, p.cf)
    d.p("FISCAL_CODE", v, h)
    d.t("\n7. Documento: ")
    S.ident_doc(d)
    d.t(" rilasciato da ")
    body(d)
    d.t(" il ")
    S.ddate(d)
    d.t("\n8. Residenza: ").p("ADDRESS", S.address_value(d, p))
    d.t("\n9. Cellulare: ").p("PHONE", p.phone)
    d.t("\n10. E-mail: ")
    S.mail(d, p, .25)
    d.t("\n11. Professione: " + r.choice(["lavoratore dipendente", "pensionato", "artigiano", "libero professionista"]) +
        "\n12. Reddito annuo: ")
    S.money(d, 9000, 120000)
    d.t("\n13. Persona politicamente esposta: NO\n14. Scopo del rapporto: " + r.choice(["mutuo prima casa", "conto corrente", "investimento"]) + "\n")


def cv(d: Doc) -> None:
    r = d.r
    p = I.person(r, .3)
    d.t("CURRICULUM VITAE\n\n")
    S.name(d, p, r.choice(["UPPER", "fl"]))
    d.t("\n").p("ADDRESS", S.address_value(d, p))
    d.t(" | ").p("PHONE", p.phone).t(" | ")
    S.mail(d, p, .2)
    d.t("\n" + r.choice(["Data di nascita: ", "Nato/a il ", "D.o.b. "])).p("DATE_OF_BIRTH", I.birth_date(r, p)[0])
    d.t(" | Nazionalità: " + (p.country or "italiana"))
    if r.random() < .5:
        d.t(" | LinkedIn: linkedin.com/in/").p("USERNAME", I._slug(p.first) + "-" + I._slug(p.last) + "-" + I.digits(r, 3))
    d.t("\n\nESPERIENZA PROFESSIONALE\n")
    for _ in range(r.randint(1, 3)):
        d.t(f"{r.randint(2008, 2020)} - {r.choice(['oggi', str(r.randint(2021, 2025))])}  ")
        org(d)
        d.t(" - " + r.choice(["Addetto alla contabilità", "Magazziniere", "Sviluppatore backend", "Operatrice socio-sanitaria",
                              "Responsabile acquisti"]) + "\n")
    d.t("\nISTRUZIONE\n" + r.choice(["Diploma di ragioneria", "Laurea in Economia", "Qualifica OSS", "Laurea in Informatica"]) +
        f" ({r.randint(1990, 2020)})\n\nREFERENZE\n")
    ref = I.person(r)
    S.titled(d, ref, "fl")
    d.t(", tel. ").p("PHONE", ref.phone)
    d.t("\n\nAutorizzo il trattamento dei dati personali ai sensi del ")
    d.n("LAW_REF", "Reg. UE 2016/679")
    d.t(".\n")


def hr_letter(d: Doc) -> None:
    r = d.r
    w, hr = I.person(r), I.person(r, 0)
    d.t("")
    org(d)
    d.t("\nUfficio Risorse Umane\n\nRaccomandata A/R\nEgr./Gent.ma ")
    S.name(d, w, r.choice(["fl", "Lf"]))
    d.t("\n").p("ADDRESS", S.address_value(d, w))
    d.t("\n\n" + r.choice(I.TOWNS)[0] + ", ")
    S.ddate(d)
    if r.random() < .5:
        d.t("\n\nOggetto: contestazione disciplinare ai sensi dell'")
        d.n("LAW_REF", "art. 7 L. 300/1970")
        d.t("\n\nCon la presente Le contestiamo che in data ")
        S.ddate(d)
        d.t(" Ella, matricola ").p("EMPLOYEE_ID", I.digits(r, r.choice([5, 6])))
        d.t(", si è allontanata dalla postazione senza autorizzazione, come riferito dal capoturno ")
        S.name(d, I.person(r), r.choice(["fl", "last"]))
        d.t(".\nLa invitiamo a fornire eventuali giustificazioni entro cinque giorni.\n")
    else:
        d.t("\n\nOggetto: lettera di assunzione\n\nSiamo lieti di comunicarLe l'assunzione a tempo " +
            r.choice(["indeterminato", "determinato"]) + " con decorrenza ")
        S.ddate(d)
        d.t(", livello " + r.choice(["3°", "4°", "5°"]) + " CCNL " + r.choice(["Commercio", "Metalmeccanico", "Turismo"]) +
            ", retribuzione annua lorda ")
        S.money(d, 18000, 45000)
        d.t(".\nLe è stata assegnata la matricola ").p("EMPLOYEE_ID", "M" + I.digits(r, 5))
        d.t(" e l'account aziendale ").p("USERNAME", I._slug(w.first)[0] + I._slug(w.last))
        d.t(". La retribuzione sarà accreditata sull'IBAN da Lei indicato ")
        v, h = I.iban_form(r, I.iban(r))
        d.p("IBAN", v, h)
        d.t(".\n")
    d.t("\nDistinti saluti\nL'HR Manager\n")
    S.name(d, hr, r.choice(["fl", "init"]))
    d.t("\n")


def scuola(d: Doc) -> None:
    r = d.r
    kid, par = I.person(r, .25), I.person(r, .25)
    kid.y = r.randint(2010, 2019)
    d.t("ISTITUTO COMPRENSIVO STATALE \"" + r.choice(["Grazia Deledda", "Don Lorenzo Milani", "Gianni Rodari", "Rita Levi-Montalcini"]) +
        "\" di " + r.choice(I.TOWNS)[0] + "\n")
    if r.random() < .5:
        d.t("DOMANDA DI ISCRIZIONE - A.S. 2026/2027\n\nIl/La sottoscritto/a ")
        S.name(d, par, "fl")
        S.fiscal(d, par)
        d.t(", in qualità di genitore, CHIEDE l'iscrizione dell'alunno/a ")
        S.name(d, kid, r.choice(["fl", "LF"]))
        S.birth(d, kid)
        S.fiscal(d, kid)
        d.t(" alla classe " + r.choice(["prima", "seconda", "terza"]) + ".\nRecapiti: cell. ").p("PHONE", par.phone)
        d.t(", e-mail ")
        S.mail(d, par, .15)
        d.t("\nAlunno con certificazione ")
        d.p("INDIRECT", r.choice(["L. 104/92 art. 3 c. 3", "DSA (L. 170/2010)"]), {"health"})
        d.t(": " + r.choice(["sì", "sì, allegata"]) + "\n")
    else:
        d.t("COMUNICAZIONE SCUOLA-FAMIGLIA\n\nAi genitori dell'alunno/a ")
        S.name(d, kid, r.choice(["fl", "first"]))
        d.t(", classe " + str(r.randint(1, 5)) + r.choice("ABCDE") + "\n\nSi comunica che in data ")
        S.ddate(d)
        d.t(" " + r.choice(["l'alunno/a è stato/a coinvolto/a in un episodio di bullismo segnalato dalla docente ",
                             "si è verificato un infortunio durante l'ora di educazione fisica, assistito dal docente "]))
        S.titled(d, I.person(r, 0), r.choice(["fl", "last"]))
        d.t(".\nSi prega di contattare la segreteria al numero ").n("CODE", "0" + I.digits(r, 2) + " " + I.digits(r, 6))
        d.t(" o di scrivere a ")
        S.mail(d, par, .1)
        d.t(" per un colloquio.\n")
    d.t("Il Dirigente Scolastico\n")
    S.titled(d, I.person(r, 0), "fl")
    d.t("\n")


PRIVATE = {"private": [("sinistro_cai", sinistro, 15, .15, .2), ("lettera_dimissione", dimissione, 15, .2, 0),
                       ("ricetta_ssn", ricetta, 10, .1, 0), ("estratto_conto", estratto_conto, 13, .15, 0),
                       ("adeguata_verifica", kyc, 13, .1, .15), ("curriculum", cv, 15, .2, 0),
                       ("lettera_hr", hr_letter, 13, .15, 0), ("scuola", scuola, 13, .1, 0)]}

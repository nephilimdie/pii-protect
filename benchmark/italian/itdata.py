"""Synthetic Italian identities and identifiers for the benchmark generator.

Why: gold PII must look like the real thing (valid checksums, real formats) without
belonging to anyone; every value here is generated from a seeded RNG.
What: lexicons (names, cities with cadastral codes, streets, companies) and
generators for codice fiscale (incl. omocodia), partita IVA, IBAN IT, card numbers,
phones, e-mails/PEC, plates, ID documents, INPS/INAIL numbers.
Test: benchmark/italian/tests/test_italian_bench.py checks CF/P.IVA/IBAN/Luhn validity.

Formats are written from the public specifications (DM 23/12/1976 for CF, DPR 633/72
for P.IVA, ISO 13616 + CIN for IBAN, ISO/IEC 7812 Luhn), NOT from the engine regexes.
"""
from __future__ import annotations

import random
import string
from dataclasses import dataclass

MALE = ["Mario", "Luca", "Giuseppe", "Marco", "Francesco", "Alessandro", "Andrea", "Matteo",
        "Lorenzo", "Davide", "Simone", "Federico", "Riccardo", "Stefano", "Paolo", "Giovanni",
        "Antonio", "Roberto", "Massimo", "Fabio", "Claudio", "Salvatore", "Vincenzo", "Gianluca",
        "Pietro", "Emanuele", "Nicola", "Carlo", "Enrico", "Tommaso", "Domenico", "Raffaele"]
FEMALE = ["Giulia", "Francesca", "Chiara", "Sara", "Martina", "Valentina", "Elena", "Laura",
          "Alessia", "Federica", "Silvia", "Anna", "Maria", "Paola", "Roberta", "Elisa",
          "Ilaria", "Beatrice", "Giorgia", "Monica", "Cristina", "Daniela", "Teresa", "Lucia",
          "Caterina", "Simona", "Barbara", "Antonella", "Marta", "Noemi"]
# First names / surnames that are also ordinary Italian words (hard for NER and for denylists).
AMBIGUOUS_FIRST_M = ["Fortunato", "Angelo", "Leone", "Sole", "Benedetto", "Celeste", "Felice", "Primo"]
AMBIGUOUS_FIRST_F = ["Rosa", "Serena", "Speranza", "Vittoria", "Gioia", "Stella", "Bianca", "Viola"]
SURNAMES = ["Rossi", "Russo", "Ferrari", "Esposito", "Romano", "Colombo", "Ricci", "Bruno",
            "Conti", "De Luca", "Mancini", "Costa", "Giordano", "Rizzo", "Lombardi", "Moretti",
            "Barbieri", "Fontana", "Santoro", "Mariani", "Rinaldi", "Caruso", "Ferrara", "Galli",
            "Martini", "Leone", "Longo", "Gentile", "Martinelli", "Vitale", "Lombardo", "Serra",
            "Coppola", "De Santis", "D'Angelo", "Marchetti", "Parisi", "Villa", "Conte", "Ferri",
            "Fabbri", "Pellegrini", "Palumbo", "Sanna", "Farina", "Di Stefano", "Cattaneo", "Orlando"]
AMBIGUOUS_SURNAMES = ["Bianco", "Fortunato", "Gallo", "Marino", "Fiore", "Grasso", "Monti",
                      "Bellini", "Vecchio", "Sorrentino", "Benedetti", "Pace", "Riva", "Re", "Messina"]
# (first, last, gender, birth-country cadastral code, country name)
FOREIGN = [("Mohamed", "El Amrani", "M", "Z330", "Marocco"), ("Olena", "Kovalenko", "F", "Z138", "Ucraina"),
           ("Wei", "Zhang", "M", "Z210", "Cina"), ("Ionuț", "Popescu", "M", "Z129", "Romania"),
           ("Fatou", "Diallo", "F", "Z343", "Senegal"), ("Kevin", "O'Brien", "M", "Z116", "Irlanda"),
           ("Ana Lucía", "Gómez", "F", "Z131", "Spagna"), ("Ahmed", "Ben Salah", "M", "Z352", "Tunisia"),
           ("Svetlana", "Ivanova", "F", "Z154", "Russia"), ("Rajesh", "Kumar", "M", "Z222", "India"),
           ("Agnieszka", "Nowak", "F", "Z127", "Polonia"), ("Elvis", "Hoxha", "M", "Z100", "Albania"),
           ("Jean-Pierre", "Dubois", "M", "Z110", "Francia"), ("Thi Lan", "Nguyen", "F", "Z251", "Vietnam")]
NICKNAMES = {"Giuseppe": "Peppe", "Luigi": "Gigi", "Francesco": "Ciccio", "Salvatore": "Totò",
             "Alessandro": "Ale", "Federica": "Fede", "Valentina": "Vale", "Domenico": "Mimmo",
             "Vincenzo": "Enzo", "Antonio": "Tonino", "Raffaele": "Lello", "Roberto": "Bobo",
             "Giovanni": "Gianni", "Francesca": "Franci", "Elisabetta": "Betta", "Massimo": "Max"}
# city, province, CAP, cadastral (Belfiore) code
CITIES = [("Roma", "RM", "00185", "H501"), ("Milano", "MI", "20121", "F205"), ("Napoli", "NA", "80134", "F839"),
          ("Torino", "TO", "10121", "L219"), ("Palermo", "PA", "90133", "G273"), ("Bologna", "BO", "40121", "A944"),
          ("Firenze", "FI", "50122", "D612"), ("Venezia", "VE", "30121", "L736"), ("Bari", "BA", "70121", "A662"),
          ("Catania", "CT", "95121", "C351"), ("Padova", "PD", "35121", "G224"), ("Verona", "VR", "37121", "L781"),
          ("Lecce", "LE", "73100", "E506"), ("Cagliari", "CA", "09124", "B354"), ("Salerno", "SA", "84121", "H703"),
          ("Genova", "GE", "16121", "D969"), ("Trieste", "TS", "34121", "L424"), ("Brescia", "BS", "25121", "B157"),
          ("Bergamo", "BG", "24121", "A794"), ("Perugia", "PG", "06121", "G478"), ("Ancona", "AN", "60121", "A271"),
          ("Pescara", "PE", "65121", "G482"), ("Treviso", "TV", "31100", "L407"), ("Lodi", "LO", "26900", "E648"),
          ("Cuneo", "CN", "12100", "D205"), ("Bobbio", "PC", "29022", "A909"), ("Matera", "MT", "75100", "F052"),
          ("Sassari", "SS", "07100", "I452"), ("Rimini", "RN", "47921", "H294"), ("Trento", "TN", "38122", "L378")]
STREETS = ["Garibaldi", "Roma", "Mazzini", "Cavour", "Dante Alighieri", "Verdi", "dei Mille", "XX Settembre",
           "Vittorio Emanuele II", "della Repubblica", "Marconi", "Matteotti", "San Francesco", "delle Rose",
           "Gramsci", "Indipendenza", "Manzoni", "Leopardi", "dei Gelsi", "Carducci", "Trieste", "Nazionale",
           "Aldo Moro", "Belvedere", "dei Pini", "Santa Lucia", "Fiume", "Colombo", "IV Novembre", "Pascoli"]
STREET_KINDS = [("Via", "via", "V."), ("Viale", "viale", "V.le"), ("Piazza", "piazza", "P.zza"),
                ("Corso", "corso", "C.so"), ("Largo", "largo", "L.go"), ("Vicolo", "vicolo", "Vic."),
                ("Contrada", "contrada", "C.da"), ("Località", "località", "Loc.")]
COMPANIES = ["Edilnord S.r.l.", "Alfa Logistica S.p.A.", "Tecnoservizi Srl", "Ristorante Da Gino S.n.c.",
             "Studio Associato Delta", "Immobiliare Belvedere S.r.l.", "Assicurazioni Generose S.p.A.",
             "Banca Popolare del Nord", "Officine Meccaniche Lombarde S.p.A.", "Farmacia Centrale S.a.s.",
             "Consorzio Agrario Padano", "Software House Gamma S.r.l.", "Trasporti Veloci S.r.l.",
             "Cooperativa Sociale Il Ponte", "Hotel Miramare S.r.l."]
PUBLIC_BODIES = ["Tribunale di Milano", "Corte d'Appello di Roma", "Agenzia delle Entrate", "INPS",
                 "INAIL", "Giudice di Pace di Napoli", "Comune di Torino", "Agenzia delle Entrate - Riscossione",
                 "Tribunale di Bologna", "Questura di Firenze", "Ufficio Provinciale - Territorio di Bari",
                 "Camera di Commercio di Padova", "ASL Roma 1", "Corte di Cassazione"]
LAW_REFS = ["art. 2043 c.c.", "art. 1453 del codice civile", "D.Lgs. 196/2003", "Reg. UE 2016/679",
            "art. 6 par. 1 lett. b) GDPR", "L. 104/1992", "art. 18 della L. 300/1970", "D.P.R. 633/1972",
            "art. 36 D.P.R. 600/1973", "art. 2118 c.c.", "art. 700 c.p.c.", "D.Lgs. 81/2008",
            "art. 1571 c.c.", "art. 4 del D.Lgs. 23/2015", "art. 186 C.d.S.", "L. 392/1978",
            "art. 13 D.Lgs. 472/1997", "art. 1917 c.c.", "art. 2697 c.c.", "art. 3 Cost."]
MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
          "settembre", "ottobre", "novembre", "dicembre"]
EMAIL_DOMAINS = ["gmail.com", "libero.it", "yahoo.it", "hotmail.it", "outlook.it", "tiscali.it", "alice.it", "virgilio.it"]
PEC_DOMAINS = ["pec.it", "legalmail.it", "pec.ordineavvocatimilano.it", "postacert.it", "arubapec.it", "cert.ordine-commercialisti.it"]

_CF_ODD = [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23]
_CF_MONTHS = "ABCDEHLMPRST"
_OMOCODIA = "LMNPQRSTUV"
_PLATE_LETTERS = "ABCDEFGHJKLMNPRSTVWXYZ"


def _cf_value(ch: str, odd: bool) -> int:
    idx = int(ch) if ch.isdigit() else ord(ch) - 65
    return _CF_ODD[idx] if odd else idx


def cf_check_char(body: str) -> str:
    """Why: CF, and the CIN of an Italian IBAN, share the same odd/even check algorithm.
    What: returns the check letter for an uppercase alphanumeric body.
    Test: cf_check_char('RSSMRA80A01H501') == 'U'.
    """
    return chr(65 + sum(_cf_value(c, i % 2 == 0) for i, c in enumerate(body)) % 26)


def _letters(s: str, vowels: bool) -> str:
    s = "".join(c for c in s.upper() if c.isalpha() and c in string.ascii_uppercase)
    return "".join(c for c in s if (c in "AEIOU") == vowels)


def codice_fiscale(first: str, last: str, gender: str, y: int, m: int, d: int, place: str,
                   omocodia: int = 0) -> str:
    """Why: gold CFs must be checksum-valid like real ones (and omocodia variants must exist).
    What: builds the 16-char CF; omocodia=k replaces the k rightmost digits with letters.
    Test: codice_fiscale('Mario','Rossi','M',1980,1,1,'H501') == 'RSSMRA80A01H501U'.
    """
    sur = (_letters(last, False) + _letters(last, True) + "XXX")[:3]
    cons = _letters(first, False)
    name = cons[0] + cons[2] + cons[3] if len(cons) >= 4 else (cons + _letters(first, True) + "XXX")[:3]
    body = list(f"{sur}{name}{y % 100:02d}{_CF_MONTHS[m - 1]}{d + (40 if gender == 'F' else 0):02d}{place}")
    for pos in [14, 13, 12, 10, 9, 7, 6][:omocodia]:
        body[pos] = _OMOCODIA[int(body[pos])]
    body = "".join(body)
    return body + cf_check_char(body)


def partita_iva(rng: random.Random) -> str:
    """Why: P.IVA of individuals (professionals, sole traders) is personal data with a check digit.
    What: 7 random digits + province office code + Luhn-style check digit.
    Test: piva_valid(partita_iva(rng)) for any seed.
    """
    base = f"{rng.randint(0, 9999999):07d}{rng.randint(1, 100):03d}"
    return base + str(_piva_check(base))


def _piva_check(base: str) -> int:
    total = 0
    for i, ch in enumerate(base):
        v = int(ch)
        if i % 2:
            v *= 2
            v -= 9 if v > 9 else 0
        total += v
    return (10 - total % 10) % 10


def piva_valid(p: str) -> bool:
    return len(p) == 11 and p.isdigit() and _piva_check(p[:10]) == int(p[10])


def iban_it(rng: random.Random) -> str:
    """Why: Italian IBANs carry two checks (CIN + ISO 7064 mod 97); both must hold.
    What: random ABI/CAB/account, computes CIN then the IBAN check digits.
    Test: iban_valid(iban_it(rng)) for any seed.
    """
    bban = f"{rng.randint(1000, 99999):05d}{rng.randint(1000, 99999):05d}{rng.randint(0, 10**12 - 1):012d}"
    bban = cf_check_char(bban) + bban
    return f"IT{98 - _mod97(bban + 'IT00'):02d}{bban}"


def _mod97(s: str) -> int:
    return int("".join(str(int(c, 36)) for c in s)) % 97


def iban_valid(iban: str) -> bool:
    iban = iban.replace(" ", "")
    return _mod97(iban[4:] + iban[:4]) == 1


def luhn_valid(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()][::-1]
    return sum(d if i % 2 == 0 else (d * 2 - 9 if d * 2 > 9 else d * 2) for i, d in enumerate(digits)) % 10 == 0


def card_number(rng: random.Random) -> str:
    """Why: card numbers must pass Luhn, as validators check it.
    What: Visa/Mastercard 16 digits or Amex 15 digits with a valid Luhn digit.
    Test: luhn_valid(card_number(rng)).
    """
    prefix, length = rng.choice([("4", 16), (str(rng.randint(51, 55)), 16), (rng.choice(["34", "37"]), 15)])
    body = prefix + "".join(str(rng.randint(0, 9)) for _ in range(length - len(prefix) - 1))
    return next(body + str(d) for d in range(10) if luhn_valid(body + str(d)))


def group(s: str, size: int = 4, sep: str = " ") -> str:
    return sep.join(s[i:i + size] for i in range(0, len(s), size))


def mobile(rng: random.Random) -> str:
    n = f"3{rng.randint(20, 93)}{rng.randint(0, 9999999):07d}"
    return rng.choice([f"{n[:3]} {n[3:]}", f"+39 {n[:3]} {n[3:]}", n, f"{n[:3]} {n[3:6]} {n[6:]}",
                       f"+39{n}", f"{n[:3]}-{n[3:]}", f"0039 {n[:3]} {n[3:]}", f"({n[:3]}) {n[3:]}"])


def landline(rng: random.Random) -> str:
    pre = rng.choice(["02", "06", "011", "081", "051", "055", "041", "080", "091", "010", "0832", "0523"])
    n = f"{rng.randint(10**(9 - len(pre)), 10**(10 - len(pre)) - 1)}"
    return rng.choice([f"{pre} {n}", f"{pre}/{n}", f"{pre}{n}", f"+39 {pre} {n}", f"{pre}-{n}"])


def plate(rng: random.Random) -> str:
    L = lambda k: "".join(rng.choice(_PLATE_LETTERS) for _ in range(k))  # noqa: E731
    a, n, b = L(2), f"{rng.randint(0, 999):03d}", L(2)
    return rng.choice([f"{a}{n}{b}", f"{a} {n} {b}", f"{a}{n}{b}".lower() if rng.random() < .15 else f"{a}-{n}-{b}"])


def id_document(rng: random.Random) -> tuple[str, str]:
    """What: (kind description, number) for carta d'identità (CIE/paper), passport, licence, health card."""
    L = lambda k: "".join(rng.choice(string.ascii_uppercase) for _ in range(k))  # noqa: E731
    D = lambda k: "".join(str(rng.randint(0, 9)) for _ in range(k))  # noqa: E731
    return rng.choice([
        ("carta d'identità n.", f"CA{D(5)}{L(2)}"), ("carta d'identità elettronica n.", f"C{L(1)}{D(5)}{L(2)}"),
        ("carta d'identità cartacea n.", f"A{L(1)} {D(7)}"), ("passaporto n.", f"Y{L(1)}{D(7)}"),
        ("passaporto n.", f"{L(2)}{D(7)}"), ("patente di guida n.", f"{L(2)}{D(7)}{L(1)}"),
        ("patente n.", f"U1{L(1)}{D(6)}{L(1)}"), ("tessera sanitaria n.", f"80380{D(15)}"),
    ])


@dataclass
class Person:
    first: str
    last: str
    gender: str
    birth: tuple[int, int, int]
    birth_city: str
    birth_code: str
    cf: str
    city: tuple[str, str, str, str]
    street: str
    phone: str
    email: str
    foreign: bool = False

    @property
    def full(self) -> str:
        return f"{self.first} {self.last}"


def _ascii(s: str) -> str:
    table = str.maketrans("àèéìòùÀÈÉÌÒÙțșăîâçáíóúñ'", "aeeiouAEEIOUtsaiacaioun ")
    return s.translate(table).replace(" ", "").lower()


def person(rng: random.Random, ambiguous: bool = False, foreign: bool = False) -> Person:
    """Why: one coherent fake identity feeds every PII slot of a document.
    What: name, birth data, consistent CF (5% omocodia), home address, phone, e-mail.
    Test: CF of the result ends with cf_check_char of its first 15 chars.
    """
    if foreign:
        first, last, gender, code, country = rng.choice(FOREIGN)
        birth_city = country
    else:
        gender = rng.choice("MF")
        pool = (AMBIGUOUS_FIRST_M if gender == "M" else AMBIGUOUS_FIRST_F) if ambiguous and rng.random() < .6 \
            else (MALE if gender == "M" else FEMALE)
        first = rng.choice(pool)
        last = rng.choice(AMBIGUOUS_SURNAMES if ambiguous and rng.random() < .7 else SURNAMES)
        birth_city, _, _, code = rng.choice(CITIES)
    y, m, d = rng.randint(1945, 2004), rng.randint(1, 12), rng.randint(1, 28)
    cf = codice_fiscale(first, last, gender, y, m, d, code, omocodia=rng.choice([1, 2]) if rng.random() < .05 else 0)
    city = rng.choice(CITIES)
    kind = rng.choice(STREET_KINDS[:5])[0]
    street = f"{kind} {rng.choice(STREETS)}"
    local = rng.choice([f"{_ascii(first)}.{_ascii(last)}", f"{_ascii(first)[0]}{_ascii(last)}",
                        f"{_ascii(last)}{rng.randint(1, 99)}", f"{_ascii(first)}{y % 100:02d}"])
    phone = mobile(rng) if rng.random() < .8 else landline(rng)
    return Person(first, last, gender, (y, m, d), birth_city, code, cf, city, street, phone,
                  f"{local}@{rng.choice(EMAIL_DOMAINS)}", foreign)

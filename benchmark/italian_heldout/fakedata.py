"""Fake identities for the held-out corpus, written from scratch (no import from benchmark/italian).

Why: a held-out set that reuses the original generator's name/place pools or code generators
would share its blind spots; this module has its own pools, distributions and checksums.
What: Persona (names incl. double surnames, particles, nicknames, foreign names; birth data;
valid codice fiscale / IBAN / P.IVA / Luhn card; contacts) plus small fake-ID helpers.
Test: tests/test_heldout.py checks the checksums against hand-verified public examples.
"""
from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass

# ------------------------------------------------------------------ checksums (public algorithms)
_ODD = dict(zip("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6,
                 8, 12, 14, 16, 10, 22, 25, 24, 23]))
_EVEN = {c: (int(c) if c.isdigit() else ord(c) - 65) for c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
_MONTH = "ABCDEHLMPRST"


def control_char(s: str) -> str:
    """Why: codice fiscale and the Italian IBAN CIN share one odd/even weighting scheme.
    What: check letter for an uppercase alphanumeric string (1-based odd positions weighted).
    Test: control_char('RSSMRA80A01H501') == 'U'."""
    return chr(65 + sum(_ODD[c] if i % 2 == 0 else _EVEN[c] for i, c in enumerate(s)) % 26)


def _plain(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if c.isalpha() and c.isascii()).upper()


def _cons_vow(s: str) -> tuple[str, str]:
    s = _plain(s)
    return "".join(c for c in s if c not in "AEIOU"), "".join(c for c in s if c in "AEIOU")


def codice_fiscale(first: str, last: str, female: bool, y: int, m: int, d: int, belfiore: str) -> str:
    """What: standard 16-char codice fiscale. Test: ('Mario','Rossi',False,1980,1,1,'H501') -> RSSMRA80A01H501U."""
    c, v = _cons_vow(last)
    sur = (c + v + "XXX")[:3]
    c, v = _cons_vow(first)
    nam = c[0] + c[2] + c[3] if len(c) >= 4 else (c + v + "XXX")[:3]
    body = f"{sur}{nam}{y % 100:02d}{_MONTH[m - 1]}{d + 40 * female:02d}{belfiore}"
    return body + control_char(body)


def luhn_digit(digits: str) -> str:
    """What: Luhn check digit (also the P.IVA check). Test: luhn_digit('7992739871') == '3'."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch) * (2 if i % 2 == 0 else 1)
        total += n - 9 if n > 9 else n
    return str((10 - total % 10) % 10)


def iban_check(country: str, bban: str) -> str:
    """What: ISO 13616 mod-97 check digits. Test: iban_check('IT','X0542811101000000123456') == '60'."""
    num = "".join(str(int(c, 36)) for c in bban + country + "00")
    return f"{98 - int(num) % 97:02d}"


def iban(rng: random.Random, country: str = "IT") -> str:
    dg = lambda k: "".join(rng.choice("0123456789") for _ in range(k))  # noqa: E731
    if country == "IT":
        core = dg(5) + dg(5) + rng.choice(["0000", "1000", "CC00"]) + dg(8)
        bban = control_char(core) + core
    elif country == "DE":
        bban = dg(18)
    elif country == "FR":
        bban = dg(23)
    elif country == "ES":
        bban = dg(20)
    else:  # RO
        bban = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(4)) + dg(16)
    return country + iban_check(country, bban) + bban


def group4(s: str) -> str:
    return " ".join(s[i:i + 4] for i in range(0, len(s), 4))


def partita_iva(rng: random.Random) -> str:
    body = "".join(rng.choice("0123456789") for _ in range(7)) + f"{rng.randint(1, 100):03d}"
    return body + luhn_digit(body)


def card(rng: random.Random) -> str:
    pre = rng.choice(["4", "4", "51", "53", "55", "37"])
    n = 15 if pre == "37" else 16
    body = pre + "".join(rng.choice("0123456789") for _ in range(n - len(pre) - 1))
    return body + luhn_digit(body)


# ------------------------------------------------------------------ pools (deliberately varied)
M_IT = ["Ottavio", "Raffaele", "Gianfranco", "Ermanno", "Corrado", "Tancredi", "Settimio", "Nazzareno", "Dario",
        "Ivano", "Cosimo", "Gennaro", "Brunello", "Achille", "Ruggero", "Lorenzo", "Mattia", "Elia", "Tommaso",
        "Edoardo", "Samuele", "Gian Marco", "Pier Paolo", "Gian Luca", "Carmine", "Rocco", "Salvatore", "Filippo",
        "Luigi", "Giuseppe", "Federico", "Alessandro", "Massimiliano", "Stefano", "Simone", "Roberto"]
F_IT = ["Ornella", "Graziella", "Loredana", "Tiziana", "Ilaria", "Noemi", "Azzurra", "Ludovica", "Benedetta",
        "Rebecca", "Ginevra", "Assunta", "Immacolata", "Concetta", "Maria Grazia", "Anna Lisa", "Maria Teresa",
        "Elisabetta", "Federica", "Valentina", "Caterina", "Francesca", "Alessandra", "Simona", "Giovanna"]
AMBIG_M = ["Fortunato", "Leone", "Felice", "Benvenuto", "Marino", "Sole"]
AMBIG_F = ["Rosa", "Speranza", "Serena", "Vittoria", "Bianca", "Celeste", "Gioia"]
LAST_IT = ["Bonaccorsi", "Scognamiglio", "Pellegatta", "Trombetta", "Zanella", "Mazzoleni", "Cuomo", "Iannuzzi",
           "Brambilla", "Sanna", "Pisu", "Tedeschi", "Occhipinti", "Lombardo", "Barbieri", "Fumagalli", "Cattaneo",
           "Esposito", "Marchetti", "Rinaldi", "Caruso", "Fabbri", "Ferraro", "Melis", "Giordano", "Mele", "Riva",
           "Dell'Orto", "D'Ambrosio", "Lo Russo", "De Santis", "Dal Bosco", "La Rocca", "Di Stefano", "Li Causi",
           "Della Valle", "De Angelis", "Lo Presti", "D'Alessio", "Del Prete"]
AMBIG_LAST = ["Gentile", "Ferro", "Grasso", "Monti", "Porta", "Bello", "Colombo", "Piccolo", "Lupo", "Gallo", "Russo"]
NICK = {"Filippo": "Pippo", "Luigi": "Gigi", "Giuseppe": "Beppe", "Salvatore": "Totò", "Elisabetta": "Betta",
        "Federica": "Fede", "Federico": "Fede", "Alessandro": "Ale", "Valentina": "Vale", "Francesca": "Fra",
        "Roberto": "Robi", "Massimiliano": "Max", "Caterina": "Cate", "Stefano": "Ste", "Simone": "Simo",
        "Giovanna": "Giò", "Tommaso": "Tommi", "Lorenzo": "Lollo", "Alessandra": "Sandra", "Simona": "Simo"}
# (first, last, gender, country, Belfiore Z-code); some given with family name first in source documents
FOREIGN = [("Ionuț", "Popescu", "M", "Romania", "Z129"), ("Elena", "Dumitrescu", "F", "Romania", "Z129"),
           ("Arben", "Hoxha", "M", "Albania", "Z100"), ("Blerina", "Kola", "F", "Albania", "Z100"),
           ("Fatima Zahra", "El Idrissi", "F", "Marocco", "Z330"), ("Youssef", "Benali", "M", "Marocco", "Z330"),
           ("Wei", "Zhang", "M", "Cina", "Z210"), ("Xiaoling", "Chen", "F", "Cina", "Z210"),
           ("Oksana", "Kovalenko", "F", "Ucraina", "Z138"), ("Dmytro", "Shevchuk", "M", "Ucraina", "Z138"),
           ("Mamadou", "Diop", "M", "Senegal", "Z343"), ("Awa", "Ndiaye", "F", "Senegal", "Z343"),
           ("Rosa María", "Quispe Huamán", "F", "Perù", "Z611"), ("Luis Alberto", "Mendoza Rojas", "M", "Perù", "Z611"),
           ("Priya", "Sharma", "F", "India", "Z222"), ("Gurpreet", "Singh", "M", "India", "Z222"),
           ("Jerome", "Dela Cruz", "M", "Filippine", "Z216"), ("Maricel", "Santos", "F", "Filippine", "Z216"),
           ("Ahmed", "Abdelrahman", "M", "Egitto", "Z336"), ("Rahim", "Uddin", "M", "Bangladesh", "Z249"),
           ("Chukwuemeka", "Okafor", "M", "Nigeria", "Z335"), ("Ana Clara", "Ferreira da Silva", "F", "Brasile", "Z602"),
           ("Jürgen", "Hofmann", "M", "Germania", "Z112"), ("Amélie", "Dubois", "F", "Francia", "Z110"),
           ("Iuliana", "Rusu", "F", "Moldavia", "Z140"), ("Karim", "Trabelsi", "M", "Tunisia", "Z352")]
FOREIGN_CITY = {"Romania": ["Bucarest", "Iași", "Craiova"], "Albania": ["Tirana", "Durazzo", "Valona"],
                "Marocco": ["Casablanca", "Fès", "Khouribga"], "Cina": ["Wenzhou", "Shanghai", "Qingtian"],
                "Ucraina": ["Leopoli", "Kharkiv", "Odessa"], "Senegal": ["Dakar", "Thiès", "Touba"],
                "Perù": ["Lima", "Arequipa", "Trujillo"], "India": ["Amritsar", "Mumbai", "Ludhiana"],
                "Filippine": ["Manila", "Quezon City", "Batangas"], "Egitto": ["Il Cairo", "Alessandria d'Egitto"],
                "Bangladesh": ["Dacca", "Sylhet"], "Nigeria": ["Lagos", "Benin City"], "Brasile": ["San Paolo", "Belo Horizonte"],
                "Germania": ["Monaco di Baviera", "Stoccarda"], "Francia": ["Lione", "Marsiglia"],
                "Moldavia": ["Chișinău", "Bălți"], "Tunisia": ["Sfax", "Sousse"]}
# (comune, provincia, CAP, Belfiore); mixes big cities, small towns and multi-word names
COMUNI = [("Roccaraso", "AQ", "67037", "H400"), ("Sappada", "UD", "33012", "I421"), ("Gallipoli", "LE", "73014", "D883"),
          ("Castelfranco Emilia", "MO", "41013", "C107"), ("Montepulciano", "SI", "53045", "F592"),
          ("Gubbio", "PG", "06024", "E256"), ("Tolmezzo", "UD", "33028", "L195"), ("Bassano del Grappa", "VI", "36061", "A703"),
          ("Alghero", "SS", "07041", "A192"), ("Caltagirone", "CT", "95041", "B428"), ("Vasto", "CH", "66054", "E372"),
          ("Sulmona", "AQ", "67039", "I804"), ("Chioggia", "VE", "30015", "C638"), ("Cefalù", "PA", "90015", "C421"),
          ("Bra", "CN", "12042", "B111"), ("Merano", "BZ", "39012", "F132"), ("Lugo", "RA", "48022", "E730"),
          ("Fano", "PU", "61032", "D488"), ("Vigevano", "PV", "27029", "L872"), ("Termoli", "CB", "86039", "L113"),
          ("San Giovanni in Persiceto", "BO", "40017", "G467"), ("Reggio nell'Emilia", "RE", "42121", "H223"),
          ("Castel San Pietro Terme", "BO", "40024", "C265"), ("Sant'Agata de' Goti", "BN", "82019", "I197"),
          ("Torre del Greco", "NA", "80059", "L259"), ("Milano", "MI", "20137", "F205"), ("Roma", "RM", "00176", "H501"),
          ("Napoli", "NA", "80134", "F839"), ("Torino", "TO", "10153", "L219"), ("Palermo", "PA", "90144", "G273"),
          ("Bari", "BA", "70126", "A662"), ("Verona", "VR", "37138", "L781"), ("Cagliari", "CA", "09129", "B354"),
          ("Trento", "TN", "38122", "L378"), ("Ancona", "AN", "60124", "A271"), ("Lecce", "LE", "73100", "E506")]
STREETS = ["Via dei Mille", "Via Pietro Nenni", "Viale delle Rimembranze", "Corso Garibaldi", "Via San Rocco",
           "Via Nuova Marina", "Vicolo del Pozzo", "Largo Augusto", "Piazzale Kennedy", "Via Aurelio Saffi",
           "Strada Provinciale 22", "Via Madonna delle Grazie", "Borgo Pinti", "Salita Santa Teresa",
           "Via Monte Grappa", "Viale Europa", "Via Antonio Gramsci", "Lungomare Cristoforo Colombo",
           "Via Giovanni XXIII", "Via del Lavoro", "Contrada Sant'Elia", "Località Pian del Lago", "Via IV Novembre"]
EMAIL_DOM = ["gmail.com", "libero.it", "hotmail.it", "yahoo.it", "tiscali.it", "outlook.com", "icloud.com",
             "fastwebnet.it", "virgilio.it", "alice.it"]
PEC_DOM = ["pec.it", "legalmail.it", "pec.ordineavvocatiroma.it", "arubapec.it", "postacert.it", "pec.commercialisti.it"]


@dataclass
class Persona:
    first: str
    last: str
    female: bool
    foreign: bool
    country: str
    birth: tuple[int, int, int]
    birth_city: str
    belfiore: str
    city: tuple[str, str, str, str]
    street: str
    number: str
    phone: str
    email: str
    cf: str
    ambiguous: bool
    nickname: str | None

    @property
    def full(self) -> str:
        return f"{self.first} {self.last}"


def _phone(rng: random.Random, foreign_country: str | None) -> str:
    if foreign_country == "Romania" and rng.random() < .5:
        return f"+40 7{rng.randint(20, 99)} {rng.randint(100, 999)} {rng.randint(100, 999)}"
    mob = f"3{rng.choice(['20', '24', '28', '29', '33', '34', '38', '39', '40', '45', '47', '48', '49', '51', '66', '71', '88', '92'])}"
    rest = f"{rng.randint(1000000, 9999999)}"
    style = rng.randrange(7)
    if style == 0:
        return f"+39 {mob} {rest[:3]} {rest[3:]}"
    if style == 1:
        return f"{mob}{rest}"
    if style == 2:
        return f"{mob}-{rest}"
    if style == 3:
        return f"{mob}.{rest[:2]}.{rest[2:4]}.{rest[4:]}"
    if style == 4:
        return f"0039 {mob} {rest}"
    if style == 5:  # landline
        return rng.choice(["0471", "0542", "06", "02", "081", "0874", "0833"]) + rng.choice(["/", " ", "-"]) + f"{rng.randint(100000, 9999999)}"
    return f"(+39) {mob} {rest[:2]} {rest[2:4]} {rest[4:]}"


def _email(rng: random.Random, first: str, last: str, y: int) -> str:
    f, ln = _plain(first).lower(), _plain(last).lower()
    user = rng.choice([f"{f}.{ln}", f"{f[0]}{ln}{y % 100:02d}", f"{ln}.{f}", f"{f}{ln}", f"{f}_{ln}{rng.randint(1, 99)}",
                       f"{f[0]}.{ln}", f"{ln}{rng.randint(60, 99)}"])
    return f"{user}@{rng.choice(EMAIL_DOM)}"


def persona(rng: random.Random, foreign: float = .22, ambiguous: float = .12) -> Persona:
    """What: one consistent fake person; ~22% foreign-born, ~12% with word-like names.
    Test: codice fiscale of the persona always ends with its own control_char."""
    is_foreign = rng.random() < foreign
    amb = rng.random() < ambiguous
    if is_foreign:
        first, last, g, country, code = rng.choice(FOREIGN)
        female, birth_city = g == "F", rng.choice(FOREIGN_CITY[country])
    else:
        female = rng.random() < .5
        first = rng.choice(AMBIG_F if female else AMBIG_M) if amb else rng.choice(F_IT if female else M_IT)
        last = rng.choice(AMBIG_LAST) if amb and rng.random() < .6 else rng.choice(LAST_IT)
        if rng.random() < .1:  # double surname
            last = f"{last} {rng.choice(LAST_IT)}"
        country = "Italia"
        bc = rng.choice(COMUNI)
        birth_city, code = bc[0], bc[3]
    y, m, d = rng.randint(1941, 2006), rng.randint(1, 12), rng.randint(1, 28)
    city = rng.choice(COMUNI)
    num = rng.choice([str(rng.randint(1, 240)), f"{rng.randint(1, 80)}/{rng.choice('ABCD')}", f"{rng.randint(2, 60)}bis",
                      f"{rng.randint(1, 99)} sc. {rng.choice('ABC')}"])
    return Persona(first, last, female, is_foreign, country, (y, m, d), birth_city, code, city, rng.choice(STREETS), num,
                   _phone(rng, country if is_foreign else None), _email(rng, first, last, y),
                   codice_fiscale(first, last, female, y, m, d, code), amb, NICK.get(first))


# ------------------------------------------------------------------ misc fake identifiers
_PL = "ABCDEFGHJKLMNPRSTVWXYZ"


def plate(rng: random.Random) -> str:
    return f"{rng.choice(_PL)}{rng.choice(_PL)}{rng.randint(0, 999):03d}{rng.choice(_PL)}{rng.choice(_PL)}"


def cie(rng: random.Random) -> str:
    return f"C{rng.choice('ABCDEF')}{rng.randint(10000, 99999)}{rng.choice(_PL)}{rng.choice(_PL)}"


def passport(rng: random.Random) -> str:
    return f"Y{rng.choice('ABCDE')}{rng.randint(1000000, 9999999)}"


def patente(rng: random.Random) -> str:
    return f"U1{rng.choice(_PL)}{rng.randint(10, 99)}{rng.choice(_PL)}{rng.randint(100, 999)}{rng.choice(_PL)}"


def ip(rng: random.Random) -> str:
    if rng.random() < .12:
        return "2001:db8:" + ":".join(f"{rng.randint(0, 65535):x}" for _ in range(3)) + "::" + f"{rng.randint(1, 4095):x}"
    first = rng.choice([5, 31, 37, 79, 82, 87, 93, 95, 151, 176, 188, 213])
    return f"{first}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


def digits(rng: random.Random, k: int) -> str:
    return "".join(rng.choice("0123456789") for _ in range(k))


def eur(rng: random.Random, lo: int = 20, hi: int = 90000) -> str:
    v = rng.randint(lo, hi) + rng.randint(0, 99) / 100
    return f"{v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
          "novembre", "dicembre"]

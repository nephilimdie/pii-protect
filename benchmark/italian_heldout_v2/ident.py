"""Fake identities for it_pii_heldout_v2, written from scratch (no import from benchmark/italian*).

Why: a test set must not share name/place pools or code generators with the corpora used for
development (it_pii_v1, it_pii_heldout_v1) or with any training generator.
What: own pools (different first names, rarer surnames, other foreign nationalities, other towns),
own checksums (codice fiscale, IT CIN + IBAN mod-97, Luhn, P.IVA) and value formatters.
Test: tests/test_v2.py checks the checksums against public examples.
"""
from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass, field

# ------------------------------------------------------------------ checksums (public algorithms)
_ODD_W = [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23]


def _odd(ch: str) -> int:
    return _ODD_W[int(ch) if ch.isdigit() else ord(ch) - 65]


def _even(ch: str) -> int:
    return int(ch) if ch.isdigit() else ord(ch) - 65


def check_letter(body: str) -> str:
    """What: codice-fiscale style check letter (positions 1,3,5.. odd table). Test: RSSMRA80A01H501 -> U."""
    return chr(65 + sum(_odd(c) if i % 2 == 0 else _even(c) for i, c in enumerate(body)) % 26)


def _ascii_upper(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if c.isascii() and c.isalpha()).upper()


def cf(first: str, last: str, female: bool, y: int, m: int, d: int, code: str) -> str:
    """What: 16-char codice fiscale. Test: cf('Mario','Rossi',False,1980,1,1,'H501') == 'RSSMRA80A01H501U'."""
    def split(s: str) -> tuple[str, str]:
        s = _ascii_upper(s)
        return "".join(c for c in s if c not in "AEIOU"), "".join(c for c in s if c in "AEIOU")
    cs, vs = split(last)
    part1 = (cs + vs + "XXX")[:3]
    cn, vn = split(first)
    part2 = (cn[0] + cn[2] + cn[3]) if len(cn) > 3 else (cn + vn + "XXX")[:3]
    body = f"{part1}{part2}{y % 100:02d}{'ABCDEHLMPRST'[m - 1]}{d + (40 if female else 0):02d}{code}"
    return body + check_letter(body)


def luhn(digits: str) -> str:
    """What: Luhn check digit. Test: luhn('7992739871') == '3'."""
    s = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch) * (2 if i % 2 == 0 else 1)
        s += n - 9 if n > 9 else n
    return str(-s % 10)


def mod97(country: str, bban: str) -> str:
    """What: IBAN check digits. Test: mod97('IT','X0542811101000000123456') == '60'."""
    return f"{98 - int(''.join(str(int(c, 36)) for c in bban + country + '00')) % 97:02d}"


def _digits(r: random.Random, n: int) -> str:
    return "".join(r.choice("0123456789") for _ in range(n))


def iban(r: random.Random, country: str = "IT") -> str:
    if country == "IT":
        rest = _digits(r, 10) + r.choice(["0000", "CC00", "0100"]) + _digits(r, 8)
        bban = check_letter(rest) + rest
    else:
        bban = {"PL": lambda: _digits(r, 24), "BE": lambda: _digits(r, 12), "PT": lambda: _digits(r, 21),
                "AT": lambda: _digits(r, 16)}[country]()
    return country + mod97(country, bban) + bban


def piva(r: random.Random) -> str:
    body = _digits(r, 7) + r.choice(["001", "015", "021", "037", "058", "063", "080"])
    return body + luhn(body)


def card(r: random.Random) -> str:
    body = r.choice(["4", "51", "53", "37"]) + _digits(r, 14)
    body = body[:15] if not body.startswith("37") else body[:14]
    return body + luhn(body)


# ------------------------------------------------------------------ pools (v2 only)
M = ("Arturo Adelmo Cirillo Edmondo Ezio Fausto Orazio Fermo Lamberto Manlio Iacopo Liberato Raffaello Sesto "
     "Teodoro Ubaldo Vasco Zeno Amedeo Nicandro Ciro Donato Egidio Fiorenzo Gualtiero Ignazio Leopoldo Mirko "
     "Nevio Oreste Pasquale Remo Saverio Tazio Vittorino Aurelio Delio Elio Flavio Graziano Italo Lucio Gilberto "
     "Natale Osvaldo Pompeo Medardo Santino Tullio").split()
F = ("Adelina Brunella Clelia Dorotea Edvige Fulvia Gemma Lavinia Mafalda Ersilia Fernanda Priscilla Rosalba Selene "
     "Tecla Ursula Viviana Zaira Agnese Bice Albina Donatella Erminia Flora Giuditta Iolanda Letizia Marisa Nives "
     "Ofelia Piera Romina Sabrina Ines Vanda Annunziata Carmela Elvira Filomena Cesira Domitilla Lidia "
     "Mirella Nadia Palmira Rina Gisella Velia").split()
COMPOUND = ["Maria Grazia", "Gian Paolo", "Anna Rita", "Pier Luigi", "Rosa Maria", "Gian Marco", "Maria Gisella"]
SUR = ("Abbracciavento Bagnasco Cappellini Dattilo Evangelista Faraone Gargiulo Iacovelli Lanzetta Mazzocchi "
       "Nardella Orlandini Pellizzari Quaranta Rapisarda Scarpellini Tagliaferri Uccello Vitiello Zampieri "
       "Brambati Ciaccio Fumarola Guarnieri Lattanzi Malagoli Nicoletti Ostuni Pistillo Rinaldini Sciortino "
       "Tamburrino Valsecchi Zanoni Arcuri Bellomo Carbonaro Ferraiuolo Gismondi Mastrangelo Nocera Russomanno "
       "Spadaro Trombini Venturelli Zucchelli Allegra Fortuna Merlo Volpe").split()
PARTICLE_SUR = ["Del Vecchio", "Di Pietrantonio", "La Torre", "Lo Iacono", "Dell'Aquila", "Della Corte", "De Feo",
                "D'Ippolito", "Li Vigni", "Dal Pozzo"]
WORDLIKE = {"Allegra", "Fortuna", "Merlo", "Volpe", "Natale", "Santino", "Flora", "Gemma"}
FOREIGN = {  # nationality -> (male, female, surnames, Belfiore code, country, phone prefix)
    "bangladesh": (["Mohammad", "Rafiqul", "Tanvir"], ["Sharmin", "Nusrat", "Farzana"], ["Rahman", "Islam", "Hossain"],
                   "Z249", "Bangladesh", "+880"),
    "srilanka": (["Nuwan", "Kasun", "Chaminda"], ["Dilani", "Nirosha"], ["Perera", "Fernando", "Jayasinghe"],
                 "Z209", "Sri Lanka", "+94"),
    "pakistan": (["Imran", "Bilal"], ["Ayesha", "Sana"], ["Qureshi", "Malik", "Chaudhry"], "Z236", "Pakistan", "+92"),
    "polonia": (["Tomasz", "Paweł", "Krzysztof"], ["Katarzyna", "Joanna", "Małgorzata"],
                ["Mazur", "Wiśniewski", "Kowalczyk", "Zieliński"], "Z127", "Polonia", "+48"),
    "moldavia": (["Ion", "Vasile"], ["Natalia", "Doina"], ["Ceban", "Cojocaru", "Lungu"], "Z140", "Moldavia", "+373"),
    "tunisia": (["Mehdi", "Anis"], ["Amira", "Sonia"], ["Gharbi", "Ben Amor", "Jebali"], "Z352", "Tunisia", "+216"),
    "ecuador": (["Jorge", "Wilson"], ["Mayra", "Jessenia"], ["Quishpe", "Guamán", "Chiluisa"], "Z605", "Ecuador", "+593"),
    "nigeria": (["Chinedu", "Emeka"], ["Blessing", "Ngozi"], ["Eze", "Adeyemi", "Nwachukwu"], "Z335", "Nigeria", "+234"),
    "egitto": (["Tarek", "Mahmoud"], ["Mona", "Heba"], ["Elsayed", "Hassan", "Mostafa"], "Z336", "Egitto", "+20"),
    "brasile": (["João", "Thiago"], ["Thaís", "Luana"], ["Pereira da Silva", "Oliveira", "Santos Costa"],
                "Z602", "Brasile", "+55"),
    "georgia": (["Giorgi", "Levan"], ["Nino", "Tamar"], ["Beridze", "Kapanadze"], "Z254", "Georgia", "+995"),
}
# (town, province, CAP, Belfiore)
TOWNS = [("Rovereto", "TN", "38068", "H612"), ("Rende", "CS", "87036", "H235"), ("Poggibonsi", "SI", "53036", "G752"),
         ("Pordenone", "PN", "33170", "G888"), ("Carpi", "MO", "41012", "B819"), ("Udine", "UD", "33100", "L483"),
         ("Gaeta", "LT", "04024", "D843"), ("Orvieto", "TR", "05018", "G148"), ("Cosenza", "CS", "87100", "D086"),
         ("Ravenna", "RA", "48121", "H199"), ("Piombino", "LI", "57025", "G687"), ("Avellino", "AV", "83100", "A509"),
         ("Ariano Irpino", "AV", "83031", "A399"), ("Modena", "MO", "41121", "F257"), ("Siena", "SI", "53100", "I726"),
         ("Livorno", "LI", "57121", "E625"), ("Viterbo", "VT", "01100", "M082"), ("Latina", "LT", "04100", "E472"),
         ("Foggia", "FG", "71121", "D643"), ("Taranto", "TA", "74121", "L049"), ("Ragusa", "RG", "97100", "H163"),
         ("Trapani", "TP", "91100", "L331"), ("Nuoro", "NU", "08100", "F979"), ("Aosta", "AO", "11100", "A326"),
         ("Belluno", "BL", "32100", "A757"), ("Rovigo", "RO", "45100", "H620"), ("Cremona", "CR", "26100", "D150"),
         ("Mantova", "MN", "46100", "E897"), ("Novara", "NO", "28100", "F952"), ("Seriate", "BG", "24068", "I628"),
         ("Savona", "SV", "17100", "I480"), ("Pistoia", "PT", "51100", "G713"), ("Terni", "TR", "05100", "L117"),
         ("Frosinone", "FR", "03100", "D810"), ("Campobasso", "CB", "86100", "B519"), ("Chieti", "CH", "66100", "C632"),
         ("Crotone", "KR", "88900", "D122"), ("Enna", "EN", "94100", "C342"), ("Oristano", "OR", "09170", "G113"),
         ("Pisticci", "MT", "75015", "G712"), ("Iglesias", "SU", "09016", "E281"), ("Ozieri", "SS", "07014", "G203"),
         ("Nardò", "LE", "73048", "F842"), ("Lanciano", "CH", "66034", "E435"),
         ("Bassano del Grappa", "VI", "36061", "A703"), ("Foligno", "PG", "06034", "D653"),
         ("Sciacca", "AG", "92019", "I533"), ("Fasano", "BR", "72015", "D508"), ("Cesenatico", "FC", "47042", "C574"),
         ("Castelfranco Veneto", "TV", "31033", "C111"), ("San Nicandro del Tronto", "AP", "63074", "H769"),
         ("Mazara del Vallo", "TP", "91026", "F061"), ("Borgo San Lorenzo", "FI", "50032", "B036"),
         ("Montebelluna", "TV", "31044", "F443"), ("Sant'Antioco", "SU", "09017", "I294"),
         ("Castellammare di Stabia", "NA", "80053", "C129"), ("Città di Castello", "PG", "06012", "C745"),
         ("Reggio nell'Emilia", "RE", "42121", "H223")]
STREET_KIND = ["Via", "Via", "Via", "Viale", "Corso", "Piazza", "Vicolo", "Strada", "Largo", "Contrada", "Borgo",
               "Lungomare", "Traversa"]
STREET_NAME = ["dei Mille", "delle Acacie", "San Medardo", "Monte Grappa", "dei Tigli", "Cesare Battisti",
               "Giacomo Matteotti", "Pietro Nenni", "Bruno Buozzi", "Fratelli Rosselli", "Don Minzoni",
               "delle Ginestre", "del Lavoro", "Nazionale", "del Campo Sportivo", "Sette Martiri", "IV Novembre",
               "XXV Aprile", "Trieste", "dei Gelsi", "Santa Lucia", "del Porto", "Cristoforo Colombo",
               "Ugo Foscolo", "Enrico Fermi", "Padre Pio", "delle Rimembranze", "Vittorio Veneto", "Roma",
               "dei Caduti", "Madonna delle Grazie", "Antonio Gramsci", "della Libertà", "Marconi", "degli Ulivi"]
MAIL_DOM = ["libero.it", "tiscali.it", "alice.it", "virgilio.it", "fastwebnet.it", "gmail.com", "outlook.it",
            "icloud.com", "yahoo.it", "hotmail.it", "email.it", "inwind.it"]
PEC_DOM = ["pec.it", "legalmail.it", "postecert.it", "arubapec.it", "pec.ordineavvocatiperugia.it", "cert.studio.it"]
MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
          "novembre", "dicembre"]
MON3 = ["GEN", "FEB", "MAR", "APR", "MAG", "GIU", "LUG", "AGO", "SET", "OTT", "NOV", "DIC"]


@dataclass
class Person:
    first: str
    last: str
    female: bool
    y: int
    m: int
    d: int
    birth_town: str
    birth_prov: str
    cf: str
    street: str
    town: tuple
    phone: str
    email: str
    hard: set = field(default_factory=set)
    country: str | None = None

    @property
    def full(self) -> str:
        return f"{self.first} {self.last}"


def _phone(r: random.Random, prefix: str | None) -> str:
    if prefix:
        return f"{prefix} {_digits(r, 3)} {_digits(r, 3)} {_digits(r, 3)}"
    mob = "3" + r.choice("234567890") + _digits(r, 1)
    return r.choice([f"{mob} {_digits(r, 7)}", f"+39 {mob} {_digits(r, 3)} {_digits(r, 4)}", f"{mob}/{_digits(r, 7)}",
                     f"{mob}.{_digits(r, 3)}.{_digits(r, 4)}", f"0{_digits(r, 2)} {_digits(r, 6)}",
                     f"(+39) 0{_digits(r, 3)}-{_digits(r, 6)}", f"0039{mob}{_digits(r, 7)}", f"{mob}-{_digits(r, 3)}-{_digits(r, 4)}"])


def _slug(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if c.isascii() and (c.isalnum()))


def mail_for(r: random.Random, first: str, last: str, y: int, pec: bool = False) -> str:
    f, l_ = _slug(first), _slug(last)
    local = r.choice([f"{f}.{l_}", f"{f[0]}{l_}", f"{l_}.{f}", f"{f}{l_}{y % 100:02d}", f"{f}_{l_}", f"{l_}{f[0]}{r.randint(1, 99)}"])
    return f"{local}@{r.choice(PEC_DOM if pec else MAIL_DOM)}"


def address(r: random.Random) -> tuple[str, tuple]:
    n = str(r.randint(1, 240)) + r.choice(["", "", "", "/A", " bis", "B"])
    return f"{r.choice(STREET_KIND)} {r.choice(STREET_NAME)} {n}", r.choice(TOWNS)


def person(r: random.Random, foreign: float = .2) -> Person:
    hard: set[str] = set()
    female = r.random() < .5
    nat = r.choice(list(FOREIGN)) if r.random() < foreign else None
    if nat:
        fm, ff, fs, code, country, pre = FOREIGN[nat]
        first, last = r.choice(ff if female else fm), r.choice(fs)
        hard.add("foreign")
        btown, bprov = country, "EE"
    else:
        first = r.choice(COMPOUND) if r.random() < .08 else r.choice(F if female else M)
        roll = r.random()
        if roll < .12:
            last = r.choice(PARTICLE_SUR)
            hard.add("particle")
        elif roll < .2:
            last = f"{r.choice(SUR)} {r.choice(SUR)}"
            hard.add("double_surname")
        else:
            last = r.choice(SUR)
        if " " in first:
            hard.add("compound_first")
        t = r.choice(TOWNS)
        btown, bprov, code = t[0], t[1], t[3]
        pre = None
    if WORDLIKE & {first, last}:
        hard.add("word_like")
    y, m, d = r.randint(1938, 2006), r.randint(1, 12), r.randint(1, 28)
    street, town = address(r)
    return Person(first, last, female, y, m, d, btown, bprov, cf(first, last, female, y, m, d, code), street, town,
                  _phone(r, pre if pre and r.random() < .6 else None), mail_for(r, first, last, y), hard,
                  FOREIGN[nat][4] if nat else None)


def birth_date(r: random.Random, p: Person) -> tuple[str, set[str]]:
    k = r.randrange(9)
    if k == 0:
        return f"{p.d:02d}/{p.m:02d}/{p.y}", set()
    if k == 1:
        return f"{p.d} {MONTHS[p.m - 1]} {p.y}", set()
    if k == 2:
        return f"{p.d:02d}-{MON3[p.m - 1]}-{p.y}", {"month_abbrev"}
    if k == 3:
        return f"{p.d:02d}.{p.m:02d}.{p.y}", set()
    if k == 4:
        return f"{p.y}-{p.m:02d}-{p.d:02d}", {"iso_date"}
    if k == 5:
        return f"{p.d}/{p.m}/{p.y % 100:02d}", {"short_year"}
    if k == 6:
        return f"{p.d} {MON3[p.m - 1].lower()}. {p.y}", {"month_abbrev"}
    if k == 7:
        return f"{p.d:02d}{MON3[p.m - 1]}{p.y}", {"month_abbrev"}
    return f"{p.d:02d}-{p.m:02d}-{p.y}", set()


def cf_form(r: random.Random, code: str) -> tuple[str, set[str]]:
    k = r.random()
    if k < .1:
        return f"{code[:3]} {code[3:6]} {code[6:11]} {code[11:]}", {"spaced_code"}
    if k < .16:
        return " ".join(code), {"spaced_code"}
    if k < .24:
        return code.lower(), {"lowercase"}
    return code, set()


def iban_form(r: random.Random, code: str) -> tuple[str, set[str]]:
    if r.random() < .45:
        return " ".join(code[i:i + 4] for i in range(0, len(code), 4)), {"spaced_code"}
    return code, set()


def obfuscate_mail(r: random.Random, mail: str) -> tuple[str, set[str]]:
    local, dom = mail.split("@")
    head, _, tld = dom.rpartition(".")
    form = r.choice([f"{local} [at] {head} [dot] {tld}", f"{local}(at){dom}", f"{local} at {head} punto {tld}",
                     f"{local}%40{dom}", f"{local} @ {head} . {tld}", f"{local}[chiocciola]{dom}",
                     f"{local} AT {head} DOT {tld}"])
    return form, {"obfuscated"}


def ipv4(r: random.Random) -> str:
    return r.choice([f"93.{r.randint(32, 63)}.{r.randint(0, 255)}.{r.randint(1, 254)}",
                     f"151.{r.randint(0, 99)}.{r.randint(0, 255)}.{r.randint(1, 254)}",
                     f"79.{r.randint(0, 59)}.{r.randint(0, 255)}.{r.randint(1, 254)}",
                     f"2.{r.randint(32, 47)}.{r.randint(0, 255)}.{r.randint(1, 254)}"])


def ipv6(r: random.Random) -> str:
    g = lambda: f"{r.randint(0, 0xffff):x}"  # noqa: E731
    return r.choice([f"2a01:{g()}:{g()}:{g()}::{g()}", f"2001:b07:{g()}:{g()}:{g()}:{g()}:{g()}:{g()}",
                     f"2a02:{g()}:{g()}::{g()}:{g()}"])


def cie(r: random.Random) -> str:
    return r.choice(["CA", "CB", "CD", "CE"]) + _digits(r, 5) + "".join(r.choice("ABCDEFGHLMNPRSTUVZ") for _ in range(2))


def passport(r: random.Random) -> str:
    return r.choice(["YA", "YB", "YC", "AA"]) + _digits(r, 7)


def licence(r: random.Random) -> str:
    return r.choice(["U1", "PZ", "CB", "RM"]) + _digits(r, 7) + r.choice("ABCDEFGHKLMNPRSTVZ")


def plate(r: random.Random) -> str:
    L = "ABCDEFGHJKLMNPRSTVWXYZ"
    a, b = r.choice(L) + r.choice(L), r.choice(L) + r.choice(L)
    return r.choice([f"{a}{_digits(r, 3)}{b}", f"{a} {_digits(r, 3)} {b}", f"{a}-{_digits(r, 3)}-{b}"])


def eur(r: random.Random, lo: int = 15, hi: int = 250000) -> str:
    v = r.uniform(lo, hi)
    whole = f"{int(v):,}".replace(",", ".")
    return r.choice([f"€ {whole},{int(v * 100) % 100:02d}", f"{whole},{int(v * 100) % 100:02d} euro",
                     f"EUR {whole},{int(v * 100) % 100:02d}", f"€{whole}"])


def doc_date(r: random.Random) -> str:
    y, m, d = r.randint(2019, 2026), r.randint(1, 12), r.randint(1, 28)
    return r.choice([f"{d:02d}/{m:02d}/{y}", f"{d} {MONTHS[m - 1]} {y}", f"{d:02d}.{m:02d}.{y}"])


digits = _digits

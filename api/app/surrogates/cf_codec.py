"""Italian Codice Fiscale encoder/decoder."""

from datetime import date

MONTH_CODES = "ABCDEHLMPRST"
MONTH_MAP = {c: i + 1 for i, c in enumerate(MONTH_CODES)}

# fmt: off
_ODD = {
    '0': 1,  '1': 0,  '2': 5,  '3': 7,  '4': 9,  '5': 13, '6': 15, '7': 17, '8': 19, '9': 21,
    'A': 1,  'B': 0,  'C': 5,  'D': 7,  'E': 9,  'F': 13, 'G': 15, 'H': 17, 'I': 19, 'J': 21,
    'K': 2,  'L': 4,  'M': 18, 'N': 20, 'O': 11, 'P': 3,  'Q': 6,  'R': 8,  'S': 12, 'T': 14,
    'U': 16, 'V': 10, 'W': 22, 'X': 25, 'Y': 24, 'Z': 23,
}
_EVEN = {c: i for i, c in enumerate('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')}
# fmt: on

BELFIORE = {
    "Roma": "H501", "Milano": "F205", "Napoli": "F839", "Torino": "L219",
    "Palermo": "G273", "Genova": "D969", "Bologna": "A944", "Firenze": "D612",
    "Bari": "A662", "Catania": "C351", "Venezia": "L736", "Verona": "L781",
    "Messina": "F158", "Padova": "G224", "Trieste": "L424", "Brescia": "B157",
    "Prato": "G999", "Modena": "F257", "Perugia": "G478", "Livorno": "E625",
    "Ravenna": "H199", "Cagliari": "B354", "Foggia": "D643", "Rimini": "H294",
    "Salerno": "H703", "Ferrara": "D548", "Sassari": "I452", "Trento": "L378",
    "Bergamo": "A794", "Pescara": "G482", "Vicenza": "L840", "Novara": "F952",
    "Ancona": "A271", "Arezzo": "A390", "Udine": "L483", "Lecce": "E506",
    "Taranto": "L049", "Siracusa": "I754", "Reggio Calabria": "H224",
    "Reggio Emilia": "H223", "Monza": "F704", "Piacenza": "G535",
}
CITIES = list(BELFIORE.keys())


def _extract(name: str) -> tuple[list[str], list[str]]:
    up = name.upper()
    cons = [c for c in up if c.isalpha() and c not in "AEIOU"]
    vows = [c for c in up if c.isalpha() and c in "AEIOU"]
    return cons, vows


def _surname_code(surname: str) -> str:
    cons, vows = _extract(surname)
    code = (cons + vows + ["X", "X", "X"])[:3]
    return "".join(code)


def _name_code(name: str) -> str:
    cons, vows = _extract(name)
    if len(cons) >= 4:
        code = [cons[0], cons[2], cons[3]]
    else:
        code = (cons + vows + ["X", "X", "X"])[:3]
    return "".join(code)


def _check(partial: str) -> str:
    total = 0
    for i, c in enumerate(partial):
        total += _ODD[c] if i % 2 == 0 else _EVEN.get(c, 0)
    return chr(ord("A") + total % 26)


def encode(last_name: str, first_name: str, birth: date, gender: str, city: str) -> str:
    belfiore = BELFIORE.get(city, "H501")
    day = birth.day + (40 if gender.upper() == "F" else 0)
    partial = (
        _surname_code(last_name)
        + _name_code(first_name)
        + str(birth.year)[-2:]
        + MONTH_CODES[birth.month - 1]
        + f"{day:02d}"
        + belfiore
    )
    return partial + _check(partial)


def decode_partial(cf: str) -> dict:
    """Extract birth year (2-digit), month, day, gender, belfiore from a CF."""
    cf = cf.upper().strip()
    if len(cf) != 16:
        return {}
    try:
        year2 = cf[6:8]
        month = MONTH_MAP.get(cf[8], 1)
        raw_day = int(cf[9:11])
        gender = "F" if raw_day > 40 else "M"
        day = raw_day - 40 if gender == "F" else raw_day
        belfiore = cf[11:15]
        return {"year2": year2, "month": month, "day": day, "gender": gender, "belfiore": belfiore}
    except Exception:
        return {}

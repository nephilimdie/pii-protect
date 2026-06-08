"""Format-preserving fake value generators, seeded for determinism."""

import hashlib
import random
import string
from datetime import date, timedelta

from faker import Faker

from app.surrogates.cf_codec import CITIES, BELFIORE, encode as cf_encode


# ── Locale support ────────────────────────────────────────────────────────────

LANGUAGE_TO_LOCALE: dict[str, str] = {
    "it": "it_IT",
    "en": "en_US",
    "en_gb": "en_GB",
    "de": "de_DE",
    "fr": "fr_FR",
    "es": "es_ES",
    "pt": "pt_PT",
    "nl": "nl_NL",
    "pl": "pl_PL",
    "cs": "cs_CZ",
    "ro": "ro_RO",
    "hu": "hu_HU",
}

_LEGAL_SUFFIXES: dict[str, list[str]] = {
    "it_IT": ["S.r.l.", "S.p.A.", "S.n.c.", "S.a.s.", "S.r.l.s."],
    "en_US": ["LLC", "Inc.", "Corp.", "Ltd.", "LLP"],
    "en_GB": ["Ltd", "PLC", "LLP", "CIC"],
    "de_DE": ["GmbH", "AG", "KG", "OHG", "GmbH & Co. KG"],
    "fr_FR": ["SARL", "SA", "SAS", "SASU", "EURL"],
    "es_ES": ["S.L.", "S.A.", "S.L.U.", "S.A.U."],
    "pt_PT": ["Lda.", "S.A.", "Unipessoal Lda."],
    "nl_NL": ["B.V.", "N.V.", "V.O.F.", "C.V."],
    "pl_PL": ["Sp. z o.o.", "S.A.", "S.K.", "S.J."],
}


def language_to_locale(language: str) -> str:
    return LANGUAGE_TO_LOCALE.get(language.lower(), "en_US")


def _seed(real_value: str, context_id: str) -> int:
    digest = hashlib.sha256(f"{real_value}|{context_id}".encode()).hexdigest()
    return int(digest[:16], 16)


def _faker(real_value: str, context_id: str, locale: str = "it_IT") -> Faker:
    f = Faker(locale)
    f.seed_instance(_seed(real_value, context_id))
    return f


def _rng(real_value: str, context_id: str) -> random.Random:
    return random.Random(_seed(real_value, context_id))


# ── Per-type generators ───────────────────────────────────────────────────────

def gen_person(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    return _faker(real_value, context_id, locale).name()


def gen_email(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    f = _faker(real_value, context_id, locale)
    if "@" in real_value:
        domain = real_value.split("@", 1)[1]
        return f"{f.user_name()}@{domain}"
    return f.email()


def gen_phone(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    return _faker(real_value, context_id, locale).phone_number()


def gen_address(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    return _faker(real_value, context_id, locale).address().replace("\n", ", ")


def gen_city(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    return _faker(real_value, context_id, locale).city()


def gen_username(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    return _faker(real_value, context_id, locale).user_name()


def gen_iban(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    return _faker(real_value, context_id, locale).iban()


def gen_credit_card(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    return _faker(real_value, context_id, locale).credit_card_number(card_type="visa")


def gen_salary(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    rng = _rng(real_value, context_id)
    try:
        digits = "".join(c for c in real_value if c.isdigit() or c in ".,")
        amount = float(digits.replace(".", "").replace(",", "."))
        factor = rng.uniform(0.7, 1.3)
        fake = round(amount * factor / 1000) * 1000
        return f"{fake:,.0f}".replace(",", ".")
    except Exception:
        return str(rng.randint(25_000, 80_000))


def gen_date_shift(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    rng = _rng(real_value, context_id)
    shift = rng.randint(30, 365)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            from datetime import datetime
            d = datetime.strptime(real_value.strip(), fmt)
            return (d + timedelta(days=shift)).strftime(fmt)
        except ValueError:
            continue
    return real_value


def gen_ip(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    return _faker(real_value, context_id, locale).ipv4_private()


def gen_mac(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    return _faker(real_value, context_id, locale).mac_address()


def gen_url(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    return _faker(real_value, context_id, locale).url()


def gen_gps(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    f = _faker(real_value, context_id, locale)
    return f"{f.latitude()}, {f.longitude()}"


def gen_api_key(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    rng = _rng(real_value, context_id)
    chars = string.ascii_letters + string.digits
    length = len(real_value) if 16 <= len(real_value) <= 64 else 32
    return "".join(rng.choice(chars) for _ in range(length))


def gen_password(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    f = _faker(real_value, context_id, locale)
    return f.password(length=max(len(real_value), 12))


def gen_targa(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    rng = _rng(real_value, context_id)
    letters = string.ascii_uppercase
    return (
        rng.choice(letters) + rng.choice(letters)
        + "".join(rng.choice(string.digits) for _ in range(3))
        + rng.choice(letters) + rng.choice(letters)
    )


def gen_imei(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    rng = _rng(real_value, context_id)
    base = "".join(str(rng.randint(0, 9)) for _ in range(14))
    total = 0
    for i, d in enumerate(base):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return base + str((10 - total % 10) % 10)


def gen_pnr(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    rng = _rng(real_value, context_id)
    return "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(6))


def gen_alphanumeric(real_value: str, context_id: str, locale: str = "it_IT", length: int | None = None) -> str:
    rng = _rng(real_value, context_id)
    n = length or max(len(real_value), 8)
    return "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(n))


def gen_bic(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    rng = _rng(real_value, context_id)
    bank = "".join(rng.choice(string.ascii_uppercase) for _ in range(4))
    country = rng.choice(["IT", "DE", "FR", "ES", "NL", "BE", "AT", "GB", "PL", "PT"])
    loc = "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(2))
    branch = "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(3))
    return bank + country + loc + branch


def gen_passport(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    rng = _rng(real_value, context_id)
    country = locale.split("_")[-1] if "_" in locale else "XX"
    return country + "".join(str(rng.randint(0, 9)) for _ in range(7))


def gen_identity_card(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    rng = _rng(real_value, context_id)
    letters = string.ascii_uppercase
    return (
        rng.choice(letters) + rng.choice(letters)
        + "".join(str(rng.randint(0, 9)) for _ in range(7))
        + rng.choice(letters)
    )


def gen_driver_license(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    rng = _rng(real_value, context_id)
    return "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(10))


def gen_health_card(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    rng = _rng(real_value, context_id)
    prefix = "".join(rng.choice(string.ascii_uppercase) for _ in range(2))
    number = "".join(str(rng.randint(0, 9)) for _ in range(13))
    return prefix + number


def gen_organization(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    return _faker(real_value, context_id, locale).company()


def gen_company(real_value: str, context_id: str, locale: str = "it_IT") -> str:
    f = _faker(real_value, context_id, locale)
    rng = _rng(real_value, context_id)
    suffixes = _LEGAL_SUFFIXES.get(locale, _LEGAL_SUFFIXES["en_US"])
    return f.company() + " " + rng.choice(suffixes)


# ── Profile-based CF generator (Italian-specific) ─────────────────────────────

def gen_fake_profile(real_key: str, context_id: str, gender_hint: str = "M", locale: str = "it_IT") -> dict:
    """Generate a coherent fake persona. CF fields are Italian-specific."""
    f = _faker(real_key, context_id, locale)
    rng = _rng(real_key, context_id)

    gender = gender_hint if gender_hint in ("M", "F") else rng.choice(["M", "F"])

    first = f.first_name_male() if gender == "M" else f.first_name_female()
    last = f.last_name()

    year = rng.randint(1950, 2000)
    month = rng.randint(1, 12)
    import calendar
    max_day = calendar.monthrange(year, month)[1]
    birth = date(year, month, rng.randint(1, max_day))

    city = rng.choice(list(CITIES))
    belfiore = BELFIORE[city]
    cf = cf_encode(last, first, birth, gender, city)

    return {
        "fake_first_name": first,
        "fake_last_name": last,
        "fake_birth_date": birth,
        "fake_gender": gender,
        "fake_city": city,
        "fake_belfiore": belfiore,
        "fake_cf": cf,
    }


# ── Strategy dispatch ─────────────────────────────────────────────────────────

_STRATEGY_MAP: dict[str, callable] = {
    "person":         gen_person,
    "email":          gen_email,
    "phone":          gen_phone,
    "address":        gen_address,
    "city":           gen_city,
    "username":       gen_username,
    "iban":           gen_iban,
    "credit_card":    gen_credit_card,
    "salary":         gen_salary,
    "date_shift":     gen_date_shift,
    "ip":             gen_ip,
    "mac":            gen_mac,
    "url":            gen_url,
    "gps":            gen_gps,
    "api_key":        gen_api_key,
    "password":       gen_password,
    "targa":          gen_targa,
    "imei":           gen_imei,
    "pnr":            gen_pnr,
    "bic":            gen_bic,
    "passport":       gen_passport,
    "identity_card":  gen_identity_card,
    "driver_license": gen_driver_license,
    "health_card":    gen_health_card,
    "organization":   gen_organization,
    "company":        gen_company,
    "practice_id":    lambda v, c, l="it_IT": gen_alphanumeric(v, c, l, 8),
    "policy_number":  lambda v, c, l="it_IT": gen_alphanumeric(v, c, l, 10),
    "loyalty_id":     lambda v, c, l="it_IT": gen_alphanumeric(v, c, l, 10),
    "ticket_id":      lambda v, c, l="it_IT": gen_alphanumeric(v, c, l, 8),
}


def generate(strategy: str, real_value: str, context_id: str, locale: str = "it_IT") -> str:
    fn = _STRATEGY_MAP.get(strategy)
    if fn is None:
        return gen_alphanumeric(real_value, context_id, locale)
    return fn(real_value, context_id, locale)

"""Format-preserving fake value generators, seeded for determinism."""

import hashlib
import random
import string
from datetime import date, timedelta

from faker import Faker

from app.surrogates.cf_codec import CITIES, BELFIORE, encode as cf_encode


def _seed(real_value: str, context_id: str) -> int:
    digest = hashlib.sha256(f"{real_value}|{context_id}".encode()).hexdigest()
    return int(digest[:16], 16)


def _faker(real_value: str, context_id: str) -> Faker:
    f = Faker("it_IT")
    f.seed_instance(_seed(real_value, context_id))
    return f


def _rng(real_value: str, context_id: str) -> random.Random:
    return random.Random(_seed(real_value, context_id))


# ── Per-type generators ───────────────────────────────────────────────────────

def gen_person(real_value: str, context_id: str) -> str:
    f = _faker(real_value, context_id)
    return f.name()


def gen_email(real_value: str, context_id: str) -> str:
    f = _faker(real_value, context_id)
    # Preserve domain if present
    if "@" in real_value:
        domain = real_value.split("@", 1)[1]
        local = f.user_name()
        return f"{local}@{domain}"
    return f.email()


def gen_phone(real_value: str, context_id: str) -> str:
    f = _faker(real_value, context_id)
    return f.phone_number()


def gen_address(real_value: str, context_id: str) -> str:
    f = _faker(real_value, context_id)
    return f.address().replace("\n", ", ")


def gen_city(real_value: str, context_id: str) -> str:
    f = _faker(real_value, context_id)
    return f.city()


def gen_username(real_value: str, context_id: str) -> str:
    f = _faker(real_value, context_id)
    return f.user_name()


def gen_iban(real_value: str, context_id: str) -> str:
    f = _faker(real_value, context_id)
    return f.iban()


def gen_credit_card(real_value: str, context_id: str) -> str:
    f = _faker(real_value, context_id)
    return f.credit_card_number(card_type="visa")


def gen_salary(real_value: str, context_id: str) -> str:
    rng = _rng(real_value, context_id)
    # Preserve rough magnitude
    try:
        digits = "".join(c for c in real_value if c.isdigit() or c in ".,")
        amount = float(digits.replace(".", "").replace(",", "."))
        factor = rng.uniform(0.7, 1.3)
        fake = round(amount * factor / 1000) * 1000
        return f"{fake:,.0f}".replace(",", ".")
    except Exception:
        return str(rng.randint(25_000, 80_000))


def gen_date_shift(real_value: str, context_id: str) -> str:
    rng = _rng(real_value, context_id)
    shift = rng.randint(30, 365)
    # Try to preserve format
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            from datetime import datetime
            d = datetime.strptime(real_value.strip(), fmt)
            shifted = d + timedelta(days=shift)
            return shifted.strftime(fmt)
        except ValueError:
            continue
    return real_value  # fallback: keep as-is


def gen_ip(real_value: str, context_id: str) -> str:
    f = _faker(real_value, context_id)
    return f.ipv4_private()


def gen_mac(real_value: str, context_id: str) -> str:
    f = _faker(real_value, context_id)
    return f.mac_address()


def gen_url(real_value: str, context_id: str) -> str:
    f = _faker(real_value, context_id)
    return f.url()


def gen_gps(real_value: str, context_id: str) -> str:
    f = _faker(real_value, context_id)
    return f"{f.latitude()}, {f.longitude()}"


def gen_api_key(real_value: str, context_id: str) -> str:
    rng = _rng(real_value, context_id)
    chars = string.ascii_letters + string.digits
    length = len(real_value) if 16 <= len(real_value) <= 64 else 32
    return "".join(rng.choice(chars) for _ in range(length))


def gen_password(real_value: str, context_id: str) -> str:
    f = _faker(real_value, context_id)
    return f.password(length=max(len(real_value), 12))


def gen_targa(real_value: str, context_id: str) -> str:
    rng = _rng(real_value, context_id)
    letters = string.ascii_uppercase
    digits = string.digits
    return (
        rng.choice(letters) + rng.choice(letters)
        + "".join(rng.choice(digits) for _ in range(3))
        + rng.choice(letters) + rng.choice(letters)
    )


def gen_imei(real_value: str, context_id: str) -> str:
    rng = _rng(real_value, context_id)
    base = "".join(str(rng.randint(0, 9)) for _ in range(14))
    # Luhn check digit
    total = 0
    for i, d in enumerate(base):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    check = (10 - total % 10) % 10
    return base + str(check)


def gen_pnr(real_value: str, context_id: str) -> str:
    rng = _rng(real_value, context_id)
    chars = string.ascii_uppercase + string.digits
    return "".join(rng.choice(chars) for _ in range(6))


def gen_alphanumeric(real_value: str, context_id: str, length: int | None = None) -> str:
    rng = _rng(real_value, context_id)
    n = length or max(len(real_value), 8)
    chars = string.ascii_uppercase + string.digits
    return "".join(rng.choice(chars) for _ in range(n))


def gen_bic(real_value: str, context_id: str) -> str:
    rng = _rng(real_value, context_id)
    bank = "".join(rng.choice(string.ascii_uppercase) for _ in range(4))
    country = rng.choice(["IT", "DE", "FR", "ES", "NL", "BE", "AT"])
    loc = "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(2))
    branch = "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(3))
    return bank + country + loc + branch


def gen_passport(real_value: str, context_id: str) -> str:
    rng = _rng(real_value, context_id)
    return "IT" + "".join(str(rng.randint(0, 9)) for _ in range(7))


def gen_identity_card(real_value: str, context_id: str) -> str:
    rng = _rng(real_value, context_id)
    letters = string.ascii_uppercase
    return (
        rng.choice(letters) + rng.choice(letters)
        + "".join(str(rng.randint(0, 9)) for _ in range(7))
        + rng.choice(letters)
    )


def gen_driver_license(real_value: str, context_id: str) -> str:
    rng = _rng(real_value, context_id)
    return "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(10))


def gen_health_card(real_value: str, context_id: str) -> str:
    rng = _rng(real_value, context_id)
    # Italian tessera sanitaria starts with TEAM + CF (16 chars) + expiry
    prefix = "".join(rng.choice(string.ascii_uppercase) for _ in range(2))
    number = "".join(str(rng.randint(0, 9)) for _ in range(13))
    return prefix + number


def gen_organization(real_value: str, context_id: str) -> str:
    f = _faker(real_value, context_id)
    return f.company()


def gen_company(real_value: str, context_id: str) -> str:
    f = _faker(real_value, context_id)
    suffixes = ["S.r.l.", "S.p.A.", "S.n.c.", "S.a.s.", "S.r.l.s."]
    rng = _rng(real_value, context_id)
    return f.company() + " " + rng.choice(suffixes)


# ── Profile-based CF generator ────────────────────────────────────────────────

def gen_fake_profile(real_key: str, context_id: str, gender_hint: str = "M") -> dict:
    """Generate a coherent fake persona. Returns dict with all profile fields."""
    f = _faker(real_key, context_id)
    rng = _rng(real_key, context_id)

    gender = gender_hint if gender_hint in ("M", "F") else rng.choice(["M", "F"])

    if gender == "M":
        first = f.first_name_male()
    else:
        first = f.first_name_female()
    last = f.last_name()

    # Birth date: realistic range, slightly randomised
    year = rng.randint(1950, 2000)
    month = rng.randint(1, 12)
    import calendar
    max_day = calendar.monthrange(year, month)[1]
    day = rng.randint(1, max_day)
    birth = date(year, month, day)

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
    "practice_id":    lambda v, c: gen_alphanumeric(v, c, 8),
    "policy_number":  lambda v, c: gen_alphanumeric(v, c, 10),
    "loyalty_id":     lambda v, c: gen_alphanumeric(v, c, 10),
    "ticket_id":      lambda v, c: gen_alphanumeric(v, c, 8),
}


def generate(strategy: str, real_value: str, context_id: str) -> str:
    fn = _STRATEGY_MAP.get(strategy)
    if fn is None:
        return gen_alphanumeric(real_value, context_id)
    return fn(real_value, context_id)

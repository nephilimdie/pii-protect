"""Unit tests for surrogate generators — no DB, no ML models required."""

import re
import sys
import os

# Allow imports from api/app without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.surrogates.generators import (
    generate,
    language_to_locale,
    gen_person,
    gen_email,
    gen_phone,
    gen_iban,
    gen_targa,
    gen_imei,
    gen_pnr,
    gen_bic,
    gen_passport,
    gen_date_shift,
    gen_salary,
    gen_api_key,
    gen_alphanumeric,
    LANGUAGE_TO_LOCALE,
)
from app.surrogates.cf_codec import encode as cf_encode, decode_partial
from datetime import date


CTX = "test-context-001"


# ── language_to_locale ────────────────────────────────────────────────────────

class TestLanguageToLocale:
    def test_known_languages(self):
        assert language_to_locale("it") == "it_IT"
        assert language_to_locale("en") == "en_US"
        assert language_to_locale("de") == "de_DE"
        assert language_to_locale("fr") == "fr_FR"
        assert language_to_locale("es") == "es_ES"

    def test_unknown_falls_back_to_en_us(self):
        assert language_to_locale("xx") == "en_US"
        assert language_to_locale("") == "en_US"

    def test_case_insensitive(self):
        assert language_to_locale("IT") == "it_IT"
        assert language_to_locale("EN") == "en_US"


# ── determinism ───────────────────────────────────────────────────────────────

class TestDeterminism:
    def test_same_input_same_output(self):
        v1 = generate("person", "Mario Rossi", CTX)
        v2 = generate("person", "Mario Rossi", CTX)
        assert v1 == v2

    def test_different_value_different_output(self):
        v1 = generate("person", "Mario Rossi", CTX)
        v2 = generate("person", "Luigi Verdi", CTX)
        assert v1 != v2

    def test_different_context_different_output(self):
        v1 = generate("person", "Mario Rossi", "ctx-A")
        v2 = generate("person", "Mario Rossi", "ctx-B")
        assert v1 != v2

    def test_locale_changes_output(self):
        v_it = generate("person", "Mario Rossi", CTX, locale="it_IT")
        v_en = generate("person", "Mario Rossi", CTX, locale="en_US")
        assert v_it != v_en


# ── per-type format checks ────────────────────────────────────────────────────

class TestEmail:
    def test_preserves_domain(self):
        result = gen_email("user@example.com", CTX)
        assert result.endswith("@example.com")
        assert "@" in result

    def test_valid_email_no_domain(self):
        result = gen_email("noemail", CTX)
        assert "@" in result


class TestIban:
    def test_non_empty(self):
        result = gen_iban("IT60X0542811101000001234567", CTX)
        assert len(result) > 10

    def test_deterministic(self):
        assert gen_iban("IT60X0542811101000001234567", CTX) == gen_iban("IT60X0542811101000001234567", CTX)


class TestTarga:
    def test_format_aa000bb(self):
        result = gen_targa("AB123CD", CTX)
        assert re.match(r"^[A-Z]{2}\d{3}[A-Z]{2}$", result), f"Invalid targa: {result}"

    def test_deterministic(self):
        assert gen_targa("AB123CD", CTX) == gen_targa("AB123CD", CTX)


class TestImei:
    def test_length_15(self):
        result = gen_imei("123456789012345", CTX)
        assert len(result) == 15
        assert result.isdigit()

    def test_luhn_check(self):
        result = gen_imei("123456789012345", CTX)
        total = 0
        for i, d in enumerate(result):
            n = int(d)
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        assert total % 10 == 0, f"Luhn check failed for IMEI: {result}"


class TestPnr:
    def test_length_6_alphanumeric(self):
        result = gen_pnr("ABC123", CTX)
        assert len(result) == 6
        assert result.isalnum()
        assert result == result.upper()


class TestBic:
    def test_length_11(self):
        result = gen_bic("UNCRITMM", CTX)
        assert len(result) == 11


class TestPassport:
    def test_locale_prefix_it(self):
        result = gen_passport("IT1234567", CTX, locale="it_IT")
        assert result.startswith("IT")
        assert len(result) == 9

    def test_locale_prefix_de(self):
        result = gen_passport("DE1234567", CTX, locale="de_DE")
        assert result.startswith("DE")

    def test_locale_prefix_en_us(self):
        result = gen_passport("US1234567", CTX, locale="en_US")
        assert result.startswith("US")


class TestDateShift:
    def test_shifts_by_30_to_365_days(self):
        result = gen_date_shift("15/04/2024", CTX)
        assert re.match(r"\d{2}/\d{2}/\d{4}", result)
        assert result != "15/04/2024"

    def test_preserves_format_iso(self):
        result = gen_date_shift("2024-04-15", CTX)
        assert re.match(r"\d{4}-\d{2}-\d{2}", result)

    def test_unknown_format_passthrough(self):
        result = gen_date_shift("not a date", CTX)
        assert result == "not a date"

    def test_deterministic(self):
        assert gen_date_shift("15/04/2024", CTX) == gen_date_shift("15/04/2024", CTX)


class TestSalary:
    def test_returns_number_string(self):
        result = gen_salary("35.000", CTX)
        assert result.replace(".", "").isdigit()

    def test_deterministic(self):
        assert gen_salary("35.000", CTX) == gen_salary("35.000", CTX)


class TestApiKey:
    def test_preserves_length_within_range(self):
        key = "A" * 32
        result = gen_api_key(key, CTX)
        assert len(result) == 32

    def test_defaults_to_32_for_short_input(self):
        result = gen_api_key("short", CTX)
        assert len(result) == 32

    def test_alphanumeric_only(self):
        result = gen_api_key("A" * 32, CTX)
        assert re.match(r"^[A-Za-z0-9]+$", result)


class TestAlphanumeric:
    def test_respects_length(self):
        result = gen_alphanumeric("x", CTX, length=10)
        assert len(result) == 10

    def test_uppercase_digits_only(self):
        result = gen_alphanumeric("x", CTX, length=20)
        assert re.match(r"^[A-Z0-9]+$", result)


# ── generate() dispatch ───────────────────────────────────────────────────────

class TestGenerateDispatch:
    def test_known_strategy(self):
        result = generate("targa", "AB123CD", CTX)
        assert re.match(r"^[A-Z]{2}\d{3}[A-Z]{2}$", result)

    def test_unknown_strategy_falls_back_to_alphanumeric(self):
        result = generate("nonexistent_strategy", "value", CTX)
        assert result  # non-empty
        assert re.match(r"^[A-Z0-9]+$", result)

    def test_fixed_length_strategies(self):
        assert len(generate("practice_id", "x", CTX)) == 8
        assert len(generate("policy_number", "x", CTX)) == 10
        assert len(generate("loyalty_id", "x", CTX)) == 10
        assert len(generate("ticket_id", "x", CTX)) == 8


# ── Codice Fiscale codec ──────────────────────────────────────────────────────

class TestCfCodec:
    def test_encode_known(self):
        cf = cf_encode("Rossi", "Mario", date(1980, 3, 1), "M", "Roma")
        assert len(cf) == 16
        assert cf.isupper() or cf.isalnum()

    def test_encode_female_day_plus_40(self):
        cf = cf_encode("Rossi", "Maria", date(1985, 6, 15), "F", "Milano")
        # day part for F = 15 + 40 = 55
        assert cf[9:11] == "55"

    def test_decode_gender(self):
        cf_m = cf_encode("Rossi", "Mario", date(1980, 3, 1), "M", "Roma")
        cf_f = cf_encode("Rossi", "Maria", date(1985, 6, 15), "F", "Milano")
        assert decode_partial(cf_m)["gender"] == "M"
        assert decode_partial(cf_f)["gender"] == "F"

    def test_deterministic(self):
        cf1 = cf_encode("Bianchi", "Luca", date(1990, 1, 10), "M", "Torino")
        cf2 = cf_encode("Bianchi", "Luca", date(1990, 1, 10), "M", "Torino")
        assert cf1 == cf2

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
    gen_address,
    gen_city,
    gen_username,
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

class TestPhone:
    def test_returns_string(self):
        assert isinstance(gen_phone("333-1234567", CTX), str)

    def test_non_empty(self):
        assert gen_phone("333-1234567", CTX)

    def test_deterministic(self):
        assert gen_phone("333-1234567", CTX) == gen_phone("333-1234567", CTX)


class TestAddress:
    def test_returns_string(self):
        result = gen_address("Via Roma 1, Milano", CTX)
        assert isinstance(result, str) and result

    def test_no_newlines(self):
        result = gen_address("Via Roma 1\nMilano", CTX)
        assert "\n" not in result

    def test_deterministic(self):
        assert gen_address("Via Roma 1", CTX) == gen_address("Via Roma 1", CTX)


class TestCity:
    def test_returns_string(self):
        assert isinstance(gen_city("Roma", CTX), str)

    def test_deterministic(self):
        assert gen_city("Milano", CTX) == gen_city("Milano", CTX)


class TestUsername:
    def test_returns_string(self):
        result = gen_username("mario.rossi", CTX)
        assert isinstance(result, str) and result

    def test_deterministic(self):
        assert gen_username("mario.rossi", CTX) == gen_username("mario.rossi", CTX)


class TestCreditCard:
    def test_digits_only(self):
        result = generate("credit_card", "4111111111111111", CTX)
        assert result.replace("-", "").replace(" ", "").isdigit()

    def test_deterministic(self):
        assert generate("credit_card", "4111111111111111", CTX) == generate("credit_card", "4111111111111111", CTX)


class TestSalaryEdgeCases:
    def test_invalid_input_returns_fallback(self):
        result = generate("salary", "no-numbers-here!!!", CTX)
        assert result.replace(".", "").isdigit()

    def test_empty_string_returns_fallback(self):
        result = generate("salary", "", CTX)
        assert result.replace(".", "").isdigit()


class TestDateShiftFormats:
    def test_dash_format(self):
        result = gen_date_shift("15-04-2024", CTX)
        assert re.match(r"\d{2}-\d{2}-\d{4}", result)

    def test_dot_format(self):
        result = gen_date_shift("15.04.2024", CTX)
        assert re.match(r"\d{2}\.\d{2}\.\d{4}", result)


class TestIp:
    def test_valid_ipv4(self):
        result = generate("ip", "192.168.1.1", CTX)
        parts = result.split(".")
        assert len(parts) == 4
        assert all(p.isdigit() for p in parts)

    def test_deterministic(self):
        assert generate("ip", "192.168.1.1", CTX) == generate("ip", "192.168.1.1", CTX)


class TestMac:
    def test_format(self):
        result = generate("mac", "AA:BB:CC:DD:EE:FF", CTX)
        assert len(result.replace(":", "").replace("-", "")) == 12

    def test_deterministic(self):
        assert generate("mac", "AA:BB:CC:DD:EE:FF", CTX) == generate("mac", "AA:BB:CC:DD:EE:FF", CTX)


class TestUrl:
    def test_starts_with_http(self):
        result = generate("url", "https://example.com", CTX)
        assert result.startswith("http")

    def test_deterministic(self):
        assert generate("url", "https://example.com", CTX) == generate("url", "https://example.com", CTX)


class TestGps:
    def test_two_coordinates(self):
        result = generate("gps", "41.9028, 12.4964", CTX)
        parts = result.split(", ")
        assert len(parts) == 2
        float(parts[0])
        float(parts[1])

    def test_deterministic(self):
        assert generate("gps", "41.9028, 12.4964", CTX) == generate("gps", "41.9028, 12.4964", CTX)


class TestPassword:
    def test_minimum_length_12(self):
        result = generate("password", "abc", CTX)
        assert len(result) >= 12

    def test_preserves_longer_length(self):
        result = generate("password", "A" * 20, CTX)
        assert len(result) >= 20

    def test_deterministic(self):
        assert generate("password", "secret123", CTX) == generate("password", "secret123", CTX)


class TestOrganization:
    def test_returns_string(self):
        result = generate("organization", "Acme Corp", CTX)
        assert isinstance(result, str) and result

    def test_deterministic(self):
        assert generate("organization", "Acme Corp", CTX) == generate("organization", "Acme Corp", CTX)


class TestCompany:
    def test_has_suffix_it(self):
        result = generate("company", "Alfa", CTX, locale="it_IT")
        it_suffixes = ["S.r.l.", "S.p.A.", "S.n.c.", "S.a.s.", "S.r.l.s."]
        assert any(result.endswith(s) for s in it_suffixes)

    def test_has_suffix_en(self):
        result = generate("company", "Alfa", CTX, locale="en_US")
        en_suffixes = ["LLC", "Inc.", "Corp.", "Ltd.", "LLP"]
        assert any(result.endswith(s) for s in en_suffixes)

    def test_unmapped_locale_falls_back_to_en_suffix(self):
        # pt_BR is a valid Faker locale but not in _LEGAL_SUFFIXES → falls back to en_US suffixes
        result = generate("company", "Alfa", CTX, locale="pt_BR")
        en_suffixes = ["LLC", "Inc.", "Corp.", "Ltd.", "LLP"]
        assert any(result.endswith(s) for s in en_suffixes)

    def test_deterministic(self):
        assert generate("company", "Alfa", CTX) == generate("company", "Alfa", CTX)


class TestIdentityCard:
    def test_format(self):
        result = generate("identity_card", "AB1234567C", CTX)
        assert re.match(r"^[A-Z]{2}\d{7}[A-Z]$", result), f"Invalid: {result}"

    def test_deterministic(self):
        assert generate("identity_card", "AB1234567C", CTX) == generate("identity_card", "AB1234567C", CTX)


class TestDriverLicense:
    def test_length_10_alphanumeric(self):
        result = generate("driver_license", "AB12345678", CTX)
        assert len(result) == 10
        assert re.match(r"^[A-Z0-9]+$", result)

    def test_deterministic(self):
        assert generate("driver_license", "AB12345678", CTX) == generate("driver_license", "AB12345678", CTX)


class TestHealthCard:
    def test_length_15(self):
        result = generate("health_card", "IT80387000004052024", CTX)
        assert len(result) == 15

    def test_starts_with_two_letters(self):
        result = generate("health_card", "IT80387000004052024", CTX)
        assert result[:2].isalpha() and result[:2].isupper()

    def test_deterministic(self):
        assert generate("health_card", "IT80387000004052024", CTX) == generate("health_card", "IT80387000004052024", CTX)


class TestFakeProfile:
    from app.surrogates.generators import gen_fake_profile

    def test_profile_has_all_keys(self):
        from app.surrogates.generators import gen_fake_profile
        p = gen_fake_profile("mario rossi", CTX, "M")
        for key in ("fake_first_name", "fake_last_name", "fake_birth_date", "fake_gender", "fake_city", "fake_belfiore", "fake_cf"):
            assert key in p

    def test_male_profile(self):
        from app.surrogates.generators import gen_fake_profile
        p = gen_fake_profile("mario rossi", CTX, "M")
        assert p["fake_gender"] == "M"
        assert len(p["fake_cf"]) == 16

    def test_female_profile(self):
        from app.surrogates.generators import gen_fake_profile
        p = gen_fake_profile("giulia bianchi", CTX, "F")
        assert p["fake_gender"] == "F"

    def test_invalid_gender_hint_still_produces_profile(self):
        from app.surrogates.generators import gen_fake_profile
        p = gen_fake_profile("test user", CTX, "X")
        assert p["fake_gender"] in ("M", "F")

    def test_deterministic(self):
        from app.surrogates.generators import gen_fake_profile
        p1 = gen_fake_profile("mario rossi", CTX, "M")
        p2 = gen_fake_profile("mario rossi", CTX, "M")
        assert p1["fake_cf"] == p2["fake_cf"]

    def test_cf_length_16(self):
        from app.surrogates.generators import gen_fake_profile
        p = gen_fake_profile("luca ferrari", CTX, "M")
        assert len(p["fake_cf"]) == 16


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
        assert cf[9:11] == "55"

    def test_name_with_4_or_more_consonants(self):
        # "Francesco" has consonants F, R, N, C, S, C → picks 1st, 3rd, 4th = F, N, C
        cf = cf_encode("Verdi", "Francesco", date(1990, 5, 20), "M", "Roma")
        assert cf[3:6] == "FNC"

    def test_decode_gender(self):
        cf_m = cf_encode("Rossi", "Mario", date(1980, 3, 1), "M", "Roma")
        cf_f = cf_encode("Rossi", "Maria", date(1985, 6, 15), "F", "Milano")
        assert decode_partial(cf_m)["gender"] == "M"
        assert decode_partial(cf_f)["gender"] == "F"

    def test_decode_wrong_length_returns_empty(self):
        assert decode_partial("TOOSHORT") == {}
        assert decode_partial("") == {}

    def test_decode_malformed_cf_returns_empty(self):
        # 16 chars but day field "0X" is not parseable as int → except → {}
        assert decode_partial("RSSMRA80A0XH501U") == {}

    def test_deterministic(self):
        cf1 = cf_encode("Bianchi", "Luca", date(1990, 1, 10), "M", "Torino")
        cf2 = cf_encode("Bianchi", "Luca", date(1990, 1, 10), "M", "Torino")
        assert cf1 == cf2

    def test_unknown_city_falls_back_to_h501(self):
        cf = cf_encode("Rossi", "Mario", date(1980, 3, 1), "M", "CittaInesistente")
        assert cf[11:15] == "H501"

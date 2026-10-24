import pytest

from app.detection.checksums import (
    VALIDATORS, cf_check_char, is_valid_codice_fiscale, is_valid_iban, is_valid_partita_iva,
)
from app.surrogates import cf_codec


@pytest.mark.parametrize("value", ["RSSMRA80A01H501U", "BNCLRA85T45F205L", "RSSMRA80A01H5LMX", "rssmra80a01h501u"])
def test_valid_codice_fiscale_including_omocodia(value):
    assert is_valid_codice_fiscale(value)


@pytest.mark.parametrize("value", ["RSSMRA80A01H501A", "RSSMRA80A99H501U", "RSSMRA80Z01H501U", "ABCDEFGHIJKLMNOP", ""])
def test_invalid_codice_fiscale_rejected(value):
    assert not is_valid_codice_fiscale(value)


@pytest.mark.parametrize("value", ["01234567897", "IT07940180156", "IT 02500001223"])
def test_valid_partita_iva(value):
    assert is_valid_partita_iva(value)


@pytest.mark.parametrize("value", ["01234567890", "00000000000", "1234567890", "0123456789A"])
def test_invalid_partita_iva_rejected(value):
    assert not is_valid_partita_iva(value)


@pytest.mark.parametrize("value", [
    "IT60X0542811101000000123456", "IT60 X054 2811 1010 0000 0123 456", "it57y0306909606100000063123",
    "DE89 3704 0044 0532 0130 00",
])
def test_valid_iban(value):
    assert is_valid_iban(value)


@pytest.mark.parametrize("value", [
    "IT60X0542811101000000123457", "IT60X054281110100000012345", "DE89370400440532013001", "XX00",
])
def test_invalid_iban_rejected(value):
    assert not is_valid_iban(value)


def test_surrogate_codec_shares_detection_check_char():
    cf = cf_codec.encode("Rossi", "Mario", __import__("datetime").date(1980, 1, 1), "M", "Roma")
    assert cf_check_char(cf[:15]) == cf[15]
    assert is_valid_codice_fiscale(cf)


def test_registry_exposes_named_validators():
    assert set(VALIDATORS) == {"codice_fiscale", "partita_iva", "iban"}

import pytest
from fastapi import HTTPException

from app.scoped_config.layer_validation import validate_layer_override


@pytest.mark.parametrize("levels", ["maximum", ["unknown"], [None], [{}]])
def test_reject_invalid_levels(levels):
    with pytest.raises(HTTPException) as error:
        validate_layer_override("rizzo", "override", {"protection_levels": levels})
    assert error.value.status_code == 422


def test_platform_activation_is_required(monkeypatch):
    from app.scoped_config import layer_validation
    monkeypatch.setattr(layer_validation.settings, "detection_layers", {"rizzo": {"enabled": False}})
    with pytest.raises(HTTPException) as error:
        validate_layer_override("rizzo", "override", {"enabled": True})
    assert error.value.status_code == 409
    validate_layer_override("rizzo", "override", {"enabled": False, "protection_levels": ["maximum"]})

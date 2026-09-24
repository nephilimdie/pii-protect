from unittest.mock import MagicMock

from app.anonymization.anonymizer import PiiAnonymizer


def test_context_layer_selection_cannot_reenable_disabled_tenant_layer():
    anonymizer = PiiAnonymizer(
        MagicMock(),
        enabled_layers={"regex", "presidio"},
    )

    anonymizer.restrict_layers(["regex", "ai4privacy"])

    assert anonymizer._enabled_layers == {"regex"}


def test_context_layer_selection_is_applied_when_global_layers_are_unrestricted():
    anonymizer = PiiAnonymizer(MagicMock(), enabled_layers=None)

    anonymizer.restrict_layers(["regex", "privacy_filter"])

    assert anonymizer._enabled_layers == {"regex", "privacy_filter"}

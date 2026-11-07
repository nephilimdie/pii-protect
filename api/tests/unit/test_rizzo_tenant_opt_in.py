"""Rizzo installed on the platform stays off for every tenant (and tenant-less requests) until a tenant opts in."""
import asyncio

from app.config import Settings
from app.detection import config_resolver as cr
from app.detection.config_resolver import (
    GlobalDetectionConfigResolver,
    _apply_layer_overrides,
    _global_enabled_layers,
)


def _rows(s: Settings) -> list[dict]:
    from app.detection.layer_config import LAYER_META
    return [{"code": c, "enabled": s.layer_tenant_default(c), "installed": s.layer_enabled(c),
             "protection_levels": s.layer_levels(c)} for c in LAYER_META]


def test_should_install_rizzo_without_turning_it_on_for_tenants():
    s = Settings(detection_layers={"rizzo": {"enabled": "true"}})  # what PII_RIZZO_ENABLED=true produces
    assert s.layer_enabled("rizzo") and not s.layer_tenant_default("rizzo")
    assert s.layer_tenant_default("presidio") and s.layer_levels("rizzo") == ["maximum"]


def test_should_read_string_false_as_false():
    s = Settings(detection_layers={"presidio": {"enabled": "false"}, "rizzo": {"enabled": "false"}})
    assert not s.layer_enabled("presidio") and not s.layer_enabled("rizzo")


def test_should_allow_explicit_platform_default_on():
    s = Settings(detection_layers={"rizzo": {"enabled": True, "tenant_default": "true"}})
    assert s.layer_tenant_default("rizzo")


def test_tenant_without_override_does_not_run_rizzo_but_opt_in_does():
    rows = _rows(Settings(detection_layers={"rizzo": {"enabled": "true"}}))
    assert "rizzo" not in _apply_layer_overrides(rows, [])
    opt_in = [{"item_key": "rizzo", "action": "override", "data": {"enabled": True}}]
    assert "rizzo" in _apply_layer_overrides(rows, opt_in)


def test_global_resolver_excludes_default_off_layer(monkeypatch):
    rows = _rows(Settings(detection_layers={"rizzo": {"enabled": "true"}}))
    assert _global_enabled_layers(rows) == {"regex", "presidio", "privacy_filter", "ai4privacy"}
    # rizzo not installed: unchanged behaviour (all loaded layers)
    assert _global_enabled_layers(_rows(Settings())) is None

    class State:
        detection_layers_raw = rows
    monkeypatch.setattr(cr, "_cache", {})
    cfg = asyncio.run(GlobalDetectionConfigResolver.for_request(State()))
    assert "rizzo" not in cfg.enabled_layers


def test_collection_query_shows_installed_rizzo_as_off(monkeypatch):
    from app.scoped_config import collections
    import app.config as config
    monkeypatch.setattr(config.settings, "detection_layers", {"rizzo": {"enabled": "true"}})
    sql = collections.detection_layers_query()
    rizzo_row = next(part for part in sql.split("),") if "'rizzo'" in part)
    assert "false" in rizzo_row and "'maximum'" in rizzo_row


def test_tenant_opt_in_is_accepted_when_installed(monkeypatch):
    from app.scoped_config import layer_validation
    monkeypatch.setattr(layer_validation.settings, "detection_layers", {"rizzo": {"enabled": "true"}})
    layer_validation.validate_layer_override("rizzo", "override", {"enabled": True, "protection_levels": ["maximum"]})

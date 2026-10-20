"""Surrogate inserts must infer the partial indexes created by migration 051."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.surrogates.surrogate_service import SurrogateService


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant", [None, "tenant-a"])
@pytest.mark.parametrize("pii_type,value", [("PERSON", "Mario Rossi"), ("EMAIL", "mario@example.com")])
async def test_conflict_target_matches_tenant_partial_index(tenant, pii_type, value):
    result = MagicMock()
    result.fetchone.return_value = None
    db = AsyncMock()
    db.execute.return_value = result
    service = SurrogateService(db, tenant_id=tenant, project_id="project-a")

    await service.get_or_create("context-a", value, pii_type, None)

    inserts = [call for call in db.execute.call_args_list if str(call.args[0]).startswith("INSERT")]
    assert len(inserts) == (2 if pii_type == "PERSON" else 1)
    for call in inserts:
        query, params = call.args
        columns = "project_id, context_id, "
        if "surrogate_mappings" in str(query):
            columns += "pii_type, "
        columns += "real_hash"
        predicate = "tenant_id IS NULL"
        if tenant is not None:
            columns = "tenant_id, " + columns
            predicate = "tenant_id IS NOT NULL"
        assert f"ON CONFLICT ({columns}) WHERE {predicate} DO NOTHING" in str(query)
        assert params["tenant"] == tenant
        assert params["project"] == "project-a"

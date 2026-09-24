from __future__ import annotations

from urllib.parse import urlparse
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import AnyHttpUrl, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.identity.dependencies import require_service
from app.identity.models import ApiKey
from app.identity.tenant import get_tenant_id
from app.jobs.codec import JobPayloadCodec
from app.jobs.repository import JobRepository
from app.routers._anonymize_models import AnonymizeRequest

router = APIRouter()


class AsyncAnonymizeRequest(AnonymizeRequest):
    webhook_url: AnyHttpUrl | None = Field(default=None)


def _allowed_webhook(url: str | None) -> bool:
    if url is None:
        return True
    parsed = urlparse(url)
    allowed = {host.strip().lower() for host in settings.async_job_webhook_hosts.split(",") if host.strip()}
    return parsed.scheme == "https" and bool(parsed.hostname) and parsed.hostname.lower() in allowed


@router.post("/anonymize/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    body: AsyncAnonymizeRequest,
    api_key: ApiKey = Depends(require_service),
    tenant_id: str | None = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    x_api_key: str = Header(..., alias="X-Api-Key"),
) -> dict:
    if not _allowed_webhook(str(body.webhook_url) if body.webhook_url else None):
        raise HTTPException(status_code=400, detail="webhook_host_not_allowed")

    payload = body.model_dump(exclude={"webhook_url"})
    payload["api_key"] = x_api_key
    job = await JobRepository(db).create(
        api_key_id=api_key.id,
        tenant_id=tenant_id,
        request_encrypted=JobPayloadCodec().encode(payload),
        webhook_url=str(body.webhook_url) if body.webhook_url else None,
    )
    return {
        "job_id": str(job.id),
        "status": job.status,
        "status_url": f"/v1/anonymize/jobs/{job.id}",
    }


@router.get("/anonymize/jobs/{job_id}")
async def get_job(
    job_id: uuid.UUID,
    api_key: ApiKey = Depends(require_service),
    tenant_id: str | None = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    job = await JobRepository(db).find_owned(job_id, api_key.id, tenant_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")

    response = {
        "job_id": str(job.id),
        "status": job.status,
        "attempts": job.attempts,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
    }
    if job.status == "completed" and job.result_encrypted:
        response["result"] = JobPayloadCodec().decode(job.result_encrypted)
    if job.status == "failed":
        response["error_code"] = job.error_code
    return response

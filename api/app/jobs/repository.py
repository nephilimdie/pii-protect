from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.models import AnonymizationJob


class JobRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, **values) -> AnonymizationJob:
        job = AnonymizationJob(**values)
        self._db.add(job)
        await self._db.commit()
        await self._db.refresh(job)
        return job

    async def find_owned(self, job_id: uuid.UUID, api_key_id: uuid.UUID, tenant_id: str | None) -> AnonymizationJob | None:
        result = await self._db.execute(
            select(AnonymizationJob).where(
                AnonymizationJob.id == job_id,
                AnonymizationJob.api_key_id == api_key_id,
                AnonymizationJob.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def claim(self) -> AnonymizationJob | None:
        result = await self._db.execute(
            select(AnonymizationJob)
            .where(AnonymizationJob.status == "queued")
            .order_by(AnonymizationJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None
        job.status = "processing"
        job.attempts += 1
        job.started_at = datetime.utcnow()
        await self._db.commit()
        return job

    async def complete(self, job: AnonymizationJob, result_encrypted: str) -> None:
        job.status = "completed"
        job.result_encrypted = result_encrypted
        job.completed_at = datetime.utcnow()
        await self._db.commit()

    async def fail(self, job: AnonymizationJob, error_code: str, retry: bool) -> None:
        job.status = "queued" if retry else "failed"
        job.error_code = error_code
        job.completed_at = None if retry else datetime.utcnow()
        await self._db.commit()

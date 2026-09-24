from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import settings
from app.database import AsyncSessionLocal
from app.jobs.codec import JobPayloadCodec
from app.jobs.repository import JobRepository

logger = logging.getLogger(__name__)


async def process_one() -> bool:
    async with AsyncSessionLocal() as db:
        job = await JobRepository(db).claim()
        if job is None:
            return False
        try:
            payload = JobPayloadCodec().decode(job.request_encrypted)
            api_key = str(payload.pop("api_key"))
            headers = {"X-Api-Key": api_key}
            if job.tenant_id is not None:
                headers["X-Pii-Tenant-Id"] = job.tenant_id
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.post(
                    settings.async_job_worker_api_url.rstrip("/") + "/v1/anonymize",
                    headers=headers,
                    json=payload,
                )
            if response.status_code >= 400:
                retry = job.attempts < settings.async_job_max_attempts
                await JobRepository(db).fail(job, f"ENGINE_HTTP_{response.status_code}", retry)
                return True

            result = response.json()
            await JobRepository(db).complete(job, JobPayloadCodec().encode(result))
            if job.webhook_url:
                await _deliver_webhook(job.webhook_url, str(job.id), result)
            return True
        except Exception:
            logger.exception("async anonymization job failed: %s", job.id)
            await JobRepository(db).fail(job, "WORKER_PROCESSING_FAILED", job.attempts < settings.async_job_max_attempts)
            return True


async def _deliver_webhook(url: str, job_id: str, result: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                url,
                json={"job_id": job_id, "status": "completed", "result": result},
                headers={"X-Pseudora-Job-Id": job_id},
            )
            response.raise_for_status()
    except Exception:
        logger.exception("async job webhook delivery failed: %s", job_id)


async def run_worker() -> None:
    while True:
        processed = await process_one()
        if not processed:
            await asyncio.sleep(settings.async_job_poll_seconds)


if __name__ == "__main__":
    asyncio.run(run_worker())

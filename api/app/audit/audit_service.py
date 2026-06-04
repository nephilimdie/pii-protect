import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.audit.models import AuditLog


class AuditService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def log(
        self,
        api_key_id: uuid.UUID,
        action: str,
        context_id: str | None = None,
        pii_types_found: list[str] | None = None,
        char_count: int | None = None,
    ) -> None:
        entry = AuditLog(
            id=uuid.uuid4(),
            api_key_id=api_key_id,
            action=action,
            context_id=context_id,
            pii_types_found=pii_types_found,
            char_count=char_count,
        )
        self._db.add(entry)
        await self._db.commit()

    async def list_paginated(
        self,
        page: int,
        per_page: int,
        action_filter: str | None = None,
    ) -> tuple[list[AuditLog], int]:
        stmt = select(AuditLog)
        count_stmt = select(func.count()).select_from(AuditLog)

        if action_filter:
            stmt = stmt.where(AuditLog.action == action_filter)
            count_stmt = count_stmt.where(AuditLog.action == action_filter)

        total_result = await self._db.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = stmt.order_by(AuditLog.created_at.desc())
        stmt = stmt.offset((page - 1) * per_page).limit(per_page)
        result = await self._db.execute(stmt)
        items = list(result.scalars().all())
        return items, total

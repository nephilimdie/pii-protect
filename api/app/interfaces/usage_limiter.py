from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class UsageContext:
    tenant_id: str | None
    chars_in: int
    endpoint: str
    request_id: str = ""


class UsageLimiterInterface(ABC):
    @abstractmethod
    async def check(self, ctx: UsageContext) -> None:
        """Raise HTTPException(429) if a rate or quota limit is exceeded."""
        ...

    @abstractmethod
    async def record(self, ctx: UsageContext, chars_out: int, status: int) -> None:
        """Persist usage after the request completes. Must not raise."""
        ...


class LocalUsageLimiter(UsageLimiterInterface):
    """Self-hosted limiter. Commercial quota (requests/min, chars/month) is pii-cloud's responsibility."""

    async def check(self, ctx: UsageContext) -> None:
        pass

    async def record(self, ctx: UsageContext, chars_out: int, status: int) -> None:
        pass

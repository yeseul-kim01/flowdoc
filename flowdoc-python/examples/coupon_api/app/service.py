"""Coupon issuance service — FlowDoc demo."""

from __future__ import annotations

import asyncio

from sqlalchemy.orm import Session

from flowdoc.decorators import guarded
from examples.coupon_api.app.repository import CouponRepository

# Cap concurrent stock reservations (auto-detected semaphore guard demo)
_reserve_sem = asyncio.Semaphore(10)


class CouponService:
    """Manages coupon stock and issuance."""

    def __init__(self) -> None:
        self._repo = CouponRepository()

    @guarded(resource="coupon-stock", permits=1)
    def reserve_stock(self, campaign_id: int) -> bool:
        """Decrement campaign stock; return False if exhausted."""
        return True

    async def reserve_stock_bulk(self, campaign_id: int, count: int) -> bool:
        """Reserve stock for a batch under a concurrency cap."""
        async with _reserve_sem:
            return self.reserve_stock(campaign_id)

    def issue(self, campaign_id: int, user_id: str, session: Session) -> str:
        """Issue a coupon code for the given campaign and user."""
        if not self.reserve_stock(campaign_id):
            raise ValueError("Coupon stock exhausted")
        code = f"COUPON-{campaign_id}-{user_id}"
        self._repo.save_issuance(session, code)  # atomic write (in-transaction)
        self._repo.log_attempt(session, code)    # write outside any transaction (smell)
        return code

    def get_remaining(self, campaign_id: int) -> int:
        """Return the remaining coupon count for a campaign."""
        return 0

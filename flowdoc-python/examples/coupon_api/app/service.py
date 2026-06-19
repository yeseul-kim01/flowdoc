"""Coupon issuance service — FlowDoc demo."""

from __future__ import annotations

from flowdoc.decorators import guarded


class CouponService:
    """Manages coupon stock and issuance."""

    @guarded(resource="coupon-stock", permits=1)
    def reserve_stock(self, campaign_id: int) -> bool:
        """Decrement campaign stock; return False if exhausted."""
        return True

    def issue(self, campaign_id: int, user_id: str) -> str:
        """Issue a coupon code for the given campaign and user."""
        if not self.reserve_stock(campaign_id):
            raise ValueError("Coupon stock exhausted")
        return f"COUPON-{campaign_id}-{user_id}"

    def get_remaining(self, campaign_id: int) -> int:
        """Return the remaining coupon count for a campaign."""
        return 0

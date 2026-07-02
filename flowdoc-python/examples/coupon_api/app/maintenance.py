"""Scheduled coupon maintenance — FlowDoc demo of the 'scheduled' trigger kind.

Mirrors coupon-rush (Spring) CouponMaintenance.reportStock (@Scheduled) to
validate Python parity for Issue #2.
"""

from __future__ import annotations

from fastapi_utils.tasks import repeat_every

from examples.coupon_api.app.service import CouponService

_svc = CouponService()


@repeat_every(seconds=86400)
def report_stock() -> None:
    """Report remaining stock for all campaigns once a day."""
    _svc.get_remaining(0)

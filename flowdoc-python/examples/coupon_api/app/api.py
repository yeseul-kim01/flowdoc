"""Coupon API router — FlowDoc demo.

Mirrors coupon-rush (Spring) to validate Python parity:
  POST /{campaignId}/coupons  →  issue coupon
  GET  /{campaignId}/remaining →  remaining count
"""

from __future__ import annotations

from fastapi import APIRouter

from flowdoc.decorators import flow_entry
from examples.coupon_api.app.service import CouponService

router = APIRouter(prefix="/coupon")
_svc = CouponService()


@flow_entry("issue-coupon")
@router.post("/{campaign_id}/coupons")
def issue_coupon(campaign_id: int, user_id: str) -> dict:
    """Issue a coupon for the given campaign and user."""
    code = _svc.issue(campaign_id, user_id)
    return {"code": code}


@router.get("/{campaign_id}/remaining")
def get_remaining(campaign_id: int) -> dict:
    """Return remaining coupon count for the campaign."""
    remaining = _svc.get_remaining(campaign_id)
    return {"remaining": remaining}

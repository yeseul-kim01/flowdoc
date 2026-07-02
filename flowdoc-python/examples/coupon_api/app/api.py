"""Coupon API router — FlowDoc demo.

Mirrors coupon-rush (Spring) to validate Python parity:
  POST /{campaignId}/coupons  →  issue coupon
  GET  /{campaignId}/remaining →  remaining count
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from flowdoc.decorators import flow_entry
from examples.coupon_api.app.service import CouponService

router = APIRouter(prefix="/coupon")
_svc = CouponService()


def get_session() -> Session:
    """Provide a database session (wired by the app in production)."""
    ...


@flow_entry("issue-coupon")
@router.post("/{campaign_id}/coupons")
def issue_coupon(campaign_id: int, user_id: str, session: Session = Depends(get_session)) -> dict:
    """Issue a coupon for the given campaign and user."""
    code = _svc.issue(campaign_id, user_id, session)
    return {"code": code}


@router.get("/{campaign_id}/remaining")
def get_remaining(campaign_id: int) -> dict:
    """Return remaining coupon count for the campaign."""
    remaining = _svc.get_remaining(campaign_id)
    return {"remaining": remaining}


@router.websocket("/live")
async def live_stock(campaign_id: int) -> None:
    """Stream remaining stock updates over a WebSocket."""
    _svc.get_remaining(campaign_id)

"""Coupon persistence — FlowDoc demo of transaction-boundary detection.

Mirrors coupon-rush (Spring) to validate Python parity for Issue #4:
  save_issuance  → writes inside `with session.begin()` (in-transaction)
  log_attempt    → writes with no surrounding transaction (atomicity smell)

The scanner emits markers.transaction on the boundary opener and markers.dataAccess
on the writes; the UI threads in-transaction state through the call tree and badges
a write reached outside any transaction.
"""

from __future__ import annotations

from sqlalchemy.orm import Session


class CouponRepository:
    """Stores coupon issuances and attempt logs."""

    def save_issuance(self, session: Session, code: str) -> None:
        """Persist an issuance atomically (inside a transaction)."""
        with session.begin():
            session.add(code)

    def log_attempt(self, session: Session, code: str) -> None:
        """Append an attempt log — intentionally outside any transaction."""
        session.add(code)

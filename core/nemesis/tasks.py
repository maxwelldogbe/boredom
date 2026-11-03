"""Nemesis upkeep run by the daily background loop (analytics.recorder)."""

import logging

from nemesis import ids, ledger, wallet

logger = logging.getLogger(__name__)


def daily() -> None:
    """Ledger check (a mismatch is logged as an ERROR) and ID image retention."""
    result = ledger.reconcile()
    if not result.ok:
        logger.error("Ledger check FAILED: %s", result.as_dict())
    removed = ids.prune_images()
    if removed:
        logger.info("Deleted the images of %s ID verifications", removed)


def frequent() -> None:
    """Expire deposit requests left awaiting payment past DEPOSIT_REQUEST_TTL_MIN."""
    expired = wallet.expire_deposits()
    if expired:
        logger.info("Expired %s unpaid deposit requests", expired)

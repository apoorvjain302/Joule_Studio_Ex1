"""HU Correction Tool.

Validates preconditions before the agent:
  1. Unloads / cancels the pick of an incorrect HU via `unload_handling_unit` MCP tool.
  2. Loads / picks the correct HU onto the pallet via `load_handling_unit` MCP tool.

Only valid when a PARTIAL_MATCH or MISMATCH is detected with sufficient confidence,
and the delivery is NOT already blocked.
"""

import logging
from datetime import datetime, timezone

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_CORRECTABLE_STATUSES = {"PARTIAL_MATCH", "MISMATCH"}
_MIN_CONFIDENCE = 0.75


@tool
def validate_hu_correction_preconditions(
    match_status: str,
    delivery_blocked: bool,
    overall_confidence: float,
    extra_on_pallet: list,
    missing_from_pallet: list,
) -> dict:
    """Validate preconditions before correcting a pallet -- cancelling incorrect HU picks
    and triggering picks for the correct HUs.

    Args:
        match_status: HU match status from match_hu_to_delivery.
                      Must be PARTIAL_MATCH or MISMATCH.
        delivery_blocked: Whether the delivery is already blocked. Correction NOT allowed
                          when blocked.
        overall_confidence: AI detection confidence (0.0-1.0). Must be >= 0.75.
        extra_on_pallet: HU IDs detected on pallet but NOT in delivery (must be unloaded).
        missing_from_pallet: HU IDs in delivery but NOT on pallet (must be loaded).

    Returns:
        dict with allowed, reason, hus_to_unload, hus_to_load, checked_at.
    """
    now = datetime.now(timezone.utc).isoformat()

    if delivery_blocked:
        logger.warning(
            "M7.missed: hu correction precondition failed -- delivery is blocked"
        )
        return {
            "allowed": False,
            "reason": (
                "HU correction is not allowed because the delivery is already blocked. "
                "A supervisor must clear the block before any HU correction can be made."
            ),
            "hus_to_unload": [],
            "hus_to_load": [],
            "checked_at": now,
        }

    if match_status not in _CORRECTABLE_STATUSES:
        logger.info(
            "M7.missed: hu correction not needed -- match_status=%s", match_status
        )
        return {
            "allowed": False,
            "reason": (
                f"HU correction is only applicable for PARTIAL_MATCH or MISMATCH status, "
                f"but current status is '{match_status}'. No correction needed."
            ),
            "hus_to_unload": [],
            "hus_to_load": [],
            "checked_at": now,
        }

    if overall_confidence < _MIN_CONFIDENCE:
        logger.warning(
            "M7.missed: hu correction precondition failed -- confidence=%.2f below threshold=%.2f",
            overall_confidence,
            _MIN_CONFIDENCE,
        )
        return {
            "allowed": False,
            "reason": (
                f"HU correction requires detection confidence >= {_MIN_CONFIDENCE:.0%}, "
                f"but current confidence is {overall_confidence:.0%}. "
                "Please retake the photo with better lighting before attempting correction."
            ),
            "hus_to_unload": [],
            "hus_to_load": [],
            "checked_at": now,
        }

    if not extra_on_pallet and not missing_from_pallet:
        logger.warning(
            "M7.missed: hu correction called with empty discrepancy lists"
        )
        return {
            "allowed": False,
            "reason": (
                "No HU discrepancies were provided (extra_on_pallet and "
                "missing_from_pallet are both empty). Nothing to correct."
            ),
            "hus_to_unload": [],
            "hus_to_load": [],
            "checked_at": now,
        }

    logger.info(
        "M7.achieved: hu correction preconditions met -- "
        "unload=%s, load=%s, confidence=%.2f",
        extra_on_pallet,
        missing_from_pallet,
        overall_confidence,
    )
    return {
        "allowed": True,
        "reason": "",
        "hus_to_unload": list(extra_on_pallet),
        "hus_to_load": list(missing_from_pallet),
        "checked_at": now,
    }

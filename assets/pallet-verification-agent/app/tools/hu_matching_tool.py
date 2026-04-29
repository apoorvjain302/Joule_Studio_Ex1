"""REQ-03 & REQ-04: HU Cross-Reference Matching tool."""

from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def match_hu_to_delivery(detected_hus: list, expected_hus: list) -> dict:
    """Cross-reference detected HUs against expected HUs on the EWM outbound delivery.

    Args:
        detected_hus: List of SSCC/barcode strings from the pallet photo.
        expected_hus: List of SSCC strings from the EWM delivery HU assignment.

    Returns:
        dict: matched, missing_from_pallet, extra_on_pallet, unreadable_labels, match_status.
    """
    if not detected_hus and not expected_hus:
        logger.warning("M4.missed: HU matching could not be completed — insufficient label data or delivery data unavailable")
        return {"matched": [], "missing_from_pallet": [], "extra_on_pallet": [], "unreadable_labels": 0, "match_status": "MISMATCH"}

    if not detected_hus:
        logger.warning("M4.missed: HU matching could not be completed — insufficient label data or delivery data unavailable")
        return {"matched": [], "missing_from_pallet": list(expected_hus), "extra_on_pallet": [], "unreadable_labels": 0, "match_status": "MISMATCH"}

    if not expected_hus:
        logger.warning("M4.missed: HU matching could not be completed — insufficient label data or delivery data unavailable")
        return {"matched": [], "missing_from_pallet": [], "extra_on_pallet": list(detected_hus), "unreadable_labels": 0, "match_status": "MISMATCH"}

    readable = [hu.strip().upper() for hu in detected_hus if hu and hu.strip()]
    unreadable_count = len(detected_hus) - len(readable)
    expected_set = {hu.strip().upper() for hu in expected_hus if hu and hu.strip()}
    detected_set = set(readable)

    matched = sorted(detected_set & expected_set)
    missing = sorted(expected_set - detected_set)
    extra = sorted(detected_set - expected_set)

    if not matched:
        status = "MISMATCH"
    elif missing or extra or unreadable_count > 0:
        status = "PARTIAL_MATCH"
    else:
        status = "FULL_MATCH"

    logger.info(
        "M4.achieved: HU matching completed — matched=%d, missing=%d, extra=%d, unreadable=%d",
        len(matched), len(missing), len(extra), unreadable_count,
    )
    return {"matched": matched, "missing_from_pallet": missing, "extra_on_pallet": extra, "unreadable_labels": unreadable_count, "match_status": status}

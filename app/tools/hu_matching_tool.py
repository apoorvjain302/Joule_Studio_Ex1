"""REQ-03 & REQ-04: HU Cross-Reference Matching tool.

Cross-references detected HUs from the pallet photo against the expected HU list
from the EWM outbound delivery. Identifies missing, extra, and unreadable HUs.
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def match_hu_to_delivery(detected_hus: list, expected_hus: list) -> dict:
    """Cross-reference detected HUs against expected HUs on the EWM outbound delivery.

    Compares the HU SSCC/barcode values extracted from the pallet photo against
    the expected HU list retrieved from the EWM delivery record. Reports matched,
    missing, and extra HUs along with an overall match status.

    Args:
        detected_hus: List of SSCC/barcode strings extracted from the pallet photo
                      by the detect_hu_labels tool.
        expected_hus: List of SSCC strings from the EWM delivery HU assignment,
                      retrieved via MCP tool calls.

    Returns:
        dict with keys:
            matched (list[str]): HU IDs found both on the pallet and in the delivery.
            missing_from_pallet (list[str]): HU IDs expected on delivery but not detected.
            extra_on_pallet (list[str]): HU IDs detected on pallet but not on delivery.
            unreadable_labels (int): Count of labels detected but with empty barcode values.
            match_status (str): One of 'FULL_MATCH', 'PARTIAL_MATCH', 'MISMATCH'.
    """
    if not detected_hus and not expected_hus:
        logger.warning(
            "M4.missed: HU matching could not be completed — insufficient label data or delivery data unavailable"
        )
        return {
            "matched": [],
            "missing_from_pallet": [],
            "extra_on_pallet": [],
            "unreadable_labels": 0,
            "match_status": "MISMATCH",
        }

    if not detected_hus:
        logger.warning(
            "M4.missed: HU matching could not be completed — insufficient label data or delivery data unavailable"
        )
        return {
            "matched": [],
            "missing_from_pallet": list(expected_hus),
            "extra_on_pallet": [],
            "unreadable_labels": 0,
            "match_status": "MISMATCH",
        }

    if not expected_hus:
        logger.warning(
            "M4.missed: HU matching could not be completed — insufficient label data or delivery data unavailable"
        )
        return {
            "matched": [],
            "missing_from_pallet": [],
            "extra_on_pallet": list(detected_hus),
            "unreadable_labels": 0,
            "match_status": "MISMATCH",
        }

    # Normalise to uppercase stripped strings; filter out empty barcode values
    readable_detected = [hu.strip().upper() for hu in detected_hus if hu and hu.strip()]
    unreadable_count = len(detected_hus) - len(readable_detected)

    expected_set = {hu.strip().upper() for hu in expected_hus if hu and hu.strip()}
    detected_set = set(readable_detected)

    matched = sorted(detected_set & expected_set)
    missing_from_pallet = sorted(expected_set - detected_set)
    extra_on_pallet = sorted(detected_set - expected_set)

    # Determine match status
    if not matched:
        match_status = "MISMATCH"
    elif missing_from_pallet or extra_on_pallet or unreadable_count > 0:
        match_status = "PARTIAL_MATCH"
    else:
        match_status = "FULL_MATCH"

    logger.info(
        "M4.achieved: HU matching completed — matched=%d, missing=%d, extra=%d, unreadable=%d",
        len(matched),
        len(missing_from_pallet),
        len(extra_on_pallet),
        unreadable_count,
    )

    return {
        "matched": matched,
        "missing_from_pallet": missing_from_pallet,
        "extra_on_pallet": extra_on_pallet,
        "unreadable_labels": unreadable_count,
        "match_status": match_status,
    }

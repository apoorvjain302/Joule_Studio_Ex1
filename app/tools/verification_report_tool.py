"""REQ-06: Structured Pass/Fail Verification Report tool.

Generates a comprehensive pass/fail verification report from the HU matching result
and label detection data, and records whether the delivery was blocked.
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def generate_verification_report(
    delivery_number: str,
    match_result: dict,
    label_result: dict,
    delivery_blocked: bool,
) -> dict:
    """Generate a structured pass/fail verification report for a pallet load.

    Combines HU matching results and label detection results into a single report
    that warehouse workers can act on immediately.

    Args:
        delivery_number: The EWM outbound delivery number (e.g. '0080001234').
        match_result: Output from the match_hu_to_delivery tool containing
                      'matched', 'missing_from_pallet', 'extra_on_pallet',
                      'unreadable_labels', and 'match_status'.
        label_result: Output from the detect_hu_labels tool containing
                      'labels', 'overall_confidence', and 'low_quality'.
        delivery_blocked: Whether a delivery block was set on the EWM delivery
                          as a result of this verification.

    Returns:
        dict with keys:
            overall_status (str): 'PASS' or 'FAIL'.
            delivery_number (str): The verified delivery number.
            matched_hu_count (int): Number of HUs that matched.
            total_expected_hu_count (int): Total HUs expected on delivery.
            missing_hus (list[str]): HU IDs missing from the pallet.
            extra_hus (list[str]): HU IDs on pallet not on delivery.
            unreadable_labels (int): Count of unreadable labels.
            delivery_blocked (bool): Whether the delivery is blocked.
            summary (str): Human-readable summary for the worker.
    """
    try:
        match_status = match_result.get("match_status", "MISMATCH")
        matched = match_result.get("matched", [])
        missing_hus = match_result.get("missing_from_pallet", [])
        extra_hus = match_result.get("extra_on_pallet", [])
        unreadable_labels = int(match_result.get("unreadable_labels", 0))

        labels = label_result.get("labels", [])
        all_unreadable = len(labels) > 0 and all(
            not lbl.get("readable", True) for lbl in labels
        )

        total_expected = len(matched) + len(missing_hus)

        # PASS only when full match AND all labels readable AND not low_quality
        is_pass = (
            match_status == "FULL_MATCH"
            and unreadable_labels == 0
            and not all_unreadable
            and not label_result.get("low_quality", False)
        )
        overall_status = "PASS" if is_pass else "FAIL"

        # Build human-readable summary
        if overall_status == "PASS":
            summary = (
                f"All {len(matched)} HUs verified. "
                f"Pallet matches outbound delivery {delivery_number}. "
                "Ready to load."
            )
        else:
            issues = []
            if missing_hus:
                issues.append(f"{len(missing_hus)} HU(s) missing from pallet: {', '.join(missing_hus)}")
            if extra_hus:
                issues.append(f"{len(extra_hus)} unexpected HU(s) on pallet: {', '.join(extra_hus)}")
            if unreadable_labels:
                issues.append(f"{unreadable_labels} unreadable label(s)")
            if all_unreadable:
                issues.append("all labels are unreadable")
            if label_result.get("low_quality", False):
                issues.append("photo quality below threshold — retake required")

            issue_text = "; ".join(issues) if issues else "discrepancy detected"
            blocked_text = " Delivery has been BLOCKED." if delivery_blocked else ""
            summary = (
                f"Verification FAILED for delivery {delivery_number}: {issue_text}."
                f"{blocked_text}"
            )

        logger.info(
            "M5.achieved: verification report delivered — status=%s, delivery_blocked=%s",
            overall_status,
            str(delivery_blocked).lower(),
        )

        return {
            "overall_status": overall_status,
            "delivery_number": delivery_number,
            "matched_hu_count": len(matched),
            "total_expected_hu_count": total_expected,
            "missing_hus": missing_hus,
            "extra_hus": extra_hus,
            "unreadable_labels": unreadable_labels,
            "delivery_blocked": delivery_blocked,
            "summary": summary,
        }

    except Exception as exc:
        logger.error(
            "M5.missed: verification report generation failed — worker notified to escalate. Error: %s",
            exc,
        )
        return {
            "overall_status": "FAIL",
            "delivery_number": delivery_number,
            "matched_hu_count": 0,
            "total_expected_hu_count": 0,
            "missing_hus": [],
            "extra_hus": [],
            "unreadable_labels": 0,
            "delivery_blocked": delivery_blocked,
            "summary": f"Verification report generation failed for delivery {delivery_number}. Please escalate to supervisor.",
        }

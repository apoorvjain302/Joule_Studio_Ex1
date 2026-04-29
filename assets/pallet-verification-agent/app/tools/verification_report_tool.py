"""REQ-06: Structured Pass/Fail Verification Report tool."""

from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def generate_verification_report(delivery_number: str, match_result: dict, label_result: dict, delivery_blocked: bool) -> dict:
    """Generate a structured pass/fail verification report for a pallet load.

    Args:
        delivery_number: EWM outbound delivery number (e.g. '0080001234').
        match_result: Output from match_hu_to_delivery tool.
        label_result: Output from detect_hu_labels tool.
        delivery_blocked: Whether a delivery block was set on the EWM delivery.

    Returns:
        dict: overall_status, delivery_number, matched_hu_count, total_expected_hu_count,
              missing_hus, extra_hus, unreadable_labels, delivery_blocked, summary.
    """
    try:
        match_status = match_result.get("match_status", "MISMATCH")
        matched = match_result.get("matched", [])
        missing_hus = match_result.get("missing_from_pallet", [])
        extra_hus = match_result.get("extra_on_pallet", [])
        unreadable_labels = int(match_result.get("unreadable_labels", 0))

        labels = label_result.get("labels", [])
        all_unreadable = len(labels) > 0 and all(not l.get("readable", True) for l in labels)
        total_expected = len(matched) + len(missing_hus)

        is_pass = (
            match_status == "FULL_MATCH"
            and unreadable_labels == 0
            and not all_unreadable
            and not label_result.get("low_quality", False)
        )
        overall_status = "PASS" if is_pass else "FAIL"

        if overall_status == "PASS":
            summary = f"All {len(matched)} HUs verified. Pallet matches outbound delivery {delivery_number}. Ready to load."
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
            summary = f"Verification FAILED for delivery {delivery_number}: {issue_text}.{blocked_text}"

        logger.info(
            "M5.achieved: verification report delivered — status=%s, delivery_blocked=%s",
            overall_status, str(delivery_blocked).lower(),
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
        logger.error("M5.missed: verification report generation failed — worker notified to escalate. Error: %s", exc)
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

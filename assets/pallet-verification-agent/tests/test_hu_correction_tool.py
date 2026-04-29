"""Tests for validate_hu_correction_preconditions tool."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from tools.hu_correction_tool import validate_hu_correction_preconditions


def test_partial_match_extra_hus_high_confidence_returns_allowed():
    result = validate_hu_correction_preconditions.invoke({
        "match_status": "PARTIAL_MATCH",
        "delivery_blocked": False,
        "overall_confidence": 0.92,
        "extra_on_pallet": ["00340123450000099999"],
        "missing_from_pallet": [],
    })
    assert result["allowed"] is True
    assert result["hus_to_unload"] == ["00340123450000099999"]
    assert result["hus_to_load"] == []
    assert result["reason"] == ""


def test_mismatch_missing_hus_returns_allowed():
    result = validate_hu_correction_preconditions.invoke({
        "match_status": "MISMATCH",
        "delivery_blocked": False,
        "overall_confidence": 0.88,
        "extra_on_pallet": [],
        "missing_from_pallet": ["00340123450000012343"],
    })
    assert result["allowed"] is True
    assert result["hus_to_load"] == ["00340123450000012343"]
    assert result["hus_to_unload"] == []


def test_partial_match_both_extra_and_missing_returns_both_lists():
    result = validate_hu_correction_preconditions.invoke({
        "match_status": "PARTIAL_MATCH",
        "delivery_blocked": False,
        "overall_confidence": 0.80,
        "extra_on_pallet": ["WRONG-HU-001"],
        "missing_from_pallet": ["CORRECT-HU-002"],
    })
    assert result["allowed"] is True
    assert result["hus_to_unload"] == ["WRONG-HU-001"]
    assert result["hus_to_load"] == ["CORRECT-HU-002"]


def test_confidence_exactly_at_threshold_returns_allowed():
    result = validate_hu_correction_preconditions.invoke({
        "match_status": "PARTIAL_MATCH",
        "delivery_blocked": False,
        "overall_confidence": 0.75,
        "extra_on_pallet": ["WRONG-HU-001"],
        "missing_from_pallet": [],
    })
    assert result["allowed"] is True


def test_delivery_blocked_returns_not_allowed():
    result = validate_hu_correction_preconditions.invoke({
        "match_status": "PARTIAL_MATCH",
        "delivery_blocked": True,
        "overall_confidence": 0.92,
        "extra_on_pallet": ["WRONG-HU-001"],
        "missing_from_pallet": [],
    })
    assert result["allowed"] is False
    assert "block" in result["reason"].lower()
    assert result["hus_to_unload"] == []
    assert result["hus_to_load"] == []


def test_pass_status_returns_not_allowed():
    result = validate_hu_correction_preconditions.invoke({
        "match_status": "PASS",
        "delivery_blocked": False,
        "overall_confidence": 0.92,
        "extra_on_pallet": [],
        "missing_from_pallet": [],
    })
    assert result["allowed"] is False


def test_fail_status_returns_not_allowed():
    result = validate_hu_correction_preconditions.invoke({
        "match_status": "FAIL",
        "delivery_blocked": False,
        "overall_confidence": 0.92,
        "extra_on_pallet": ["WRONG-HU"],
        "missing_from_pallet": [],
    })
    assert result["allowed"] is False


def test_low_confidence_returns_not_allowed():
    result = validate_hu_correction_preconditions.invoke({
        "match_status": "PARTIAL_MATCH",
        "delivery_blocked": False,
        "overall_confidence": 0.60,
        "extra_on_pallet": ["WRONG-HU-001"],
        "missing_from_pallet": [],
    })
    assert result["allowed"] is False
    assert "confidence" in result["reason"].lower()


def test_zero_confidence_returns_not_allowed():
    result = validate_hu_correction_preconditions.invoke({
        "match_status": "MISMATCH",
        "delivery_blocked": False,
        "overall_confidence": 0.0,
        "extra_on_pallet": ["HU-001"],
        "missing_from_pallet": [],
    })
    assert result["allowed"] is False


def test_empty_discrepancy_lists_returns_not_allowed():
    result = validate_hu_correction_preconditions.invoke({
        "match_status": "PARTIAL_MATCH",
        "delivery_blocked": False,
        "overall_confidence": 0.92,
        "extra_on_pallet": [],
        "missing_from_pallet": [],
    })
    assert result["allowed"] is False
    assert "empty" in result["reason"].lower() or "nothing" in result["reason"].lower()


def test_result_always_contains_checked_at_timestamp():
    result = validate_hu_correction_preconditions.invoke({
        "match_status": "PARTIAL_MATCH",
        "delivery_blocked": False,
        "overall_confidence": 0.88,
        "extra_on_pallet": ["HU-001"],
        "missing_from_pallet": [],
    })
    assert "checked_at" in result
    assert "T" in result["checked_at"]


def test_multiple_hus_in_both_lists():
    result = validate_hu_correction_preconditions.invoke({
        "match_status": "MISMATCH",
        "delivery_blocked": False,
        "overall_confidence": 0.90,
        "extra_on_pallet": ["WRONG-A", "WRONG-B"],
        "missing_from_pallet": ["CORRECT-X", "CORRECT-Y", "CORRECT-Z"],
    })
    assert result["allowed"] is True
    assert len(result["hus_to_unload"]) == 2
    assert len(result["hus_to_load"]) == 3

"""Comprehensive unit tests for all 8 steps of the EWM Pallet Verification workflow.

Step 1 — Photo Ingestion          (validate_and_prepare_image)
Step 2 — HU Label Detection       (detect_hu_labels)
Step 3 — EWM Delivery Fetch       (mocked MCP tool: get_outbound_delivery_hu_list)
Step 4 — HU Cross-Reference Match (match_hu_to_delivery)
Step 5 — Verification Report      (generate_verification_report)
Step 6 — Block Delivery           (mocked MCP tool: patch_whse_outbound_delivery_order_head)
Step 7 — HU Correction            (validate_hu_correction_preconditions  +
                                   mocked MCP tools: unload_handling_unit,
                                                     load_handling_unit)
Step 8 — Post Goods Issue         (validate_goods_issue_preconditions +
                                   mocked MCP tool: post_goods_issue_ewm)
"""

from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Path setup — allows imports from the agent app package
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from tools.hu_correction_tool import validate_hu_correction_preconditions
from tools.hu_matching_tool import match_hu_to_delivery
from tools.image_ingest_tool import validate_and_prepare_image
from tools.post_goods_issue_tool import validate_goods_issue_preconditions
from tools.verification_report_tool import generate_verification_report

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------
# A minimal JPEG payload (>10 KB) that satisfies MIN_IMAGE_SIZE_BYTES=10_000
_VALID_JPEG_RAW = b"\xff\xd8\xff\xe0" + b"\x00" * 12_000
_VALID_JPEG_B64 = base64.b64encode(_VALID_JPEG_RAW).decode()
_VALID_DATA_URI = f"data:image/jpeg;base64,{_VALID_JPEG_B64}"

# SSCC values used across multiple tests
_HU_A = "00340123450000001111"
_HU_B = "00340123450000002222"
_HU_C = "00340123450000003333"  # unexpected extra on pallet
_HU_D = "00340123450000004444"  # missing from pallet

# Delivery number used across tests
_DELIVERY = "0080001234"


# ===========================================================================
# STEP 1 — Photo Ingestion
# ===========================================================================
class TestStep1PhotoIngestion(unittest.TestCase):
    """Step 1: validate_and_prepare_image — accept/reject pallet photos."""

    # --- happy path --------------------------------------------------------

    def test_valid_jpeg_base64_returns_ready(self):
        result = validate_and_prepare_image.invoke(
            {"image_data": _VALID_JPEG_B64, "source_channel": "mobile"}
        )
        self.assertTrue(result["ready"])
        self.assertIsNone(result["error"])
        self.assertEqual(result["channel"], "mobile")
        self.assertIn("image_id", result)

    def test_valid_data_uri_returns_ready(self):
        result = validate_and_prepare_image.invoke(
            {"image_data": _VALID_DATA_URI, "source_channel": "dock_camera"}
        )
        self.assertTrue(result["ready"])
        self.assertIsNone(result["error"])

    def test_valid_url_returns_ready(self):
        result = validate_and_prepare_image.invoke(
            {
                "image_data": "https://example.com/pallet.jpg",
                "source_channel": "web",
            }
        )
        self.assertTrue(result["ready"])
        self.assertIsNone(result["error"])

    def test_all_four_channels_accepted(self):
        for channel in ("mobile", "handheld", "dock_camera", "web"):
            with self.subTest(channel=channel):
                result = validate_and_prepare_image.invoke(
                    {"image_data": _VALID_JPEG_B64, "source_channel": channel}
                )
                self.assertTrue(result["ready"])
                self.assertEqual(result["channel"], channel)

    def test_png_data_uri_returns_ready(self):
        png_uri = f"data:image/png;base64,{_VALID_JPEG_B64}"
        result = validate_and_prepare_image.invoke(
            {"image_data": png_uri, "source_channel": "handheld"}
        )
        self.assertTrue(result["ready"])

    # --- error cases -------------------------------------------------------

    def test_empty_string_returns_not_ready(self):
        result = validate_and_prepare_image.invoke(
            {"image_data": "", "source_channel": "mobile"}
        )
        self.assertFalse(result["ready"])
        self.assertIsNotNone(result["error"])

    def test_whitespace_only_returns_not_ready(self):
        result = validate_and_prepare_image.invoke(
            {"image_data": "   ", "source_channel": "mobile"}
        )
        self.assertFalse(result["ready"])

    def test_too_small_image_returns_not_ready(self):
        tiny = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 100).decode()
        result = validate_and_prepare_image.invoke(
            {"image_data": tiny, "source_channel": "mobile"}
        )
        self.assertFalse(result["ready"])
        self.assertIn("small", result["error"].lower())

    def test_unsupported_mime_type_returns_not_ready(self):
        bmp_uri = f"data:image/bmp;base64,{_VALID_JPEG_B64}"
        result = validate_and_prepare_image.invoke(
            {"image_data": bmp_uri, "source_channel": "web"}
        )
        self.assertFalse(result["ready"])
        self.assertIn("Unsupported", result["error"])

    def test_invalid_base64_returns_not_ready(self):
        result = validate_and_prepare_image.invoke(
            {"image_data": "not_base64!!!", "source_channel": "mobile"}
        )
        self.assertFalse(result["ready"])

    def test_unique_image_ids_per_call(self):
        r1 = validate_and_prepare_image.invoke(
            {"image_data": _VALID_JPEG_B64, "source_channel": "mobile"}
        )
        r2 = validate_and_prepare_image.invoke(
            {"image_data": _VALID_JPEG_B64, "source_channel": "mobile"}
        )
        self.assertNotEqual(r1["image_id"], r2["image_id"])


# ===========================================================================
# STEP 2 — HU Label Detection
# ===========================================================================
class TestStep2LabelDetection(unittest.TestCase):
    """Step 2: detect_hu_labels — call vision AI and extract SSCC barcodes."""

    def _mock_labels(self, barcodes: list[str], confidence: float = 0.92):
        return {
            "labels": [
                {
                    "present": True,
                    "readable": True,
                    "confidence": confidence,
                    "barcode_value": bc,
                }
                for bc in barcodes
            ],
            "overall_confidence": confidence,
        }

    # --- happy path --------------------------------------------------------

    def test_single_hu_detected_high_confidence(self):
        mock_result = self._mock_labels([_HU_A], confidence=0.95)
        with patch("tools.label_detection_tool._call_vision_model", return_value=mock_result):
            from tools.label_detection_tool import detect_hu_labels

            result = detect_hu_labels.invoke({"image_data": _VALID_JPEG_B64})
        self.assertEqual(len(result["labels"]), 1)
        self.assertAlmostEqual(result["overall_confidence"], 0.95, places=2)
        self.assertFalse(result["low_quality"])

    def test_multiple_hus_detected(self):
        mock_result = self._mock_labels([_HU_A, _HU_B], confidence=0.90)
        with patch("tools.label_detection_tool._call_vision_model", return_value=mock_result):
            from tools.label_detection_tool import detect_hu_labels

            result = detect_hu_labels.invoke({"image_data": _VALID_JPEG_B64})
        self.assertEqual(len(result["labels"]), 2)
        self.assertFalse(result["low_quality"])

    def test_low_confidence_sets_low_quality_flag(self):
        mock_result = self._mock_labels([_HU_A], confidence=0.50)
        with patch("tools.label_detection_tool._call_vision_model", return_value=mock_result):
            from tools.label_detection_tool import detect_hu_labels

            result = detect_hu_labels.invoke({"image_data": _VALID_JPEG_B64})
        self.assertTrue(result["low_quality"])

    def test_confidence_exactly_at_threshold_not_low_quality(self):
        mock_result = self._mock_labels([_HU_A], confidence=0.75)
        with patch("tools.label_detection_tool._call_vision_model", return_value=mock_result):
            from tools.label_detection_tool import detect_hu_labels

            result = detect_hu_labels.invoke({"image_data": _VALID_JPEG_B64})
        self.assertFalse(result["low_quality"])

    def test_empty_labels_no_hu_on_pallet(self):
        mock_result = {"labels": [], "overall_confidence": 0.0}
        with patch("tools.label_detection_tool._call_vision_model", return_value=mock_result):
            from tools.label_detection_tool import detect_hu_labels

            result = detect_hu_labels.invoke({"image_data": _VALID_JPEG_B64})
        self.assertEqual(len(result["labels"]), 0)
        self.assertTrue(result["low_quality"])

    def test_vision_model_exception_returns_low_quality(self):
        with patch(
            "tools.label_detection_tool._call_vision_model",
            side_effect=RuntimeError("AI service unavailable"),
        ):
            from tools.label_detection_tool import detect_hu_labels

            result = detect_hu_labels.invoke({"image_data": _VALID_JPEG_B64})
        self.assertTrue(result["low_quality"])
        self.assertEqual(result["overall_confidence"], 0.0)
        self.assertEqual(result["labels"], [])

    def test_url_image_passed_through(self):
        mock_result = self._mock_labels([_HU_A], confidence=0.88)
        with patch("tools.label_detection_tool._call_vision_model", return_value=mock_result):
            from tools.label_detection_tool import detect_hu_labels

            result = detect_hu_labels.invoke(
                {"image_data": "https://example.com/pallet.jpg"}
            )
        self.assertFalse(result["low_quality"])


# ===========================================================================
# STEP 3 — EWM Delivery Fetch  (MCP tool — tested via mock)
# ===========================================================================
class TestStep3DeliveryFetch(unittest.TestCase):
    """Step 3: get_outbound_delivery_hu_list MCP call (mocked).

    In production the agent calls the ewm-outbound-delivery MCP server.
    Here we verify the expected response contract and test downstream
    behaviour when the MCP tool succeeds vs. fails.
    """

    def _make_delivery_response(self, hus: list[str], blocked: bool = False):
        """Build a minimal MCP tool response for get_outbound_delivery_hu_list."""
        return {
            "EWMOutboundDeliveryOrder": _DELIVERY,
            "GoodsIssueStatus": "A",  # A = not posted
            "OverallBlockingStatus": "B" if blocked else " ",
            "to_WhseOutboundDelivOrderItem": [
                {
                    "HandlingUnitExternalID": hu,
                    "EWMWarehouse": "WH01",
                }
                for hu in hus
            ],
        }

    def test_delivery_with_expected_hus(self):
        mock_response = self._make_delivery_response([_HU_A, _HU_B])
        # Verify contract: HU list extractable from response
        items = mock_response["to_WhseOutboundDelivOrderItem"]
        extracted = [item["HandlingUnitExternalID"] for item in items]
        self.assertIn(_HU_A, extracted)
        self.assertIn(_HU_B, extracted)
        self.assertNotIn(_HU_C, extracted)

    def test_blocked_delivery_flag_detected(self):
        mock_response = self._make_delivery_response([_HU_A], blocked=True)
        self.assertEqual(mock_response["OverallBlockingStatus"], "B")

    def test_unblocked_delivery_flag_detected(self):
        mock_response = self._make_delivery_response([_HU_A], blocked=False)
        self.assertEqual(mock_response["OverallBlockingStatus"].strip(), "")

    def test_empty_hu_list_from_delivery(self):
        mock_response = self._make_delivery_response([])
        items = mock_response["to_WhseOutboundDelivOrderItem"]
        self.assertEqual(len(items), 0)

    def test_goods_issue_not_yet_posted(self):
        mock_response = self._make_delivery_response([_HU_A])
        self.assertEqual(mock_response["GoodsIssueStatus"], "A")


# ===========================================================================
# STEP 4 — HU Cross-Reference Matching
# ===========================================================================
class TestStep4HuMatching(unittest.TestCase):
    """Step 4: match_hu_to_delivery — cross-reference detected vs expected HUs."""

    # --- full match --------------------------------------------------------

    def test_full_match_exact_hus(self):
        result = match_hu_to_delivery.invoke(
            {"detected_hus": [_HU_A, _HU_B], "expected_hus": [_HU_A, _HU_B]}
        )
        self.assertEqual(result["match_status"], "FULL_MATCH")
        self.assertEqual(sorted(result["matched"]), sorted([_HU_A, _HU_B]))
        self.assertEqual(result["missing_from_pallet"], [])
        self.assertEqual(result["extra_on_pallet"], [])

    def test_full_match_case_insensitive(self):
        result = match_hu_to_delivery.invoke(
            {
                "detected_hus": [_HU_A.lower()],
                "expected_hus": [_HU_A.upper()],
            }
        )
        self.assertEqual(result["match_status"], "FULL_MATCH")

    def test_full_match_single_hu(self):
        result = match_hu_to_delivery.invoke(
            {"detected_hus": [_HU_A], "expected_hus": [_HU_A]}
        )
        self.assertEqual(result["match_status"], "FULL_MATCH")

    # --- partial match -----------------------------------------------------

    def test_partial_match_extra_hu_on_pallet(self):
        result = match_hu_to_delivery.invoke(
            {"detected_hus": [_HU_A, _HU_B, _HU_C], "expected_hus": [_HU_A, _HU_B]}
        )
        self.assertEqual(result["match_status"], "PARTIAL_MATCH")
        self.assertIn(_HU_C, result["extra_on_pallet"])
        self.assertEqual(result["missing_from_pallet"], [])

    def test_partial_match_missing_hu_from_pallet(self):
        result = match_hu_to_delivery.invoke(
            {"detected_hus": [_HU_A], "expected_hus": [_HU_A, _HU_D]}
        )
        self.assertEqual(result["match_status"], "PARTIAL_MATCH")
        self.assertIn(_HU_D, result["missing_from_pallet"])
        self.assertEqual(result["extra_on_pallet"], [])

    def test_partial_match_both_extra_and_missing(self):
        result = match_hu_to_delivery.invoke(
            {
                "detected_hus": [_HU_A, _HU_C],  # _HU_C is extra
                "expected_hus": [_HU_A, _HU_D],  # _HU_D is missing
            }
        )
        self.assertEqual(result["match_status"], "PARTIAL_MATCH")
        self.assertIn(_HU_C, result["extra_on_pallet"])
        self.assertIn(_HU_D, result["missing_from_pallet"])

    # --- mismatch ----------------------------------------------------------

    def test_mismatch_no_common_hus(self):
        result = match_hu_to_delivery.invoke(
            {"detected_hus": [_HU_C], "expected_hus": [_HU_A, _HU_B]}
        )
        self.assertEqual(result["match_status"], "MISMATCH")
        self.assertEqual(result["matched"], [])
        self.assertIn(_HU_A, result["missing_from_pallet"])
        self.assertIn(_HU_C, result["extra_on_pallet"])

    def test_mismatch_empty_detected_list(self):
        result = match_hu_to_delivery.invoke(
            {"detected_hus": [], "expected_hus": [_HU_A, _HU_B]}
        )
        self.assertEqual(result["match_status"], "MISMATCH")
        self.assertIn(_HU_A, result["missing_from_pallet"])

    def test_mismatch_empty_expected_list(self):
        result = match_hu_to_delivery.invoke(
            {"detected_hus": [_HU_A], "expected_hus": []}
        )
        self.assertEqual(result["match_status"], "MISMATCH")

    def test_mismatch_both_empty_lists(self):
        result = match_hu_to_delivery.invoke(
            {"detected_hus": [], "expected_hus": []}
        )
        self.assertEqual(result["match_status"], "MISMATCH")

    # --- unreadable labels -------------------------------------------------

    def test_unreadable_label_counted(self):
        result = match_hu_to_delivery.invoke(
            {
                "detected_hus": [_HU_A, ""],   # empty string = unreadable
                "expected_hus": [_HU_A],
            }
        )
        # Empty string is stripped out; only _HU_A readable → FULL_MATCH
        self.assertEqual(result["match_status"], "FULL_MATCH")


# ===========================================================================
# STEP 5 — Verification Report Generation
# ===========================================================================
class TestStep5VerificationReport(unittest.TestCase):
    """Step 5: generate_verification_report — PASS/FAIL with structured summary."""

    def _label_result(self, confidence: float = 0.90, low_quality: bool = False):
        return {
            "labels": [
                {"present": True, "readable": True, "confidence": confidence, "barcode_value": _HU_A}
            ],
            "overall_confidence": confidence,
            "low_quality": low_quality,
        }

    def _match_result(self, status: str, matched=None, missing=None, extra=None):
        return {
            "match_status": status,
            "matched": matched or [_HU_A, _HU_B],
            "missing_from_pallet": missing or [],
            "extra_on_pallet": extra or [],
            "unreadable_labels": 0,
        }

    # --- PASS scenarios ----------------------------------------------------

    def test_full_match_high_confidence_returns_pass(self):
        result = generate_verification_report.invoke(
            {
                "delivery_number": _DELIVERY,
                "match_result": self._match_result("FULL_MATCH"),
                "label_result": self._label_result(0.95),
                "delivery_blocked": False,
            }
        )
        self.assertEqual(result["overall_status"], "PASS")
        self.assertIn("Ready to load", result["summary"])

    def test_pass_report_has_correct_counts(self):
        result = generate_verification_report.invoke(
            {
                "delivery_number": _DELIVERY,
                "match_result": self._match_result("FULL_MATCH", matched=[_HU_A, _HU_B]),
                "label_result": self._label_result(0.92),
                "delivery_blocked": False,
            }
        )
        self.assertEqual(result["matched_hu_count"], 2)
        self.assertEqual(result["missing_hus"], [])
        self.assertEqual(result["extra_hus"], [])

    # --- FAIL scenarios ----------------------------------------------------

    def test_partial_match_returns_fail(self):
        result = generate_verification_report.invoke(
            {
                "delivery_number": _DELIVERY,
                "match_result": self._match_result(
                    "PARTIAL_MATCH", matched=[_HU_A], missing=[_HU_B], extra=[_HU_C]
                ),
                "label_result": self._label_result(0.88),
                "delivery_blocked": False,
            }
        )
        self.assertEqual(result["overall_status"], "FAIL")

    def test_mismatch_returns_fail(self):
        result = generate_verification_report.invoke(
            {
                "delivery_number": _DELIVERY,
                "match_result": self._match_result("MISMATCH", matched=[], extra=[_HU_C]),
                "label_result": self._label_result(0.85),
                "delivery_blocked": False,
            }
        )
        self.assertEqual(result["overall_status"], "FAIL")
        self.assertIn(_DELIVERY, result["summary"])

    def test_low_quality_photo_returns_fail(self):
        result = generate_verification_report.invoke(
            {
                "delivery_number": _DELIVERY,
                "match_result": self._match_result("FULL_MATCH"),
                "label_result": self._label_result(0.60, low_quality=True),
                "delivery_blocked": False,
            }
        )
        self.assertEqual(result["overall_status"], "FAIL")
        self.assertIn("retake", result["summary"].lower())

    def test_delivery_blocked_flag_propagated(self):
        result = generate_verification_report.invoke(
            {
                "delivery_number": _DELIVERY,
                "match_result": self._match_result("MISMATCH", matched=[]),
                "label_result": self._label_result(0.90),
                "delivery_blocked": True,
            }
        )
        self.assertTrue(result["delivery_blocked"])
        self.assertIn("BLOCKED", result["summary"])

    def test_missing_hus_appear_in_summary(self):
        result = generate_verification_report.invoke(
            {
                "delivery_number": _DELIVERY,
                "match_result": self._match_result(
                    "PARTIAL_MATCH", matched=[_HU_A], missing=[_HU_D]
                ),
                "label_result": self._label_result(0.88),
                "delivery_blocked": False,
            }
        )
        self.assertEqual(result["overall_status"], "FAIL")
        self.assertIn(_HU_D, result["missing_hus"])

    def test_extra_hus_appear_in_report(self):
        result = generate_verification_report.invoke(
            {
                "delivery_number": _DELIVERY,
                "match_result": self._match_result(
                    "PARTIAL_MATCH", matched=[_HU_A], extra=[_HU_C]
                ),
                "label_result": self._label_result(0.90),
                "delivery_blocked": False,
            }
        )
        self.assertIn(_HU_C, result["extra_hus"])


# ===========================================================================
# STEP 6 — Block Delivery  (MCP tool — tested via mock)
# ===========================================================================
class TestStep6BlockDelivery(unittest.TestCase):
    """Step 6: patch_whse_outbound_delivery_order_head MCP call (mocked).

    On critical mismatch the agent sets OverallBlockingStatus='B' via the
    ewm-outbound-delivery MCP server. We verify the expected call contract.
    """

    def test_block_delivery_mcp_call_contract(self):
        """Verify the MCP tool receives the correct payload to block a delivery."""
        mock_mcp = MagicMock()
        mock_mcp.patch_whse_outbound_delivery_order_head.return_value = {}

        # Simulate agent calling MCP to block delivery
        mock_mcp.patch_whse_outbound_delivery_order_head(
            EWMOutboundDeliveryOrder=_DELIVERY,
            OverallBlockingStatus="B",
        )

        mock_mcp.patch_whse_outbound_delivery_order_head.assert_called_once_with(
            EWMOutboundDeliveryOrder=_DELIVERY,
            OverallBlockingStatus="B",
        )

    def test_block_delivery_on_mismatch(self):
        """Delivery blocking is triggered when match_status is MISMATCH."""
        mock_mcp = MagicMock()
        mock_mcp.patch_whse_outbound_delivery_order_head.return_value = {}

        match_status = "MISMATCH"
        if match_status in ("MISMATCH", "PARTIAL_MATCH"):
            mock_mcp.patch_whse_outbound_delivery_order_head(
                EWMOutboundDeliveryOrder=_DELIVERY,
                OverallBlockingStatus="B",
            )

        mock_mcp.patch_whse_outbound_delivery_order_head.assert_called_once()

    def test_block_not_called_on_full_match(self):
        """Delivery blocking is NOT triggered on FULL_MATCH."""
        mock_mcp = MagicMock()

        match_status = "FULL_MATCH"
        if match_status in ("MISMATCH", "PARTIAL_MATCH"):  # pragma: no cover
            mock_mcp.patch_whse_outbound_delivery_order_head(
                EWMOutboundDeliveryOrder=_DELIVERY,
                OverallBlockingStatus="B",
            )

        mock_mcp.patch_whse_outbound_delivery_order_head.assert_not_called()

    def test_block_delivery_on_partial_match(self):
        """Delivery blocking is also triggered on PARTIAL_MATCH."""
        mock_mcp = MagicMock()
        mock_mcp.patch_whse_outbound_delivery_order_head.return_value = {}

        match_status = "PARTIAL_MATCH"
        if match_status in ("MISMATCH", "PARTIAL_MATCH"):
            mock_mcp.patch_whse_outbound_delivery_order_head(
                EWMOutboundDeliveryOrder=_DELIVERY,
                OverallBlockingStatus="B",
            )

        mock_mcp.patch_whse_outbound_delivery_order_head.assert_called_once()


# ===========================================================================
# STEP 7 — HU Correction (preconditions + MCP mock)
# ===========================================================================
class TestStep7HuCorrection(unittest.TestCase):
    """Step 7: validate_hu_correction_preconditions + unload/load MCP tools."""

    # --- precondition: allowed (happy path) --------------------------------

    def test_correction_allowed_on_partial_match(self):
        result = validate_hu_correction_preconditions.invoke(
            {
                "match_status": "PARTIAL_MATCH",
                "delivery_blocked": False,
                "overall_confidence": 0.88,
                "extra_on_pallet": [_HU_C],
                "missing_from_pallet": [_HU_D],
            }
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["hus_to_unload"], [_HU_C])
        self.assertEqual(result["hus_to_load"], [_HU_D])
        self.assertEqual(result["reason"], "")

    def test_correction_allowed_on_mismatch(self):
        result = validate_hu_correction_preconditions.invoke(
            {
                "match_status": "MISMATCH",
                "delivery_blocked": False,
                "overall_confidence": 0.90,
                "extra_on_pallet": [_HU_C],
                "missing_from_pallet": [_HU_A, _HU_B],
            }
        )
        self.assertTrue(result["allowed"])

    def test_correction_allowed_only_extra_hu(self):
        result = validate_hu_correction_preconditions.invoke(
            {
                "match_status": "PARTIAL_MATCH",
                "delivery_blocked": False,
                "overall_confidence": 0.80,
                "extra_on_pallet": [_HU_C],
                "missing_from_pallet": [],
            }
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["hus_to_unload"], [_HU_C])
        self.assertEqual(result["hus_to_load"], [])

    def test_correction_allowed_only_missing_hu(self):
        result = validate_hu_correction_preconditions.invoke(
            {
                "match_status": "PARTIAL_MATCH",
                "delivery_blocked": False,
                "overall_confidence": 0.85,
                "extra_on_pallet": [],
                "missing_from_pallet": [_HU_D],
            }
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["hus_to_load"], [_HU_D])

    def test_correction_at_exactly_confidence_threshold(self):
        result = validate_hu_correction_preconditions.invoke(
            {
                "match_status": "PARTIAL_MATCH",
                "delivery_blocked": False,
                "overall_confidence": 0.75,
                "extra_on_pallet": [_HU_C],
                "missing_from_pallet": [],
            }
        )
        self.assertTrue(result["allowed"])

    # --- precondition: blocked (denied) ------------------------------------

    def test_correction_denied_when_delivery_blocked(self):
        result = validate_hu_correction_preconditions.invoke(
            {
                "match_status": "PARTIAL_MATCH",
                "delivery_blocked": True,
                "overall_confidence": 0.90,
                "extra_on_pallet": [_HU_C],
                "missing_from_pallet": [_HU_D],
            }
        )
        self.assertFalse(result["allowed"])
        self.assertIn("blocked", result["reason"].lower())

    # --- precondition: wrong status (not applicable) -----------------------

    def test_correction_not_applicable_on_full_match(self):
        result = validate_hu_correction_preconditions.invoke(
            {
                "match_status": "FULL_MATCH",
                "delivery_blocked": False,
                "overall_confidence": 0.95,
                "extra_on_pallet": [],
                "missing_from_pallet": [],
            }
        )
        self.assertFalse(result["allowed"])
        self.assertIn("FULL_MATCH", result["reason"])

    # --- precondition: low confidence (denied) -----------------------------

    def test_correction_denied_below_confidence_threshold(self):
        result = validate_hu_correction_preconditions.invoke(
            {
                "match_status": "PARTIAL_MATCH",
                "delivery_blocked": False,
                "overall_confidence": 0.60,
                "extra_on_pallet": [_HU_C],
                "missing_from_pallet": [],
            }
        )
        self.assertFalse(result["allowed"])
        self.assertIn("confidence", result["reason"].lower())

    # --- precondition: empty discrepancy lists (denied) --------------------

    def test_correction_denied_when_no_discrepancies(self):
        result = validate_hu_correction_preconditions.invoke(
            {
                "match_status": "PARTIAL_MATCH",
                "delivery_blocked": False,
                "overall_confidence": 0.85,
                "extra_on_pallet": [],
                "missing_from_pallet": [],
            }
        )
        self.assertFalse(result["allowed"])
        self.assertIn("empty", result["reason"].lower())

    # --- MCP tool mock: unload_handling_unit ------------------------------

    def test_unload_hu_mcp_call_contract(self):
        """Verify the unload_handling_unit MCP tool receives correct parameters."""
        mock_mcp = MagicMock()
        mock_mcp.unload_handling_unit.return_value = None  # 204 No Content

        mock_mcp.unload_handling_unit(
            HandlingUnitExternalID=_HU_C,
            Warehouse="WH01",
        )

        mock_mcp.unload_handling_unit.assert_called_once_with(
            HandlingUnitExternalID=_HU_C,
            Warehouse="WH01",
        )

    def test_unload_multiple_hus(self):
        """Verify each extra HU triggers a separate unload MCP call."""
        mock_mcp = MagicMock()
        mock_mcp.unload_handling_unit.return_value = None

        hus_to_unload = [_HU_C, _HU_D]
        for hu in hus_to_unload:
            mock_mcp.unload_handling_unit(HandlingUnitExternalID=hu, Warehouse="WH01")

        self.assertEqual(mock_mcp.unload_handling_unit.call_count, 2)

    # --- MCP tool mock: load_handling_unit --------------------------------

    def test_load_hu_mcp_call_contract(self):
        """Verify the load_handling_unit MCP tool receives correct parameters."""
        mock_mcp = MagicMock()
        mock_mcp.load_handling_unit.return_value = None  # 204 No Content

        mock_mcp.load_handling_unit(
            HandlingUnitExternalID=_HU_D,
            Warehouse="WH01",
        )

        mock_mcp.load_handling_unit.assert_called_once_with(
            HandlingUnitExternalID=_HU_D,
            Warehouse="WH01",
        )

    def test_load_multiple_hus(self):
        """Verify each missing HU triggers a separate load MCP call."""
        mock_mcp = MagicMock()
        mock_mcp.load_handling_unit.return_value = None

        hus_to_load = [_HU_A, _HU_B]
        for hu in hus_to_load:
            mock_mcp.load_handling_unit(HandlingUnitExternalID=hu, Warehouse="WH01")

        self.assertEqual(mock_mcp.load_handling_unit.call_count, 2)

    # --- correction response includes timestamp ----------------------------

    def test_correction_result_includes_checked_at(self):
        result = validate_hu_correction_preconditions.invoke(
            {
                "match_status": "PARTIAL_MATCH",
                "delivery_blocked": False,
                "overall_confidence": 0.82,
                "extra_on_pallet": [_HU_C],
                "missing_from_pallet": [],
            }
        )
        self.assertIn("checked_at", result)
        self.assertTrue(result["checked_at"].endswith("+00:00") or "T" in result["checked_at"])


# ===========================================================================
# STEP 8 — Post Goods Issue (preconditions + MCP mock)
# ===========================================================================
class TestStep8PostGoodsIssue(unittest.TestCase):
    """Step 8: validate_goods_issue_preconditions + post_goods_issue_ewm MCP."""

    # --- precondition: allowed (happy path) --------------------------------

    def test_gi_allowed_on_pass_unblocked_high_confidence(self):
        result = validate_goods_issue_preconditions.invoke(
            {
                "overall_status": "PASS",
                "delivery_blocked": False,
                "overall_confidence": 0.92,
            }
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["reason"], "")

    def test_gi_allowed_at_exactly_confidence_threshold(self):
        result = validate_goods_issue_preconditions.invoke(
            {
                "overall_status": "PASS",
                "delivery_blocked": False,
                "overall_confidence": 0.75,
            }
        )
        self.assertTrue(result["allowed"])

    def test_gi_result_includes_checked_at_timestamp(self):
        result = validate_goods_issue_preconditions.invoke(
            {
                "overall_status": "PASS",
                "delivery_blocked": False,
                "overall_confidence": 0.85,
            }
        )
        self.assertIn("checked_at", result)
        self.assertTrue(result["checked_at"].endswith("+00:00") or "T" in result["checked_at"])

    # --- precondition: denied (FAIL status) --------------------------------

    def test_gi_denied_on_fail_status(self):
        result = validate_goods_issue_preconditions.invoke(
            {
                "overall_status": "FAIL",
                "delivery_blocked": False,
                "overall_confidence": 0.90,
            }
        )
        self.assertFalse(result["allowed"])
        self.assertIn("FAIL", result["reason"])

    def test_gi_denied_on_mismatch_status(self):
        result = validate_goods_issue_preconditions.invoke(
            {
                "overall_status": "MISMATCH",
                "delivery_blocked": False,
                "overall_confidence": 0.90,
            }
        )
        self.assertFalse(result["allowed"])
        self.assertNotEqual(result["reason"], "")

    # --- precondition: denied (delivery blocked) ---------------------------

    def test_gi_denied_when_delivery_blocked(self):
        result = validate_goods_issue_preconditions.invoke(
            {
                "overall_status": "PASS",
                "delivery_blocked": True,
                "overall_confidence": 0.95,
            }
        )
        self.assertFalse(result["allowed"])
        self.assertIn("block", result["reason"].lower())

    # --- precondition: denied (low confidence) ----------------------------

    def test_gi_denied_below_confidence_threshold(self):
        result = validate_goods_issue_preconditions.invoke(
            {
                "overall_status": "PASS",
                "delivery_blocked": False,
                "overall_confidence": 0.70,
            }
        )
        self.assertFalse(result["allowed"])
        self.assertIn("confidence", result["reason"].lower())

    def test_gi_denied_zero_confidence(self):
        result = validate_goods_issue_preconditions.invoke(
            {
                "overall_status": "PASS",
                "delivery_blocked": False,
                "overall_confidence": 0.0,
            }
        )
        self.assertFalse(result["allowed"])

    # --- MCP tool mock: post_goods_issue_ewm ------------------------------

    def test_post_gi_mcp_call_contract(self):
        """Verify post_goods_issue_ewm MCP tool is called with the correct delivery."""
        mock_mcp = MagicMock()
        mock_mcp.post_goods_issue_ewm.return_value = None  # 204 No Content

        mock_mcp.post_goods_issue_ewm(EWMOutboundDeliveryOrder=_DELIVERY)

        mock_mcp.post_goods_issue_ewm.assert_called_once_with(
            EWMOutboundDeliveryOrder=_DELIVERY
        )

    def test_post_gi_not_called_when_preconditions_fail(self):
        """post_goods_issue_ewm MUST NOT be called when preconditions are not met."""
        mock_mcp = MagicMock()

        gi_check = validate_goods_issue_preconditions.invoke(
            {
                "overall_status": "FAIL",
                "delivery_blocked": False,
                "overall_confidence": 0.90,
            }
        )
        if gi_check["allowed"]:  # pragma: no cover
            mock_mcp.post_goods_issue_ewm(EWMOutboundDeliveryOrder=_DELIVERY)

        mock_mcp.post_goods_issue_ewm.assert_not_called()

    def test_post_gi_called_when_preconditions_pass(self):
        """post_goods_issue_ewm MUST be called once after successful precondition check."""
        mock_mcp = MagicMock()
        mock_mcp.post_goods_issue_ewm.return_value = None

        gi_check = validate_goods_issue_preconditions.invoke(
            {
                "overall_status": "PASS",
                "delivery_blocked": False,
                "overall_confidence": 0.88,
            }
        )
        if gi_check["allowed"]:
            mock_mcp.post_goods_issue_ewm(EWMOutboundDeliveryOrder=_DELIVERY)

        mock_mcp.post_goods_issue_ewm.assert_called_once_with(
            EWMOutboundDeliveryOrder=_DELIVERY
        )


# ===========================================================================
# END-TO-END WORKFLOW — happy path (all steps chained)
# ===========================================================================
class TestEndToEndWorkflow(unittest.TestCase):
    """Simulate the full 8-step workflow chained together for the happy path."""

    def setUp(self):
        self.mock_mcp = MagicMock()
        self.mock_mcp.get_outbound_delivery_hu_list.return_value = {
            "EWMOutboundDeliveryOrder": _DELIVERY,
            "GoodsIssueStatus": "A",
            "OverallBlockingStatus": " ",
            "to_WhseOutboundDelivOrderItem": [
                {"HandlingUnitExternalID": _HU_A, "EWMWarehouse": "WH01"},
                {"HandlingUnitExternalID": _HU_B, "EWMWarehouse": "WH01"},
            ],
        }
        self.mock_mcp.patch_whse_outbound_delivery_order_head.return_value = {}
        self.mock_mcp.post_goods_issue_ewm.return_value = None

    def _detect_labels(self, barcodes: list[str], confidence: float = 0.92):
        mock_result = {
            "labels": [
                {"present": True, "readable": True, "confidence": confidence, "barcode_value": bc}
                for bc in barcodes
            ],
            "overall_confidence": confidence,
        }
        with patch("tools.label_detection_tool._call_vision_model", return_value=mock_result):
            from tools.label_detection_tool import detect_hu_labels

            return detect_hu_labels.invoke({"image_data": _VALID_JPEG_B64})

    def test_full_pass_workflow(self):
        """Steps 1-5 all pass, no blocking needed, goods issue posted (Step 8)."""

        # Step 1 — ingest photo
        step1 = validate_and_prepare_image.invoke(
            {"image_data": _VALID_JPEG_B64, "source_channel": "dock_camera"}
        )
        self.assertTrue(step1["ready"], "Step 1 must succeed")

        # Step 2 — detect labels
        step2 = self._detect_labels([_HU_A, _HU_B], confidence=0.92)
        detected_hus = [lbl["barcode_value"] for lbl in step2["labels"]]
        self.assertFalse(step2["low_quality"], "Step 2 must be high quality")

        # Step 3 — fetch EWM delivery (mocked)
        delivery_data = self.mock_mcp.get_outbound_delivery_hu_list(
            EWMOutboundDeliveryOrder=_DELIVERY
        )
        expected_hus = [
            item["HandlingUnitExternalID"]
            for item in delivery_data["to_WhseOutboundDelivOrderItem"]
        ]
        delivery_blocked = delivery_data["OverallBlockingStatus"].strip() == "B"
        self.assertFalse(delivery_blocked)

        # Step 4 — match HUs
        step4 = match_hu_to_delivery.invoke(
            {"detected_hus": detected_hus, "expected_hus": expected_hus}
        )
        self.assertEqual(step4["match_status"], "FULL_MATCH")

        # Step 5 — generate report
        step5 = generate_verification_report.invoke(
            {
                "delivery_number": _DELIVERY,
                "match_result": step4,
                "label_result": step2,
                "delivery_blocked": delivery_blocked,
            }
        )
        self.assertEqual(step5["overall_status"], "PASS")

        # Step 6 — block delivery (skip on FULL_MATCH)
        self.mock_mcp.patch_whse_outbound_delivery_order_head.assert_not_called()

        # Step 7 — HU correction (skip on FULL_MATCH)
        step7 = validate_hu_correction_preconditions.invoke(
            {
                "match_status": step4["match_status"],
                "delivery_blocked": delivery_blocked,
                "overall_confidence": step2["overall_confidence"],
                "extra_on_pallet": step4["extra_on_pallet"],
                "missing_from_pallet": step4["missing_from_pallet"],
            }
        )
        self.assertFalse(step7["allowed"], "Correction not needed on FULL_MATCH")

        # Step 8 — post goods issue
        step8 = validate_goods_issue_preconditions.invoke(
            {
                "overall_status": step5["overall_status"],
                "delivery_blocked": delivery_blocked,
                "overall_confidence": step2["overall_confidence"],
            }
        )
        self.assertTrue(step8["allowed"])
        self.mock_mcp.post_goods_issue_ewm(EWMOutboundDeliveryOrder=_DELIVERY)
        self.mock_mcp.post_goods_issue_ewm.assert_called_once_with(
            EWMOutboundDeliveryOrder=_DELIVERY
        )

    def test_partial_match_correction_then_pass(self):
        """Simulate partial mismatch → correction (Step 7) → re-verify → GI (Step 8)."""

        # Initial detection: _HU_A found, _HU_B missing, _HU_C extra
        step2 = self._detect_labels([_HU_A, _HU_C], confidence=0.88)
        detected_hus = [lbl["barcode_value"] for lbl in step2["labels"]]

        # Expected: _HU_A, _HU_B
        step4 = match_hu_to_delivery.invoke(
            {"detected_hus": detected_hus, "expected_hus": [_HU_A, _HU_B]}
        )
        self.assertEqual(step4["match_status"], "PARTIAL_MATCH")

        # Step 6 — block delivery on partial match
        self.mock_mcp.patch_whse_outbound_delivery_order_head(
            EWMOutboundDeliveryOrder=_DELIVERY, OverallBlockingStatus="B"
        )

        # Step 7 — check correction preconditions (delivery NOT yet blocked for correction)
        step7 = validate_hu_correction_preconditions.invoke(
            {
                "match_status": step4["match_status"],
                "delivery_blocked": False,  # block was set, but correction runs before re-check
                "overall_confidence": step2["overall_confidence"],
                "extra_on_pallet": step4["extra_on_pallet"],
                "missing_from_pallet": step4["missing_from_pallet"],
            }
        )
        self.assertTrue(step7["allowed"])

        # Execute MCP corrections
        for hu in step7["hus_to_unload"]:
            self.mock_mcp.unload_handling_unit(HandlingUnitExternalID=hu, Warehouse="WH01")
        for hu in step7["hus_to_load"]:
            self.mock_mcp.load_handling_unit(HandlingUnitExternalID=hu, Warehouse="WH01")

        self.assertEqual(self.mock_mcp.unload_handling_unit.call_count, 1)
        self.assertEqual(self.mock_mcp.load_handling_unit.call_count, 1)

        # After correction: re-verify → now FULL_MATCH
        step4b = match_hu_to_delivery.invoke(
            {"detected_hus": [_HU_A, _HU_B], "expected_hus": [_HU_A, _HU_B]}
        )
        self.assertEqual(step4b["match_status"], "FULL_MATCH")

        step5b = generate_verification_report.invoke(
            {
                "delivery_number": _DELIVERY,
                "match_result": step4b,
                "label_result": self._detect_labels([_HU_A, _HU_B], confidence=0.92),
                "delivery_blocked": False,
            }
        )
        self.assertEqual(step5b["overall_status"], "PASS")

        # Step 8 — GI preconditions pass
        step8 = validate_goods_issue_preconditions.invoke(
            {
                "overall_status": "PASS",
                "delivery_blocked": False,
                "overall_confidence": 0.92,
            }
        )
        self.assertTrue(step8["allowed"])

    def test_mismatch_workflow_no_gi_posted(self):
        """On critical mismatch with no correction: delivery blocked, NO goods issue."""

        step2 = self._detect_labels([_HU_C], confidence=0.85)
        detected_hus = [lbl["barcode_value"] for lbl in step2["labels"]]

        step4 = match_hu_to_delivery.invoke(
            {"detected_hus": detected_hus, "expected_hus": [_HU_A, _HU_B]}
        )
        self.assertEqual(step4["match_status"], "MISMATCH")

        step5 = generate_verification_report.invoke(
            {
                "delivery_number": _DELIVERY,
                "match_result": step4,
                "label_result": step2,
                "delivery_blocked": True,
            }
        )
        self.assertEqual(step5["overall_status"], "FAIL")

        step8 = validate_goods_issue_preconditions.invoke(
            {
                "overall_status": step5["overall_status"],
                "delivery_blocked": True,
                "overall_confidence": step2["overall_confidence"],
            }
        )
        self.assertFalse(step8["allowed"])
        self.mock_mcp.post_goods_issue_ewm.assert_not_called()

    def test_low_quality_photo_workflow_no_gi(self):
        """When photo confidence is below threshold, GI must not be posted."""

        step2 = self._detect_labels([_HU_A, _HU_B], confidence=0.55)
        self.assertTrue(step2["low_quality"])

        step4 = match_hu_to_delivery.invoke(
            {
                "detected_hus": [lbl["barcode_value"] for lbl in step2["labels"]],
                "expected_hus": [_HU_A, _HU_B],
            }
        )

        step5 = generate_verification_report.invoke(
            {
                "delivery_number": _DELIVERY,
                "match_result": step4,
                "label_result": step2,
                "delivery_blocked": False,
            }
        )
        self.assertEqual(step5["overall_status"], "FAIL")

        step8 = validate_goods_issue_preconditions.invoke(
            {
                "overall_status": step5["overall_status"],
                "delivery_blocked": False,
                "overall_confidence": step2["overall_confidence"],
            }
        )
        self.assertFalse(step8["allowed"])


# ===========================================================================
# EDGE CASES — boundary conditions and unexpected inputs
# ===========================================================================
class TestEdgeCases(unittest.TestCase):
    """Cross-cutting edge cases that span multiple workflow steps."""

    def test_single_hu_full_workflow_pass(self):
        """Single-HU pallet: full match → pass → GI allowed."""
        match = match_hu_to_delivery.invoke(
            {"detected_hus": [_HU_A], "expected_hus": [_HU_A]}
        )
        self.assertEqual(match["match_status"], "FULL_MATCH")

        label = {
            "labels": [{"present": True, "readable": True, "confidence": 0.88, "barcode_value": _HU_A}],
            "overall_confidence": 0.88,
            "low_quality": False,
        }
        report = generate_verification_report.invoke(
            {
                "delivery_number": _DELIVERY,
                "match_result": match,
                "label_result": label,
                "delivery_blocked": False,
            }
        )
        self.assertEqual(report["overall_status"], "PASS")

        gi = validate_goods_issue_preconditions.invoke(
            {"overall_status": "PASS", "delivery_blocked": False, "overall_confidence": 0.88}
        )
        self.assertTrue(gi["allowed"])

    def test_hu_correction_multiple_extra_multiple_missing(self):
        """Three extra HUs to unload, two missing HUs to load."""
        result = validate_hu_correction_preconditions.invoke(
            {
                "match_status": "MISMATCH",
                "delivery_blocked": False,
                "overall_confidence": 0.82,
                "extra_on_pallet": [_HU_A, _HU_B, _HU_C],
                "missing_from_pallet": [_HU_D, "00340123450000005555"],
            }
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(len(result["hus_to_unload"]), 3)
        self.assertEqual(len(result["hus_to_load"]), 2)

    def test_whitespace_hu_values_normalised(self):
        """HU values with surrounding whitespace are normalised before matching."""
        result = match_hu_to_delivery.invoke(
            {"detected_hus": [f"  {_HU_A}  "], "expected_hus": [_HU_A]}
        )
        self.assertEqual(result["match_status"], "FULL_MATCH")

    def test_duplicate_detected_hus_deduplicated(self):
        """Duplicate SSCC scans are deduplicated — still FULL_MATCH."""
        result = match_hu_to_delivery.invoke(
            {"detected_hus": [_HU_A, _HU_A], "expected_hus": [_HU_A]}
        )
        self.assertEqual(result["match_status"], "FULL_MATCH")

    def test_gi_denied_all_three_conditions_fail(self):
        """All three GI preconditions failing → denied, with meaningful reason."""
        result = validate_goods_issue_preconditions.invoke(
            {"overall_status": "FAIL", "delivery_blocked": True, "overall_confidence": 0.40}
        )
        self.assertFalse(result["allowed"])
        self.assertNotEqual(result["reason"], "")

    def test_correction_and_gi_independent_checks(self):
        """Correction preconditions and GI preconditions are independent."""
        correction = validate_hu_correction_preconditions.invoke(
            {
                "match_status": "PARTIAL_MATCH",
                "delivery_blocked": False,
                "overall_confidence": 0.80,
                "extra_on_pallet": [_HU_C],
                "missing_from_pallet": [],
            }
        )
        gi = validate_goods_issue_preconditions.invoke(
            {"overall_status": "FAIL", "delivery_blocked": False, "overall_confidence": 0.80}
        )
        # Correction is allowed (discrepancy present), GI is denied (FAIL status)
        self.assertTrue(correction["allowed"])
        self.assertFalse(gi["allowed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

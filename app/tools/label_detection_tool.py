"""REQ-02 & REQ-08: AI Vision-Based HU Label Detection with Confidence Scoring.

Uses the multimodal LLM (vision model) to detect HU labels on pallet photos,
assess their physical presence and readability, and extract barcode/SSCC values.
"""

from __future__ import annotations

import json
import logging
import os

import litellm
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Confidence threshold below which a low-quality flag is raised
CONFIDENCE_THRESHOLD = 0.75

_LABEL_DETECTION_PROMPT = """You are a warehouse pallet verification AI assistant. 
Analyse the provided pallet image and identify ALL visible Handling Unit (HU) labels.

For EACH visible HU label, return a JSON object with:
- "present": true/false — whether the label is physically present and visible
- "readable": true/false — whether the label content is clearly readable
- "confidence": float between 0.0 and 1.0 — your confidence in this detection
- "barcode_value": string — the SSCC/barcode value if readable, empty string if not

Return a JSON object (no markdown, no code blocks) in this exact format:
{
  "labels": [
    {"present": true, "readable": true, "confidence": 0.92, "barcode_value": "00340123450000012345"},
    {"present": true, "readable": false, "confidence": 0.65, "barcode_value": ""}
  ],
  "overall_confidence": 0.88
}

If no labels are detected at all, return:
{"labels": [], "overall_confidence": 0.0}

Be conservative with confidence scores. If lighting is poor, occlusion is present, 
or labels appear damaged, lower the confidence score accordingly.
"""


def _call_vision_model(image_data: str) -> dict:
    """Call the LLM vision model via LiteLLM with the pallet image."""
    model = os.environ.get("AICORE_MODEL_NAME", "gpt-4o")

    # Build image content depending on format (URL vs base64)
    if image_data.startswith("http://") or image_data.startswith("https://"):
        image_content = {
            "type": "image_url",
            "image_url": {"url": image_data},
        }
    else:
        # Ensure proper data URI prefix
        if not image_data.startswith("data:"):
            image_data = f"data:image/jpeg;base64,{image_data}"
        image_content = {
            "type": "image_url",
            "image_url": {"url": image_data},
        }

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": _LABEL_DETECTION_PROMPT},
                image_content,
            ],
        }
    ]

    response = litellm.completion(
        model=model,
        messages=messages,
        temperature=0.0,
        max_tokens=1024,
    )

    raw_text = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    return json.loads(raw_text)


@tool
def detect_hu_labels(image_data: str) -> dict:
    """Detect HU (Handling Unit) labels on a pallet photo using the vision model.

    Calls the multimodal LLM with the pallet image to identify all visible HU labels,
    assess their physical presence and readability, and extract barcode/SSCC values.
    Flags low-quality results when overall confidence is below the threshold.

    Args:
        image_data: Base64-encoded image string (with or without data URI prefix)
                    or a publicly accessible image URL of the pallet.

    Returns:
        dict with keys:
            labels (list[dict]): Each entry has 'present' (bool), 'readable' (bool),
                                 'confidence' (float), 'barcode_value' (str).
            overall_confidence (float): Average confidence score across all detections.
            low_quality (bool): True when overall_confidence < CONFIDENCE_THRESHOLD.
    """
    try:
        result = _call_vision_model(image_data)

        labels = result.get("labels", [])
        overall_confidence = float(result.get("overall_confidence", 0.0))

        # Recompute overall confidence as average of individual scores when not provided
        if labels and overall_confidence == 0.0:
            overall_confidence = sum(float(lbl.get("confidence", 0.0)) for lbl in labels) / len(labels)

        low_quality = overall_confidence < CONFIDENCE_THRESHOLD

        unreadable_count = sum(1 for lbl in labels if not lbl.get("readable", True))

        if not low_quality:
            logger.info(
                "M2.achieved: HU labels detected — count=%d, confidence=%.2f, low_readability_flags=%d",
                len(labels),
                overall_confidence,
                unreadable_count,
            )
        else:
            logger.warning(
                "M2.missed: HU label detection failed or confidence below threshold — retake requested"
            )

        return {
            "labels": labels,
            "overall_confidence": overall_confidence,
            "low_quality": low_quality,
        }

    except Exception as exc:
        logger.error(
            "M2.missed: HU label detection failed or confidence below threshold — retake requested. Error: %s",
            exc,
        )
        return {
            "labels": [],
            "overall_confidence": 0.0,
            "low_quality": True,
        }

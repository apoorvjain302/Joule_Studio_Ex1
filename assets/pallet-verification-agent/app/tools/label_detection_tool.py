"""REQ-02 & REQ-08: AI Vision-Based HU Label Detection with Confidence Scoring."""

from __future__ import annotations

import json
import logging
import os

import litellm
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.75

_LABEL_DETECTION_PROMPT = """You are a warehouse pallet verification AI assistant.
Analyse the provided pallet image and identify ALL visible Handling Unit (HU) labels.

For EACH visible HU label return a JSON entry with:
- "present": true/false
- "readable": true/false
- "confidence": float 0.0-1.0
- "barcode_value": string (SSCC if readable, else empty string)

Return ONLY a JSON object in this exact format (no markdown):
{"labels": [{"present": true, "readable": true, "confidence": 0.92, "barcode_value": "00340123450000012345"}], "overall_confidence": 0.92}

If no labels found: {"labels": [], "overall_confidence": 0.0}
"""


def _call_vision_model(image_data: str) -> dict:
    model = os.environ.get("AICORE_MODEL_NAME", "gpt-4o")
    if image_data.startswith("http://") or image_data.startswith("https://"):
        img_url = image_data
    else:
        if not image_data.startswith("data:"):
            image_data = f"data:image/jpeg;base64,{image_data}"
        img_url = image_data

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": _LABEL_DETECTION_PROMPT},
                {"type": "image_url", "image_url": {"url": img_url}},
            ],
        }
    ]
    response = litellm.completion(model=model, messages=messages, temperature=0.0, max_tokens=1024)
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


@tool
def detect_hu_labels(image_data: str) -> dict:
    """Detect HU labels on a pallet photo using the vision model.

    Calls the multimodal LLM to detect all visible HU labels, assess readability,
    and extract barcode/SSCC values. Sets low_quality=True when confidence is below threshold.

    Args:
        image_data: Base64-encoded image string or publicly accessible image URL.

    Returns:
        dict: labels (list), overall_confidence (float), low_quality (bool).
    """
    try:
        result = _call_vision_model(image_data)
        labels = result.get("labels", [])
        overall_confidence = float(result.get("overall_confidence", 0.0))
        if labels and overall_confidence == 0.0:
            overall_confidence = sum(float(l.get("confidence", 0.0)) for l in labels) / len(labels)
        low_quality = overall_confidence < CONFIDENCE_THRESHOLD
        unreadable = sum(1 for l in labels if not l.get("readable", True))
        if not low_quality:
            logger.info(
                "M2.achieved: HU labels detected — count=%d, confidence=%.2f, low_readability_flags=%d",
                len(labels), overall_confidence, unreadable,
            )
        else:
            logger.warning("M2.missed: HU label detection failed or confidence below threshold — retake requested")
        return {"labels": labels, "overall_confidence": overall_confidence, "low_quality": low_quality}
    except Exception as exc:
        logger.error("M2.missed: HU label detection failed or confidence below threshold — retake requested. Error: %s", exc)
        return {"labels": [], "overall_confidence": 0.0, "low_quality": True}

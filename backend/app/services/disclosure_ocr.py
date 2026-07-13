"""Evidence-preserving OCR quality metrics for official disclosure images."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
from statistics import median
from urllib.parse import urlparse


TRANSACTION_CUES = (
    "amount",
    "asset",
    "date",
    "description",
    "exchange",
    "notification",
    "purchase",
    "sale",
    "transaction",
    "type",
)
FIELD_LABELS = {
    "asset": ("asset", "asset description", "asset name"),
    "owner": ("owner",),
    "transaction_date": ("transaction date", "date of transaction"),
    "notification_date": ("notification date", "date notified"),
    "transaction_type": ("transaction type", "type of transaction"),
    "amount": ("amount", "amount of transaction"),
}


def official_source_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.query or parsed.fragment:
        return False
    if parsed.netloc == "disclosures-clerk.house.gov":
        return parsed.path.startswith("/public_disc/ptr-pdfs/") and parsed.path.endswith(".pdf")
    if parsed.netloc == "efd-media-public.senate.gov":
        return parsed.path.startswith("/media/") and parsed.path.lower().endswith(
            (".gif", ".png", ".jpg", ".jpeg", ".tif", ".tiff")
        )
    return False


def normalize_text(value: str) -> str:
    return " ".join("".join(character if character.isalnum() else " " for character in value.lower()).split())


def field_label_confidence(text: str, *, mean_word_confidence: float) -> dict[str, float]:
    normalized = normalize_text(text)
    tokens = set(normalized.split())
    ocr_factor = max(0.0, min(1.0, mean_word_confidence / 100))
    output = {}
    for field, labels in FIELD_LABELS.items():
        best = 0.0
        for label in labels:
            normalized_label = normalize_text(label)
            label_tokens = normalized_label.split()
            coverage = (
                sum(token in tokens for token in label_tokens) / len(label_tokens)
                if label_tokens
                else 0.0
            )
            if normalized_label in normalized:
                coverage = 1.0
            best = max(best, coverage * ocr_factor)
        output[field] = round(best, 4)
    return output


def enrich_page_quality(*, text: str, quality: dict) -> dict:
    output = dict(quality)
    mean_confidence = float(output.get("mean_word_confidence") or 0.0)
    word_factor = min(1.0, int(output.get("word_count") or 0) / 80)
    line_factor = min(1.0, int(output.get("line_count") or 0) / 18)
    block_factor = min(1.0, int(output.get("layout_block_count") or 0) / 6)
    character_factor = min(1.0, int(output.get("character_count") or 0) / 800)
    layout_confidence = round(
        0.30 * word_factor
        + 0.30 * line_factor
        + 0.20 * block_factor
        + 0.20 * character_factor,
        4,
    )
    fields = field_label_confidence(text, mean_word_confidence=mean_confidence)
    output.update(
        {
            "ocr_confidence": round(max(0.0, min(1.0, mean_confidence / 100)), 4),
            "layout_confidence": layout_confidence,
            "field_label_confidence": fields,
            "transaction_form_candidate": sum(value >= 0.5 for value in fields.values()) >= 3,
            "review_quality_score": round(float(output.get("quality_score") or 0.0) / 100, 4),
        }
    )
    return output


def page_quality(*, text: str, words: list[dict], width: int, height: int) -> dict:
    confidences = [float(word["confidence"]) for word in words if float(word["confidence"]) >= 0]
    normalized = " ".join(text.lower().split())
    cue_hits = sorted(cue for cue in TRANSACTION_CUES if cue in normalized)
    line_keys = {
        (word.get("block"), word.get("paragraph"), word.get("line"))
        for word in words
        if word.get("text")
    }
    block_count = len({word.get("block") for word in words if word.get("text")})
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    median_confidence = median(confidences) if confidences else 0.0
    low_confidence_count = sum(value < 60 for value in confidences)
    readable_ratio = (
        sum(value >= 60 for value in confidences) / len(confidences)
        if confidences
        else 0.0
    )
    confidence_points = min(45.0, mean_confidence * 0.45)
    density_points = min(20.0, len(normalized) / 80.0)
    cue_points = min(20.0, len(cue_hits) * 4.0)
    layout_points = min(15.0, block_count * 2.0 + len(line_keys) / 8.0)
    quality_score = round(confidence_points + density_points + cue_points + layout_points, 2)
    if not confidences or len(normalized) < 40:
        review_status = "ocr_failed_or_blank_review_required"
    elif quality_score >= 78 and readable_ratio >= 0.8:
        review_status = "high_quality_ocr_review_required"
    elif quality_score >= 55 and readable_ratio >= 0.55:
        review_status = "usable_ocr_review_required"
    else:
        review_status = "low_quality_ocr_review_required"
    quality = {
        "character_count": len(text),
        "word_count": len(confidences),
        "line_count": len(line_keys),
        "layout_block_count": block_count,
        "page_width": int(width),
        "page_height": int(height),
        "mean_word_confidence": round(mean_confidence, 2),
        "median_word_confidence": round(float(median_confidence), 2),
        "low_confidence_word_count": low_confidence_count,
        "readable_word_ratio": round(readable_ratio, 4),
        "transaction_cue_hits": cue_hits,
        "quality_score": quality_score,
        "review_status": review_status,
        "ocr_text_sha256": sha256(text.encode("utf-8")).hexdigest(),
    }
    return enrich_page_quality(text=text, quality=quality)


def document_quality(pages: list[dict]) -> dict:
    page_metrics = [page["quality"] for page in pages]
    status_counts = Counter(row["review_status"] for row in page_metrics)
    scores = [float(row["quality_score"]) for row in page_metrics]
    word_count = sum(int(row["word_count"]) for row in page_metrics)
    character_count = sum(int(row["character_count"]) for row in page_metrics)
    readable_pages = sum(
        row["review_status"] in {"high_quality_ocr_review_required", "usable_ocr_review_required"}
        for row in page_metrics
    )
    if not page_metrics:
        status = "ocr_not_processed"
    elif readable_pages == len(page_metrics):
        status = "ocr_complete_review_required"
    elif readable_pages:
        status = "ocr_partial_review_required"
    else:
        status = "ocr_low_quality_review_required"
    field_confidence = {
        field: round(
            sum(float(row.get("field_label_confidence", {}).get(field, 0.0)) for row in page_metrics)
            / len(page_metrics),
            4,
        )
        if page_metrics
        else 0.0
        for field in FIELD_LABELS
    }
    return {
        "page_count": len(page_metrics),
        "readable_page_count": readable_pages,
        "word_count": word_count,
        "character_count": character_count,
        "mean_page_quality_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "minimum_page_quality_score": round(min(scores), 2) if scores else 0.0,
        "mean_ocr_confidence": round(
            sum(float(row.get("ocr_confidence") or 0.0) for row in page_metrics) / len(page_metrics),
            4,
        )
        if page_metrics
        else 0.0,
        "mean_layout_confidence": round(
            sum(float(row.get("layout_confidence") or 0.0) for row in page_metrics) / len(page_metrics),
            4,
        )
        if page_metrics
        else 0.0,
        "field_label_confidence": field_confidence,
        "mean_review_quality_score": round(sum(scores) / len(scores) / 100, 4) if scores else 0.0,
        "page_review_status_counts": dict(sorted(status_counts.items())),
        "processing_status": status,
        "human_review_required": True,
        "transaction_rows_created": 0,
    }

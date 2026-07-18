from __future__ import annotations

import re
from typing import Any

from .ids import evidence_id
from .transcript_normalizer import TranscriptSegment, segment_metadata


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def youtube_timestamp_url(source_url: str, seconds: float) -> str:
    return f"{source_url}&t={int(seconds)}s" if "?" in source_url else f"{source_url}?t={int(seconds)}s"


def _short_quote(text: str, limit: int = 360) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    clipped = cleaned[:limit].rsplit(" ", 1)[0].rstrip(".,;:!? ")
    return f"{clipped}…"


def build_evidence(media_id: str, source_url: str, provider: str, segments: list[TranscriptSegment]) -> list[dict[str, Any]]:
    source_types = {
        "official_transcript": "official_transcript",
        "ulisten": "third_party_transcript",
        "usetranscribe": "third_party_transcript",
        "manual_markdown": "manual_transcript",
        "youtube_export": "youtube_caption",
    }
    result = []
    for index, segment in enumerate(segments, 1):
        confidence, method = segment_metadata(segment)
        result.append({
            "evidence_id": evidence_id(media_id, index),
            "media_id": media_id,
            "source_type": source_types.get(provider, "third_party_transcript"),
            "provider": provider,
            "speaker": segment.speaker or "unknown",
            "speaker_confidence": confidence,
            "attribution_method": method,
            "start_seconds": int(segment.start_seconds) if segment.start_seconds.is_integer() else segment.start_seconds,
            "end_seconds": int(segment.end_seconds) if segment.end_seconds.is_integer() else segment.end_seconds,
            "timestamp": format_timestamp(segment.start_seconds),
            "youtube_url": youtube_timestamp_url(source_url, segment.start_seconds),
            "section": segment.section,
            "quote": _short_quote(segment.text),
            "summary_zh": "",
            "relevance": "unrated",
            "needs_review": confidence < 0.8,
        })
    return result

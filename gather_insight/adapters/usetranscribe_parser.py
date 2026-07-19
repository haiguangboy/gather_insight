from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from gather_insight.pipeline.evidence_builder import format_timestamp, youtube_timestamp_url
from gather_insight.pipeline.transcript_normalizer import parse_timestamp


_TIMESTAMP = r"\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?"
_RANGE_CUE = re.compile(
    rf"^\s*(?:#{{1,6}}\s*)?(?:\[)?(?P<start>{_TIMESTAMP})\s*(?:-|–|—|-->|to)\s*(?P<end>{_TIMESTAMP})(?:\])?(?:\([^)]*\))?\s*(?P<text>.*)$",
    re.IGNORECASE,
)
_DOUBLE_LINKED_CUE = re.compile(
    rf"^\s*(?:#{{1,6}}\s*)?\[\[(?P<start>{_TIMESTAMP})\]\](?:\([^)]*\))?\s*(?:[-–—|:])?\s*(?P<text>.*)$"
)
_LINKED_CUE = re.compile(
    rf"^\s*(?:#{{1,6}}\s*)?\[(?P<start>{_TIMESTAMP})\](?:\([^)]*\))?\s*(?:[-–—|:])?\s*(?P<text>.*)$"
)
_PLAIN_CUE = re.compile(
    rf"^\s*(?:#{{1,6}}\s*)?(?P<start>{_TIMESTAMP})\s*(?:[-–—|:])?\s*(?P<text>.*)$"
)


@dataclass(frozen=True)
class UseTranscribeSegment:
    segment_id: str
    media_id: str
    provider: str
    provider_id: str | None
    speaker: None
    chapter: None
    chapter_index: None
    chapter_start_seconds: None
    chapter_end_seconds: None
    reference_url: None
    start_seconds: float
    end_seconds: float
    timestamp: str
    end_timestamp: str
    text: str
    text_raw: str
    youtube_url: str

    def as_dict(self) -> dict[str, object]:
        return {
            "segment_id": self.segment_id,
            "media_id": self.media_id,
            "provider": self.provider,
            "provider_id": self.provider_id,
            "speaker": None,
            "chapter": None,
            "chapter_index": None,
            "chapter_start_seconds": None,
            "chapter_end_seconds": None,
            "reference_url": None,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "timestamp": self.timestamp,
            "end_timestamp": self.end_timestamp,
            "text": self.text,
            "text_raw": self.text_raw,
            "youtube_url": self.youtube_url,
        }


@dataclass(frozen=True)
class UseTranscribeParseResult:
    segments: list[UseTranscribeSegment]


def _cue(line: str) -> tuple[str, str | None, str] | None:
    for pattern in (_RANGE_CUE, _DOUBLE_LINKED_CUE, _LINKED_CUE, _PLAIN_CUE):
        match = pattern.fullmatch(line)
        if match:
            return match.group("start"), match.groupdict().get("end"), match.group("text").strip()
    return None


def parse_usetranscribe_markdown(*, raw: str, media_id: str, youtube_url: str, video_duration_seconds: float | None, provider_id: str | None = None) -> UseTranscribeParseResult:
    if not media_id.startswith("yt_"):
        raise ValueError("UseTranscribe parsing requires a canonical YouTube media_id")
    pending: dict[str, object] | None = None
    parsed: list[dict[str, object]] = []

    def flush() -> None:
        nonlocal pending
        if pending is None:
            return
        pending["text"] = " ".join(str(part).strip() for part in pending.get("body", []) if str(part).strip()).strip()
        parsed.append(pending)
        pending = None

    for raw_line in raw.replace("\ufeff", "").splitlines():
        line = raw_line.strip()
        cue = _cue(line) if line else None
        if cue:
            flush()
            start_timestamp, end_timestamp, inline_text = cue
            pending = {
                "start_timestamp": start_timestamp.replace(",", "."),
                "end_timestamp": end_timestamp.replace(",", ".") if end_timestamp else None,
                "start_seconds": parse_timestamp(start_timestamp.replace(",", ".")),
                "explicit_end_seconds": parse_timestamp(end_timestamp.replace(",", ".")) if end_timestamp else None,
                "body": [inline_text] if inline_text else [],
            }
            continue
        if pending is not None and line and not line.startswith(("# ", "## ", "### ")):
            pending["body"].append(line)
    flush()

    if not parsed:
        raise ValueError("no UseTranscribe timestamped segments found")
    result: list[UseTranscribeSegment] = []
    for index, item in enumerate(parsed):
        start_seconds = float(item["start_seconds"])
        explicit_end = item.get("explicit_end_seconds")
        if explicit_end is not None:
            end_seconds = float(explicit_end)
        elif index + 1 < len(parsed):
            end_seconds = float(parsed[index + 1]["start_seconds"])
        elif video_duration_seconds is not None:
            end_seconds = float(video_duration_seconds)
        else:
            raise ValueError("video duration is required when the final UseTranscribe segment has no end timestamp")
        if end_seconds < start_seconds:
            raise ValueError(f"UseTranscribe segment ends before it starts: {index + 1}")
        text = str(item.get("text", ""))
        result.append(UseTranscribeSegment(
            segment_id=f"{media_id}.seg_{index + 1:04d}",
            media_id=media_id,
            provider="usetranscribe",
            provider_id=provider_id,
            speaker=None,
            chapter=None,
            chapter_index=None,
            chapter_start_seconds=None,
            chapter_end_seconds=None,
            reference_url=None,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            timestamp=str(item["start_timestamp"]),
            end_timestamp=str(item.get("end_timestamp") or format_timestamp(end_seconds)),
            text=text,
            text_raw=text,
            youtube_url=youtube_timestamp_url(youtube_url, start_seconds),
        ))
    return UseTranscribeParseResult(segments=result)


def parse_usetranscribe_file(*, path: Path, media_id: str, youtube_url: str, video_duration_seconds: float | None, provider_id: str | None = None) -> UseTranscribeParseResult:
    if path.name != "source_usetranscribe_raw.md":
        raise ValueError("UseTranscribe production input must be named source_usetranscribe_raw.md")
    return parse_usetranscribe_markdown(
        raw=path.read_text(encoding="utf-8"),
        media_id=media_id,
        youtube_url=youtube_url,
        video_duration_seconds=video_duration_seconds,
        provider_id=provider_id,
    )


def segments_as_dicts(result: UseTranscribeParseResult) -> list[dict[str, object]]:
    return [segment.as_dict() for segment in result.segments]

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from gather_insight.pipeline.evidence_builder import format_timestamp, youtube_timestamp_url
from gather_insight.pipeline.transcript_normalizer import parse_timestamp


_CHAPTER_RANGE = re.compile(
    r"^(?P<start>\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(?P<end>\d{1,2}:\d{2}(?::\d{2})?)$"
)
_CHAPTER_HEADING = re.compile(r"^####\s+(?P<title>.+?)\s*$")
_SPEAKER_TIMESTAMP = re.compile(r"^(?P<speaker>.+?)(?P<timestamp>\d{1,2}:\d{2}(?::\d{2})?)$")
_REFERENCE_URL = re.compile(r"\s*\((?P<url>https?://[^)\s]+)\)\s*$")


@dataclass(frozen=True)
class UlistenChapter:
    index: int
    title: str
    start_seconds: float
    end_seconds: float
    start_timestamp: str
    end_timestamp: str
    reference_url: str | None = None


@dataclass(frozen=True)
class UlistenSegment:
    segment_id: str
    media_id: str
    provider: str
    provider_id: str | None
    speaker: str
    chapter: str
    chapter_index: int
    chapter_start_seconds: float
    chapter_end_seconds: float
    reference_url: str | None
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
            "speaker": self.speaker,
            "chapter": self.chapter,
            "chapter_index": self.chapter_index,
            "chapter_start_seconds": self.chapter_start_seconds,
            "chapter_end_seconds": self.chapter_end_seconds,
            "reference_url": self.reference_url,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "timestamp": self.timestamp,
            "end_timestamp": self.end_timestamp,
            "text": self.text,
            "text_raw": self.text_raw,
            "youtube_url": self.youtube_url,
        }


@dataclass(frozen=True)
class UlistenParseResult:
    chapters: list[UlistenChapter]
    segments: list[UlistenSegment]


def _split_reference(title: str) -> tuple[str, str | None]:
    match = _REFERENCE_URL.search(title)
    if not match:
        return title.strip(), None
    return title[: match.start()].strip(), match.group("url")


def _is_speaker_line(line: str) -> re.Match[str] | None:
    match = _SPEAKER_TIMESTAMP.fullmatch(line.strip())
    if not match:
        return None
    speaker = match.group("speaker").strip()
    if not speaker or speaker in {"uListen", "Read AlongSearch & Jump", "Jump to live"}:
        return None
    return match


def _is_ignored_ui(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped in {"−", "-", "uListen", "At a Glance📜Every Spoken Word🧭Discover", "Read AlongSearch & Jump", "Jump to live"}


def _flush_pending(
    pending: dict[str, object] | None,
    chapter: UlistenChapter | None,
    segments: list[dict[str, object]],
) -> None:
    if pending is None or chapter is None:
        return
    segments.append({
        "speaker": str(pending["speaker"]),
        "start_seconds": float(pending["start_seconds"]),
        "timestamp": str(pending["timestamp"]),
        "text_raw": str(pending.get("text_raw", "")),
        "chapter": chapter,
    })


def _iter_lines(raw: str) -> Iterable[str]:
    for line in raw.replace("\ufeff", "").splitlines():
        yield line.rstrip("\r")


def parse_ulisten_markdown(*, raw: str, media_id: str, youtube_url: str, provider_id: str | None = None) -> UlistenParseResult:
    if not media_id.startswith("yt_"):
        raise ValueError("uListen parsing requires a canonical YouTube media_id")
    chapters: list[UlistenChapter] = []
    pending_ranges: list[tuple[str, str]] = []
    raw_segments: list[dict[str, object]] = []
    current_chapter: UlistenChapter | None = None
    pending: dict[str, object] | None = None
    lines = list(_iter_lines(raw))
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        range_match = _CHAPTER_RANGE.fullmatch(line)
        if range_match:
            _flush_pending(pending, current_chapter, raw_segments)
            pending = None
            pending_ranges.append((range_match.group("start"), range_match.group("end")))
            index += 1
            continue
        heading_match = _CHAPTER_HEADING.fullmatch(line)
        if heading_match and pending_ranges:
            start_timestamp, end_timestamp = pending_ranges.pop(0)
            title, reference_url = _split_reference(heading_match.group("title"))
            current_chapter = UlistenChapter(
                index=len(chapters) + 1,
                title=title,
                start_seconds=parse_timestamp(start_timestamp),
                end_seconds=parse_timestamp(end_timestamp),
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                reference_url=reference_url,
            )
            chapters.append(current_chapter)
            index += 1
            continue
        speaker_match = _is_speaker_line(line)
        if speaker_match and current_chapter is not None:
            _flush_pending(pending, current_chapter, raw_segments)
            pending = {
                "speaker": speaker_match.group("speaker").strip(),
                "start_seconds": parse_timestamp(speaker_match.group("timestamp")),
                "timestamp": speaker_match.group("timestamp"),
                "text_raw": "",
            }
            index += 1
            continue
        if pending is not None:
            if _is_ignored_ui(line) or _CHAPTER_RANGE.fullmatch(line) or _CHAPTER_HEADING.fullmatch(line):
                index += 1
                continue
            pending["text_raw"] = f"{pending['text_raw']}{line}"
        index += 1
    _flush_pending(pending, current_chapter, raw_segments)

    if not chapters:
        raise ValueError("no uListen chapters found")
    if not raw_segments:
        raise ValueError("no uListen speaker segments found")

    result: list[UlistenSegment] = []
    for number, item in enumerate(raw_segments, 1):
        chapter = item["chapter"]
        assert isinstance(chapter, UlistenChapter)
        start_seconds = float(item["start_seconds"])
        next_item = raw_segments[number] if number < len(raw_segments) else None
        if next_item is not None and next_item["chapter"] == chapter:
            end_seconds = float(next_item["start_seconds"])
        else:
            end_seconds = chapter.end_seconds
        if end_seconds < start_seconds:
            raise ValueError(f"uListen segment ends before it starts: {number}")
        text_raw = str(item["text_raw"])
        result.append(UlistenSegment(
            segment_id=f"{media_id}.seg_{number:04d}",
            media_id=media_id,
            provider="ulisten",
            provider_id=provider_id,
            speaker=str(item["speaker"]),
            chapter=chapter.title,
            chapter_index=chapter.index,
            chapter_start_seconds=chapter.start_seconds,
            chapter_end_seconds=chapter.end_seconds,
            reference_url=chapter.reference_url,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            timestamp=str(item["timestamp"]),
            end_timestamp=format_timestamp(end_seconds),
            text=text_raw,
            text_raw=text_raw,
            youtube_url=youtube_timestamp_url(youtube_url, start_seconds),
        ))
    return UlistenParseResult(chapters=chapters, segments=result)


def parse_ulisten_file(*, path: Path, media_id: str, youtube_url: str, provider_id: str | None = None) -> UlistenParseResult:
    return parse_ulisten_markdown(raw=path.read_text(encoding="utf-8"), media_id=media_id, youtube_url=youtube_url, provider_id=provider_id)


def segments_as_dicts(result: UlistenParseResult) -> list[dict[str, object]]:
    return [segment.as_dict() for segment in result.segments]


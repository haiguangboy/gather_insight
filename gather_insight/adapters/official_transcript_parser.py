from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gather_insight.pipeline.evidence_builder import format_timestamp, youtube_timestamp_url
from gather_insight.pipeline.transcript_normalizer import load_transcript


@dataclass(frozen=True)
class OfficialTranscriptSegment:
    segment_id: str
    media_id: str
    provider: str
    provider_id: str | None
    speaker: str | None
    chapter: str | None
    chapter_index: int | None
    chapter_start_seconds: float | None
    chapter_end_seconds: float | None
    reference_url: str | None
    start_seconds: float
    end_seconds: float
    timestamp: str
    end_timestamp: str
    text: str
    text_raw: str
    youtube_url: str

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class OfficialTranscriptParseResult:
    segments: list[OfficialTranscriptSegment]


def parse_official_transcript_file(*, path: Path, media_id: str, youtube_url: str, provider_id: str | None = None) -> OfficialTranscriptParseResult:
    if path.name != "source_official_transcript_raw.md":
        raise ValueError("official transcript input must be named source_official_transcript_raw.md")
    _, parsed = load_transcript(path, "markdown")
    segments: list[OfficialTranscriptSegment] = []
    chapter_indexes: dict[str, int] = {}
    for index, item in enumerate(parsed, 1):
        chapter = item.section
        if chapter and chapter not in chapter_indexes:
            chapter_indexes[chapter] = len(chapter_indexes) + 1
        speaker = item.speaker if item.speaker and item.speaker.lower() != "unknown" else None
        segments.append(OfficialTranscriptSegment(
            segment_id=f"{media_id}.seg_{index:04d}",
            media_id=media_id,
            provider="official_transcript",
            provider_id=provider_id,
            speaker=speaker,
            chapter=chapter,
            chapter_index=chapter_indexes.get(chapter) if chapter else None,
            chapter_start_seconds=None,
            chapter_end_seconds=None,
            reference_url=None,
            start_seconds=item.start_seconds,
            end_seconds=item.end_seconds,
            timestamp=format_timestamp(item.start_seconds),
            end_timestamp=format_timestamp(item.end_seconds),
            text=item.text,
            text_raw=item.text,
            youtube_url=youtube_timestamp_url(youtube_url, item.start_seconds),
        ))
    return OfficialTranscriptParseResult(segments)

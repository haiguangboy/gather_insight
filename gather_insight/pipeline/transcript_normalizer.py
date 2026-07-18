from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TranscriptSegment:
    start_seconds: float
    end_seconds: float
    text: str
    speaker: str = "unknown"
    section: str | None = None


_RANGE = re.compile(
    r"(?:\[)?(?P<start>\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)\s*(?:-|–|—|--> )\s*"
    r"(?P<end>\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)(?:\])?"
)
_STAMP = re.compile(r"(?:\[)?(?P<stamp>\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)(?:\])?")


def parse_timestamp(value: str) -> float:
    parts = value.strip().split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    raise ValueError(f"invalid timestamp: {value}")


def _clean_text(lines: list[str]) -> str:
    text = " ".join(line.strip() for line in lines if line.strip())
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_markdown(text: str) -> list[TranscriptSegment]:
    """Parse the deliberately small, human-editable Markdown transcript format.

    Supported cue headers are ``## [00:10-00:30] Speaker`` and
    ``[00:10] Speaker: text``. A header's following paragraphs belong to it.
    """
    segments: list[TranscriptSegment] = []
    current: dict[str, object] | None = None
    body: list[str] = []

    def flush() -> None:
        nonlocal current, body
        if not current:
            body = []
            return
        value = _clean_text(body)
        if value:
            segments.append(
                TranscriptSegment(
                    float(current["start"]),
                    float(current["end"]),
                    value,
                    str(current.get("speaker") or "unknown"),
                    str(current.get("section")) if current.get("section") else None,
                )
            )
        current = None
        body = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        header = line.lstrip("# ").strip()
        match = _RANGE.search(header)
        if match:
            flush()
            before = header[: match.start()].strip(" []|-–—")
            after = header[match.end() :].strip(" []|-–—")
            speaker = after or before or "unknown"
            section = None
            if "|" in speaker:
                speaker, section = [part.strip() for part in speaker.split("|", 1)]
            current = {
                "start": parse_timestamp(match.group("start")),
                "end": parse_timestamp(match.group("end")),
                "speaker": speaker or "unknown",
                "section": section,
            }
            continue
        inline = _STAMP.match(header)
        if inline:
            flush()
            start = parse_timestamp(inline.group("stamp"))
            remainder = header[inline.end() :].strip(" :-|–—")
            speaker = "unknown"
            text_part = remainder
            if ":" in remainder:
                speaker, text_part = [part.strip() for part in remainder.split(":", 1)]
            current = {"start": start, "end": start, "speaker": speaker}
            if text_part:
                body.append(text_part)
            continue
        if current:
            body.append(line)
    flush()

    if not segments:
        raise ValueError("no timestamped transcript segments found")
    for segment in segments:
        if segment.end_seconds < segment.start_seconds:
            raise ValueError("transcript segment ends before it starts")
    normalized: list[TranscriptSegment] = []
    for index, segment in enumerate(segments):
        end = segment.end_seconds
        if end == segment.start_seconds:
            next_start = segments[index + 1].start_seconds if index + 1 < len(segments) else segment.start_seconds + 15
            end = max(segment.start_seconds, next_start)
        normalized.append(TranscriptSegment(segment.start_seconds, end, segment.text, segment.speaker, segment.section))
    return normalized


def load_markdown(path: Path) -> tuple[str, list[TranscriptSegment]]:
    raw = path.read_text(encoding="utf-8")
    return raw, parse_markdown(raw)


def _speaker_confidence(speaker: str) -> tuple[float, str]:
    if not speaker or speaker.lower() == "unknown":
        return 0.0, "unknown"
    return 0.75, "manual_label"


def chunk_segments(segments: list[TranscriptSegment], target_seconds: float = 45.0, max_seconds: float = 60.0) -> list[TranscriptSegment]:
    chunks: list[TranscriptSegment] = []
    current: list[TranscriptSegment] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        first, last = current[0], current[-1]
        chunks.append(TranscriptSegment(first.start_seconds, last.end_seconds, _clean_text([s.text for s in current]), first.speaker, first.section))
        current = []

    for segment in segments:
        if not current:
            current = [segment]
            continue
        first = current[0]
        same_context = segment.speaker == first.speaker and segment.section == first.section
        proposed_end = segment.end_seconds
        if (not same_context) or proposed_end - first.start_seconds > max_seconds or (proposed_end - first.start_seconds >= target_seconds and current):
            flush()
            current = [segment]
        else:
            current.append(segment)
    flush()
    return chunks


def segment_metadata(segment: TranscriptSegment) -> tuple[float, str]:
    return _speaker_confidence(segment.speaker)

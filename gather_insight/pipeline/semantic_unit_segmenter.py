from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence


SEMANTIC_UNIT_VERSION = "semantic_units_v1"
_TOKEN = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9'_.%-]*\b")
_EVENT = re.compile(r"\[(?:applause|audience applauding|clapping|laughter|laughs|music|on-hold music)\]", re.IGNORECASE)
_PRIMARY_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_SECONDARY_BOUNDARY = re.compile(r"(?<=[;:])\s+")
_CLAUSE_BOUNDARY = re.compile(r"(?:,\s+|\s+)(?=(?:and|but|so|because|while|then|however|therefore)\b)", re.IGNORECASE)


@dataclass(frozen=True)
class SemanticUnit:
    unit_id: str
    secondary_segment_id: str
    text: str
    original_char_start: int
    original_char_end: int
    token_start: int
    token_end: int
    approx_start_seconds: float
    approx_end_seconds: float
    unit_type: str
    boundary_start_confidence: float
    boundary_end_confidence: float

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def _trimmed_span(text: str, start: int, end: int) -> tuple[int, int] | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if end > start else None


def _split_by_regex(text: str, start: int, end: int, pattern: re.Pattern[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = start
    for match in pattern.finditer(text, start, end):
        trimmed = _trimmed_span(text, cursor, match.start())
        if trimmed:
            spans.append(trimmed)
        cursor = match.end()
    trimmed = _trimmed_span(text, cursor, end)
    if trimmed:
        spans.append(trimmed)
    return spans


def _split_long_clause(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    if end - start <= max_chars:
        return [(start, end)]
    candidates = list(_CLAUSE_BOUNDARY.finditer(text, start, end))
    if not candidates:
        return [(start, end)]
    midpoint = (start + end) / 2
    cut = min(candidates, key=lambda match: abs(match.start() - midpoint))
    if cut.start() - start < 40 or end - cut.end() < 40:
        return [(start, end)]
    return _split_long_clause(text, start, cut.start(), max_chars) + _split_long_clause(text, cut.end(), end, max_chars)


def _semantic_spans(text: str, max_chars: int) -> list[tuple[int, int, str, float, float]]:
    pieces: list[tuple[int, int, str, float, float]] = []
    cursor = 0
    for event in _EVENT.finditer(text):
        if event.start() > cursor:
            pieces.extend(_language_spans(text, cursor, event.start(), max_chars))
        pieces.append((event.start(), event.end(), "event", 0.98, 0.98))
        cursor = event.end()
    if cursor < len(text):
        pieces.extend(_language_spans(text, cursor, len(text), max_chars))
    return pieces


def _language_spans(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int, str, float, float]]:
    output: list[tuple[int, int, str, float, float]] = []
    primary = _split_by_regex(text, start, end, _PRIMARY_BOUNDARY)
    for p_start, p_end in primary:
        secondary = _split_by_regex(text, p_start, p_end, _SECONDARY_BOUNDARY)
        for s_start, s_end in secondary:
            for c_start, c_end in _split_long_clause(text, s_start, s_end, max_chars):
                value = text[c_start:c_end]
                if value.rstrip().endswith((".", "?", "!")):
                    kind, end_confidence = "sentence", 0.95
                elif value.rstrip().endswith((";", ":")):
                    kind, end_confidence = "clause", 0.86
                else:
                    kind, end_confidence = "clause", 0.72
                output.append((c_start, c_end, kind, 0.9, end_confidence))
    return output


def segment_secondary_text(segments: Sequence[object], *, max_unit_chars: int = 260) -> list[SemanticUnit]:
    units: list[SemanticUnit] = []
    global_char = 0
    global_token = 0
    for segment in segments:
        text = str(getattr(segment, "text"))
        start_seconds = float(getattr(segment, "start_seconds"))
        end_seconds = float(getattr(segment, "end_seconds"))
        duration = max(0.0, end_seconds - start_seconds)
        local_tokens = list(_TOKEN.finditer(text))
        for local_index, (start, end, unit_type, start_conf, end_conf) in enumerate(_semantic_spans(text, max_unit_chars), 1):
            local_token_start = sum(match.end() <= start for match in local_tokens)
            local_token_end = sum(match.start() < end for match in local_tokens)
            ratio_start = start / max(1, len(text))
            ratio_end = end / max(1, len(text))
            secondary_id = str(getattr(segment, "segment_id"))
            units.append(SemanticUnit(
                unit_id=f"{secondary_id}.unit_{local_index:04d}",
                secondary_segment_id=secondary_id,
                text=text[start:end],
                original_char_start=global_char + start,
                original_char_end=global_char + end,
                token_start=global_token + local_token_start,
                token_end=global_token + local_token_end,
                approx_start_seconds=round(start_seconds + duration * ratio_start, 3),
                approx_end_seconds=round(start_seconds + duration * ratio_end, 3),
                unit_type=unit_type,
                boundary_start_confidence=start_conf,
                boundary_end_confidence=end_conf,
            ))
        global_char += len(text) + 1
        global_token += len(local_tokens)
    return units


def canonical_secondary_text(segments: Sequence[object]) -> str:
    return "\n".join(str(getattr(segment, "text")) for segment in segments)

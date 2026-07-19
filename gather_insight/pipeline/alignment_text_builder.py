from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from gather_insight.adapters.ulisten_parser import UlistenSegment


ALIGNMENT_TEXT_VERSION = "conservative_spacing_v1"
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'_.-]*")
_ALPHA_RUN = re.compile(r"[A-Za-z]{8,}")


@dataclass(frozen=True)
class AlignmentText:
    text: str
    method: str
    is_authoritative: bool
    protected_terms: list[str]


def protected_terms(segment: UlistenSegment) -> list[str]:
    values = [segment.speaker, segment.chapter]
    if segment.reference_url:
        values.append(urlparse(segment.reference_url).path.rsplit("/", 1)[-1])
    terms = {match.group(0) for value in values for match in _WORD.finditer(value or "") if len(match.group(0)) >= 2}
    return sorted(terms, key=lambda item: (-len(item), item.lower()))


def _split_run(run: str, protected: list[str]) -> list[str]:
    lowered = run.lower()
    matches: list[tuple[int, int, str]] = []
    for term in protected:
        compact = re.sub(r"[^A-Za-z0-9]", "", term)
        if len(compact) < 2:
            continue
        start = lowered.find(compact.lower())
        if start >= 0:
            matches.append((start, start + len(compact), run[start:start + len(compact)]))
    if matches:
        start, end, value = min(matches)
        return _split_run(run[:start], protected) + [value] + _split_run(run[end:], protected)
    if len(run) < 8:
        return [run] if run else []
    try:
        import wordninja
    except ImportError:
        return [run]
    parts = wordninja.split(run)
    return parts if len(parts) > 1 else [run]


def build_alignment_text(segment: UlistenSegment) -> AlignmentText:
    terms = protected_terms(segment)
    raw = segment.text_raw
    spaced = re.sub(r"([.!?;:,\[\]()])", r"\1 ", raw)
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", spaced)
    chunks: list[str] = []
    cursor = 0
    for match in _ALPHA_RUN.finditer(spaced):
        chunks.append(spaced[cursor:match.start()])
        chunks.append(" ".join(_split_run(match.group(0), terms)))
        cursor = match.end()
    chunks.append(spaced[cursor:])
    text = re.sub(r"\s+", " ", "".join(chunks)).strip()
    method = "conservative_spacing_wordninja" if text != raw else "character_anchor_only"
    return AlignmentText(text=text or raw, method=method, is_authoritative=False, protected_terms=terms)

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import Iterable

from gather_insight.adapters.ulisten_parser import UlistenSegment
from gather_insight.adapters.usetranscribe_parser import UseTranscribeSegment


_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_NUMBER_TOKEN = re.compile(r"\d+(?:\.\d+)?(?:%|x)?", re.IGNORECASE)
_MODEL_TOKEN = re.compile(r"(?:GPT|Llama|DeepSeek|Claude|Gemini|H|A|B|o)\s*-?\s*\d[0-9A-Za-z.\-]*", re.IGNORECASE)
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'\-]*")
_NEGATIONS = {"not", "no", "never", "cannot", "can't", "won't", "without"}
_STOPWORDS = {"the", "and", "from", "with", "under", "more", "into", "this", "that", "paper", "modeling"}


@dataclass(frozen=True)
class FusedSegment:
    segment_id: str
    media_id: str
    speaker: str
    chapter: str
    chapter_index: int
    reference_url: str | None
    start_seconds: float
    end_seconds: float
    text: str
    text_ulisten_raw: str
    text_usetranscribe_raw: str | None
    structure_source: str
    text_source: str
    alignment_method: str
    alignment_confidence: float | None
    alignment_components: dict[str, float] | None
    needs_review: bool
    review_reasons: list[str]
    conflicts: list[dict[str, object]]
    youtube_url: str
    fusion_mode: str
    matched_secondary_segment_ids: list[str] | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "segment_id": self.segment_id,
            "media_id": self.media_id,
            "speaker": self.speaker,
            "chapter": self.chapter,
            "chapter_index": self.chapter_index,
            "reference_url": self.reference_url,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "text": self.text,
            "text_ulisten_raw": self.text_ulisten_raw,
            "text_usetranscribe_raw": self.text_usetranscribe_raw,
            "structure_source": self.structure_source,
            "text_source": self.text_source,
            "alignment_method": self.alignment_method,
            "alignment_confidence": self.alignment_confidence,
            "alignment_components": self.alignment_components,
            "needs_review": self.needs_review,
            "review_reasons": self.review_reasons,
            "conflicts": self.conflicts,
            "youtube_url": self.youtube_url,
            "fusion_mode": self.fusion_mode,
        }


@dataclass(frozen=True)
class FusionDiagnostics:
    secondary_segment_reuse_count: int
    cross_speaker_boundary_count: int
    adjacent_text_duplication_rate: float
    unconsumed_secondary_segment_count: int

    def as_dict(self) -> dict[str, int | float]:
        return {
            "secondary_segment_reuse_count": self.secondary_segment_reuse_count,
            "cross_speaker_boundary_count": self.cross_speaker_boundary_count,
            "adjacent_text_duplication_rate": self.adjacent_text_duplication_rate,
            "unconsumed_secondary_segment_count": self.unconsumed_secondary_segment_count,
        }


@dataclass(frozen=True)
class FusionResult:
    mode: str
    segments: list[FusedSegment]
    diagnostics: FusionDiagnostics | None = None


def normalize_for_similarity(text: str) -> str:
    return _NON_ALNUM.sub("", text.lower())


def normalized_text_similarity(left: str, right: str) -> float:
    normalized_left = normalize_for_similarity(left)
    normalized_right = normalize_for_similarity(right)
    if not normalized_left and not normalized_right:
        return 1.0
    if not normalized_left or not normalized_right:
        return 0.0
    return SequenceMatcher(None, normalized_left, normalized_right, autojunk=False).ratio()


def _merge_intervals(intervals: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    ordered = sorted(intervals)
    merged: list[tuple[float, float]] = []
    for start, end in ordered:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def time_overlap_score(structure: UlistenSegment, text_segments: list[UseTranscribeSegment]) -> float:
    duration = structure.end_seconds - structure.start_seconds
    if duration <= 0:
        return 1.0 if any(segment.start_seconds == structure.start_seconds for segment in text_segments) else 0.0
    intersections = []
    for segment in text_segments:
        start = max(structure.start_seconds, segment.start_seconds)
        end = min(structure.end_seconds, segment.end_seconds)
        if end > start:
            intersections.append((start, end))
    covered = sum(end - start for start, end in _merge_intervals(intersections))
    return min(1.0, max(0.0, covered / duration))


def _chapter_consistency(structure: UlistenSegment, text_segments: list[UseTranscribeSegment]) -> float:
    chapters = {segment.chapter for segment in text_segments if segment.chapter}
    if not chapters:
        return 0.5
    normalized = normalize_for_similarity(structure.chapter)
    return 1.0 if any(normalize_for_similarity(chapter or "") == normalized for chapter in chapters) else 0.0


def _overlapping_segments(structure: UlistenSegment, text_segments: list[UseTranscribeSegment], tolerance_seconds: float) -> list[UseTranscribeSegment]:
    actual = [
        segment for segment in text_segments
        if segment.end_seconds > structure.start_seconds
        and segment.start_seconds < structure.end_seconds
    ]
    if actual:
        return actual
    return [
        segment for segment in text_segments
        if segment.end_seconds >= structure.start_seconds - tolerance_seconds
        and segment.start_seconds <= structure.end_seconds + tolerance_seconds
    ]


def _terms_from_structure(structure: UlistenSegment) -> set[str]:
    values = _WORD.findall(f"{structure.speaker} {structure.chapter}")
    return {value.lower() for value in values if len(value) >= 3 and value.lower() not in _STOPWORDS}


def _model_tokens(text: str) -> set[str]:
    return {normalize_for_similarity(match.group(0)) for match in _MODEL_TOKEN.finditer(text)}


def _numeric_tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in _NUMBER_TOKEN.finditer(text)}


def _negation_tokens(text: str) -> set[str]:
    return {word.lower() for word in _WORD.findall(text) if word.lower() in _NEGATIONS}


def detect_conflicts(structure: UlistenSegment, text: str) -> list[dict[str, object]]:
    conflicts: list[dict[str, object]] = []
    ulisten_numbers = _numeric_tokens(structure.text_raw)
    text_numbers = _numeric_tokens(text)
    if ulisten_numbers and text_numbers and ulisten_numbers != text_numbers:
        conflicts.append({"type": "numeric_conflict", "ulisten": sorted(ulisten_numbers), "usetranscribe": sorted(text_numbers)})
    ulisten_models = _model_tokens(structure.text_raw)
    text_models = _model_tokens(text)
    if (ulisten_models or text_models) and ulisten_models != text_models:
        conflicts.append({"type": "model_name_conflict", "ulisten": sorted(ulisten_models), "usetranscribe": sorted(text_models)})
    ulisten_negations = _negation_tokens(structure.text_raw)
    text_negations = _negation_tokens(text)
    if ulisten_negations != text_negations:
        conflicts.append({"type": "negation_conflict", "ulisten": sorted(ulisten_negations), "usetranscribe": sorted(text_negations)})
    compact_ulisten = normalize_for_similarity(structure.text_raw)
    compact_text = normalize_for_similarity(text)
    differing_terms = []
    for term in sorted(_terms_from_structure(structure)):
        in_ulisten = term in compact_ulisten
        in_text = term in compact_text
        if in_ulisten != in_text:
            differing_terms.append(term)
    if differing_terms:
        conflicts.append({"type": "protected_term_conflict", "terms": differing_terms})
    return conflicts


def _degraded(structure: UlistenSegment, mode: str, fixture_text: str | None = None) -> FusedSegment:
    is_fixture = mode == "fixture"
    return FusedSegment(
        segment_id=structure.segment_id,
        media_id=structure.media_id,
        speaker=structure.speaker,
        chapter=structure.chapter,
        chapter_index=structure.chapter_index,
        reference_url=structure.reference_url,
        start_seconds=structure.start_seconds,
        end_seconds=structure.end_seconds,
        text=fixture_text if is_fixture and fixture_text is not None else structure.text_raw,
        text_ulisten_raw=structure.text_raw,
        text_usetranscribe_raw=None,
        structure_source="ulisten_manual_browser_copy",
        text_source="spacing_reconstruction_fixture" if is_fixture else "ulisten_raw_degraded",
        alignment_method="fixture_passthrough" if is_fixture else "single_source_degraded",
        alignment_confidence=None,
        alignment_components=None,
        needs_review=True,
        review_reasons=["fixture_text_is_not_production"] if is_fixture else ["secondary_source_missing"],
        conflicts=[],
        youtube_url=structure.youtube_url,
        fusion_mode=mode,
        matched_secondary_segment_ids=None,
    )


def _diagnose_secondary_usage(fused: list[FusedSegment], text_segments: list[UseTranscribeSegment]) -> tuple[list[FusedSegment], FusionDiagnostics]:
    usage: dict[str, list[int]] = defaultdict(list)
    for index, segment in enumerate(fused):
        for secondary_id in segment.matched_secondary_segment_ids or []:
            usage[secondary_id].append(index)

    reused_across_speakers = {
        secondary_id
        for secondary_id, indexes in usage.items()
        if len({fused[index].speaker for index in indexes}) > 1
    }
    if reused_across_speakers:
        reviewed: list[FusedSegment] = []
        for segment in fused:
            if reused_across_speakers.intersection(segment.matched_secondary_segment_ids or []):
                reasons = list(dict.fromkeys(segment.review_reasons + ["secondary_segment_reused_across_speakers"]))
                segment = replace(segment, needs_review=True, review_reasons=reasons)
            reviewed.append(segment)
        fused = reviewed

    cross_speaker_boundary_count = 0
    adjacent_duplicate_count = 0
    adjacent_pair_count = max(0, len(fused) - 1)
    for left, right in zip(fused, fused[1:]):
        shared_secondary = bool(set(left.matched_secondary_segment_ids or []).intersection(right.matched_secondary_segment_ids or []))
        if left.speaker != right.speaker and shared_secondary:
            cross_speaker_boundary_count += 1
        normalized_left = normalize_for_similarity(left.text)
        normalized_right = normalize_for_similarity(right.text)
        if normalized_left and normalized_left == normalized_right:
            adjacent_duplicate_count += 1

    consumed = set(usage)
    all_secondary = {segment.segment_id for segment in text_segments}
    diagnostics = FusionDiagnostics(
        secondary_segment_reuse_count=len(reused_across_speakers),
        cross_speaker_boundary_count=cross_speaker_boundary_count,
        adjacent_text_duplication_rate=round(adjacent_duplicate_count / adjacent_pair_count, 4) if adjacent_pair_count else 0.0,
        unconsumed_secondary_segment_count=len(all_secondary - consumed),
    )
    return fused, diagnostics


def fuse_transcripts(*, structure_segments: list[UlistenSegment], text_segments: list[UseTranscribeSegment] | None, tolerance_seconds: float = 3.0, fixture_texts: dict[str, str] | None = None) -> FusionResult:
    if fixture_texts is not None:
        return FusionResult("fixture", [_degraded(segment, "fixture", fixture_texts.get(segment.segment_id)) for segment in structure_segments])
    if not text_segments:
        return FusionResult("degraded", [_degraded(segment, "degraded") for segment in structure_segments])

    fused: list[FusedSegment] = []
    for structure in structure_segments:
        matches = _overlapping_segments(structure, text_segments, tolerance_seconds)
        candidate_text = " ".join(segment.text.strip() for segment in matches if segment.text.strip()).strip()
        text_similarity = normalized_text_similarity(structure.text_raw, candidate_text) if matches else 0.0
        overlap = time_overlap_score(structure, matches) if matches else 0.0
        chapter = _chapter_consistency(structure, matches) if matches else 0.0
        confidence = round(0.55 * text_similarity + 0.35 * overlap + 0.10 * chapter, 4)
        conflicts = detect_conflicts(structure, candidate_text) if candidate_text else []
        reasons: list[str] = []
        if not matches:
            reasons.append("no_time_match")
        elif confidence < 0.65:
            reasons.append("alignment_below_0.65")
        elif confidence < 0.85:
            reasons.append("alignment_between_0.65_and_0.85")
        if not candidate_text:
            reasons.append("secondary_text_empty")
        reasons.extend(conflict["type"] for conflict in conflicts)
        accept_text = confidence >= 0.65 and bool(candidate_text)
        fused.append(FusedSegment(
            segment_id=structure.segment_id,
            media_id=structure.media_id,
            speaker=structure.speaker,
            chapter=structure.chapter,
            chapter_index=structure.chapter_index,
            reference_url=structure.reference_url,
            start_seconds=structure.start_seconds,
            end_seconds=structure.end_seconds,
            text=candidate_text if accept_text else structure.text_raw,
            text_ulisten_raw=structure.text_raw,
            text_usetranscribe_raw=candidate_text or None,
            structure_source="ulisten_manual_browser_copy",
            text_source="usetranscribe_manual_export" if accept_text else "ulisten_raw_review_fallback",
            alignment_method="timestamp_plus_normalized_text",
            alignment_confidence=confidence,
            alignment_components={
                "normalized_text_similarity": round(text_similarity, 4),
                "time_overlap_score": round(overlap, 4),
                "chapter_consistency": round(chapter, 4),
            },
            needs_review=bool(reasons),
            review_reasons=list(dict.fromkeys(reasons)),
            conflicts=conflicts,
            youtube_url=structure.youtube_url,
            fusion_mode="dual_source",
            matched_secondary_segment_ids=[segment.segment_id for segment in matches],
        ))
    fused, diagnostics = _diagnose_secondary_usage(fused, text_segments)
    return FusionResult("dual_source", fused, diagnostics)


def fused_as_dicts(result: FusionResult) -> list[dict[str, object]]:
    return [segment.as_dict() for segment in result.segments]

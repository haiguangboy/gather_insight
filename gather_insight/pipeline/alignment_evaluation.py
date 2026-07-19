from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class AlignmentEvaluation:
    alignment_precision: float
    alignment_recall: float
    alignment_f1: float
    character_overlap_precision: float
    character_overlap_recall: float
    character_overlap_f1: float
    wrong_speaker_assignment_count: int
    speaker_boundary_accuracy: float | None
    fallback_accuracy: float | None
    evaluated_segment_count: int

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def _prf(predicted: set[Any], gold: set[Any]) -> tuple[float, float, float]:
    overlap = len(predicted & gold)
    precision = overlap / len(predicted) if predicted else (1.0 if not gold else 0.0)
    recall = overlap / len(gold) if gold else (1.0 if not predicted else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return round(precision, 6), round(recall, 6), round(f1, 6)


def _range_points(ranges: Iterable[Iterable[int]]) -> set[int]:
    output: set[int] = set()
    for value in ranges:
        start, end = list(value)
        output.update(range(int(start), int(end)))
    return output


def evaluate_alignment(records: list[dict[str, object]], golden: list[dict[str, object]]) -> AlignmentEvaluation:
    by_id = {str(record["segment_id"]): record for record in records}
    predicted_pairs: set[tuple[str, str]] = set()
    gold_pairs: set[tuple[str, str]] = set()
    predicted_chars: set[tuple[str, int]] = set()
    gold_chars: set[tuple[str, int]] = set()
    wrong_speaker = 0
    boundary_results: list[bool] = []
    fallback_results: list[bool] = []
    for item in golden:
        segment_id = str(item["segment_id"])
        record = by_id.get(segment_id, {})
        predicted_units = {str(value) for value in record.get("semantic_unit_ids", [])}
        gold_units = {str(value) for value in item.get("semantic_unit_ids", [])}
        predicted_pairs.update((segment_id, value) for value in predicted_units)
        gold_pairs.update((segment_id, value) for value in gold_units)
        predicted_ranges = []
        if record.get("secondary_char_start") is not None and record.get("secondary_char_end") is not None:
            predicted_ranges.append([int(record["secondary_char_start"]), int(record["secondary_char_end"])])
        for point in _range_points(predicted_ranges):
            predicted_chars.add((segment_id, point))
        for point in _range_points(item.get("secondary_char_ranges", [])):
            gold_chars.add((segment_id, point))
        if gold_units and predicted_units and not (gold_units & predicted_units):
            wrong_speaker += 1
        if item.get("speaker_boundary"):
            boundary_results.append(predicted_units == gold_units)
        if "should_fallback" in item:
            predicted_fallback = record.get("text_source") == "ulisten_raw_review_fallback"
            fallback_results.append(predicted_fallback == bool(item["should_fallback"]))
    ap, ar, af = _prf(predicted_pairs, gold_pairs)
    cp, cr, cf = _prf(predicted_chars, gold_chars)
    return AlignmentEvaluation(
        alignment_precision=ap,
        alignment_recall=ar,
        alignment_f1=af,
        character_overlap_precision=cp,
        character_overlap_recall=cr,
        character_overlap_f1=cf,
        wrong_speaker_assignment_count=wrong_speaker,
        speaker_boundary_accuracy=round(sum(boundary_results) / len(boundary_results), 6) if boundary_results else None,
        fallback_accuracy=round(sum(fallback_results) / len(fallback_results), 6) if fallback_results else None,
        evaluated_segment_count=len(golden),
    )

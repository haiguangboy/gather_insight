"""Vecalign/SentAlign-style monotonic transcript alignment.

This module deliberately uses the established document-position dynamic
programming formulation.  It is not a beam search and it does not generate
transcript text.  Embeddings are supplied by the existing SemanticScorer;
target text is always projected from immutable semantic-unit spans.
"""

from __future__ import annotations

import math
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Sequence

from gather_insight.adapters.ulisten_parser import UlistenSegment

from .alignment_text_builder import ALIGNMENT_TEXT_VERSION, build_alignment_text
from .semantic_scorer import SemanticScorer, build_scorer, cosine
from .semantic_unit_segmenter import SEMANTIC_UNIT_VERSION, SemanticUnit, segment_secondary_text
from .transcript_fuser import detect_conflicts, normalize_for_similarity


ALIGNMENT_ALGORITHM_VERSION = "vecalign_dp_v1"


@dataclass(frozen=True)
class VecalignConfig:
    algorithm: str = "vecalign"
    score_mode: str = "margin"
    max_alignment_size: int = 7
    max_source_concatenations: int = 3
    max_target_concatenations: int = 6
    time_padding_seconds: float = 30.0
    margin_k: int = 4
    gap_percentile: float = 0.20
    accept_threshold: float = 0.65
    auto_threshold: float = 0.85
    semantic_unit_max_chars: int = 260
    sentalign_score_cutoff: float = 0.40
    sentalign_free_concatenations: int = 2

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "VecalignConfig":
        value = value or {}
        nested = value.get("vecalign") if isinstance(value.get("vecalign"), dict) else {}
        merged = {**value, **nested}
        algorithm = str(merged.get("alignment_algorithm", merged.get("algorithm", "vecalign")))
        return cls(
            algorithm=algorithm,
            score_mode=str(merged.get("score_mode", merged.get("vecalign_score_mode", "margin"))),
            max_alignment_size=max(2, int(merged.get("max_alignment_size", 7))),
            max_source_concatenations=max(1, int(merged.get("max_source_concatenations", 3))),
            max_target_concatenations=max(1, int(merged.get("max_target_concatenations", 6))),
            time_padding_seconds=float(merged.get("time_padding_seconds", 30.0)),
            margin_k=max(1, int(merged.get("margin_k", 4))),
            gap_percentile=min(1.0, max(0.0, float(merged.get("gap_percentile", 0.20)))),
            accept_threshold=float(merged.get("accept_threshold", 0.65)),
            auto_threshold=float(merged.get("auto_threshold", 0.85)),
            semantic_unit_max_chars=max(80, int(merged.get("max_unit_chars", merged.get("semantic_unit_max_chars", 260)))),
            sentalign_score_cutoff=float(merged.get("sentalign_score_cutoff", 0.40)),
            sentalign_free_concatenations=max(0, int(merged.get("sentalign_free_concatenations", 2))),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "alignment_algorithm": self.algorithm,
            "score_mode": self.score_mode,
            "max_alignment_size": self.max_alignment_size,
            "max_source_concatenations": self.max_source_concatenations,
            "max_target_concatenations": self.max_target_concatenations,
            "time_padding_seconds": self.time_padding_seconds,
            "margin_k": self.margin_k,
            "gap_percentile": self.gap_percentile,
            "accept_threshold": self.accept_threshold,
            "auto_threshold": self.auto_threshold,
            "semantic_unit_max_chars": self.semantic_unit_max_chars,
            "sentalign_score_cutoff": self.sentalign_score_cutoff,
            "sentalign_free_concatenations": self.sentalign_free_concatenations,
        }


@dataclass(frozen=True)
class VecalignPathStep:
    source_start: int
    source_end: int
    target_start: int
    target_end: int
    score: float
    raw_cosine: float | None
    margin_score: float | None

    @property
    def source_count(self) -> int:
        return self.source_end - self.source_start

    @property
    def target_count(self) -> int:
        return self.target_end - self.target_start

    def as_dict(self) -> dict[str, object]:
        return {
            "source_indices": list(range(self.source_start, self.source_end)),
            "target_indices": list(range(self.target_start, self.target_end)),
            "source_count": self.source_count,
            "target_count": self.target_count,
            "operation": f"{self.source_count}:{self.target_count}",
            "score": self.score,
            "raw_cosine": self.raw_cosine,
            "margin_score": self.margin_score,
        }


@dataclass(frozen=True)
class VecalignResult:
    records: list[dict[str, object]]
    units: list[SemanticUnit]
    unallocated_units: list[SemanticUnit]
    diagnostics: dict[str, object]
    trace: list[dict[str, object]]
    scorer_metadata: dict[str, object]
    config: VecalignConfig
    elapsed_seconds: float


def _vector_mean(vectors: Sequence[list[float]]) -> list[float]:
    if not vectors:
        return []
    out = [0.0] * len(vectors[0])
    for vector in vectors:
        for index, value in enumerate(vector):
            out[index] += value
    scale = 1.0 / len(vectors)
    out = [value * scale for value in out]
    norm = math.sqrt(sum(value * value for value in out)) or 1.0
    return [value / norm for value in out]


def _prefix_vectors(vectors: Sequence[list[float]]) -> list[list[float]]:
    if not vectors:
        return [[]]
    output = [[0.0] * len(vectors[0])]
    for vector in vectors:
        output.append([left + right for left, right in zip(output[-1], vector)])
    return output


def _mean_from_prefix(prefix: list[list[float]], start: int, end: int) -> list[float]:
    count = max(1, end - start)
    values = [(right - left) / count for left, right in zip(prefix[start], prefix[end])]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def _normalise_margin(value: float, lower: float, upper: float) -> float:
    if upper <= lower + 1e-9:
        return 0.5
    return min(1.0, max(0.0, (value - lower) / (upper - lower)))


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 1.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return float(ordered[index])


def _legal_operations(config: VecalignConfig) -> list[tuple[int, int]]:
    operations = [(1, 1), (1, 0), (0, 1)]
    for source_count in range(1, config.max_source_concatenations + 1):
        for target_count in range(1, config.max_target_concatenations + 1):
            if source_count == target_count == 1:
                continue
            if source_count + target_count <= config.max_alignment_size:
                operations.append((source_count, target_count))
    return operations


def _time_legal(source_start: float, source_end: float, selected: Sequence[SemanticUnit], padding: float) -> bool:
    if not selected:
        return False
    target_start = selected[0].approx_start_seconds
    target_end = selected[-1].approx_end_seconds
    return target_start >= source_start - padding and target_end <= source_end + padding


def _text_for_units(units: Sequence[SemanticUnit]) -> str:
    return " ".join(unit.text.strip() for unit in units if unit.text.strip()).strip()


def _block_conflict_types(structure: UlistenSegment, text: str) -> list[dict[str, object]]:
    return detect_conflicts(structure, text)


def _build_record(structure: UlistenSegment, units: Sequence[SemanticUnit], step: VecalignPathStep | None, *, text_source: str, source_is_fixture: bool, algorithm: str, accept_threshold: float, auto_threshold: float, fallback_reason: str | None, extra_reasons: list[str]) -> dict[str, object]:
    candidate_units = list(units[step.target_start:step.target_end]) if step and step.target_count else []
    candidate_text = _text_for_units(candidate_units)
    confidence_value = min(step.score, max(0.0, step.raw_cosine if step.raw_cosine is not None else step.score)) if step else None
    usable = bool(step and step.target_count and step.source_count == 1 and candidate_text and confidence_value is not None and confidence_value >= accept_threshold)
    selected = candidate_units if usable else []
    reasons = list(dict.fromkeys(extra_reasons))
    effective_fallback = fallback_reason
    if not usable:
        effective_fallback = fallback_reason or ("alignment_score_below_accept_threshold" if step and step.target_count else "no_reliable_monotonic_candidate")
        reasons.append(effective_fallback)
        text = structure.text_raw
        final_source = "ulisten_raw_review_fallback"
        confidence = None
        conflicts: list[dict[str, object]] = []
    else:
        text = candidate_text
        final_source = text_source
        confidence = round(float(confidence_value), 6)
        conflicts = _block_conflict_types(structure, text)
        reasons.extend(str(item.get("type")) for item in conflicts)
        if confidence < auto_threshold:
            reasons.append("alignment_between_0.65_and_0.85")
    details = {
        "allocation_method": f"{algorithm}_monotonic_dp",
        "semantic_unit_ids": [unit.unit_id for unit in selected],
        "secondary_segment_ids": list(dict.fromkeys(unit.secondary_segment_id for unit in selected)),
        "secondary_char_start": selected[0].original_char_start if selected else None,
        "secondary_char_end": selected[-1].original_char_end if selected else None,
        "secondary_token_start": selected[0].token_start if selected else None,
        "secondary_token_end": selected[-1].token_end if selected else None,
        "raw_cosine": step.raw_cosine if step else None,
        "margin_score": step.margin_score if step else None,
        "source_text_consumed_once": usable,
        "fallback_reason": effective_fallback,
    }
    return {
        "segment_id": structure.segment_id,
        "media_id": structure.media_id,
        "speaker": structure.speaker,
        "chapter": structure.chapter,
        "chapter_index": structure.chapter_index,
        "reference_url": structure.reference_url,
        "start_seconds": structure.start_seconds,
        "end_seconds": structure.end_seconds,
        "text": text,
        "text_ulisten_raw": structure.text_raw,
        "text_usetranscribe_raw": None if text_source.startswith("official") else (candidate_text if usable else None),
        "text_official_raw": candidate_text if usable and text_source.startswith("official") else None,
        "structure_source": "ulisten_manual_browser_copy",
        "text_source": final_source,
        "source_is_fixture": source_is_fixture,
        "alignment_method": f"{algorithm}_monotonic_dp",
        "alignment_confidence": confidence,
        "alignment_components": {"raw_cosine": step.raw_cosine, "margin_score": step.margin_score} if step else None,
        "needs_review": bool(reasons),
        "review_reasons": reasons,
        "conflicts": conflicts,
        "youtube_url": structure.youtube_url,
        "fusion_mode": "official_dual" if text_source.startswith("official") else "dual_source",
        "speaker_needs_review": False,
        "speaker_status": "source_provided",
        "speaker_review_reasons": [],
        "text_status": "readable" if usable else "raw_structure_only",
        "structure_status": "source_provided",
        **details,
    }


def align_vecalign(*, structure_segments: list[UlistenSegment], secondary_segments: Sequence[object], config_value: dict[str, Any], cache_root: Any = None, scorer: SemanticScorer | None = None, text_source: str = "usetranscribe_manual_export", source_is_fixture: bool = False) -> VecalignResult:
    started = time.monotonic()
    config = VecalignConfig.from_dict(config_value)
    if config.algorithm not in {"vecalign", "sentalign"}:
        raise ValueError(f"unsupported document alignment algorithm: {config.algorithm}")
    if config.score_mode not in {"raw", "raw_cosine", "cosine", "margin"}:
        raise ValueError(f"unsupported document alignment score mode: {config.score_mode}")
    if not structure_segments:
        raise ValueError("Vecalign requires at least one structure segment")
    units = segment_secondary_text(secondary_segments, max_unit_chars=config.semantic_unit_max_chars)
    if not units:
        raise ValueError("Vecalign requires at least one secondary semantic unit")
    alignment_texts = [build_alignment_text(segment).text for segment in structure_segments]
    embedding_config = config_value.get("embedding", {}) if isinstance(config_value, dict) else {}
    scorer = scorer or build_scorer(
        backend=str(config_value.get("mode", "local_semantic")),
        embedding=embedding_config,
        semantic_unit_version=SEMANTIC_UNIT_VERSION,
        alignment_text_version=ALIGNMENT_TEXT_VERSION,
        cache_root=cache_root,
    )
    source_vectors = scorer.embed(alignment_texts)
    target_vectors = scorer.embed([unit.text for unit in units])
    source_prefix = _prefix_vectors(source_vectors)
    target_prefix = _prefix_vectors(target_vectors)
    source_blocks = {(start, count): _mean_from_prefix(source_prefix, start, start + count) for start in range(len(structure_segments)) for count in range(1, min(config.max_source_concatenations, len(structure_segments) - start) + 1)}
    target_blocks = {(start, count): _mean_from_prefix(target_prefix, start, start + count) for start in range(len(units)) for count in range(1, min(config.max_target_concatenations, len(units) - start) + 1)}

    base_matrix: list[list[float]] = []
    for left in source_vectors:
        base_matrix.append([round(cosine(left, right), 6) for right in target_vectors])
    row_baseline: list[float] = []
    col_baseline: list[float] = []
    k = config.margin_k
    for row in base_matrix:
        row_baseline.append(sum(sorted(row, reverse=True)[:k]) / max(1, min(k, len(row))))
    for col in range(len(units)):
        values = [base_matrix[row][col] for row in range(len(structure_segments))]
        col_baseline.append(sum(sorted(values, reverse=True)[:k]) / max(1, min(k, len(values))))
    base_margins = [base_matrix[i][j] - (row_baseline[i] + col_baseline[j]) / 2 for i in range(len(structure_segments)) for j in range(len(units))]
    margin_lower = _percentile(base_margins, 0.02)
    margin_upper = _percentile(base_margins, 0.98)

    score_cache: dict[tuple[int, int, int, int], tuple[float, float]] = {}

    def score_block(source_start: int, source_count: int, target_start: int, target_count: int) -> tuple[float, float, float]:
        key = (source_start, source_count, target_start, target_count)
        cached = score_cache.get(key)
        if cached:
            raw, margin = cached
        else:
            raw = cosine(source_blocks[(source_start, source_count)], target_blocks[(target_start, target_count)])
            margin = raw - (sum(row_baseline[source_start:source_start + source_count]) / source_count + sum(col_baseline[target_start:target_start + target_count]) / target_count) / 2
            score_cache[key] = (raw, margin)
        normalized = raw if config.score_mode in {"raw", "raw_cosine", "cosine"} else _normalise_margin(margin, margin_lower, margin_upper)
        return round(raw, 6), round(margin, 6), round(normalized, 6)

    use_raw_score = config.score_mode in {"raw", "raw_cosine", "cosine"}
    base_costs = [1.0 - (value if use_raw_score else _normalise_margin(margin, margin_lower, margin_upper)) for value, margin in zip((item for row in base_matrix for item in row), base_margins)]
    # Vecalign estimates the skip cost from random 1:1 pairs. In tiny test
    # documents an exact match can occupy the requested percentile, which is
    # not representative of random-pair sampling and would make gaps free.
    sampled_costs = [value for value in base_costs if value > 1e-9]
    gap_cost = _percentile(sampled_costs, config.gap_percentile) if sampled_costs else 1.0
    if config.algorithm == "sentalign":
        gap_cost = -config.sentalign_score_cutoff
    operations = _legal_operations(config)
    n, m = len(structure_segments), len(units)
    inf = float("inf")
    dp = [[inf] * (m + 1) for _ in range(n + 1)]
    parents: list[list[tuple[int, int, VecalignPathStep | None] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            if dp[i][j] == inf:
                continue
            for source_count, target_count in operations:
                next_i, next_j = i + source_count, j + target_count
                if next_i > n or next_j > m:
                    continue
                if source_count == 0 or target_count == 0:
                    cost = gap_cost
                    step = VecalignPathStep(i, next_i, j, next_j, 0.0, None, None)
                else:
                    selected = units[j:next_j]
                    if not _time_legal(structure_segments[i].start_seconds, structure_segments[next_i - 1].end_seconds, selected, config.time_padding_seconds):
                        continue
                    raw, margin, normalized = score_block(i, source_count, j, target_count)
                    if config.algorithm == "sentalign":
                        total_splits = source_count + target_count
                        exponent = max(1, total_splits - config.sentalign_free_concatenations + 1)
                        utility = (max(0.0, normalized) ** exponent) * total_splits
                        cost = -utility
                    else:
                        cost = (1.0 - normalized) * source_count * target_count
                    step = VecalignPathStep(i, next_i, j, next_j, round(normalized, 6), raw, margin)
                total = dp[i][j] + cost
                previous = parents[next_i][next_j]
                tie_key = (step.target_count == 0, step.source_count + step.target_count, step.target_start, step.source_start)
                previous_key = (previous[2].target_count == 0, previous[2].source_count + previous[2].target_count, previous[2].target_start, previous[2].source_start) if previous else None
                if total < dp[next_i][next_j] - 1e-9 or (abs(total - dp[next_i][next_j]) <= 1e-9 and (previous_key is None or tie_key < previous_key)):
                    dp[next_i][next_j] = total
                    parents[next_i][next_j] = (i, j, step)

    if parents[n][m] is None:
        raise ValueError("Vecalign DP found no monotonic path")
    path: list[VecalignPathStep] = []
    current = (n, m)
    while current != (0, 0):
        parent = parents[current[0]][current[1]]
        if parent is None:
            raise ValueError("Vecalign traceback encountered a missing parent")
        previous_i, previous_j, step = parent
        assert step is not None
        path.append(step)
        current = (previous_i, previous_j)
    path.reverse()
    by_source: dict[int, VecalignPathStep] = {}
    source_extra: dict[int, list[str]] = defaultdict(list)
    for step in path:
        if step.source_count == 1 and step.target_count:
            by_source[step.source_start] = step
        elif step.source_count > 1 and step.target_count:
            by_source[step.source_start] = step
            for index in range(step.source_start + 1, step.source_end):
                source_extra[index].append("multi_source_alignment_projection_review")
        elif step.source_count:
            for index in range(step.source_start, step.source_end):
                source_extra[index].append("secondary_source_gap")
    records: list[dict[str, object]] = []
    for index, structure in enumerate(structure_segments):
        step = by_source.get(index)
        fallback = None if step and step.target_count and step.source_count == 1 else ("multi_source_alignment_projection" if step and step.target_count else "secondary_source_gap")
        extras = list(source_extra.get(index, []))
        if fallback:
            extras.append("alignment_path_requires_review")
        records.append(_build_record(structure, units, step if step and step.source_start == index else None, text_source=text_source, source_is_fixture=source_is_fixture, algorithm=config.algorithm, accept_threshold=config.accept_threshold, auto_threshold=config.auto_threshold, fallback_reason=fallback, extra_reasons=extras))
    unit_index_by_id = {unit.unit_id: index for index, unit in enumerate(units)}
    allocated_indexes = {
        unit_index_by_id[str(unit_id)]
        for record in records
        for unit_id in record.get("semantic_unit_ids", [])
        if str(unit_id) in unit_index_by_id
    }
    # Speaker transitions that share a secondary *segment* remain review items,
    # while semantic-unit character ranges themselves remain disjoint.
    segment_speakers: dict[str, set[str]] = defaultdict(set)
    for index, record in enumerate(records):
        for secondary_id in record.get("secondary_segment_ids", []):
            segment_speakers[str(secondary_id)].add(str(structure_segments[index].speaker))
    reused_segments = {segment_id for segment_id, speakers in segment_speakers.items() if len(speakers) > 1}
    for record in records:
        if reused_segments.intersection(record.get("secondary_segment_ids", [])):
            record["needs_review"] = True
            record["review_reasons"] = list(dict.fromkeys([*record.get("review_reasons", []), "secondary_segment_reused_across_speakers"]))
    unallocated = [unit for index, unit in enumerate(units) if index not in allocated_indexes]
    transitions = Counter((step.source_count, step.target_count) for step in path)
    speaker_boundary_count = 0
    for left, right in zip(records, records[1:]):
        if left.get("speaker") == right.get("speaker"):
            continue
        left_ids = set(left.get("secondary_segment_ids", []))
        right_ids = set(right.get("secondary_segment_ids", []))
        if left_ids.intersection(right_ids):
            speaker_boundary_count += 1
            left["needs_review"] = True
            right["needs_review"] = True
            left["review_reasons"] = list(dict.fromkeys([*left.get("review_reasons", []), "speaker_boundary_secondary_segment_overlap"]))
            right["review_reasons"] = list(dict.fromkeys([*right.get("review_reasons", []), "speaker_boundary_secondary_segment_overlap"]))
    owners_by_unit: dict[int, set[str]] = defaultdict(set)
    allocation_counts: Counter[int] = Counter()
    for record in records:
        for unit_id in record.get("semantic_unit_ids", []):
            unit_index = unit_index_by_id.get(str(unit_id))
            if unit_index is not None:
                owners_by_unit[unit_index].add(str(record.get("speaker")))
                allocation_counts[unit_index] += 1
    total_chars = sum(unit.original_char_end - unit.original_char_start for unit in units)
    allocated_chars = sum(unit.original_char_end - unit.original_char_start for index, unit in enumerate(units) if index in allocated_indexes)
    reused_chars = sum((count - 1) * (units[index].original_char_end - units[index].original_char_start) for index, count in allocation_counts.items() if count > 1)
    cross_speaker_chars = sum(units[index].original_char_end - units[index].original_char_start for index, speakers in owners_by_unit.items() if len(speakers) > 1)
    monotonic_violations = 0
    previous_source_end = previous_target_end = 0
    for step in path:
        if step.source_start < previous_source_end or step.target_start < previous_target_end:
            monotonic_violations += 1
        previous_source_end = step.source_end
        previous_target_end = step.target_end
    readable = [str(record["text"]) for record in records if record.get("text_source") != "ulisten_raw_review_fallback"]
    exact_duplicates = partial_duplicates = 0
    for left, right in zip(readable, readable[1:]):
        similarity = SequenceMatcher(None, normalize_for_similarity(left), normalize_for_similarity(right), autojunk=False).ratio()
        if similarity >= 0.999:
            exact_duplicates += 1
        elif similarity >= 0.35:
            partial_duplicates += 1
    diagnostics: dict[str, object] = {
        "alignment_algorithm": config.algorithm,
        "alignment_algorithm_version": "sentalign_full_dp_v1" if config.algorithm == "sentalign" else ALIGNMENT_ALGORITHM_VERSION,
        "alignment_score_mode": config.score_mode,
        "alignment_operations": {f"{source}:{target}": count for (source, target), count in sorted(transitions.items())},
        "one_to_one_count": transitions.get((1, 1), 0),
        "one_to_many_count": sum(count for (source, target), count in transitions.items() if source == 1 and target > 1),
        "many_to_one_count": sum(count for (source, target), count in transitions.items() if source > 1 and target == 1),
        "gap_count": sum(count for (source, target), count in transitions.items() if source == 0 or target == 0),
        "path_length": len(path),
        "semantic_unit_count": len(units),
        "allocated_semantic_unit_count": len(allocated_indexes),
        "unallocated_semantic_unit_count": len(unallocated),
        "secondary_character_consumption_rate": round(allocated_chars / max(1, total_chars), 6),
        "secondary_character_reuse_rate": round(reused_chars / max(1, total_chars), 8),
        "unallocated_secondary_character_count": total_chars - allocated_chars,
        "monotonic_violation_count": monotonic_violations,
        "cross_speaker_shared_character_count": cross_speaker_chars,
        "cross_speaker_boundary_count": speaker_boundary_count,
        "secondary_segment_reuse_count": len(reused_segments),
        "unconsumed_secondary_segment_count": len({unit.secondary_segment_id for unit in units} - {unit.secondary_segment_id for index, unit in enumerate(units) if index in allocated_indexes}),
        "adjacent_text_duplication_rate": round(exact_duplicates / max(1, len(readable) - 1), 6),
        "partial_adjacent_duplication_rate": round(partial_duplicates / max(1, len(readable) - 1), 6),
        "boundary_low_confidence_count": sum("alignment_between_0.65_and_0.85" in record.get("review_reasons", []) for record in records),
        "mean_semantic_similarity": round(statistics.mean([step.raw_cosine or 0.0 for step in path if step.raw_cosine is not None]), 6) if any(step.raw_cosine is not None for step in path) else None,
        "median_semantic_similarity": round(statistics.median([step.raw_cosine or 0.0 for step in path if step.raw_cosine is not None]), 6) if any(step.raw_cosine is not None for step in path) else None,
        "ambiguous_candidate_count": 0,
        "fallback_count": sum(record.get("text_source") == "ulisten_raw_review_fallback" for record in records),
        "fallback_reason_distribution": dict(Counter(str(record["fallback_reason"]) for record in records if record.get("fallback_reason"))),
        "semantic_backend": scorer.provider,
        "semantic_model": scorer.model,
        "semantic_alignment_degraded": scorer.degraded,
        "semantic_alignment_status": "degraded" if scorer.degraded else "active",
        "gap_cost": round(gap_cost, 6),
        "score_normalization": "raw_cosine" if config.score_mode.startswith("raw") else "bidirectional_margin_normalized",
        **scorer.stats.as_dict(),
    }
    trace = [{"algorithm": config.algorithm, "score_mode": config.score_mode, "source_text_count": len(structure_segments), "target_unit_count": len(units), "gap_cost": round(gap_cost, 6), "path": [step.as_dict() for step in path]}]
    return VecalignResult(records=records, units=units, unallocated_units=unallocated, diagnostics=diagnostics, trace=trace, scorer_metadata=scorer.metadata(), config=config, elapsed_seconds=round(time.monotonic() - started, 3))

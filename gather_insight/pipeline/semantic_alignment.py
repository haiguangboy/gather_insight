from __future__ import annotations

import json
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Sequence

from gather_insight.adapters.ulisten_parser import UlistenSegment

from .alignment_text_builder import ALIGNMENT_TEXT_VERSION, AlignmentText, build_alignment_text, protected_terms
from .semantic_scorer import DeepSeekJudge, MockJudge, SemanticBackendUnavailable, SemanticScorer, build_scorer, cosine, l2_normalize
from .semantic_unit_segmenter import SEMANTIC_UNIT_VERSION, SemanticUnit, canonical_secondary_text, segment_secondary_text
from .transcript_fuser import detect_conflicts, normalize_for_similarity


_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_.%-]*")
_NUMBER = re.compile(r"\d+(?:\.\d+)?(?:%|x)?", re.IGNORECASE)
_MODEL = re.compile(r"(?:GPT|Llama|DeepSeek|Claude|Gemini|BGE|MPC|SSD|H|A|B|o)\s*-?\s*\d[0-9A-Za-z.\-]*", re.IGNORECASE)
_NEGATION = re.compile(r"\b(?:not|no|never|cannot|can't|won't|without)\b", re.IGNORECASE)
_COMMON_SHORT = {"okay", "ok", "right", "yeah", "thank you", "thanks", "welcome", "all right"}


@dataclass(frozen=True)
class AlignmentWeights:
    semantic_similarity: float = 0.45
    lexical_anchor_score: float = 0.20
    entity_consistency_score: float = 0.15
    time_prior_score: float = 0.10
    sequence_context_score: float = 0.10

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "AlignmentWeights":
        value = value or {}
        return cls(**{name: float(value.get(name, getattr(cls(), name))) for name in cls.__dataclass_fields__})

    def as_dict(self) -> dict[str, float]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class SemanticAlignmentConfig:
    mode: str = "lexical_only"
    time_padding_seconds: float = 30.0
    max_units_per_match: int = 6
    candidate_top_k: int = 12
    beam_width: int = 24
    max_secondary_skip_units: int = 8
    accept_threshold: float = 0.65
    auto_threshold: float = 0.85
    ambiguity_margin_threshold: float = 0.08
    max_judge_calls: int = 24
    max_unit_chars: int = 260
    weights: AlignmentWeights = field(default_factory=AlignmentWeights)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "SemanticAlignmentConfig":
        value = value or {}
        return cls(
            mode=str(value.get("mode", "lexical_only")),
            time_padding_seconds=float(value.get("time_padding_seconds", 30.0)),
            max_units_per_match=int(value.get("max_units_per_match", 6)),
            candidate_top_k=int(value.get("candidate_top_k", 12)),
            beam_width=int(value.get("beam_width", 24)),
            max_secondary_skip_units=int(value.get("max_secondary_skip_units", 8)),
            accept_threshold=float(value.get("accept_threshold", 0.65)),
            auto_threshold=float(value.get("auto_threshold", 0.85)),
            ambiguity_margin_threshold=float(value.get("ambiguity_margin_threshold", 0.08)),
            max_judge_calls=int(value.get("max_judge_calls", 24)),
            max_unit_chars=int(value.get("max_unit_chars", 260)),
            weights=AlignmentWeights.from_dict(value.get("weights")),
        )

    def as_dict(self) -> dict[str, object]:
        value = self.__dict__.copy()
        value["weights"] = self.weights.as_dict()
        return value


@dataclass(frozen=True)
class AlignmentCandidate:
    candidate_id: str
    structure_index: int
    unit_start: int
    unit_end: int
    unit_ids: list[str]
    text: str
    semantic_similarity: float
    lexical_anchor_score: float
    entity_consistency_score: float
    time_prior_score: float
    sequence_context_score: float
    penalties: dict[str, float]
    alignment_score: float
    conflicts: list[dict[str, object]]
    boundary_start_confidence: float
    boundary_end_confidence: float

    def compact_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "unit_ids": self.unit_ids,
            "text": self.text[:600],
            "alignment_score": self.alignment_score,
            "semantic_similarity": self.semantic_similarity,
            "lexical_anchor_score": self.lexical_anchor_score,
            "entity_consistency_score": self.entity_consistency_score,
            "time_prior_score": self.time_prior_score,
            "conflicts": [item.get("type") for item in self.conflicts],
        }


@dataclass(frozen=True)
class SemanticAllocation:
    structure: UlistenSegment
    alignment_text: AlignmentText
    candidate: AlignmentCandidate | None
    alternatives: list[AlignmentCandidate]
    fallback_reason: str | None = None
    judge_decision: dict[str, Any] | None = None
    extra_review_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SemanticAlignmentResult:
    allocations: list[SemanticAllocation]
    units: list[SemanticUnit]
    unallocated_units: list[SemanticUnit]
    diagnostics: dict[str, object]
    trace: list[dict[str, object]]
    scorer_metadata: dict[str, object]
    judge_metadata: dict[str, object]
    config: SemanticAlignmentConfig
    elapsed_seconds: float


@dataclass(frozen=True)
class _BeamState:
    next_unit: int
    score: float
    allocations: tuple[tuple[AlignmentCandidate | None, tuple[AlignmentCandidate, ...]], ...]


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in _WORD.finditer(text)]


def _ngrams(text: str, n: int = 8) -> set[str]:
    normalized = normalize_for_similarity(text)
    return {normalized[index:index + n] for index in range(max(0, len(normalized) - n + 1))}


def lexical_anchor_score(left: str, right: str) -> float:
    compact_left = normalize_for_similarity(left)
    compact_right = normalize_for_similarity(right)
    if not compact_left or not compact_right:
        return 0.0
    sequence = SequenceMatcher(None, compact_left, compact_right, autojunk=False)
    ratio = sequence.ratio()
    longest = sequence.find_longest_match().size / max(1, min(len(compact_left), len(compact_right)))
    grams_left, grams_right = _ngrams(left), _ngrams(right)
    gram_score = len(grams_left & grams_right) / max(1, min(len(grams_left), len(grams_right)))
    return round(0.45 * ratio + 0.30 * longest + 0.25 * gram_score, 6)


def _set_score(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.35
    return len(left & right) / len(left | right)


def entity_consistency_score(structure: UlistenSegment, candidate_text: str) -> float:
    raw = structure.text_raw
    categories = [
        ({match.group(0).lower() for match in _NUMBER.finditer(raw)}, {match.group(0).lower() for match in _NUMBER.finditer(candidate_text)}),
        ({normalize_for_similarity(match.group(0)) for match in _MODEL.finditer(raw)}, {normalize_for_similarity(match.group(0)) for match in _MODEL.finditer(candidate_text)}),
        ({match.group(0).lower() for match in _NEGATION.finditer(raw)}, {match.group(0).lower() for match in _NEGATION.finditer(candidate_text)}),
    ]
    compact_candidate = normalize_for_similarity(candidate_text)
    protected = {normalize_for_similarity(term) for term in protected_terms(structure) if len(normalize_for_similarity(term)) >= 3}
    protected_hits = {term for term in protected if term in compact_candidate}
    categories.append((protected, protected_hits))
    return round(sum(_set_score(left, right) for left, right in categories) / len(categories), 6)


def time_prior_score(structure: UlistenSegment, units: Sequence[SemanticUnit]) -> float:
    start, end = units[0].approx_start_seconds, units[-1].approx_end_seconds
    overlap = max(0.0, min(structure.end_seconds, end) - max(structure.start_seconds, start))
    structure_duration = max(1.0, structure.end_seconds - structure.start_seconds)
    overlap_score = min(1.0, overlap / structure_duration)
    structure_mid = (structure.start_seconds + structure.end_seconds) / 2
    candidate_mid = (start + end) / 2
    proximity = max(0.0, 1.0 - abs(structure_mid - candidate_mid) / max(30.0, structure_duration * 2))
    return round(0.55 * overlap_score + 0.45 * proximity, 6)


def _penalties(structure: UlistenSegment, text: str, units: Sequence[SemanticUnit], padding: float) -> dict[str, float]:
    penalties: dict[str, float] = {}
    length_ratio = (len(normalize_for_similarity(text)) + 1) / (len(normalize_for_similarity(structure.text_raw)) + 1)
    length_penalty = min(0.28, abs(math.log(length_ratio)) * 0.08)
    if length_penalty:
        penalties["length_mismatch"] = round(length_penalty, 6)
    time_distance = max(0.0, structure.start_seconds - units[-1].approx_end_seconds, units[0].approx_start_seconds - structure.end_seconds)
    if time_distance > padding:
        penalties["outside_time_window"] = round(min(0.3, time_distance / max(1.0, padding) * 0.1), 6)
    tokens = _tokens(text)
    normalized = " ".join(tokens)
    if len(tokens) <= 3 or normalized in _COMMON_SHORT:
        penalties["low_information_unit"] = 0.18
    return penalties


def _candidate_spans(structure_index: int, structure: UlistenSegment, units: list[SemanticUnit], config: SemanticAlignmentConfig) -> list[tuple[int, int, str]]:
    indexes = [index for index, unit in enumerate(units) if unit.approx_end_seconds >= structure.start_seconds - config.time_padding_seconds and unit.approx_start_seconds <= structure.end_seconds + config.time_padding_seconds]
    spans: list[tuple[int, int, str]] = []
    for start in indexes:
        for count in range(1, config.max_units_per_match + 1):
            end = start + count
            if end > len(units):
                break
            selected = units[start:end]
            if selected[-1].approx_start_seconds > structure.end_seconds + config.time_padding_seconds:
                break
            text = " ".join(unit.text.strip() for unit in selected if unit.text.strip()).strip()
            if text:
                spans.append((start, end, text))
    preliminary = sorted(spans, key=lambda item: (-(0.65 * lexical_anchor_score(structure.text_raw, item[2]) + 0.35 * time_prior_score(structure, units[item[0]:item[1]])), item[0], item[1]))
    return preliminary[: config.candidate_top_k]


def _build_candidates(structures: list[UlistenSegment], alignment_texts: list[AlignmentText], units: list[SemanticUnit], scorer: SemanticScorer, config: SemanticAlignmentConfig) -> list[list[AlignmentCandidate]]:
    raw_options: list[list[tuple[int, int, str]]] = [_candidate_spans(index, structure, units, config) for index, structure in enumerate(structures)]
    score_map: dict[tuple[int, int], float] = {}
    if scorer.provider == "degraded_lexical":
        pairs: list[tuple[str, str]] = []
        locations: list[tuple[int, int]] = []
        for structure_index, options in enumerate(raw_options):
            for option_index, (_start, _end, text) in enumerate(options):
                pairs.append((alignment_texts[structure_index].text, text))
                locations.append((structure_index, option_index))
        score_map = {location: score for location, score in zip(locations, scorer.score_pairs(pairs))}
    else:
        structure_vectors = scorer.embed([item.text for item in alignment_texts])
        unit_vectors = scorer.embed([unit.text for unit in units])
        for structure_index, options in enumerate(raw_options):
            for option_index, (start, end, _text) in enumerate(options):
                selected_vectors = unit_vectors[start:end]
                selected_units = units[start:end]
                pooled = [0.0] * len(selected_vectors[0])
                total_weight = 0.0
                for vector, unit in zip(selected_vectors, selected_units):
                    weight = max(1.0, len(unit.text))
                    total_weight += weight
                    for position, value in enumerate(vector):
                        pooled[position] += value * weight
                pooled = l2_normalize([value / total_weight for value in pooled])
                score_map[(structure_index, option_index)] = round(max(0.0, cosine(structure_vectors[structure_index], pooled)), 6)
    output: list[list[AlignmentCandidate]] = []
    weights = config.weights
    for structure_index, (structure, options) in enumerate(zip(structures, raw_options)):
        candidates: list[AlignmentCandidate] = []
        for option_index, (start, end, text) in enumerate(options):
            selected = units[start:end]
            semantic = max(0.0, min(1.0, score_map.get((structure_index, option_index), 0.0)))
            lexical = lexical_anchor_score(alignment_texts[structure_index].text, text)
            entity = entity_consistency_score(structure, text)
            time_score = time_prior_score(structure, selected)
            sequence = max(0.0, 1.0 - abs(selected[0].approx_start_seconds - structure.start_seconds) / max(60.0, config.time_padding_seconds * 3))
            penalties = _penalties(structure, text, selected, config.time_padding_seconds)
            conflicts = detect_conflicts(structure, text)
            conflict_penalty = sum({
                "numeric_conflict": 0.18,
                "model_name_conflict": 0.14,
                "negation_conflict": 0.16,
                "protected_term_conflict": 0.05,
            }.get(str(item.get("type")), 0.0) for item in conflicts)
            if conflict_penalty:
                penalties["entity_or_negation_conflict"] = round(min(0.32, conflict_penalty), 6)
            score = (
                weights.semantic_similarity * semantic
                + weights.lexical_anchor_score * lexical
                + weights.entity_consistency_score * entity
                + weights.time_prior_score * time_score
                + weights.sequence_context_score * sequence
                - sum(penalties.values())
            )
            candidates.append(AlignmentCandidate(
                candidate_id=f"s{structure_index + 1:04d}_c{option_index + 1:03d}",
                structure_index=structure_index,
                unit_start=start,
                unit_end=end,
                unit_ids=[unit.unit_id for unit in selected],
                text=text,
                semantic_similarity=round(semantic, 6),
                lexical_anchor_score=lexical,
                entity_consistency_score=entity,
                time_prior_score=time_score,
                sequence_context_score=round(sequence, 6),
                penalties=penalties,
                alignment_score=round(max(0.0, min(1.0, score)), 6),
                conflicts=conflicts,
                boundary_start_confidence=selected[0].boundary_start_confidence,
                boundary_end_confidence=selected[-1].boundary_end_confidence,
            ))
        output.append(sorted(candidates, key=lambda item: (-item.alignment_score, item.unit_start, item.unit_end)))
    return output


def _beam_align(candidate_lists: list[list[AlignmentCandidate]], config: SemanticAlignmentConfig) -> list[tuple[AlignmentCandidate | None, tuple[AlignmentCandidate, ...]]]:
    beam = [_BeamState(next_unit=0, score=0.0, allocations=())]
    for candidates in candidate_lists:
        expanded: list[_BeamState] = []
        for state in beam:
            expanded.append(_BeamState(state.next_unit, state.score - 0.22, state.allocations + ((None, ()),)))
            eligible = [candidate for candidate in candidates if candidate.unit_start >= state.next_unit and candidate.unit_start - state.next_unit <= config.max_secondary_skip_units]
            for candidate in eligible:
                skip_penalty = 0.025 * (candidate.unit_start - state.next_unit)
                match_value = candidate.alignment_score - 0.34 - skip_penalty
                alternatives = tuple(item for item in eligible[:5] if item.candidate_id != candidate.candidate_id)
                expanded.append(_BeamState(candidate.unit_end, state.score + match_value, state.allocations + ((candidate, alternatives),)))
        expanded.sort(key=lambda state: (-state.score, state.next_unit, tuple((item[0].candidate_id if item[0] else "skip") for item in state.allocations)))
        beam = expanded[: config.beam_width]
    return list(beam[0].allocations) if beam else [(None, ()) for _ in candidate_lists]


def _judge_payload(index: int, structures: list[UlistenSegment], alignment_texts: list[AlignmentText], options: list[AlignmentCandidate]) -> dict[str, Any]:
    structure = structures[index]
    context = {}
    if index:
        context["previous"] = {"speaker": structures[index - 1].speaker, "text": alignment_texts[index - 1].text[:240]}
    if index + 1 < len(structures):
        context["next"] = {"speaker": structures[index + 1].speaker, "text": alignment_texts[index + 1].text[:240]}
    return {
        "structure": {"segment_id": structure.segment_id, "speaker": structure.speaker, "chapter": structure.chapter, "start_seconds": structure.start_seconds, "end_seconds": structure.end_seconds, "alignment_text": alignment_texts[index].text[:700]},
        "context": context,
        "candidates": [{"decision": f"candidate_{number}", **candidate.compact_dict()} for number, candidate in enumerate(options, 1)],
        "instruction": "Choose the candidate whose original text belongs to this structure segment, or abstain. Do not rewrite text.",
    }


def _apply_judgments(allocations: list[SemanticAllocation], structures: list[UlistenSegment], alignment_texts: list[AlignmentText], config: SemanticAlignmentConfig, judge: DeepSeekJudge | MockJudge | None) -> list[SemanticAllocation]:
    if judge is None:
        return allocations
    result = allocations[:]
    pending: list[tuple[int, int, list[AlignmentCandidate]]] = []
    for index, allocation in enumerate(result):
        candidate = allocation.candidate
        if candidate is None:
            continue
        options = [candidate, *allocation.alternatives]
        options = sorted(options, key=lambda item: -item.alignment_score)[:5]
        margin = options[0].alignment_score - options[1].alignment_score if len(options) > 1 else 1.0
        speaker_boundary = (index and structures[index - 1].speaker != allocation.structure.speaker) or (index + 1 < len(structures) and structures[index + 1].speaker != allocation.structure.speaker)
        conflict_types = {item.get("type") for item in candidate.conflicts}
        needs_judge = margin < config.ambiguity_margin_threshold or speaker_boundary or bool(conflict_types & {"numeric_conflict", "model_name_conflict", "negation_conflict"}) or (0.65 <= candidate.semantic_similarity < 0.82 and candidate.lexical_anchor_score < 0.45)
        if needs_judge:
            priority = (100 if speaker_boundary else 0) + (50 if conflict_types else 0) + (20 if margin < config.ambiguity_margin_threshold else 0)
            pending.append((priority, index, options))
    pending.sort(key=lambda item: (-item[0], item[1]))
    for position, (_priority, index, options) in enumerate(pending):
        allocation = result[index]
        if position >= config.max_judge_calls:
            result[index] = replace(allocation, candidate=None, fallback_reason="judge_call_limit_reached", extra_review_reasons=allocation.extra_review_reasons + ["judge_call_limit_reached"])
            continue
        verdict = judge.judge(_judge_payload(index, structures, alignment_texts, options))
        if not verdict or verdict.get("decision") == "abstain":
            result[index] = replace(allocation, fallback_reason="ambiguous_candidate_unresolved", judge_decision=verdict, candidate=None, extra_review_reasons=allocation.extra_review_reasons + ["judge_abstained"])
            continue
        try:
            selected_index = int(str(verdict["decision"]).split("_", 1)[1]) - 1
            selected = options[selected_index]
        except (ValueError, IndexError, KeyError):
            result[index] = replace(allocation, fallback_reason="invalid_judge_decision", judge_decision=verdict, candidate=None, extra_review_reasons=allocation.extra_review_reasons + ["judge_invalid"])
            continue
        previous_end = result[index - 1].candidate.unit_end if index and result[index - 1].candidate else 0
        next_start = result[index + 1].candidate.unit_start if index + 1 < len(result) and result[index + 1].candidate else math.inf
        if selected.unit_start < previous_end or selected.unit_end > next_start:
            result[index] = replace(allocation, fallback_reason="judge_choice_breaks_monotonic_path", judge_decision=verdict, candidate=None, extra_review_reasons=allocation.extra_review_reasons + ["judge_choice_rejected"])
        else:
            result[index] = replace(allocation, candidate=selected, judge_decision=verdict)
    return result


def _common_core_candidate(structure: UlistenSegment, alignment_text: AlignmentText, group: list[AlignmentCandidate], start: int, end: int, units: list[SemanticUnit], config: SemanticAlignmentConfig) -> AlignmentCandidate:
    selected = units[start:end]
    text = " ".join(unit.text.strip() for unit in selected if unit.text.strip()).strip()
    semantic = min(item.semantic_similarity for item in group)
    lexical = lexical_anchor_score(alignment_text.text, text)
    entity = entity_consistency_score(structure, text)
    time_score = time_prior_score(structure, selected)
    sequence = max(0.0, 1.0 - abs(selected[0].approx_start_seconds - structure.start_seconds) / max(60.0, config.time_padding_seconds * 3))
    penalties = _penalties(structure, text, selected, config.time_padding_seconds)
    conflicts = detect_conflicts(structure, text)
    conflict_penalty = sum({"numeric_conflict": 0.18, "model_name_conflict": 0.14, "negation_conflict": 0.16, "protected_term_conflict": 0.05}.get(str(item.get("type")), 0.0) for item in conflicts)
    if conflict_penalty:
        penalties["entity_or_negation_conflict"] = round(min(0.32, conflict_penalty), 6)
    weights = config.weights
    score = weights.semantic_similarity * semantic + weights.lexical_anchor_score * lexical + weights.entity_consistency_score * entity + weights.time_prior_score * time_score + weights.sequence_context_score * sequence - sum(penalties.values())
    return AlignmentCandidate(
        candidate_id=group[0].candidate_id + "_common",
        structure_index=group[0].structure_index,
        unit_start=start,
        unit_end=end,
        unit_ids=[unit.unit_id for unit in selected],
        text=text,
        semantic_similarity=semantic,
        lexical_anchor_score=lexical,
        entity_consistency_score=entity,
        time_prior_score=time_score,
        sequence_context_score=round(sequence, 6),
        penalties=penalties,
        alignment_score=round(max(0.0, min(1.0, score)), 6),
        conflicts=conflicts,
        boundary_start_confidence=selected[0].boundary_start_confidence,
        boundary_end_confidence=selected[-1].boundary_end_confidence,
    )


def _finalize_allocations(structures: list[UlistenSegment], alignment_texts: list[AlignmentText], path: list[tuple[AlignmentCandidate | None, tuple[AlignmentCandidate, ...]]], units: list[SemanticUnit], config: SemanticAlignmentConfig) -> list[SemanticAllocation]:
    allocations: list[SemanticAllocation] = []
    for structure, alignment_text, (candidate, alternatives) in zip(structures, alignment_texts, path):
        fallback_reason = None
        extra_review_reasons: list[str] = []
        if candidate is None:
            fallback_reason = "no_reliable_monotonic_candidate"
        else:
            near = [item for item in alternatives if candidate.alignment_score - item.alignment_score < config.ambiguity_margin_threshold]
            if near:
                group = [candidate, *near]
                common_start = max(item.unit_start for item in group)
                common_end = min(item.unit_end for item in group)
                common_candidate = next((item for item in group if item.unit_start == common_start and item.unit_end == common_end), None)
                if common_candidate is None and common_start < common_end:
                    common_candidate = _common_core_candidate(structure, alignment_text, group, common_start, common_end, units, config)
                if common_candidate is not None and common_candidate.alignment_score >= config.accept_threshold:
                    candidate = common_candidate
                    alternatives = tuple(item for item in alternatives if item.unit_end <= common_start or item.unit_start >= common_end)
                elif config.mode in {"local_semantic", "lexical_only"}:
                    fallback_reason = "ambiguous_candidate_unresolved"
                    candidate = None
            if candidate is not None and config.mode in {"local_semantic", "lexical_only"} and any(item.get("type") in {"numeric_conflict", "model_name_conflict", "negation_conflict"} for item in candidate.conflicts):
                fallback_reason = "critical_entity_or_negation_conflict"
                candidate = None
            elif candidate is not None and config.mode in {"local_semantic", "lexical_only"} and candidate.alignment_score < config.accept_threshold:
                fallback_reason = "semantic_score_below_0.65"
                candidate = None
        allocations.append(SemanticAllocation(structure, alignment_text, candidate, list(alternatives), fallback_reason=fallback_reason, extra_review_reasons=extra_review_reasons))
    return allocations


def _speaker_boundary_review(allocations: list[SemanticAllocation], units: list[SemanticUnit]) -> list[SemanticAllocation]:
    output = allocations[:]
    for index in range(1, len(output)):
        left, right = output[index - 1], output[index]
        if left.structure.speaker == right.structure.speaker or not left.candidate or not right.candidate:
            continue
        left_unit = units[left.candidate.unit_end - 1]
        right_unit = units[right.candidate.unit_start]
        if left_unit.secondary_segment_id == right_unit.secondary_segment_id and min(left.candidate.boundary_end_confidence, right.candidate.boundary_start_confidence) < 0.85:
            output[index - 1] = replace(left, extra_review_reasons=left.extra_review_reasons + ["speaker_boundary_low_confidence"])
            output[index] = replace(right, extra_review_reasons=right.extra_review_reasons + ["speaker_boundary_low_confidence"])
    return output


def _enforce_post_judge_safety(allocations: list[SemanticAllocation], config: SemanticAlignmentConfig) -> list[SemanticAllocation]:
    output: list[SemanticAllocation] = []
    for allocation in allocations:
        candidate = allocation.candidate
        if candidate is not None and any(item.get("type") in {"numeric_conflict", "model_name_conflict", "negation_conflict"} for item in candidate.conflicts):
            output.append(replace(allocation, candidate=None, fallback_reason="critical_entity_or_negation_conflict"))
        elif candidate is not None and candidate.alignment_score < config.accept_threshold:
            output.append(replace(allocation, candidate=None, fallback_reason="semantic_score_below_0.65"))
        else:
            output.append(allocation)
    return output


def _diagnostics(allocations: list[SemanticAllocation], units: list[SemanticUnit], scorer: SemanticScorer, judge_metadata: dict[str, object]) -> dict[str, object]:
    allocated_indexes = [index for allocation in allocations if allocation.candidate for index in range(allocation.candidate.unit_start, allocation.candidate.unit_end)]
    counts = Counter(allocated_indexes)
    allocated_set = set(allocated_indexes)
    unallocated = [unit for index, unit in enumerate(units) if index not in allocated_set]
    used_chars = sum(units[index].original_char_end - units[index].original_char_start for index in allocated_set)
    total_chars = sum(unit.original_char_end - unit.original_char_start for unit in units)
    reused_chars = sum((count - 1) * (units[index].original_char_end - units[index].original_char_start) for index, count in counts.items() if count > 1)
    monotonic = 0
    previous_end = 0
    for allocation in allocations:
        if allocation.candidate:
            if allocation.candidate.unit_start < previous_end:
                monotonic += 1
            previous_end = allocation.candidate.unit_end
    speaker_unit_owners: dict[int, set[str]] = defaultdict(set)
    for allocation in allocations:
        if allocation.candidate:
            for index in range(allocation.candidate.unit_start, allocation.candidate.unit_end):
                speaker_unit_owners[index].add(allocation.structure.speaker)
    cross_speaker_chars = sum(units[index].original_char_end - units[index].original_char_start for index, speakers in speaker_unit_owners.items() if len(speakers) > 1)
    similarities = [allocation.candidate.semantic_similarity for allocation in allocations if allocation.candidate]
    fallback_reasons = Counter(allocation.fallback_reason for allocation in allocations if allocation.fallback_reason)
    boundary_low = sum("speaker_boundary_low_confidence" in allocation.extra_review_reasons for allocation in allocations)
    readable = [allocation.candidate.text for allocation in allocations if allocation.candidate]
    exact_duplicates = 0
    partial_duplicates = 0
    for left, right in zip(readable, readable[1:]):
        similarity = SequenceMatcher(None, normalize_for_similarity(left), normalize_for_similarity(right), autojunk=False).ratio()
        if similarity >= 0.999:
            exact_duplicates += 1
        elif similarity >= 0.35:
            partial_duplicates += 1
    secondary_owners: dict[str, set[str]] = defaultdict(set)
    for allocation in allocations:
        if allocation.candidate:
            for index in range(allocation.candidate.unit_start, allocation.candidate.unit_end):
                secondary_owners[units[index].secondary_segment_id].add(allocation.structure.segment_id)
    secondary_ids = {unit.secondary_segment_id for unit in units}
    diagnostics = {
        "secondary_segment_reuse_count": 0,
        "cross_speaker_boundary_count": sum(1 for speakers in speaker_unit_owners.values() if len(speakers) > 1),
        "adjacent_text_duplication_rate": round(exact_duplicates / max(1, len(readable) - 1), 6),
        "unconsumed_secondary_segment_count": len(secondary_ids - set(secondary_owners)),
        "semantic_unit_count": len(units),
        "allocated_semantic_unit_count": len(allocated_set),
        "unallocated_semantic_unit_count": len(unallocated),
        "secondary_character_reuse_rate": round(reused_chars / max(1, total_chars), 8),
        "secondary_character_consumption_rate": round(used_chars / max(1, total_chars), 6),
        "unallocated_secondary_character_count": total_chars - used_chars,
        "monotonic_violation_count": monotonic,
        "cross_speaker_shared_character_count": cross_speaker_chars,
        "boundary_low_confidence_count": boundary_low,
        "partial_adjacent_duplication_rate": round(partial_duplicates / max(1, len(readable) - 1), 6),
        "semantic_backend": scorer.provider,
        "semantic_model": scorer.model,
        "semantic_alignment_degraded": scorer.degraded,
        "semantic_alignment_status": "degraded" if scorer.degraded else "active",
        "mean_semantic_similarity": round(statistics.mean(similarities), 6) if similarities else None,
        "median_semantic_similarity": round(statistics.median(similarities), 6) if similarities else None,
        "ambiguous_candidate_count": sum(bool(allocation.extra_review_reasons) or allocation.fallback_reason == "ambiguous_candidate_unresolved" for allocation in allocations),
        "fallback_count": sum(allocation.candidate is None for allocation in allocations),
        "fallback_reason_distribution": dict(fallback_reasons),
        **scorer.stats.as_dict(),
        **{key: value for key, value in judge_metadata.items() if key.startswith("judge_")},
    }
    return diagnostics


def align_semantically(*, structure_segments: list[UlistenSegment], secondary_segments: Sequence[object], config_value: dict[str, Any], cache_root: Path | None = None, scorer: SemanticScorer | None = None, judge: DeepSeekJudge | MockJudge | None = None) -> SemanticAlignmentResult:
    started = time.monotonic()
    config = SemanticAlignmentConfig.from_dict(config_value)
    units = segment_secondary_text(secondary_segments, max_unit_chars=config.max_unit_chars)
    alignment_texts = [build_alignment_text(segment) for segment in structure_segments]
    embedding_config = config_value.get("embedding", {})
    scorer = scorer or build_scorer(backend=config.mode, embedding=embedding_config, semantic_unit_version=SEMANTIC_UNIT_VERSION, alignment_text_version=ALIGNMENT_TEXT_VERSION, cache_root=cache_root)
    candidates = _build_candidates(structure_segments, alignment_texts, units, scorer, config)
    path = _beam_align(candidates, config)
    allocations = _finalize_allocations(structure_segments, alignment_texts, path, units, config)
    judge_metadata: dict[str, object] = {"judge_backend": "none", "judge_model": None, "judge_call_count": 0, "judge_cache_hit_count": 0, "judge_abstain_count": 0, "judge_escalation_count": 0}
    if config.mode == "mock_semantic" and judge is None:
        judge = MockJudge()
    elif config.mode == "hybrid_semantic" and judge is None:
        judge_config = config_value.get("ambiguity_judge", {})
        cache_path = Path(judge_config.get("cache_path") or ".llmcache/semantic_boundary_judgments.jsonl")
        if not cache_path.is_absolute() and cache_root:
            cache_path = cache_root / cache_path
        judge = DeepSeekJudge(config={"llm": judge_config}, cache_path=cache_path)
    if config.mode in {"hybrid_semantic", "mock_semantic"}:
        allocations = _apply_judgments(allocations, structure_segments, alignment_texts, config, judge)
        if judge:
            judge_metadata = judge.metadata()
    allocations = _enforce_post_judge_safety(allocations, config)
    allocations = _speaker_boundary_review(allocations, units)
    allocated = {index for allocation in allocations if allocation.candidate for index in range(allocation.candidate.unit_start, allocation.candidate.unit_end)}
    unallocated = [unit for index, unit in enumerate(units) if index not in allocated]
    diagnostics = _diagnostics(allocations, units, scorer, judge_metadata)
    if config.mode == "hybrid_semantic" and judge_metadata.get("judge_backend") == "unavailable":
        diagnostics["semantic_alignment_degraded"] = True
        diagnostics["semantic_alignment_status"] = "degraded"
    trace = []
    for allocation in allocations:
        trace.append({
            "segment_id": allocation.structure.segment_id,
            "speaker": allocation.structure.speaker,
            "chapter": allocation.structure.chapter,
            "text_ulisten_alignment": allocation.alignment_text.text,
            "alignment_text_method": allocation.alignment_text.method,
            "alignment_text_is_authoritative": allocation.alignment_text.is_authoritative,
            "selected_candidate": allocation.candidate.compact_dict() if allocation.candidate else None,
            "candidate_options": [candidate.compact_dict() for candidate in allocation.alternatives[:5]],
            "fallback_reason": allocation.fallback_reason,
            "extra_review_reasons": allocation.extra_review_reasons,
            "judge_decision": allocation.judge_decision,
        })
    return SemanticAlignmentResult(
        allocations=allocations,
        units=units,
        unallocated_units=unallocated,
        diagnostics=diagnostics,
        trace=trace,
        scorer_metadata=scorer.metadata(),
        judge_metadata=judge_metadata,
        config=config,
        elapsed_seconds=round(time.monotonic() - started, 3),
    )


def allocation_record(allocation: SemanticAllocation, units: list[SemanticUnit], *, text_source: str, official: bool, source_is_fixture: bool) -> dict[str, object]:
    structure = allocation.structure
    candidate = allocation.candidate
    reasons = list(allocation.extra_review_reasons)
    if candidate is None:
        reasons.append(allocation.fallback_reason or "semantic_alignment_fallback")
        text = structure.text_raw
        readable_raw = None
        confidence = None
        conflicts: list[dict[str, object]] = []
        selected_units: list[SemanticUnit] = []
        final_text_source = "ulisten_raw_review_fallback"
    else:
        selected_units = units[candidate.unit_start:candidate.unit_end]
        text = candidate.text
        readable_raw = candidate.text
        confidence = candidate.alignment_score
        conflicts = candidate.conflicts
        if official:
            conflicts = [
                {("official_transcript" if key == "usetranscribe" else key): value for key, value in conflict.items()}
                for conflict in conflicts
            ]
        if confidence < 0.85:
            reasons.append("alignment_between_0.65_and_0.85")
        reasons.extend(str(item.get("type")) for item in conflicts)
        final_text_source = text_source
    reasons = list(dict.fromkeys(reasons))
    details: dict[str, object] = {
        "allocation_method": "constrained_monotonic_semantic_alignment",
        "semantic_unit_ids": [unit.unit_id for unit in selected_units],
        "secondary_segment_ids": list(dict.fromkeys(unit.secondary_segment_id for unit in selected_units)),
        "secondary_char_start": selected_units[0].original_char_start if selected_units else None,
        "secondary_char_end": selected_units[-1].original_char_end if selected_units else None,
        "secondary_token_start": selected_units[0].token_start if selected_units else None,
        "secondary_token_end": selected_units[-1].token_end if selected_units else None,
        "semantic_similarity": candidate.semantic_similarity if candidate else None,
        "lexical_anchor_score": candidate.lexical_anchor_score if candidate else None,
        "entity_consistency_score": candidate.entity_consistency_score if candidate else None,
        "time_prior_score": candidate.time_prior_score if candidate else None,
        "sequence_context_score": candidate.sequence_context_score if candidate else None,
        "boundary_start_confidence": candidate.boundary_start_confidence if candidate else None,
        "boundary_end_confidence": candidate.boundary_end_confidence if candidate else None,
        "source_text_consumed_once": bool(candidate),
        "alignment_text_method": allocation.alignment_text.method,
        "alignment_text_is_authoritative": False,
        "fallback_reason": allocation.fallback_reason,
    }
    record: dict[str, object] = {
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
        "text_usetranscribe_raw": None if official else readable_raw,
        "text_official_raw": readable_raw if official else None,
        "structure_source": "ulisten_manual_browser_copy",
        "text_source": final_text_source,
        "source_is_fixture": source_is_fixture,
        "alignment_method": "constrained_monotonic_semantic_alignment",
        "alignment_confidence": confidence,
        "alignment_components": ({
            "semantic_similarity": candidate.semantic_similarity,
            "lexical_anchor_score": candidate.lexical_anchor_score,
            "entity_consistency_score": candidate.entity_consistency_score,
            "time_prior_score": candidate.time_prior_score,
            "sequence_context_score": candidate.sequence_context_score,
        } if candidate else None),
        "needs_review": bool(reasons),
        "review_reasons": reasons,
        "conflicts": conflicts,
        "youtube_url": structure.youtube_url,
        "fusion_mode": "official_dual" if official else "dual_source",
        "speaker_needs_review": False,
        "speaker_status": "source_provided",
        "speaker_review_reasons": [],
        "text_status": "readable" if candidate else "raw_structure_only",
        "structure_status": "source_provided",
        **details,
    }
    return record

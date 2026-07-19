"""Deterministic, high-recall trend candidate extraction.

The extractor never rewrites transcript text. Claims and supporting text are
verbatim spans selected from the supplied transcript records.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Iterable


_NUMBER = re.compile(r"\b\d+(?:\.\d+)?(?:%|x|×)?\b", re.IGNORECASE)
_NEGATION = re.compile(r"\b(?:not|no|never|cannot|can't|won't|without|fails?|failed|impossible)\b", re.IGNORECASE)
_MODEL = re.compile(r"\b(?:GPT[- ]?\w+|Llama[- ]?\w+|Claude[- ]?\w+|Gemini[- ]?\w+|DeepSeek[- ]?\w+|BGE[- ]?M3|Diffusion[- ]?MPC|LeWorldModeling|PAC[- ]?Bayes)\b", re.IGNORECASE)
_ENTITY = re.compile(r"\b(?:[A-Z][A-Za-z0-9.-]+(?:\s+[A-Z][A-Za-z0-9().-]+){0,3})\b")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_NON_CONSENSUS = re.compile(
    r"\b(?:surprising|counterintuitive|contrary|instead|unlike|does not|do not|isn't|aren't|fails?|bottleneck|limited by|only if|even when|rather than|not necessary|not enough)\b",
    re.IGNORECASE,
)
_BOUNDARY = re.compile(r"\b(?:depends? on|requires?|unless|only if|under infinite compute|data[- ]limited|compute[- ]limited|verification|constraint|condition|trade[- ]?off)\b", re.IGNORECASE)


_TOPICS: dict[str, dict[str, Any]] = {
    "speculative_decoding": {
        "label": "Speculative decoding and inference verification",
        "patterns": [r"speculative decoding", r"draft model", r"verification", r"acceptance rate", r"inference speed"],
        "implication": "Inference gains may depend more on verification and acceptance constraints than on draft generation alone.",
    },
    "diffusion_planning": {
        "label": "Diffusion planning and control",
        "patterns": [r"diffusion", r"model predictive control", r"\bMPC\b", r"trajectory", r"planning"],
        "implication": "Generative models are moving from passive generation toward constrained planning and control loops.",
    },
    "world_models": {
        "label": "World models and latent-space planning",
        "patterns": [r"world model", r"latent space", r"latent planning", r"dynamics model", r"rollout"],
        "implication": "World-model research is testing whether useful planning can move into compact learned latent spaces.",
    },
    "data_scaling": {
        "label": "Data scaling and compute per example",
        "patterns": [r"scaling", r"data point", r"per data", r"dataset", r"more data", r"compute per"],
        "implication": "Scaling strategy may shift when marginal data and marginal compute have different availability constraints.",
    },
    "infinite_compute_pretraining": {
        "label": "Pretraining under data limits and abundant compute",
        "patterns": [r"infinite compute", r"data[- ]limited", r"compute is not", r"pretraining", r"reuse data", r"multiple epochs"],
        "implication": "Training recipes may change materially when data is scarce but additional compute remains available.",
    },
    "generalization_theory": {
        "label": "Generalization theory and PAC-Bayes",
        "patterns": [r"PAC[- ]?Bayes", r"generalization", r"overparameter", r"deep learning is not", r"bound"],
        "implication": "Classical generalization explanations are being re-evaluated for heavily overparameterized models.",
    },
    "model_efficiency": {
        "label": "Model and training efficiency",
        "patterns": [r"efficien", r"throughput", r"latency", r"memory", r"FLOP", r"compute", r"speedup"],
        "implication": "Efficiency improvements increasingly depend on system-level constraints, not only model quality.",
    },
    "failure_modes": {
        "label": "Failure modes and boundary conditions",
        "patterns": [r"fail", r"doesn't work", r"not work", r"limitation", r"problem", r"breaks", r"cannot"],
        "implication": "The most decision-relevant signal may be the conditions under which a promising method stops working.",
    },
}


def _tokens(pattern: re.Pattern[str], text: str) -> set[str]:
    return {match.group(0).lower() for match in pattern.finditer(text)}


def detect_text_conflicts(left: str, right: str) -> list[dict[str, Any]]:
    """Detect high-risk disagreements without deciding which source is right."""
    conflicts: list[dict[str, Any]] = []
    for kind, pattern in (("numeric_conflict", _NUMBER), ("negation_conflict", _NEGATION), ("model_name_conflict", _MODEL)):
        left_values, right_values = _tokens(pattern, left), _tokens(pattern, right)
        if (left_values or right_values) and left_values != right_values:
            conflicts.append({"type": kind, "source_a": sorted(left_values), "source_b": sorted(right_values)})
    left_entities, right_entities = _tokens(_ENTITY, left), _tokens(_ENTITY, right)
    ignored = {"i", "the", "this", "that", "all", "and", "but", "so", "we", "you", "it"}
    left_entities -= ignored
    right_entities -= ignored
    if left_entities and right_entities and left_entities != right_entities:
        conflicts.append({"type": "entity_conflict", "source_a": sorted(left_entities), "source_b": sorted(right_entities)})
    return conflicts


def risk_summary(text: str) -> dict[str, list[str]]:
    return {
        "numeric_risks": sorted(_tokens(_NUMBER, text)),
        "entity_risks": sorted((_tokens(_MODEL, text) | _tokens(_ENTITY, text)) - {"i", "the", "this", "that"}),
        "negation_risks": sorted(_tokens(_NEGATION, text)),
    }


def _topic_matches(text: str) -> list[str]:
    return [topic for topic, value in _TOPICS.items() if any(re.search(pattern, text, re.IGNORECASE) for pattern in value["patterns"])]


def _best_claim(text: str) -> str:
    sentences = [value.strip() for value in _SENTENCE.split(text) if value.strip()]
    if not sentences:
        return text.strip()
    ranked = sorted(
        enumerate(sentences),
        key=lambda item: (
            -int(bool(_NON_CONSENSUS.search(item[1]))),
            -int(bool(_BOUNDARY.search(item[1]))),
            -len(_NUMBER.findall(item[1])),
            -len(item[1]),
            item[0],
        ),
    )
    return ranked[0][1]


def _speaker_status_rank(value: str) -> int:
    return {"source_provided": 6, "audio_confirmed": 6, "section_inferred": 4, "probable": 3, "boundary_uncertain": 2, "unknown": 1}.get(value, 0)


def _candidate_from_group(media_id: str, topic: str, rows: list[dict[str, Any]], source_mode: str) -> dict[str, Any]:
    supporting_text = " ".join(str(row.get("text") or "").strip() for row in rows if str(row.get("text") or "").strip()).strip()
    risks = risk_summary(supporting_text)
    conflicts = [conflict for row in rows for conflict in row.get("conflicts", [])]
    non_consensus = sorted({match.group(0).lower() for match in _NON_CONSENSUS.finditer(supporting_text)})
    boundary_signals = sorted({match.group(0).lower() for match in _BOUNDARY.finditer(supporting_text)})
    speakers = {row.get("speaker") for row in rows if row.get("speaker") not in {None, "unknown"}}
    statuses = [str(row.get("speaker_status") or "unknown") for row in rows]
    weakest_status = min(statuses, key=_speaker_status_rank) if statuses else "unknown"
    speaker = next(iter(speakers)) if len(speakers) == 1 else None
    source_ranges = [value for row in rows for value in row.get("source_ranges", [])]
    agreements = [str(row.get("source_agreement") or "single_source") for row in rows]
    agreement = "conflict" if conflicts else "high" if agreements and all(value == "high" for value in agreements) else "mixed" if len(set(agreements)) > 1 else agreements[0]
    novelty_type = "failure_mode" if re.search(r"fail|limitation|cannot|doesn't work|not work", supporting_text, re.IGNORECASE) else "boundary_condition" if boundary_signals else "scaling_law" if topic in {"data_scaling", "infinite_compute_pretraining"} else "mechanism"
    digest_input = f"{media_id}|{source_mode}|{topic}|{rows[0].get('start_seconds')}|{rows[-1].get('end_seconds')}|{supporting_text}"
    candidate_id = f"{media_id}.trend_{hashlib.sha256(digest_input.encode('utf-8')).hexdigest()[:12]}"
    return {
        "candidate_id": candidate_id,
        "topic": _TOPICS[topic]["label"],
        "topic_key": topic,
        "claim": _best_claim(supporting_text),
        "why_valuable": "Captures a technical mechanism, constraint, failure mode, or scaling condition that can change research or product decisions.",
        "novelty_type": novelty_type,
        "non_consensus_signal": non_consensus,
        "trend_implication": _TOPICS[topic]["implication"],
        "supporting_text": supporting_text,
        "source_ranges": source_ranges,
        "source_agreement": agreement,
        "entity_risks": risks["entity_risks"],
        "numeric_risks": risks["numeric_risks"],
        "negation_risks": risks["negation_risks"],
        "conflicts": conflicts,
        "speaker": speaker,
        "speaker_status": weakest_status,
        "speaker_confidence": min((float(row.get("speaker_confidence") or 0.0) for row in rows), default=0.0),
        "attribution_scope": "section" if speaker else "unknown",
        "exact_quote_allowed": bool(speaker and all(bool(row.get("exact_quote_allowed")) for row in rows)),
        "needs_verification": bool(conflicts or weakest_status in {"boundary_uncertain", "unknown"} or risks["numeric_risks"] or risks["negation_risks"]),
        "source_mode": source_mode,
        "start_seconds": min(float(row.get("start_seconds") or 0.0) for row in rows),
        "end_seconds": max(float(row.get("end_seconds") or 0.0) for row in rows),
        "record_ids": [row.get("record_id") or row.get("segment_id") for row in rows],
    }


def extract_high_value_candidates(records: Iterable[dict[str, Any]], *, media_id: str, source_mode: str) -> list[dict[str, Any]]:
    """Extract topic blocks with high recall using the same rules for both modes."""
    rows = sorted((dict(row) for row in records if str(row.get("text") or "").strip()), key=lambda row: (float(row.get("start_seconds") or 0.0), str(row.get("record_id") or row.get("segment_id") or "")))
    by_topic: dict[str, list[list[dict[str, Any]]]] = defaultdict(list)
    active: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        matched = _topic_matches(str(row["text"]))
        for topic in list(active):
            if topic not in matched or float(row.get("start_seconds") or 0.0) - float(active[topic][-1].get("end_seconds") or 0.0) > 90:
                by_topic[topic].append(active.pop(topic))
        for topic in matched:
            if topic not in active:
                active[topic] = []
            active[topic].append(row)
            if len(active[topic]) >= 6 or sum(len(str(item.get("text") or "")) for item in active[topic]) >= 1800:
                by_topic[topic].append(active.pop(topic))
    for topic, group in active.items():
        by_topic[topic].append(group)
    candidates = [
        _candidate_from_group(media_id, topic, group, source_mode)
        for topic, groups in by_topic.items()
        for group in groups
        if len(" ".join(str(row.get("text") or "") for row in group).strip()) >= 60
    ]
    return sorted(candidates, key=lambda item: (item["start_seconds"], item["topic_key"], item["candidate_id"]))

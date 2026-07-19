"""External golden evaluation for Phase 7.1 claims."""

from __future__ import annotations

import json
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .transcript_fuser import normalize_for_similarity


_ALLOWED_EXPECTED_RISKS = {"entity", "numeric", "negation", "speaker"}
_EXACT_SPEAKER_REQUIREMENTS = {"exact", "audio_confirmed", "source_provided"}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _text_score(left: str, right: str) -> float:
    left_norm, right_norm = normalize_for_similarity(left), normalize_for_similarity(right)
    if not left_norm or not right_norm:
        return 0.0
    sequence = SequenceMatcher(None, left_norm, right_norm, autojunk=False).ratio()
    if left_norm in right_norm or right_norm in left_norm:
        return max(sequence, 0.92)
    left_tokens, right_tokens = set(left_norm[i:i + 5] for i in range(max(0, len(left_norm) - 4))), set(right_norm[i:i + 5] for i in range(max(0, len(right_norm) - 4)))
    overlap = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
    return max(sequence, overlap)


def _time_score(gold: dict[str, Any], claim: dict[str, Any]) -> float:
    start, end = map(float, gold["supporting_time_range"])
    left, right = float(claim["source_time_start"]), float(claim["source_time_end"])
    overlap = max(0.0, min(end, right) - max(start, left))
    union = max(end, right) - min(start, left)
    if overlap > 0:
        return min(1.0, overlap / max(1.0, union))
    distance = min(abs(left - end), abs(start - right))
    return max(0.0, 1.0 - distance / 30.0)


def _match_score(gold: dict[str, Any], claim: dict[str, Any]) -> float:
    theme = 1.0 if gold.get("expected_theme") in claim.get("themes", []) else 0.0
    text = _text_score(str(gold.get("supporting_text") or gold.get("gold_claim")), str(claim.get("claim") or ""))
    time = _time_score(gold, claim)
    expected_risks = list(gold.get("expected_risks") or [])
    if expected_risks:
        detected = sum(_risk_detected(gold, claim, risk) for risk in expected_risks)
        risk_score = detected / len(expected_risks)
    else:
        risk_score = 0.5
    return 0.35 * theme + 0.25 * time + 0.25 * text + 0.15 * risk_score


def _exact_attribution_requirement_met(gold: dict[str, Any], claim: dict[str, Any]) -> bool:
    return str(gold.get("speaker_requirement") or "") not in _EXACT_SPEAKER_REQUIREMENTS or claim.get("speaker_status") in {"source_provided", "audio_confirmed"}


def _speaker_name_match(gold: dict[str, Any], claim: dict[str, Any]) -> bool | None:
    expected = str(gold.get("expected_speaker") or "").strip()
    if not expected:
        return None
    actual = str(claim.get("speaker") or "").strip()
    if not actual:
        return None
    return normalize_for_similarity(expected) == normalize_for_similarity(actual)


def _risk_detected(gold: dict[str, Any], claim: dict[str, Any], risk: str) -> bool:
    if risk == "speaker":
        name_match = _speaker_name_match(gold, claim)
        return not _exact_attribution_requirement_met(gold, claim) or name_match is False
    return bool(claim.get(f"{risk}_risks"))


def _validate_golden(golden: list[dict[str, Any]]) -> None:
    for item in golden:
        risks = item.get("expected_risks") or []
        invalid = sorted({str(value) for value in risks} - _ALLOWED_EXPECTED_RISKS)
        if invalid:
            raise ValueError(f"golden {item.get('gold_id')} has invalid expected_risks: {invalid}")
        if item.get("expected_speaker") is not None and not isinstance(item.get("expected_speaker"), str):
            raise ValueError(f"golden {item.get('gold_id')} expected_speaker must be a string")


def _prf(tp: int, predicted: int, gold: int) -> tuple[float, float, float]:
    precision = tp / max(1, predicted)
    recall = tp / max(1, gold)
    return round(precision, 6), round(recall, 6), round(2 * precision * recall / max(1e-9, precision + recall), 6)


def evaluate_phase71(*, golden_path: Path, claims_path: Path, evidence_path: Path, output_path: Path | None = None) -> dict[str, Any]:
    golden, claims, evidence = _read_jsonl(golden_path), _read_jsonl(claims_path), _read_jsonl(evidence_path)
    _validate_golden(golden)
    matches: list[dict[str, Any]] = []
    used: set[str] = set()
    matched_claims: set[str] = set()
    for gold in golden:
        candidates = sorted((( _match_score(gold, claim), claim) for claim in claims if claim["claim_id"] not in used), key=lambda item: item[0], reverse=True)
        if candidates and candidates[0][0] >= 0.55:
            score, claim = candidates[0]
            used.add(claim["claim_id"])
            matched_claims.add(claim["claim_id"])
            matches.append({"gold_id": gold["gold_id"], "claim_id": claim["claim_id"], "score": round(score, 6), "category": gold.get("category"), "theme_match": gold.get("expected_theme") in claim.get("themes", []), "exact_attribution_requirement_met": _exact_attribution_requirement_met(gold, claim), "speaker_name_match": _speaker_name_match(gold, claim)})
        else:
            matches.append({"gold_id": gold["gold_id"], "claim_id": None, "score": round(candidates[0][0], 6) if candidates else 0.0, "category": gold.get("category"), "theme_match": False, "exact_attribution_requirement_met": False, "speaker_name_match": None})
    by_gold = {item["gold_id"]: item for item in matches}
    metrics: dict[str, Any] = {}
    categories = sorted({gold.get("category", "uncategorized") for gold in golden})
    for category in ["all", *categories]:
        selected = golden if category == "all" else [item for item in golden if item.get("category") == category]
        tp = sum(bool(by_gold[item["gold_id"]].get("claim_id")) for item in selected)
        if category == "all":
            precision, recall, f1 = _prf(tp, len(claims), len(selected))
        else:
            precision, recall, f1 = None, round(tp / max(1, len(selected)), 6), None
        metrics[category] = {"gold_count": len(selected), "matched_count": tp, "claim_precision_proxy": precision, "claim_recall": recall, "claim_f1": f1}
    def recall_for(predicate):
        selected = [item for item in golden if predicate(item)]
        return round(sum(bool(by_gold[item["gold_id"]].get("claim_id")) for item in selected) / max(1, len(selected)), 6)
    metrics.update({
        "non_consensus_recall": recall_for(lambda item: "non_consensus" in item.get("value_types", [])),
        "failure_mode_recall": recall_for(lambda item: item.get("category") == "failure_mode"),
        "quantitative_claim_recall": recall_for(lambda item: "quantitative_signal" in item.get("value_types", [])),
        "boundary_condition_recall": recall_for(lambda item: "boundary_condition" in item.get("value_types", [])),
    })
    traceable = sum(bool(item.get("source_record_ids") and item.get("source_text") and item.get("source_ranges") and item.get("source_hashes")) for item in evidence)
    unsupported = sum(not item.get("evidence_ids") for item in claims)
    exact_attribution_unmet = sum(bool(item.get("claim_id")) and not item.get("exact_attribution_requirement_met") for item in matches)
    speaker_name_mismatch = sum(bool(item.get("claim_id")) and item.get("speaker_name_match") is False for item in matches)
    risk_detection: dict[str, Any] = {}
    for risk in ("entity", "numeric", "negation", "speaker"):
        selected = [item for item in golden if risk in item.get("expected_risks", [])]
        detected = 0
        for item in selected:
            matched = by_gold[item["gold_id"]].get("claim_id")
            claim = next((value for value in claims if value["claim_id"] == matched), None)
            if claim and _risk_detected(item, claim, risk):
                detected += 1
        risk_detection[f"{risk}_risk_detection_recall"] = round(detected / max(1, len(selected)), 6)
    result = {"schema_version": "phase_7_1_evaluation_v2", "gold_count": len(golden), "claim_count": len(claims), "evidence_count": len(evidence), "metrics": metrics, "meaningful_omission_rate": round(sum(not bool(item.get("claim_id")) for item in matches) / max(1, len(matches)), 6), "evidence_traceability_rate": round(traceable / max(1, len(evidence)), 6), "unsupported_claim_count": unsupported, "exact_attribution_requirement_unmet_count": exact_attribution_unmet, "speaker_name_mismatch_count": speaker_name_mismatch, **risk_detection, "matches": matches, "unmatched_claim_count": len(claims) - len(matched_claims)}
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result

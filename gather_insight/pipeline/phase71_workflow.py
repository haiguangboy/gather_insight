"""Phase 7.1 high-value claim and evidence workflow."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .evidence_builder import youtube_timestamp_url
from .phase71_value_judge import build_value_judge
from .transcript_fuser import normalize_for_similarity
from .trend_candidate_extractor import extract_high_value_candidates, risk_summary, topic_implication, topic_matches


CLAIM_SCHEMA_VERSION = "phase_7_1_claim_v1"
EVIDENCE_SCHEMA_VERSION = "phase_7_1_evidence_v1"
THEME_SCHEMA_VERSION = "phase_7_1_theme_assignment_v1"
RELATION_SCHEMA_VERSION = "phase_7_1_claim_relation_v1"
TREND_SCHEMA_VERSION = "phase_7_1_trend_candidate_v1"
VERIFICATION_SCHEMA_VERSION = "phase_7_1_verification_queue_v1"
CANONICAL_SCHEMA_VERSION = "phase_7_1_canonical_v1"
EXTRACTION_VERSION = "phase_7_1_high_recall_rules_v1"
_CREATED_AT = "2026-07-19T00:00:00Z"
_FUTURE = re.compile(r"\b(?:will|going to|expect|predict|future|may become|likely to)\b", re.IGNORECASE)
_CAUSAL = re.compile(r"\b(?:because|causes?|leads? to|results? in|due to|drives?)\b", re.IGNORECASE)
_CONDITIONAL = re.compile(r"\b(?:if|when|unless|only if|depends? on|under|condition)\b", re.IGNORECASE)
_COMPARISON = re.compile(r"\b(?:better than|worse than|compared to|unlike|versus|more than|less than)\b", re.IGNORECASE)
_QUESTION = re.compile(r"\?\s*$")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_VALUE_SIGNAL = re.compile(r"\b(?:bottleneck|fail|failure|cannot|can't|unless|because|instead|better|worse|ensemble|compared|counterintuitive|surprising|requires?|depends?|constraint|limited|overfit|faster|slower|efficiency|improvement|downstream|IID)\b", re.IGNORECASE)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_id(prefix: str, *values: object) -> str:
    digest = hashlib.sha256("|".join(str(value) for value in values).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _source_hashes(source_input_dir: Path | None, manifest: dict[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    if source_input_dir and source_input_dir.exists():
        for path in sorted(source_input_dir.iterdir()):
            if path.is_file() and (path.name.startswith("source_") or path.name == "manifest.json"):
                hashes[path.name] = _sha256(path)
    contract = manifest.get("blind_input_contract") or {}
    for key in ("source_a", "source_b"):
        value = contract.get(key) or {}
        if value.get("path") and value.get("sha256") and (source_input_dir is None or (source_input_dir / str(value["path"])).exists()):
            hashes.setdefault(str(value["path"]), str(value["sha256"]))
    return hashes


def _canonical_record(record: dict[str, Any], media_id: str, youtube_url: str, mode: str, source_hashes: dict[str, str]) -> dict[str, Any]:
    record_id = str(record.get("record_id") or record.get("segment_id"))
    start, end = float(record.get("start_seconds") or 0.0), float(record.get("end_seconds") or 0.0)
    ranges = list(record.get("source_ranges") or [])
    if not ranges and record.get("secondary_char_start") is not None:
        ranges = [{"source": str(record.get("text_source") or "secondary_transcript"), "char_start": record.get("secondary_char_start"), "char_end": record.get("secondary_char_end"), "range_precision": "semantic_projection"}]
    provider = ",".join(record.get("text_sources") or []) or str(record.get("text_source") or "unknown")
    speaker_status = str(record.get("speaker_status") or ("source_provided" if record.get("speaker") else "unknown"))
    speaker_confidence = float(record.get("speaker_confidence") if record.get("speaker_confidence") is not None else (1.0 if speaker_status == "source_provided" else 0.0))
    exact_quote = bool(record.get("exact_quote_allowed", False))
    if mode == "high_quality_structure_mode" and speaker_status == "source_provided" and not record.get("needs_review") and not record.get("conflicts"):
        exact_quote = True
    return {
        **record,
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "record_id": record_id,
        "media_id": media_id,
        "text": str(record.get("text") or ""),
        "start_seconds": start,
        "end_seconds": end,
        "source_url": str(record.get("youtube_url") or youtube_timestamp_url(youtube_url, start)),
        "provider": provider,
        "source_ranges": ranges,
        "source_hashes": source_hashes,
        "speaker_status": speaker_status,
        "speaker_confidence": speaker_confidence,
        "attribution_scope": str(record.get("attribution_scope") or ("segment" if speaker_status == "source_provided" else "section" if speaker_status == "section_inferred" else "unknown")),
        "exact_quote_allowed": exact_quote,
        "from_meaningful_unmerged": False,
        "mode": mode,
    }


def _canonical_unmerged(row: dict[str, Any], index: int, media_id: str, youtube_url: str, mode: str, source_hashes: dict[str, str]) -> dict[str, Any]:
    record_id = str(row.get("record_id") or row.get("unit_id") or f"{media_id}.unmerged_{index:04d}")
    start = float(row.get("start_seconds") if row.get("start_seconds") is not None else row.get("approx_start_seconds") or 0.0)
    end = float(row.get("end_seconds") if row.get("end_seconds") is not None else row.get("approx_end_seconds") or start)
    return {
        **row,
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "record_id": record_id,
        "media_id": media_id,
        "text": str(row.get("text") or ""),
        "start_seconds": start,
        "end_seconds": end,
        "source_url": str(row.get("youtube_url") or youtube_timestamp_url(youtube_url, start)),
        "provider": str(row.get("provider") or "meaningful_unmerged"),
        "source_ranges": list(row.get("source_ranges") or []),
        "source_hashes": source_hashes,
        "speaker": row.get("speaker"),
        "speaker_status": str(row.get("speaker_status") or "unknown"),
        "speaker_confidence": float(row.get("speaker_confidence") or 0.0),
        "attribution_scope": str(row.get("attribution_scope") or "unknown"),
        "exact_quote_allowed": False,
        "from_meaningful_unmerged": True,
        "mode": mode,
        "needs_verification": True,
    }


def prepare_phase71_canonical(*, input_dir: Path, manifest_path: Path, media_root: Path, mode: str, source_input_dir: Path | None = None) -> dict[str, Any]:
    if mode not in {"high_quality_structure_mode", "dual_text_trend_mode"}:
        raise ValueError(f"unsupported Phase 7.1 mode: {mode}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    media_id = str(manifest.get("media_id") or manifest.get("canonical_youtube_video_id"))
    if not media_id.startswith("yt_"):
        media_id = f"yt_{media_id}"
    youtube_url = str(manifest["youtube_url"])
    transcript_path = input_dir / ("no_ulisten_fused.jsonl" if (input_dir / "no_ulisten_fused.jsonl").exists() else "transcript_fused.jsonl")
    if not transcript_path.exists():
        raise ValueError("Phase 7.1 input has no supported transcript record JSONL")
    unmerged_path = input_dir / ("meaningful_unmerged.jsonl" if (input_dir / "meaningful_unmerged.jsonl").exists() else "unallocated_secondary.jsonl")
    conflicts_path = input_dir / "conflict_queue.jsonl"
    hashes = _source_hashes(source_input_dir, manifest)
    records = [_canonical_record(row, media_id, youtube_url, mode, hashes) for row in _read_jsonl(transcript_path)]
    raw_unmerged = _read_jsonl(unmerged_path)
    if unmerged_path.name == "unallocated_secondary.jsonl":
        raw_unmerged = [row for row in raw_unmerged if len(normalize_for_similarity(str(row.get("text") or ""))) >= 80]
    unmerged = [_canonical_unmerged(row, index, media_id, youtube_url, mode, hashes) for index, row in enumerate(raw_unmerged, 1)]
    conflicts = _read_jsonl(conflicts_path) if conflicts_path.exists() else [row for row in records if row.get("conflicts")]
    chapters = list(((manifest.get("youtube_metadata") or {}).get("chapters") or []))
    if not chapters:
        seen: dict[str, dict[str, Any]] = {}
        for row in records:
            chapter = str(row.get("chapter") or "").strip()
            if chapter:
                current = seen.setdefault(chapter, {"title": chapter, "start_seconds": row["start_seconds"], "end_seconds": row["end_seconds"], "speaker": row.get("speaker")})
                current["start_seconds"] = min(current["start_seconds"], row["start_seconds"])
                current["end_seconds"] = max(current["end_seconds"], row["end_seconds"])
        chapters = sorted(seen.values(), key=lambda item: item["start_seconds"])
    speaker_rows: dict[str, dict[str, Any]] = {}
    for row in [*records, *unmerged]:
        key = str(row.get("speaker") or row.get("speaker_cluster") or "unknown")
        current = speaker_rows.setdefault(key, {"speaker": row.get("speaker"), "speaker_cluster": row.get("speaker_cluster") or key, "statuses": Counter(), "record_ids": []})
        current["statuses"][row.get("speaker_status") or "unknown"] += 1
        current["record_ids"].append(row["record_id"])
    speakers = [{**value, "statuses": dict(value["statuses"])} for value in speaker_rows.values()]
    canonical_dir = media_root / "canonical"
    raw_dir = media_root / "raw"
    for directory in (raw_dir, canonical_dir, media_root / "intelligence", media_root / "views", media_root / "reports"):
        directory.mkdir(parents=True, exist_ok=True)
    _write_jsonl(canonical_dir / "transcript_records.jsonl", records)
    _write_jsonl(canonical_dir / "meaningful_unmerged.jsonl", unmerged)
    _write_jsonl(canonical_dir / "conflict_queue.jsonl", conflicts)
    (canonical_dir / "chapters.json").write_text(json.dumps(chapters, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (canonical_dir / "speakers.json").write_text(json.dumps(speakers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    canonical_manifest = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "media_id": media_id,
        "youtube_url": youtube_url,
        "title": manifest.get("title"),
        "mode": mode,
        "source_hashes": hashes,
        "source_input_path": str(input_dir.resolve()),
        "record_count": len(records),
        "meaningful_unmerged_count": len(unmerged),
        "conflict_record_count": len(conflicts),
        "chapters_count": len(chapters),
        "created_at": _CREATED_AT,
    }
    (canonical_dir / "manifest.json").write_text(json.dumps(canonical_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (raw_dir / "source_manifest.json").write_text(json.dumps({"immutable_sources": hashes, "source_input_path": str(source_input_dir.resolve()) if source_input_dir else None}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**canonical_manifest, "media_root": str(media_root.resolve())}


def _claim_type(text: str, novelty_type: str) -> str:
    if novelty_type == "failure_mode":
        return "failure_mode"
    if _QUESTION.search(text):
        return "open_question"
    if _FUTURE.search(text):
        return "prediction"
    if _CAUSAL.search(text):
        return "causal_claim"
    if _CONDITIONAL.search(text):
        return "conditional_conclusion"
    if _COMPARISON.search(text):
        return "comparison"
    if novelty_type == "boundary_condition":
        return "engineering_constraint"
    return "technical_mechanism"


def _value_types(candidate: dict[str, Any]) -> list[str]:
    values = {"trend_signal", "practical_implication"}
    if candidate.get("non_consensus_signal"):
        values.add("non_consensus")
    if candidate.get("numeric_risks"):
        values.add("quantitative_signal")
    if candidate.get("novelty_type") == "failure_mode":
        values.update({"failure_case", "boundary_condition"})
    if candidate.get("novelty_type") == "boundary_condition":
        values.update({"boundary_condition", "hidden_assumption"})
    if candidate.get("source_agreement") in {"mixed", "conflict"}:
        values.add("cross_source_connection")
    return sorted(values)


def _scores(candidate: dict[str, Any]) -> tuple[float, float, float, float]:
    non_consensus = min(1.0, 0.18 + 0.18 * len(candidate.get("non_consensus_signal") or []) + (0.18 if candidate.get("novelty_type") == "failure_mode" else 0.0))
    novelty = min(1.0, 0.35 + 0.28 * non_consensus + (0.15 if candidate.get("novelty_type") in {"failure_mode", "boundary_condition", "scaling_law"} else 0.0))
    importance = min(1.0, 0.52 + (0.10 if candidate.get("numeric_risks") else 0.0) + (0.12 if candidate.get("novelty_type") in {"failure_mode", "boundary_condition"} else 0.0) + 0.16 * non_consensus)
    agreement = str(candidate.get("source_agreement") or "single_source")
    confidence = {"high": 0.9, "medium": 0.78, "mixed": 0.72, "conflict": 0.55, "source_a_only": 0.62, "source_b_only": 0.62, "single_source": 0.65}.get(agreement, 0.65)
    return round(confidence, 6), round(novelty, 6), round(importance, 6), round(non_consensus, 6)


def _atomic_claim_seeds(rows: list[dict[str, Any]], media_id: str) -> list[dict[str, Any]]:
    """Promote risk-sensitive atomic sentences independently of topic blocks."""
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        text = str(row.get("text") or "").strip()
        row_themes = topic_matches(text) or topic_matches(str(row.get("chapter") or ""))
        for sentence in [value.strip() for value in _SENTENCE.split(text) if len(value.strip()) >= 35]:
            risks = risk_summary(sentence)
            themes = topic_matches(sentence) or row_themes
            if not themes:
                continue
            valuable = bool(risks["numeric_risks"] or _VALUE_SIGNAL.search(sentence) or _CAUSAL.search(sentence) or _COMPARISON.search(sentence) or (_FUTURE.search(sentence) and re.search(r"\b(?:model|data|compute|training|inference|planning|scaling|verification|generalization)\b", sentence, re.IGNORECASE)))
            if not valuable:
                continue
            novelty_type = "failure_mode" if re.search(r"\b(?:fail|failure|cannot|can't|bottleneck|overfit|worse)\b", sentence, re.IGNORECASE) else "boundary_condition" if _CONDITIONAL.search(sentence) or re.search(r"\b(?:only|unless|requires?|constraint|limited)\b", sentence, re.IGNORECASE) else "scaling_law" if "scal" in sentence.lower() else "mechanism"
            for theme in themes:
                key = (normalize_for_similarity(sentence), theme, str(row["record_id"]))
                if key in seen:
                    continue
                seen.add(key)
                output.append({
                    "candidate_id": _stable_id("atomic", media_id, row["record_id"], sentence, theme),
                    "topic_key": theme,
                    "topic": theme.replace("_", " ").title(),
                    "claim": sentence,
                    "trend_implication": topic_implication(theme),
                    "novelty_type": novelty_type,
                    "non_consensus_signal": [match.group(0).lower() for match in _VALUE_SIGNAL.finditer(sentence) if match.group(0).lower() in {"counterintuitive", "surprising", "instead", "not", "cannot", "can't", "bottleneck", "overfit"}],
                    "numeric_risks": risks["numeric_risks"],
                    "entity_risks": risks["entity_risks"],
                    "negation_risks": risks["negation_risks"],
                    "source_agreement": row.get("source_agreement") or "single_source",
                    "needs_verification": bool(row.get("needs_verification") or risks["numeric_risks"] or risks["negation_risks"]),
                    "record_ids": [row["record_id"]],
                    "start_seconds": row["start_seconds"],
                    "end_seconds": row["end_seconds"],
                    "extraction_pass": "atomic_risk_sensitive_v1",
                })
    return output


def _deduplicate_claims(claims: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence_by_id = {item["evidence_id"]: item for item in evidence}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        groups[(normalize_for_similarity(claim["claim"]), claim["themes"][0] if claim["themes"] else "")].append(claim)
    output_claims: list[dict[str, Any]] = []
    used_evidence: set[str] = set()
    for group in groups.values():
        selected = max(group, key=lambda item: (item["importance_score"], item["confidence"], -item["source_time_start"]))
        evidence_ids = list(dict.fromkeys(value for item in group for value in item["evidence_ids"]))
        record_ids = list(dict.fromkeys(value for item in group for value in item["source_record_ids"]))
        merged = {**selected, "evidence_ids": evidence_ids, "source_record_ids": record_ids, "source_time_start": min(item["source_time_start"] for item in group), "source_time_end": max(item["source_time_end"] for item in group), "merged_candidate_count": len(group)}
        output_claims.append(merged)
        used_evidence.update(evidence_ids)
    return sorted(output_claims, key=lambda item: (item["source_time_start"], item["claim_id"])), [evidence_by_id[item] for item in sorted(used_evidence)]


def _verification_reasons(claim: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    if claim.get("numeric_risks"):
        reasons.append("numeric_risk")
    if claim.get("negation_risks"):
        reasons.append("negation_risk")
    if claim.get("entity_risks"):
        reasons.append("entity_risk")
    if claim.get("speaker_status") not in {"source_provided", "audio_confirmed"}:
        reasons.append("speaker_not_exact")
    if not claim.get("exact_quote_allowed"):
        reasons.append("exact_quote_not_allowed")
    if any(evidence_by_id[evidence_id].get("from_meaningful_unmerged") for evidence_id in claim.get("evidence_ids", []) if evidence_id in evidence_by_id):
        reasons.append("meaningful_unmerged_source")
    if claim.get("confidence", 0) < 0.7:
        reasons.append("low_source_confidence")
    return list(dict.fromkeys(reasons))


def _relations(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for left_index, left in enumerate(claims):
        for right in claims[left_index + 1:]:
            shared_records = set(left["source_record_ids"]) & set(right["source_record_ids"])
            similarity = SequenceMatcher(None, normalize_for_similarity(left["claim"]), normalize_for_similarity(right["claim"]), autojunk=False).ratio()
            relation_type = None
            rationale = ""
            confidence = 0.0
            if similarity >= 0.9:
                relation_type, confidence, rationale = "duplicates", similarity, "near-identical normalized claims"
            elif shared_records and set(left["themes"]) != set(right["themes"]):
                relation_type, confidence, rationale = "extends", 0.72, "same evidence contributes to multiple technical themes"
            elif abs(left["source_time_start"] - right["source_time_start"]) <= 45 and left["claim_type"] == "conditional_conclusion" and right["claim_type"] in {"technical_mechanism", "engineering_constraint"}:
                relation_type, confidence, rationale = "depends_on", 0.66, "conditional claim is adjacent to a mechanism or constraint"
            if relation_type:
                relation_id = _stable_id("rel", left["claim_id"], right["claim_id"], relation_type)
                output.append({"schema_version": RELATION_SCHEMA_VERSION, "relation_id": relation_id, "media_id": left["media_id"], "source_claim_id": left["claim_id"], "target_claim_id": right["claim_id"], "relation_type": relation_type, "confidence": round(confidence, 6), "evidence_ids": list(dict.fromkeys([*left["evidence_ids"], *right["evidence_ids"]])), "relation_method": "deterministic_evidence_overlap_v1", "rationale": rationale})
    return output


def run_phase71_extraction(*, media_root: Path, judge_backend: str = "rules", judge_config: dict[str, Any] | None = None, cache_root: Path | None = None, judge_max_claims: int = 32) -> dict[str, Any]:
    canonical_dir = media_root / "canonical"
    manifest = json.loads((canonical_dir / "manifest.json").read_text(encoding="utf-8"))
    records = _read_jsonl(canonical_dir / "transcript_records.jsonl")
    unmerged = _read_jsonl(canonical_dir / "meaningful_unmerged.jsonl")
    conflict_rows = _read_jsonl(canonical_dir / "conflict_queue.jsonl")
    if not records:
        raise ValueError("Phase 7.1 canonical transcript_records.jsonl is empty")
    media_id, youtube_url = str(manifest["media_id"]), str(manifest["youtube_url"])
    all_rows = [*records, *unmerged]
    by_record = {str(row["record_id"]): row for row in all_rows}
    conflict_by_record: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in conflict_rows:
        record_id = str(row.get("record_id") or row.get("segment_id") or "")
        conflict_by_record[record_id].extend(row.get("conflicts") or [])
    block_seeds = extract_high_value_candidates(all_rows, media_id=media_id, source_mode=str(manifest["mode"]))
    atomic_seeds = _atomic_claim_seeds(all_rows, media_id)
    seeds_by_key: dict[tuple[str, str, tuple[str, ...]], dict[str, Any]] = {}
    for seed in [*block_seeds, *atomic_seeds]:
        key = (normalize_for_similarity(str(seed.get("claim") or "")), str(seed.get("topic_key") or ""), tuple(str(value) for value in seed.get("record_ids", []) if value))
        seeds_by_key.setdefault(key, seed)
    seeds = list(seeds_by_key.values())
    evidence: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    for seed in seeds:
        source_record_ids = [str(value) for value in seed.get("record_ids", []) if value and str(value) in by_record]
        selected_rows = [by_record[value] for value in source_record_ids]
        if not selected_rows:
            continue
        source_text = " ".join(str(row.get("text") or "").strip() for row in selected_rows if str(row.get("text") or "").strip()).strip()
        if not source_text:
            continue
        risks = risk_summary(source_text)
        conflicts = [value for record_id in source_record_ids for value in conflict_by_record.get(record_id, [])]
        start, end = min(float(row["start_seconds"]) for row in selected_rows), max(float(row["end_seconds"]) for row in selected_rows)
        speakers = {row.get("speaker") for row in selected_rows if row.get("speaker")}
        speaker = next(iter(speakers)) if len(speakers) == 1 else None
        speaker_statuses = [str(row.get("speaker_status") or "unknown") for row in selected_rows]
        speaker_status = "source_provided" if speaker_statuses and all(value == "source_provided" for value in speaker_statuses) else "section_inferred" if speaker_statuses and all(value in {"section_inferred", "source_provided"} for value in speaker_statuses) else "boundary_uncertain" if "boundary_uncertain" in speaker_statuses else "unknown"
        speaker_confidence = min((float(row.get("speaker_confidence") or 0.0) for row in selected_rows), default=0.0)
        exact_quote_allowed = bool(selected_rows and all(bool(row.get("exact_quote_allowed")) for row in selected_rows))
        source_ranges = [value for row in selected_rows for value in row.get("source_ranges", [])]
        evidence_id = _stable_id("ev", media_id, *source_record_ids, source_text)
        evidence.append({"schema_version": EVIDENCE_SCHEMA_VERSION, "evidence_id": evidence_id, "media_id": media_id, "source_record_ids": source_record_ids, "source_text": source_text, "normalized_text": normalize_for_similarity(source_text), "speaker": speaker, "speaker_status": speaker_status, "source_time_start": start, "source_time_end": end, "source_url": youtube_timestamp_url(youtube_url, start), "provider": ",".join(sorted({str(row.get("provider") or "unknown") for row in selected_rows})), "source_ranges": source_ranges or [{"source": "canonical_record", "record_ids": source_record_ids, "range_precision": "record"}], "source_hashes": dict(manifest.get("source_hashes") or {}), "entity_risks": risks["entity_risks"], "numeric_risks": risks["numeric_risks"], "negation_risks": risks["negation_risks"], "exact_quote_allowed": exact_quote_allowed, "verification_status": "needs_review" if risks["entity_risks"] or risks["numeric_risks"] or risks["negation_risks"] or conflicts or not exact_quote_allowed else "unreviewed", "from_meaningful_unmerged": any(bool(row.get("from_meaningful_unmerged")) for row in selected_rows)})
        confidence, novelty, importance, non_consensus = _scores(seed)
        claim_type = _claim_type(str(seed["claim"]), str(seed.get("novelty_type") or "mechanism"))
        value_types = _value_types(seed)
        claim_id = _stable_id("cl", media_id, seed["claim"], seed.get("topic_key"), start, end)
        claims.append({"schema_version": CLAIM_SCHEMA_VERSION, "claim_id": claim_id, "media_id": media_id, "claim": str(seed["claim"]), "claim_summary": str(seed.get("trend_implication") or ""), "claim_type": claim_type, "value_types": value_types, "themes": [str(seed.get("topic_key") or "unclassified")], "speaker": speaker, "speaker_status": speaker_status, "speaker_confidence": speaker_confidence, "attribution_scope": "segment" if speaker_status == "source_provided" else "section" if speaker_status == "section_inferred" else "uncertain", "source_record_ids": source_record_ids, "evidence_ids": [evidence_id], "source_time_start": start, "source_time_end": end, "source_url": youtube_timestamp_url(youtube_url, start), "confidence": confidence, "novelty_score": novelty, "importance_score": importance, "non_consensus_score": non_consensus, "entity_risks": risks["entity_risks"], "numeric_risks": risks["numeric_risks"], "negation_risks": risks["negation_risks"], "conflicts": conflicts, "needs_verification": bool(seed.get("needs_verification") or conflicts or risks["numeric_risks"] or risks["negation_risks"]), "exact_quote_allowed": exact_quote_allowed, "extraction_method": f"{EXTRACTION_VERSION}+{seed.get('extraction_pass', 'topic_block_v1')}", "created_at": _CREATED_AT, "source_hashes": dict(manifest.get("source_hashes") or {}), "evidence_text": source_text, "from_meaningful_unmerged": any(bool(row.get("from_meaningful_unmerged")) for row in selected_rows)})
    claims, evidence = _deduplicate_claims(claims, evidence)
    judge = build_value_judge(judge_backend, judge_config, cache_root)
    judged_claims = sorted(claims, key=lambda item: (-item["importance_score"], -item["novelty_score"], item["claim_id"]))[:max(0, judge_max_claims)]
    judgments = judge.judge(judged_claims)
    for claim in claims:
        judgment = judgments.get(claim["claim_id"])
        if judgment:
            for key in ("claim_type", "value_types", "importance_score", "novelty_score", "non_consensus_score"):
                claim[key] = judgment[key]
            claim["needs_verification"] = bool(claim["needs_verification"] or judgment["needs_verification"])
            claim["judge_metadata"] = {"backend": judge.backend, "model": judge.model, "prompt_version": judge.metadata()["prompt_version"], "rationale": judgment.get("rationale")}
        claim.pop("evidence_text", None)
    evidence_by_id = {item["evidence_id"]: item for item in evidence}
    assignments = [{"schema_version": THEME_SCHEMA_VERSION, "assignment_id": _stable_id("theme", claim["claim_id"], theme), "media_id": media_id, "claim_id": claim["claim_id"], "theme_id": theme, "theme_label": theme.replace("_", " ").title(), "confidence": round(max(0.55, claim["confidence"]), 6), "assignment_method": "phase_7_1_topic_rules_v1"} for claim in claims for theme in claim["themes"]]
    relations = _relations(claims)
    verification: list[dict[str, Any]] = []
    trend: list[dict[str, Any]] = []
    for claim in claims:
        reasons = _verification_reasons(claim, evidence_by_id)
        if reasons:
            claim["needs_verification"] = True
            priority = "high" if any(reason in {"numeric_risk", "negation_risk", "entity_risk"} for reason in reasons) and claim["importance_score"] >= 0.65 else "medium" if claim["importance_score"] >= 0.6 else "low"
            verification.append({"schema_version": VERIFICATION_SCHEMA_VERSION, "verification_id": _stable_id("verify", claim["claim_id"]), "media_id": media_id, "target_type": "claim", "target_id": claim["claim_id"], "priority": priority, "reasons": reasons, "status": "open", "reviewer_note": ""})
        if claim["importance_score"] >= 0.62 or claim["non_consensus_score"] >= 0.45:
            trend.append({"schema_version": TREND_SCHEMA_VERSION, "trend_candidate_id": _stable_id("trend", claim["claim_id"]), "media_id": media_id, "claim_id": claim["claim_id"], "evidence_ids": claim["evidence_ids"], "trend_signal": claim.get("claim_summary") or claim["claim"], "importance_score": claim["importance_score"], "novelty_score": claim["novelty_score"], "non_consensus_score": claim["non_consensus_score"], "needs_verification": claim["needs_verification"], "verification_reasons": reasons})
    intelligence_dir, views_dir, reports_dir = media_root / "intelligence", media_root / "views", media_root / "reports"
    _write_jsonl(intelligence_dir / "claims.jsonl", claims)
    _write_jsonl(intelligence_dir / "evidence.jsonl", evidence)
    _write_jsonl(intelligence_dir / "theme_assignments.jsonl", assignments)
    _write_jsonl(intelligence_dir / "claim_relations.jsonl", relations)
    _write_jsonl(intelligence_dir / "trend_candidates.jsonl", trend)
    _write_jsonl(intelligence_dir / "verification_queue.jsonl", verification)
    views_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (views_dir / "claim_review.html").write_text(_claim_review_html(claims, evidence_by_id), encoding="utf-8")
    (reports_dir / "media_brief.md").write_text(_media_brief_markdown(manifest, claims, verification), encoding="utf-8")
    (reports_dir / "high_value_findings.md").write_text(_findings_markdown(manifest, claims, evidence_by_id, verification), encoding="utf-8")
    # Runtime call/cache/token counters are deliberately returned to the caller,
    # but are not written into the canonical processing report.  A cache hit on
    # a repeat run must not make otherwise identical derived outputs differ.
    judge_runtime = judge.metadata()
    stable_judge = {key: value for key, value in judge_runtime.items() if key not in {"call_count", "cache_hit_count", "invalid_count", "input_tokens", "output_tokens"}}
    report = {"status": "ok", "schema_version": "phase_7_1_run_report_v1", "media_id": media_id, "mode": manifest["mode"], "canonical_record_count": len(records), "meaningful_unmerged_input_count": len(unmerged), "topic_block_seed_count": len(block_seeds), "atomic_seed_count": len(atomic_seeds), "high_recall_seed_count": len(seeds), "claim_count": len(claims), "evidence_count": len(evidence), "theme_assignment_count": len(assignments), "claim_relation_count": len(relations), "trend_candidate_count": len(trend), "verification_queue_count": len(verification), "claims_from_meaningful_unmerged": sum(bool(claim.get("from_meaningful_unmerged")) for claim in claims), "unsupported_claim_count": sum(not claim.get("evidence_ids") for claim in claims), "evidence_traceability_rate": round(sum(bool(item.get("source_record_ids") and item.get("source_text") and item.get("source_ranges") and item.get("source_hashes")) for item in evidence) / max(1, len(evidence)), 6), "risk_counts": {"entity": sum(bool(claim["entity_risks"]) for claim in claims), "numeric": sum(bool(claim["numeric_risks"]) for claim in claims), "negation": sum(bool(claim["negation_risks"]) for claim in claims)}, "judge": stable_judge, "created_at": _CREATED_AT}
    (reports_dir / "validation_report.md").write_text(_validation_markdown(report), encoding="utf-8")
    (reports_dir / "processing_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**report, "judge_runtime": judge_runtime, "media_root": str(media_root.resolve())}


def _claim_review_html(claims: list[dict[str, Any]], evidence_by_id: dict[str, dict[str, Any]]) -> str:
    cards = []
    for claim in sorted(claims, key=lambda item: (-item["importance_score"], item["source_time_start"])):
        evidence = evidence_by_id[claim["evidence_ids"][0]]
        item = {"claim_id": claim["claim_id"], "verdict": "", "edited_claim": "", "merge_into": "", "verification_status": "unreviewed", "reviewer_notes": ""}
        cards.append(f'''<article class="claim-card" data-review='{html.escape(json.dumps(item, ensure_ascii=False), quote=True)}'><h2>{html.escape(claim["claim"])}</h2><p>{html.escape(claim["claim_type"])} · {html.escape(", ".join(claim["value_types"]))} · importance {claim["importance_score"]:.2f} · novelty {claim["novelty_score"]:.2f} · non-consensus {claim["non_consensus_score"]:.2f}</p><p>speaker: {html.escape(str(claim.get("speaker") or "unknown"))} · {html.escape(claim["speaker_status"])} · <a target="_blank" href="{html.escape(claim["source_url"])}">video</a></p><pre>{html.escape(evidence["source_text"])}</pre><details><summary>traceability and risks</summary><pre>{html.escape(json.dumps({"source_record_ids": claim["source_record_ids"], "source_ranges": evidence["source_ranges"], "entity_risks": claim["entity_risks"], "numeric_risks": claim["numeric_risks"], "negation_risks": claim["negation_risks"], "meaningful_unmerged": evidence.get("from_meaningful_unmerged")}, ensure_ascii=False, indent=2))}</pre></details><div class="form"><label>verdict <select class="verdict"><option></option><option>accept</option><option>reject</option><option>edit</option><option>merge</option></select></label><label>edited claim <textarea class="edited"></textarea></label><label>merge into <input class="merge"></label><label>verification <select class="verification"><option>unreviewed</option><option>needs_review</option><option>verified</option><option>rejected</option></select></label><label>reviewer notes <textarea class="notes"></textarea></label></div></article>''')
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>Phase 7.1 claim review</title><style>body{{font:14px/1.5 system-ui;max-width:1100px;margin:24px auto}}.claim-card{{border:1px solid #bbb;padding:16px;margin:16px 0;background:#fffdf7}}pre{{white-space:pre-wrap;background:#f3f3f3;padding:10px}}.form{{display:grid;gap:8px}}.form label{{display:grid;grid-template-columns:150px 1fr;gap:8px}}.top{{position:sticky;top:0;background:white;padding:10px;border-bottom:1px solid #aaa}}</style></head><body><div class="top"><h1>Claim review</h1><button onclick="downloadReview()">Download review JSONL</button></div>{''.join(cards)}<script>function downloadReview(){{const rows=[...document.querySelectorAll('.claim-card')].map(card=>{{const row=JSON.parse(card.dataset.review);row.verdict=card.querySelector('.verdict').value;row.edited_claim=card.querySelector('.edited').value;row.merge_into=card.querySelector('.merge').value;row.verification_status=card.querySelector('.verification').value;row.reviewer_notes=card.querySelector('.notes').value;return row}});const text=rows.map(row=>JSON.stringify(row)).join('\n')+'\n';const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{{type:'application/jsonl'}}));a.download='claim_review_completed.jsonl';a.click()}}</script></body></html>'''


def _findings_markdown(manifest: dict[str, Any], claims: list[dict[str, Any]], evidence_by_id: dict[str, dict[str, Any]], verification: list[dict[str, Any]]) -> str:
    ranked = sorted(claims, key=lambda item: (-item["importance_score"], -item["novelty_score"], item["source_time_start"]))
    def lines(items: list[dict[str, Any]]) -> str:
        return "\n".join(f'- **{item["claim"]}**  \n  `{item["claim_id"]}` · {item["source_time_start"]:.1f}s · {item["speaker_status"]} · [video]({item["source_url"]})' for item in items) or "- none"
    non_consensus = [item for item in ranked if item["non_consensus_score"] >= 0.45]
    failures = [item for item in ranked if item["claim_type"] in {"failure_mode", "engineering_constraint", "conditional_conclusion"}]
    quantitative = [item for item in ranked if item["numeric_risks"]]
    direct = [item for item in ranked if not item["needs_verification"] and item["exact_quote_allowed"]]
    return f'''# High-value findings: {manifest.get("title") or manifest["media_id"]}

## One-line judgment

The transcript contains multiple route-changing mechanisms and boundary conditions across {len({theme for claim in claims for theme in claim["themes"]})} themes; the highest-value claims are traceable, but exact attribution and risk-sensitive claims remain a separate verification step.

## Most important claims

{lines(ranked[:20])}

## Non-consensus information

{lines(non_consensus[:15])}

## Failure modes and boundary conditions

{lines(failures[:15])}

## Quantitative signals

{lines(quantitative[:15])}

## Claims suitable for a long-term theme library without further attribution work

{lines(direct[:15])}

## Verification queue

- open items: {len(verification)}
- entity-sensitive claims: {sum(bool(item["entity_risks"]) for item in claims)}
- numeric claims: {sum(bool(item["numeric_risks"]) for item in claims)}
- negation-sensitive claims: {sum(bool(item["negation_risks"]) for item in claims)}

## Known limits

- Evidence is preserved verbatim; claims are not proof that an ASR entity or number is correct.
- Section-inferred speakers are sufficient for trend discovery but not exact quotation.
- Candidate extraction does not establish that a paper result generalizes beyond the presented evidence.
- This report cannot by itself establish causality, commercial impact, or correctness of a cited paper.
'''


def _media_brief_markdown(manifest: dict[str, Any], claims: list[dict[str, Any]], verification: list[dict[str, Any]]) -> str:
    ranked = sorted(claims, key=lambda item: (-item["importance_score"], -item["novelty_score"], item["source_time_start"]))
    themes = Counter(theme for claim in claims for theme in claim.get("themes", []))
    return f'''# Media brief: {manifest.get("title") or manifest["media_id"]}

- media: `{manifest["media_id"]}`
- mode: `{manifest["mode"]}`
- claims: {len(claims)}
- verification queue: {len(verification)}
- meaningful-unmerged claims: {sum(bool(item.get("from_meaningful_unmerged")) for item in claims)}
- exact-quote eligible claims: {sum(bool(item.get("exact_quote_allowed")) for item in claims)}

## Dominant themes

{chr(10).join(f'- {theme}: {count}' for theme, count in themes.most_common()) or '- none'}

## Highest-priority claims

{chr(10).join(f'- [{item["source_time_start"]:.1f}s]({item["source_url"]}) {item["claim"]}' for item in ranked[:10]) or '- none'}

This is a generated research brief. Exact quotation, speaker attribution, numeric claims, entities, and negation-sensitive conclusions remain governed by each claim's verification fields.
'''


def _validation_markdown(report: dict[str, Any]) -> str:
    return f'''# Phase 7.1 validation report

- mode: `{report["mode"]}`
- canonical records: {report["canonical_record_count"]}
- meaningful unmerged inputs: {report["meaningful_unmerged_input_count"]}
- high-recall seeds: {report["high_recall_seed_count"]}
- claims: {report["claim_count"]}
- evidence: {report["evidence_count"]}
- claims from meaningful unmerged: {report["claims_from_meaningful_unmerged"]}
- unsupported claims: {report["unsupported_claim_count"]}
- evidence traceability rate: {report["evidence_traceability_rate"]:.3f}
- trend candidates: {report["trend_candidate_count"]}
- verification queue: {report["verification_queue_count"]}
- judge backend/model: {report["judge"]["judge_backend"]} / {report["judge"]["judge_model"]}
'''

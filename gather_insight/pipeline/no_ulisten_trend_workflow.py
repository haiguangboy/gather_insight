"""Phase 7.0: two non-uListen transcript trend-mode ablation.

The blind runner refuses uListen files and previous fusion outputs. It uses the
existing Vecalign raw-cosine DP as a text-to-text alignment adapter; it does
not introduce a new alignment algorithm or tune its parameters.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from gather_insight.adapters.ulisten_parser import UlistenSegment
from gather_insight.adapters.usetranscribe_parser import parse_usetranscribe_file
from gather_insight.pipeline.alignment_text_builder import ALIGNMENT_TEXT_VERSION
from gather_insight.pipeline.evidence_builder import format_timestamp, youtube_timestamp_url
from gather_insight.pipeline.semantic_scorer import SemanticBackendUnavailable
from gather_insight.pipeline.semantic_unit_segmenter import SEMANTIC_UNIT_VERSION, SemanticUnit, segment_secondary_text
from gather_insight.pipeline.transcript_fuser import normalize_for_similarity
from gather_insight.pipeline.vecalign_alignment import align_vecalign

from .golden_annotation import _raw_cues, _segment_raw_spans, _unit_raw_map
from .trend_candidate_extractor import detect_text_conflicts, extract_high_value_candidates


_VTT_RANGE = re.compile(r"(?m)^(?P<start>\d{2}:\d{2}:\d{2}[.,]\d+)\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2}[.,]\d+).*?\n(?P<body>.*?)(?=\n\s*\n|\Z)", re.DOTALL)
_VTT_TAG = re.compile(r"<\d{2}:\d{2}:\d{2}[.,]\d+>|<[^>]+>")
_TOKEN = re.compile(r"\[[^\]]+\]|[A-Za-z0-9][A-Za-z0-9'_.%-]*")
_MEANINGFUL = re.compile(r"[A-Za-z]{4,}")
_TECHNICAL = re.compile(r"\b(?:model|data|compute|training|inference|diffusion|world|scaling|verification|paper|algorithm|latent|planning|PAC[- ]Bayes|generalization)\b", re.IGNORECASE)


@dataclass(frozen=True)
class BlindCaptionSegment:
    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str
    raw_char_start: int
    raw_char_end: int


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _parse_timestamp(value: str) -> float:
    hours, minutes, seconds = value.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _clean_caption(body: str) -> str:
    value = _VTT_TAG.sub("", body)
    value = re.sub(r"\s+", " ", value.replace("\n", " ")).strip()
    return value


def _norm_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _parse_rolling_vtt(raw: str, media_id: str) -> list[BlindCaptionSegment]:
    """Remove YouTube rolling-caption repeats while retaining cue provenance."""
    output: list[BlindCaptionSegment] = []
    emitted: list[str] = []
    for index, match in enumerate(_VTT_RANGE.finditer(raw), 1):
        text = _clean_caption(match.group("body"))
        if not text:
            continue
        token_matches = list(_TOKEN.finditer(text))
        current = [_norm_token(token.group(0)) for token in token_matches]
        previous_tail = emitted[-max(200, len(current) * 2):]
        overlap = 0
        for size in range(min(len(previous_tail), len(current)), 0, -1):
            if previous_tail[-size:] == current[:size]:
                overlap = size
                break
        if overlap >= len(current):
            continue
        novel_start = token_matches[overlap].start() if overlap < len(token_matches) else len(text)
        novel = text[novel_start:].strip()
        if not novel or len(_MEANINGFUL.findall(novel)) == 0:
            continue
        emitted.extend(current[overlap:])
        output.append(BlindCaptionSegment(
            segment_id=f"{media_id}.ytcap_{len(output) + 1:05d}",
            start_seconds=_parse_timestamp(match.group("start")),
            end_seconds=_parse_timestamp(match.group("end")),
            text=novel,
            raw_char_start=match.start(),
            raw_char_end=match.end(),
        ))
    return output


def _chapter_for(chapters: list[dict[str, Any]], start: float, end: float) -> dict[str, Any] | None:
    overlaps = [chapter for chapter in chapters if float(chapter["end_seconds"]) > start and float(chapter["start_seconds"]) < end]
    return max(overlaps, key=lambda item: min(end, float(item["end_seconds"])) - max(start, float(item["start_seconds"])), default=None)


def _speaker_info(chapters: list[dict[str, Any]], start: float, end: float, text: str) -> dict[str, Any]:
    chapter = _chapter_for(chapters, start, end)
    speaker = chapter.get("speaker") if chapter else None
    if not speaker:
        return {
            "speaker": None,
            "speaker_cluster": "unknown",
            "speaker_status": "unknown",
            "speaker_confidence": 0.0,
            "attribution_scope": "unknown",
            "boundary_confidence": 0.0,
            "speaker_evidence": [],
            "exact_quote_allowed": False,
        }
    chapter_start, chapter_end = float(chapter["start_seconds"]), float(chapter["end_seconds"])
    near_boundary = abs(start - chapter_start) <= 8 or abs(end - chapter_end) <= 8
    short_transition = len(_MEANINGFUL.findall(text)) < 12 or bool(re.search(r"\b(?:thank you|welcome|all right|okay|applause|music)\b", text, re.IGNORECASE))
    status = "boundary_uncertain" if near_boundary and short_transition else "section_inferred"
    confidence = 0.45 if status == "boundary_uncertain" else 0.82
    return {
        "speaker": speaker,
        "speaker_cluster": f"chapter_{int(chapters.index(chapter)) + 1:02d}",
        "speaker_status": status,
        "speaker_confidence": confidence,
        "attribution_scope": "section",
        "boundary_confidence": confidence,
        "speaker_evidence": [{"type": "youtube_chapter", "title": chapter.get("title"), "start_seconds": chapter_start, "end_seconds": chapter_end}],
        "exact_quote_allowed": False,
    }


def _ranges_for_units(units: list[SemanticUnit], raw_map: dict[str, dict[str, Any]], source: str) -> list[dict[str, Any]]:
    ranges: list[dict[str, Any]] = []
    for unit in units:
        mapped = raw_map.get(unit.unit_id)
        if not mapped:
            continue
        ranges.append({"source": source, "char_start": int(mapped["char_start"]), "char_end": int(mapped["char_end"]), "unit_id": unit.unit_id, "range_precision": mapped.get("range_precision", "exact")})
    return ranges


def _source_a_raw_map(parsed: Any, raw: str) -> dict[str, dict[str, Any]]:
    cues = _raw_cues(raw)
    spans = _segment_raw_spans(parsed, cues)
    units = segment_secondary_text(parsed.segments, max_unit_chars=260)
    mapped = _unit_raw_map(parsed, units, spans)
    return {unit_id: {"char_start": value["raw_char_start"], "char_end": value["raw_char_end"], "range_precision": "exact"} for unit_id, value in mapped.items()}


def _source_b_raw_map(units: list[SemanticUnit], segments: list[BlindCaptionSegment]) -> dict[str, dict[str, Any]]:
    by_id = {segment.segment_id: segment for segment in segments}
    return {
        unit.unit_id: {
            "char_start": by_id[unit.secondary_segment_id].raw_char_start,
            "char_end": by_id[unit.secondary_segment_id].raw_char_end,
            "range_precision": "cue_block",
        }
        for unit in units
        if unit.secondary_segment_id in by_id
    }


def _synthetic_source_segments(parsed: Any) -> tuple[list[UlistenSegment], list[SemanticUnit], dict[str, dict[str, Any]]]:
    raw = parsed["raw"]
    source_units = segment_secondary_text(parsed["segments"], max_unit_chars=260)
    raw_map = _source_a_raw_map(parsed["parsed"], raw)
    synthetic: list[UlistenSegment] = []
    for index, unit in enumerate(source_units, 1):
        synthetic.append(UlistenSegment(
            segment_id=unit.unit_id,
            media_id=parsed["media_id"],
            provider="blind_source_a",
            provider_id=None,
            speaker="unknown",
            chapter="",
            chapter_index=0,
            chapter_start_seconds=unit.approx_start_seconds,
            chapter_end_seconds=unit.approx_end_seconds,
            reference_url=None,
            start_seconds=unit.approx_start_seconds,
            end_seconds=max(unit.approx_start_seconds, unit.approx_end_seconds),
            timestamp=format_timestamp(unit.approx_start_seconds),
            end_timestamp=format_timestamp(unit.approx_end_seconds),
            text=unit.text,
            text_raw=unit.text,
            youtube_url=youtube_timestamp_url(parsed["youtube_url"], unit.approx_start_seconds),
        ))
    return synthetic, source_units, raw_map


def _meaningful(text: str) -> bool:
    return len(_MEANINGFUL.findall(text)) >= 10 or bool(_TECHNICAL.search(text))


def _source_agreement(score: float | None) -> str:
    if score is None:
        return "single_source"
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "medium"
    return "low"


def _build_blind_records(*, aligned: Any, source_units: list[SemanticUnit], target_units: list[SemanticUnit], source_a_map: dict[str, dict[str, Any]], source_b_map: dict[str, dict[str, Any]], target_segments: list[BlindCaptionSegment], chapters: list[dict[str, Any]], media_id: str, youtube_url: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    unmerged: list[dict[str, Any]] = []
    for position, step in enumerate(aligned.trace[0]["path"], 1):
        source_selected = source_units[int(step["source_indices"][0]):int(step["source_indices"][-1]) + 1] if step["source_indices"] else []
        target_selected = target_units[int(step["target_indices"][0]):int(step["target_indices"][-1]) + 1] if step["target_indices"] else []
        source_text = " ".join(unit.text.strip() for unit in source_selected).strip()
        target_text = " ".join(unit.text.strip() for unit in target_selected).strip()
        text = source_text or target_text
        start = min([unit.approx_start_seconds for unit in source_selected + target_selected], default=0.0)
        end = max([unit.approx_end_seconds for unit in source_selected + target_selected], default=start)
        speaker_info = _speaker_info(chapters, start, end, text)
        conflicts = detect_text_conflicts(source_text, target_text) if source_text and target_text else []
        score = float(step["raw_cosine"]) if step.get("raw_cosine") is not None else None
        operation = str(step["operation"])
        ranges = _ranges_for_units(source_selected, source_a_map, "usetranscribe") + _ranges_for_units(target_selected, source_b_map, "youtube_auto_caption")
        record = {
            "record_id": f"{media_id}.blind_{position:05d}",
            "media_id": media_id,
            "start_seconds": round(start, 3),
            "end_seconds": round(end, 3),
            "youtube_url": youtube_timestamp_url(youtube_url, start),
            "text": text,
            "source_a_text": source_text or None,
            "source_b_text": target_text or None,
            "text_sources": [value for value, present in (("usetranscribe", bool(source_text)), ("youtube_auto_caption", bool(target_text))) if present],
            "source_ranges": ranges,
            "source_a_unit_ids": [unit.unit_id for unit in source_selected],
            "source_b_unit_ids": [unit.unit_id for unit in target_selected],
            "source_agreement": _source_agreement(score) if source_text and target_text else ("source_a_only" if source_text else "source_b_only"),
            "raw_cosine": score,
            "alignment_operation": operation,
            "alignment_method": "vecalign_raw_cosine_text_to_text",
            "conflicts": conflicts,
            "needs_verification": bool(conflicts or (score is not None and score < 0.65) or speaker_info["speaker_status"] == "boundary_uncertain"),
            "speaker": speaker_info["speaker"],
            "speaker_cluster": speaker_info["speaker_cluster"],
            "speaker_status": speaker_info["speaker_status"],
            "speaker_confidence": speaker_info["speaker_confidence"],
            "attribution_scope": speaker_info["attribution_scope"],
            "boundary_confidence": speaker_info["boundary_confidence"],
            "speaker_evidence": speaker_info["speaker_evidence"],
            "exact_quote_allowed": speaker_info["exact_quote_allowed"],
            "chapter": (_chapter_for(chapters, start, end) or {}).get("title"),
            "provenance": {"source_a": "source_usetranscribe_raw.md", "source_b": "source_youtube_auto_caption_raw.en-orig.vtt"},
        }
        records.append(record)
        if (not source_selected or not target_selected) and _meaningful(text):
            unmerged.append({**record, "unmerged_reason": "source_a_gap" if source_selected else "source_b_gap"})
    return records, unmerged


def _html(records: list[dict[str, Any]], unmerged: list[dict[str, Any]], report: dict[str, Any]) -> str:
    cards: list[str] = []
    previous_speaker = None
    for record in records:
        if previous_speaker != record.get("speaker") and previous_speaker is not None:
            cards.append('<div class="switch">speaker/section boundary</div>')
        risk = " risk" if record.get("needs_verification") else ""
        cards.append(
            f'<article class="record{risk}"><header><a href="{html.escape(str(record["youtube_url"]))}" target="_blank">{format_timestamp(float(record["start_seconds"]))}</a>–{format_timestamp(float(record["end_seconds"]))} · <strong>{html.escape(str(record.get("speaker") or "unknown"))}</strong> · {html.escape(str(record.get("speaker_status")))} · {html.escape(str(record.get("source_agreement")))}</header>'
            f'<p class="chapter">{html.escape(str(record.get("chapter") or ""))}</p><div class="text">{html.escape(str(record.get("text") or ""))}</div>'
            f'<details><summary>provenance, risks and source text</summary><p>sources: {html.escape(", ".join(record.get("text_sources", [])))} · operation {html.escape(str(record.get("alignment_operation")))} · raw cosine {record.get("raw_cosine")}</p><pre>{html.escape(json.dumps({"source_a_text": record.get("source_a_text"), "source_b_text": record.get("source_b_text"), "source_ranges": record.get("source_ranges"), "conflicts": record.get("conflicts"), "speaker_evidence": record.get("speaker_evidence")}, ensure_ascii=False, indent=2))}</pre></details></article>'
        )
        previous_speaker = record.get("speaker")
    unmerged_html = "".join(f'<details class="unmerged"><summary>{html.escape(str(item.get("start_seconds")))} · {html.escape(str(item.get("unmerged_reason")))} · {html.escape(str(item.get("text"))[:180])}</summary><pre>{html.escape(str(item.get("text")))}</pre></details>' for item in unmerged)
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>No-uListen trend mode</title><style>body{{font:15px/1.55 system-ui;max-width:1100px;margin:24px auto;color:#222}}.summary{{padding:16px;background:#eef3f7;border-radius:8px}}.record{{padding:14px;border-bottom:1px solid #ddd}}.record.risk{{background:#fff6df}}.switch{{border-top:3px solid #64788b;margin-top:22px;padding-top:8px;color:#536575}}.text{{white-space:pre-wrap;margin:8px 0}}.chapter{{color:#566}}.unmerged{{background:#eef8ee;border-left:5px solid #568856;padding:9px;margin:6px 0}}pre{{white-space:pre-wrap}}</style></head><body><h1>No-uListen dual-text trend mode</h1><div class="summary"><p>{report.get("record_count")} records · {report.get("matched_record_count")} matched · {report.get("meaningful_unmerged_count")} meaningful unmerged · {report.get("conflict_count")} conflict records</p><p>Speaker attribution is section-level unless explicitly stated otherwise; exact_quote_allowed is false for inferred speakers.</p><details><summary>Run provenance and diagnostics</summary><pre>{html.escape(json.dumps(report, ensure_ascii=False, indent=2))}</pre></details></div>{''.join(cards)}<h2>Meaningful unmerged content</h2>{unmerged_html}</body></html>'''


def _shared_upstream_score(left: str, right: str) -> dict[str, Any]:
    left_norm, right_norm = normalize_for_similarity(left), normalize_for_similarity(right)
    if not left_norm or not right_norm:
        return {"normalized_sequence_similarity": 0.0, "shared_8gram_rate": 0.0, "assessment": "insufficient_text"}
    grams_left = {left_norm[index:index + 8] for index in range(max(0, len(left_norm) - 7))}
    grams_right = {right_norm[index:index + 8] for index in range(max(0, len(right_norm) - 7))}
    rate = len(grams_left & grams_right) / max(1, len(grams_left))
    score = SequenceMatcher(None, left_norm, right_norm, autojunk=False).ratio()
    return {"normalized_sequence_similarity": round(score, 6), "shared_8gram_rate": round(rate, 6), "assessment": "likely_shared_upstream_or_same_audio" if rate >= 0.35 else "independent_or_heavily_rewritten"}


def _load_manifest(input_dir: Path) -> dict[str, Any]:
    manifest = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
    contract = manifest.get("blind_input_contract", {})
    if contract.get("ulisten_allowed") is not False:
        raise ValueError("Phase 7.0 blind input must explicitly set ulisten_allowed=false")
    if (input_dir / "source_ulisten_raw.md").exists() or any("ulisten" in path.name.lower() for path in input_dir.iterdir()):
        raise ValueError("Phase 7.0 blind input contains a uListen file")
    forbidden = {"transcript_fused.jsonl", "alignment_trace.jsonl", "unallocated_secondary.jsonl"}
    if any(path.name in forbidden for path in input_dir.iterdir()):
        raise ValueError("Phase 7.0 blind input contains a derived fusion output")
    return manifest


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def run_no_ulisten_trend(*, input_dir: Path, output_dir: Path, semantic_config: dict[str, Any] | None = None, cache_root: Path | None = None) -> dict[str, Any]:
    manifest = _load_manifest(input_dir)
    media_id = str(manifest["media_id"])
    youtube_url = str(manifest["youtube_url"])
    source_a_path = input_dir / "source_usetranscribe_raw.md"
    source_b_path = input_dir / "source_youtube_auto_caption_raw.en-orig.vtt"
    if not source_a_path.exists() or not source_b_path.exists():
        raise ValueError("Phase 7.0 requires source_usetranscribe_raw.md and source_youtube_auto_caption_raw.en-orig.vtt")
    source_a_raw = source_a_path.read_text(encoding="utf-8")
    source_a = parse_usetranscribe_file(path=source_a_path, media_id=media_id, youtube_url=youtube_url, video_duration_seconds=float(manifest.get("duration_seconds") or 0))
    source_b_raw = source_b_path.read_text(encoding="utf-8")
    caption_segments = _parse_rolling_vtt(source_b_raw, media_id)
    if not caption_segments:
        raise ValueError("no non-empty rolling YouTube caption segments found")
    target_units = segment_secondary_text(caption_segments, max_unit_chars=260)
    source_payload = {"parsed": source_a, "raw": source_a_raw, "media_id": media_id, "youtube_url": youtube_url, "segments": source_a.segments}
    synthetic_segments, source_units, source_a_map = _synthetic_source_segments(source_payload)
    source_b_map = _source_b_raw_map(target_units, caption_segments)
    config = dict(semantic_config or {})
    config.update({"mode": str((semantic_config or {}).get("mode", "local_semantic")), "alignment_algorithm": "vecalign", "score_mode": "raw_cosine"})
    config.setdefault("vecalign", {"max_alignment_size": 7, "max_source_concatenations": 3, "max_target_concatenations": 6})
    embedding = dict(config.get("embedding") or {})
    embedding.setdefault("model", "bge-m3:latest")
    embedding.setdefault("normalize", True)
    embedding.setdefault("dim", 1024)
    embedding.setdefault("base_url", "http://localhost:11434")
    embedding.setdefault("cache_path", ".embcache/phase_7_0_no_ulisten.embeddings.jsonl")
    config["embedding"] = embedding
    try:
        aligned = align_vecalign(structure_segments=synthetic_segments, secondary_segments=caption_segments, config_value=config, cache_root=cache_root)
    except SemanticBackendUnavailable as exc:
        raise ValueError(f"semantic backend unavailable; Phase 7.0 cannot claim active semantic alignment: {exc}") from exc
    chapters = list(((manifest.get("youtube_metadata") or {}).get("chapters") or []))
    records, unmerged = _build_blind_records(aligned=aligned, source_units=source_units, target_units=target_units, source_a_map=source_a_map, source_b_map=source_b_map, target_segments=caption_segments, chapters=chapters, media_id=media_id, youtube_url=youtube_url)
    conflicts = [record for record in records if record.get("conflicts")]
    source_a_joined = " ".join(segment.text for segment in source_a.segments)
    source_b_joined = " ".join(segment.text for segment in caption_segments)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "ok",
        "mode": "dual_text_trend_mode",
        "blind": True,
        "media_id": media_id,
        "source_provenance": {
            "source_a": {"provider": "usetranscribe_manual_export", "path": source_a_path.name, "sha256": _sha256(source_a_path), "segment_count": len(source_a.segments)},
            "source_b": {"provider": "youtube_auto_caption", "path": source_b_path.name, "sha256": _sha256(source_b_path), "segment_count": len(caption_segments), "raw_cue_count": len(list(_VTT_RANGE.finditer(source_b_raw)))},
        },
        "source_a_segment_count": len(source_a.segments),
        "source_b_segment_count": len(caption_segments),
        "source_a_semantic_unit_count": len(source_units),
        "source_b_semantic_unit_count": len(target_units),
        "record_count": len(records),
        "matched_record_count": sum(bool(row.get("source_a_text") and row.get("source_b_text")) for row in records),
        "meaningful_unmerged_count": len(unmerged),
        "conflict_count": len(conflicts),
        "speaker_status_distribution": {status: sum(row.get("speaker_status") == status for row in records) for status in ("source_provided", "audio_confirmed", "section_inferred", "probable", "boundary_uncertain", "unknown") if any(row.get("speaker_status") == status for row in records)},
        "speaker_confidence_distribution": {"section_inferred_or_better": sum(float(row.get("speaker_confidence") or 0) >= 0.75 for row in records), "boundary_uncertain": sum(row.get("speaker_status") == "boundary_uncertain" for row in records), "unknown": sum(row.get("speaker_status") == "unknown" for row in records)},
        "shared_upstream_assessment": _shared_upstream_score(source_a_joined, source_b_joined),
        "alignment": {**aligned.diagnostics, "semantic_backend": aligned.scorer_metadata.get("semantic_backend"), "semantic_model": aligned.scorer_metadata.get("embedding_model"), "semantic_alignment_degraded": aligned.scorer_metadata.get("semantic_alignment_degraded"), "alignment_text_version": ALIGNMENT_TEXT_VERSION, "semantic_unit_version": SEMANTIC_UNIT_VERSION},
        "input_files": {path.name: _sha256(path) for path in (source_a_path, source_b_path)},
    }
    _write_jsonl(output_dir / "no_ulisten_fused.jsonl", records)
    _write_jsonl(output_dir / "meaningful_unmerged.jsonl", unmerged)
    _write_jsonl(output_dir / "conflict_queue.jsonl", conflicts)
    _write_jsonl(output_dir / "no_ulisten_high_value_candidates.jsonl", extract_high_value_candidates([*records, *unmerged], media_id=media_id, source_mode="no_ulisten"))
    (output_dir / "alignment_trace.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in aligned.trace), encoding="utf-8")
    (output_dir / "processing_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "no_ulisten_fused_reading_view.html").write_text(_html(records, unmerged, report), encoding="utf-8")
    freeze_files = [path for path in output_dir.iterdir() if path.is_file() and path.name != "blind_freeze_manifest.json"]
    frozen = {path.name: _sha256(path) for path in sorted(freeze_files)}
    freeze = {"status": "frozen", "experiment": "phase_7_0_no_ulisten_trend_mode_ablation", "input_sha256": report["input_files"], "output_sha256": frozen, "record_count": len(records), "candidate_count": len(_jsonl(output_dir / "no_ulisten_high_value_candidates.jsonl"))}
    (output_dir / "blind_freeze_manifest.json").write_text(json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**report, "output_dir": str(output_dir.resolve()), "freeze_manifest": str((output_dir / "blind_freeze_manifest.json").resolve()), "candidate_count": freeze["candidate_count"]}


def _supported_records(result_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fused = _jsonl(result_dir / "transcript_fused.jsonl")
    rows: list[dict[str, Any]] = []
    for record in fused:
        confidence = record.get("alignment_confidence")
        rows.append({
            "record_id": record.get("segment_id"), "segment_id": record.get("segment_id"), "start_seconds": record.get("start_seconds"), "end_seconds": record.get("end_seconds"), "text": record.get("text"), "speaker": record.get("speaker"), "speaker_status": "source_provided", "speaker_confidence": 1.0, "attribution_scope": "segment", "exact_quote_allowed": not bool(record.get("needs_review")), "source_agreement": "high" if confidence is not None and confidence >= 0.85 else "medium" if confidence is not None and confidence >= 0.65 else "low", "source_ranges": ([{"source": "usetranscribe", "char_start": record.get("secondary_char_start"), "char_end": record.get("secondary_char_end"), "range_precision": "semantic_projection"}] if record.get("secondary_char_start") is not None else []), "conflicts": record.get("conflicts", []), "needs_verification": bool(record.get("needs_review")),
        })
    unmerged_path = result_dir / "unallocated_secondary.jsonl"
    unmerged = _jsonl(unmerged_path) if unmerged_path.exists() else []
    extra: list[dict[str, Any]] = []
    for index, row in enumerate(unmerged, 1):
        extra.append({"record_id": f"unallocated_{index:04d}", "start_seconds": row.get("approx_start_seconds", 0), "end_seconds": row.get("approx_end_seconds", 0), "text": row.get("text"), "speaker": None, "speaker_status": "unknown", "speaker_confidence": 0.0, "attribution_scope": "unknown", "exact_quote_allowed": False, "source_agreement": "source_a_only", "source_ranges": [], "conflicts": [], "needs_verification": True})
    return rows, extra


def _candidate_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    topic_bonus = 0.25 if left.get("topic_key") == right.get("topic_key") else 0.0
    text_score = SequenceMatcher(None, normalize_for_similarity(str(left.get("supporting_text"))), normalize_for_similarity(str(right.get("supporting_text"))), autojunk=False).ratio()
    return min(1.0, topic_bonus + 0.75 * text_score)


def _topic_time_related(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("topic_key") != right.get("topic_key"):
        return False
    left_start, left_end = float(left.get("start_seconds") or 0.0), float(left.get("end_seconds") or 0.0)
    right_start, right_end = float(right.get("start_seconds") or 0.0), float(right.get("end_seconds") or 0.0)
    overlaps = min(left_end, right_end) >= max(left_start, right_start)
    center_distance = abs((left_start + left_end) / 2 - (right_start + right_end) / 2)
    return overlaps or center_distance <= 90


def compare_phase7_trend(*, blind_output_dir: Path, ulisten_result_dir: Path, output_dir: Path) -> dict[str, Any]:
    freeze_path = blind_output_dir / "blind_freeze_manifest.json"
    if not freeze_path.exists():
        raise ValueError("blind Phase 7.0 output is not frozen; comparison is refused")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    for name, expected in freeze["output_sha256"].items():
        path = blind_output_dir / name
        if not path.exists() or _sha256(path) != expected:
            raise ValueError(f"blind output changed after freeze: {name}")
    output_dir.mkdir(parents=True, exist_ok=True)
    blind_candidates = _jsonl(blind_output_dir / "no_ulisten_high_value_candidates.jsonl")
    supported_rows, supported_extra = _supported_records(ulisten_result_dir)
    media_id = str(blind_candidates[0]["candidate_id"]).split(".trend_", 1)[0] if blind_candidates else "yt_wE1ZgJdt4uM"
    supported_candidates = extract_high_value_candidates([*supported_rows, *supported_extra], media_id=media_id, source_mode="ulisten_supported")
    _write_jsonl(output_dir / "ulisten_supported_high_value_candidates.jsonl", supported_candidates)
    matches: list[dict[str, Any]] = []
    used: set[str] = set()
    for candidate in blind_candidates:
        choices = sorted((( _candidate_similarity(candidate, other), other) for other in supported_candidates if other["candidate_id"] not in used), key=lambda pair: pair[0], reverse=True)
        if choices and choices[0][0] >= 0.55:
            score, other = choices[0]
            used.add(other["candidate_id"])
            matches.append({"no_ulisten_candidate_id": candidate["candidate_id"], "ulisten_supported_candidate_id": other["candidate_id"], "similarity": round(score, 6), "same_topic": candidate.get("topic_key") == other.get("topic_key"), "trend_implication_changed": candidate.get("trend_implication") != other.get("trend_implication")})
    blind_topics = {candidate.get("topic_key") for candidate in blind_candidates}
    supported_topics = {candidate.get("topic_key") for candidate in supported_candidates}
    supported_covered = {right["candidate_id"] for right in supported_candidates if any(_topic_time_related(left, right) for left in blind_candidates)}
    blind_covered = {left["candidate_id"] for left in blind_candidates if any(_topic_time_related(left, right) for right in supported_candidates)}
    blind_nonconsensus = [candidate for candidate in blind_candidates if candidate.get("non_consensus_signal")]
    supported_nonconsensus = [candidate for candidate in supported_candidates if candidate.get("non_consensus_signal")]
    supported_nonconsensus_covered = {right["candidate_id"] for right in supported_nonconsensus if any(_topic_time_related(left, right) for left in blind_nonconsensus)}
    supported_only = [candidate for candidate in supported_candidates if candidate["candidate_id"] not in supported_covered]
    blind_only = [candidate for candidate in blind_candidates if candidate["candidate_id"] not in blind_covered]
    report = {
        "status": "ok",
        "experiment": "phase_7_0_no_ulisten_trend_mode_ablation",
        "blind_output_frozen": True,
        "no_ulisten_candidate_count": len(blind_candidates),
        "ulisten_supported_candidate_count": len(supported_candidates),
        "strict_one_to_one_candidate_match_count": len(matches),
        "strict_one_to_one_recall_proxy": round(len(matches) / max(1, len(supported_candidates)), 6),
        "topic_time_candidate_recall_proxy": round(len(supported_covered) / max(1, len(supported_candidates)), 6),
        "topic_time_candidate_precision_proxy": round(len(blind_covered) / max(1, len(blind_candidates)), 6),
        "non_consensus_recall_proxy": round(len(supported_nonconsensus_covered) / max(1, len(supported_nonconsensus)), 6),
        "technical_route_overlap": sorted(blind_topics & supported_topics),
        "only_no_ulisten_topics": sorted(blind_topics - supported_topics),
        "only_ulisten_supported_topics": sorted(supported_topics - blind_topics),
        "trend_judgment_substantive_change": bool(blind_topics != supported_topics),
        "matches": matches,
        "key_omissions": [{"candidate_id": item["candidate_id"], "topic": item["topic"], "start_seconds": item["start_seconds"], "claim": item["claim"]} for item in supported_only[:20]],
        "no_ulisten_only_candidates": [{"candidate_id": item["candidate_id"], "topic": item["topic"], "start_seconds": item["start_seconds"], "claim": item["claim"]} for item in blind_only[:20]],
        "verification_risk_summary": {
            "no_ulisten_candidates_needing_verification": sum(bool(item.get("needs_verification")) for item in blind_candidates),
            "ulisten_supported_candidates_needing_verification": sum(bool(item.get("needs_verification")) for item in supported_candidates),
            "no_ulisten_candidates_with_conflicts": sum(bool(item.get("conflicts")) for item in blind_candidates),
            "no_ulisten_numeric_risk_candidates": sum(bool(item.get("numeric_risks")) for item in blind_candidates),
            "no_ulisten_negation_risk_candidates": sum(bool(item.get("negation_risks")) for item in blind_candidates),
        },
        "speaker_effect": {"note": "Speaker was not used as a matching key; compare topic/claim candidates first. Inferred section speakers are not exact quote permission.", "no_ulisten_section_candidates": sum(candidate.get("speaker_status") == "section_inferred" for candidate in blind_candidates), "no_ulisten_boundary_uncertain_candidates": sum(candidate.get("speaker_status") == "boundary_uncertain" for candidate in blind_candidates), "supported_source_provided_candidates": sum(candidate.get("speaker_status") == "source_provided" for candidate in supported_candidates)},
        "limitations": ["This is a proxy comparison without an external human gold set.", "YouTube en-orig auto captions and UseTranscribe may share the same upstream audio/caption signal.", "Candidate extraction is deterministic high-recall and does not establish factual truth."],
        "blind_freeze_sha256": _sha256(freeze_path),
    }
    (output_dir / "phase_7_0_comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "no_ulisten_trend_comparison.md").write_text(_comparison_markdown(report), encoding="utf-8")
    return {**report, "output_dir": str(output_dir.resolve())}


def _comparison_markdown(report: dict[str, Any]) -> str:
    return f'''# Phase 7.0 No-uListen Trend-Mode Ablation

## Experimental integrity

The no-uListen run was frozen before this comparison. It used only the two non-uListen sources and did not read uListen structure, chapters, speakers, segment boundaries, or Phase 6.x fusion outputs. The frozen manifest hash is `{report["blind_freeze_sha256"]}`.

## Candidate comparison

- no-uListen candidates: **{report["no_ulisten_candidate_count"]}**
- uListen-supported candidates: **{report["ulisten_supported_candidate_count"]}**
- strict one-to-one matched pairs: **{report["strict_one_to_one_candidate_match_count"]}**
- strict one-to-one recall proxy: **{report["strict_one_to_one_recall_proxy"]:.3f}**
- topic/time candidate recall proxy: **{report["topic_time_candidate_recall_proxy"]:.3f}**
- topic/time candidate precision proxy: **{report["topic_time_candidate_precision_proxy"]:.3f}**
- non-consensus recall proxy: **{report["non_consensus_recall_proxy"]:.3f}**
- substantive trend-set change: **{report["trend_judgment_substantive_change"]}**

## Technical routes

- shared: {", ".join(report["technical_route_overlap"]) or "none"}
- only no-uListen: {", ".join(report["only_no_ulisten_topics"]) or "none"}
- only uListen-supported: {", ".join(report["only_ulisten_supported_topics"]) or "none"}

## Speaker impact

{report["speaker_effect"]["note"]}

- no-uListen section-inferred candidates: {report["speaker_effect"]["no_ulisten_section_candidates"]}
- no-uListen boundary-uncertain candidates: {report["speaker_effect"]["no_ulisten_boundary_uncertain_candidates"]}
- uListen-supported source-provided candidates: {report["speaker_effect"]["supported_source_provided_candidates"]}

## Key omissions after topic/time matching

{chr(10).join(f"- {item['start_seconds']:.1f}s · {item['topic']} · {item['claim']}" for item in report["key_omissions"]) or "- none detected by this proxy"}

## Candidates recovered only in the no-uListen view

{chr(10).join(f"- {item['start_seconds']:.1f}s · {item['topic']} · {item['claim']}" for item in report["no_ulisten_only_candidates"]) or "- none detected by this proxy"}

## Interpretation limits

{chr(10).join(f"- {item}" for item in report["limitations"])}

The two-pass policy remains: first retain all transcript records, meaningful unmerged content, and conflicts for high recall; then manually verify only the small set of high-value candidates before exact attribution or quotation.
'''

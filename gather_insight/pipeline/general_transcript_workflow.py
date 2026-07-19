from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from gather_insight.adapters.official_transcript_parser import OfficialTranscriptSegment, parse_official_transcript_file
from gather_insight.adapters.ulisten_parser import UlistenSegment, parse_ulisten_file
from gather_insight.adapters.usetranscribe_parser import UseTranscribeSegment, parse_usetranscribe_file
from gather_insight.pipeline.ids import media_id_for_url
from gather_insight.pipeline.semantic_alignment import align_semantically, allocation_record
from gather_insight.pipeline.semantic_scorer import SemanticBackendUnavailable
from gather_insight.pipeline.source_resolver import TranscriptCombinationResolution, resolve_transcript_combination
from gather_insight.pipeline.transcript_fuser import FusedSegment, fuse_transcripts
from gather_insight.run_logging import RunLogger

from .general_transcript_outputs import write_general_outputs


class GeneralTranscriptWorkflowError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest(input_dir: Path) -> dict[str, Any]:
    path = input_dir / "manifest.json"
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GeneralTranscriptWorkflowError("manifest.json must contain an object")
    return value


def _generic_record(*, segment_id: str, media_id: str, speaker: str | None, chapter: str | None, chapter_index: int | None, start: float, end: float, text: str, youtube_url: str, mode: str, structure_source: str, text_source: str, source_is_fixture: bool = False, text_ulisten_raw: str | None = None, text_usetranscribe_raw: str | None = None, text_official_raw: str | None = None, needs_review: bool = False, review_reasons: list[str] | None = None, speaker_needs_review: bool = False, speaker_status: str | None = None, speaker_review_reasons: list[str] | None = None, structure_status: str = "source_provided", alignment_method: str = "single_source_no_alignment", alignment_confidence: float | None = None, alignment_components: dict[str, float] | None = None, conflicts: list[dict[str, object]] | None = None, reference_url: str | None = None) -> dict[str, object]:
    return {
        "segment_id": segment_id,
        "media_id": media_id,
        "speaker": speaker,
        "chapter": chapter,
        "chapter_index": chapter_index,
        "reference_url": reference_url,
        "start_seconds": start,
        "end_seconds": end,
        "text": text,
        "text_ulisten_raw": text_ulisten_raw,
        "text_usetranscribe_raw": text_usetranscribe_raw,
        "text_official_raw": text_official_raw,
        "structure_source": structure_source,
        "text_source": text_source,
        "source_is_fixture": source_is_fixture,
        "alignment_method": alignment_method,
        "alignment_confidence": alignment_confidence,
        "alignment_components": alignment_components,
        "needs_review": needs_review,
        "review_reasons": review_reasons or [],
        "conflicts": conflicts or [],
        "youtube_url": youtube_url,
        "fusion_mode": mode,
        "speaker_needs_review": speaker_needs_review,
        "speaker_status": speaker_status or ("source_provided" if speaker else "unknown_needs_review"),
        "speaker_review_reasons": speaker_review_reasons or ([] if speaker else ["speaker_attribution_pending"]),
        "text_status": "readable" if text else "empty",
        "structure_status": structure_status,
    }


def _from_fused(segment: FusedSegment, *, mode: str, text_source: str, official: bool = False, source_is_fixture: bool = False) -> dict[str, object]:
    record = segment.as_dict()
    selected_text_source = text_source if segment.text_source == "usetranscribe_manual_export" else segment.text_source
    if official:
        record["text_official_raw"] = record.pop("text_usetranscribe_raw")
        record["text_usetranscribe_raw"] = None
        for conflict in record.get("conflicts", []):
            if "usetranscribe" in conflict:
                conflict["official_transcript"] = conflict.pop("usetranscribe")
    else:
        record["text_official_raw"] = None
    record.update({
        "fusion_mode": mode,
        "text_source": selected_text_source,
        "source_is_fixture": source_is_fixture,
        "speaker_needs_review": False,
        "speaker_status": "source_provided",
        "speaker_review_reasons": [],
        "text_status": "readable" if record["text"] else "empty",
        "structure_status": "source_provided",
    })
    return record


def _single_records(segments: list[UseTranscribeSegment] | list[OfficialTranscriptSegment], *, mode: str, text_source: str, structure_source: str, fixture: bool = False) -> list[dict[str, object]]:
    records = []
    for segment in segments:
        speaker = getattr(segment, "speaker", None)
        chapter = getattr(segment, "chapter", None)
        is_official = getattr(segment, "provider", "") == "official_transcript"
        text = segment.text
        records.append(_generic_record(
            segment_id=segment.segment_id,
            media_id=segment.media_id,
            speaker=speaker,
            chapter=chapter,
            chapter_index=getattr(segment, "chapter_index", None),
            start=segment.start_seconds,
            end=segment.end_seconds,
            text=text,
            youtube_url=segment.youtube_url,
            mode=mode,
            structure_source=structure_source,
            text_source=text_source,
            source_is_fixture=fixture,
            text_usetranscribe_raw=text if not is_official else None,
            text_official_raw=text if is_official else None,
            speaker_needs_review=speaker is None,
            speaker_status="source_provided" if speaker else "unknown_needs_review",
            speaker_review_reasons=[] if speaker else ["speaker_attribution_pending"],
            structure_status="source_provided" if is_official else "text_timeline_only",
            reference_url=getattr(segment, "reference_url", None),
        ))
    return records


def _resolution_metadata(resolution: TranscriptCombinationResolution, *, media_id: str, youtube_url: str, input_dir: Path, fixture_flags: dict[str, bool]) -> dict[str, Any]:
    return {
        "schema_version": "gather_insight_general_transcript_v1",
        "media_id": media_id,
        "youtube_url": youtube_url,
        "input_dir": str(input_dir),
        "fusion_mode": resolution.fusion_mode,
        "structure_source": resolution.structure_source,
        "text_source": resolution.text_source,
        "sources": {name: state.as_dict() for name, state in resolution.sources.items()},
        "limitations": resolution.limitations,
        "unused_sources": resolution.unused_sources,
        "fixture_flags": fixture_flags,
    }


_SEMANTIC_RUNTIME_KEYS = {
    "embedding_api_call_count", "embedding_cache_hit_count", "embedding_text_count", "embedding_seconds",
    "judge_call_count", "judge_cache_hit_count", "judge_abstain_count", "judge_escalation_count",
    "judge_api_seconds", "judge_prompt_tokens", "judge_completion_tokens",
}


def _stable_semantic_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key not in _SEMANTIC_RUNTIME_KEYS}


def run_general_transcript_workflow(*, input_dir: Path, output_root: Path = Path("data/media"), fixture_flags: dict[str, bool] | None = None, semantic_config: dict[str, Any] | None = None, semantic_cache_root: Path | None = None, logger: RunLogger | None = None) -> dict[str, Any]:
    manifest = _manifest(input_dir)
    youtube_url = str(manifest.get("youtube_url") or "")
    canonical_id = str(manifest.get("canonical_youtube_video_id") or "")
    if not youtube_url and canonical_id:
        youtube_url = f"https://www.youtube.com/watch?v={canonical_id}"
    if not youtube_url:
        raise GeneralTranscriptWorkflowError("manifest must provide youtube_url or canonical_youtube_video_id")
    try:
        media_id, youtube_url = media_id_for_url(youtube_url)
    except ValueError as exc:
        raise GeneralTranscriptWorkflowError(str(exc)) from exc
    media_dir = output_root / media_id
    output_dir = media_dir / "general"
    media_dir.mkdir(parents=True, exist_ok=True)
    logger = logger or RunLogger("fuse-general", global_log=output_root / "_logs" / "gather_insight.jsonl")
    logger.bind_media(media_id, media_dir)
    fixture_flags = fixture_flags or (manifest.get("fixture_flags") or {})
    semantic_config = dict(semantic_config or manifest.get("semantic_alignment") or {"mode": "lexical_only"})
    semantic_config.setdefault("mode", "lexical_only")
    semantic_cache_root = semantic_cache_root or Path(".")
    logger.event("INFO", "general_fusion.started", "general transcript workflow started", input_dir=input_dir, output_dir=output_dir)
    report_path = output_dir / "processing_report.json"
    input_hashes_before: dict[str, str] = {}
    resolution: TranscriptCombinationResolution | None = None
    try:
        parsed_video_id = media_id.removeprefix("yt_") if media_id.startswith("yt_") else None
        if canonical_id and canonical_id != parsed_video_id:
            raise GeneralTranscriptWorkflowError(
                "canonical_youtube_video_id does not match youtube_url video_id: "
                f"{canonical_id!r} != {parsed_video_id!r}"
            )
        resolution = resolve_transcript_combination(input_dir=input_dir, fixture_flags=fixture_flags, logger=logger)
        if resolution.fusion_mode == "failed":
            raise GeneralTranscriptWorkflowError("all transcript sources are missing")
        for state in resolution.sources.values():
            if state.available:
                input_hashes_before[state.filename] = _sha256(state.path)
        parsed_ulisten = None
        if resolution.sources["ulisten"].available:
            parsed_ulisten = parse_ulisten_file(
                path=resolution.sources["ulisten"].path,
                media_id=media_id,
                youtube_url=youtube_url,
                provider_id=str((manifest.get("ulisten_source") or {}).get("provider_page_id") or "") or None,
            )
        duration = float(manifest.get("duration_seconds") or (parsed_ulisten.chapters[-1].end_seconds if parsed_ulisten else 0))
        parsed_use = None
        parsed_official = None
        if resolution.sources["usetranscribe"].available:
            parsed_use = parse_usetranscribe_file(path=resolution.sources["usetranscribe"].path, media_id=media_id, youtube_url=youtube_url, video_duration_seconds=duration)
        if resolution.sources["official_transcript"].available:
            parsed_official = parse_official_transcript_file(path=resolution.sources["official_transcript"].path, media_id=media_id, youtube_url=youtube_url)

        fusion_diagnostics = None
        semantic_diagnostics = None
        semantic_metadata = None
        semantic_report_diagnostics = None
        semantic_report_metadata = None
        alignment_trace: list[dict[str, object]] = []
        unallocated_units: list[dict[str, object]] = []
        if resolution.fusion_mode == "dual_source":
            source_fixture = resolution.sources["usetranscribe"].is_fixture
            active_config = dict(semantic_config)
            try:
                aligned = align_semantically(structure_segments=parsed_ulisten.segments, secondary_segments=parsed_use.segments, config_value=active_config, cache_root=semantic_cache_root)
            except SemanticBackendUnavailable as exc:
                logger.event("ERROR", "semantic_alignment.degraded", "semantic backend unavailable; using explicit lexical fallback", error=str(exc), requested_mode=active_config.get("mode"))
                active_config = {**active_config, "mode": "lexical_only"}
                aligned = align_semantically(structure_segments=parsed_ulisten.segments, secondary_segments=parsed_use.segments, config_value=active_config, cache_root=semantic_cache_root)
                aligned.diagnostics["semantic_alignment_degraded"] = True
                aligned.diagnostics["semantic_backend_error"] = str(exc)
            records = [allocation_record(allocation, aligned.units, text_source="usetranscribe_format_fixture" if source_fixture else "usetranscribe_manual_export", official=False, source_is_fixture=source_fixture) for allocation in aligned.allocations]
            semantic_report_diagnostics = dict(aligned.diagnostics)
            semantic_diagnostics = _stable_semantic_mapping(semantic_report_diagnostics)
            fusion_diagnostics = {key: semantic_diagnostics[key] for key in ("secondary_segment_reuse_count", "cross_speaker_boundary_count", "adjacent_text_duplication_rate", "unconsumed_secondary_segment_count")}
            semantic_report_metadata = {"config": aligned.config.as_dict(), "scorer": aligned.scorer_metadata, "judge": aligned.judge_metadata, "elapsed_seconds": aligned.elapsed_seconds}
            semantic_metadata = {"config": aligned.config.as_dict(), "scorer": _stable_semantic_mapping(aligned.scorer_metadata), "judge": _stable_semantic_mapping(aligned.judge_metadata)}
            alignment_trace = aligned.trace
            unallocated_units = [unit.as_dict() for unit in aligned.unallocated_units]
        elif resolution.fusion_mode == "official_dual":
            source_fixture = resolution.sources["official_transcript"].is_fixture
            active_config = dict(semantic_config)
            try:
                aligned = align_semantically(structure_segments=parsed_ulisten.segments, secondary_segments=parsed_official.segments, config_value=active_config, cache_root=semantic_cache_root)
            except SemanticBackendUnavailable as exc:
                logger.event("ERROR", "semantic_alignment.degraded", "semantic backend unavailable; using explicit lexical fallback", error=str(exc), requested_mode=active_config.get("mode"))
                active_config = {**active_config, "mode": "lexical_only"}
                aligned = align_semantically(structure_segments=parsed_ulisten.segments, secondary_segments=parsed_official.segments, config_value=active_config, cache_root=semantic_cache_root)
                aligned.diagnostics["semantic_alignment_degraded"] = True
                aligned.diagnostics["semantic_backend_error"] = str(exc)
            records = [allocation_record(allocation, aligned.units, text_source="official_transcript_format_fixture" if source_fixture else "official_transcript", official=True, source_is_fixture=source_fixture) for allocation in aligned.allocations]
            semantic_report_diagnostics = dict(aligned.diagnostics)
            semantic_diagnostics = _stable_semantic_mapping(semantic_report_diagnostics)
            fusion_diagnostics = {key: semantic_diagnostics[key] for key in ("secondary_segment_reuse_count", "cross_speaker_boundary_count", "adjacent_text_duplication_rate", "unconsumed_secondary_segment_count")}
            semantic_report_metadata = {"config": aligned.config.as_dict(), "scorer": aligned.scorer_metadata, "judge": aligned.judge_metadata, "elapsed_seconds": aligned.elapsed_seconds}
            semantic_metadata = {"config": aligned.config.as_dict(), "scorer": _stable_semantic_mapping(aligned.scorer_metadata), "judge": _stable_semantic_mapping(aligned.judge_metadata)}
            alignment_trace = aligned.trace
            unallocated_units = [unit.as_dict() for unit in aligned.unallocated_units]
        elif resolution.fusion_mode == "structure_degraded":
            fused = fuse_transcripts(structure_segments=parsed_ulisten.segments, text_segments=None)
            source_fixture = resolution.sources["ulisten"].is_fixture
            records = [_from_fused(segment, mode="structure_degraded", text_source="ulisten_raw_degraded", source_is_fixture=source_fixture) for segment in fused.segments]
            for record in records:
                record["needs_review"] = True
                record["review_reasons"] = ["secondary_source_missing"]
                record["alignment_method"] = "single_source_degraded"
                record["text_status"] = "raw_structure_only"
        elif resolution.fusion_mode == "text_single":
            source_fixture = resolution.sources["usetranscribe"].is_fixture
            records = _single_records(parsed_use.segments, mode="text_single", text_source="usetranscribe_format_fixture" if source_fixture else "usetranscribe_manual_export", structure_source="text_timeline", fixture=source_fixture)
        else:  # official_single
            source_fixture = resolution.sources["official_transcript"].is_fixture
            records = _single_records(parsed_official.segments, mode="official_single", text_source="official_transcript_format_fixture" if source_fixture else "official_transcript", structure_source="official_transcript", fixture=source_fixture)
        metadata = _resolution_metadata(resolution, media_id=media_id, youtube_url=youtube_url, input_dir=input_dir, fixture_flags=fixture_flags)
        metadata["limitations"] = list(dict.fromkeys(metadata["limitations"] + list(manifest.get("fixture_limitations") or [])))
        metadata["segment_count"] = len(records)
        metadata["speaker_review_count"] = sum(bool(record["speaker_needs_review"]) for record in records)
        metadata["fusion_diagnostics"] = fusion_diagnostics
        metadata["semantic_alignment_diagnostics"] = semantic_diagnostics
        metadata["semantic_alignment"] = semantic_metadata
        outputs = write_general_outputs(output_dir=output_dir, records=records, metadata=metadata, fused_schema_path=Path(__file__).parents[2] / "schemas" / "transcript_fused.schema.json", alignment_trace=alignment_trace, unallocated_units=unallocated_units)
        input_hashes_after = {name: _sha256(input_dir / name) for name in input_hashes_before}
        if input_hashes_before != input_hashes_after:
            raise GeneralTranscriptWorkflowError("raw input hash changed during general fusion")
        report = {
            "status": "ok", "run_id": logger.run_id, "media_id": media_id, "fusion_mode": resolution.fusion_mode,
            "segment_count": len(records), "text_review_count": sum(bool(record["needs_review"]) for record in records),
            "speaker_review_count": sum(bool(record["speaker_needs_review"]) for record in records),
            "alignment_confidence_count": sum(record["alignment_confidence"] is not None for record in records),
            "fusion_diagnostics": fusion_diagnostics,
            "semantic_alignment_diagnostics": semantic_report_diagnostics,
            "semantic_alignment": semantic_report_metadata,
            "input_hashes_before": input_hashes_before, "input_hashes_after": input_hashes_after,
            "outputs": outputs, "logs": logger.log_paths,
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        logger.event("INFO", "general_fusion.completed", "general transcript workflow completed", fusion_mode=resolution.fusion_mode, segment_count=len(records), outputs=outputs)
        return report
    except (OSError, ValueError, json.JSONDecodeError, GeneralTranscriptWorkflowError) as exc:
        logger.exception("general_fusion.failed", exc, input_dir=input_dir, output_dir=output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        failure = {
            "status": "failed", "fusion_mode": resolution.fusion_mode if resolution else "failed",
            "run_id": logger.run_id, "media_id": media_id, "error": str(exc),
            "source_resolution": resolution.as_dict() if resolution else None,
            "input_hashes_before": input_hashes_before, "logs": logger.log_paths,
        }
        report_path.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise GeneralTranscriptWorkflowError(str(exc)) from exc

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from gather_insight.adapters.official_transcript_parser import OfficialTranscriptSegment, parse_official_transcript_file
from gather_insight.adapters.ulisten_parser import UlistenSegment, parse_ulisten_file
from gather_insight.adapters.usetranscribe_parser import UseTranscribeSegment, parse_usetranscribe_file
from gather_insight.pipeline.ids import media_id_for_url
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


def _generic_record(*, segment_id: str, media_id: str, speaker: str | None, chapter: str | None, chapter_index: int | None, start: float, end: float, text: str, youtube_url: str, mode: str, structure_source: str, text_source: str, text_ulisten_raw: str | None = None, text_usetranscribe_raw: str | None = None, text_official_raw: str | None = None, needs_review: bool = False, review_reasons: list[str] | None = None, speaker_needs_review: bool = False, speaker_status: str | None = None, speaker_review_reasons: list[str] | None = None, structure_status: str = "source_provided", alignment_method: str = "single_source_no_alignment", alignment_confidence: float | None = None, alignment_components: dict[str, float] | None = None, conflicts: list[dict[str, object]] | None = None, reference_url: str | None = None) -> dict[str, object]:
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


def _from_fused(segment: FusedSegment, *, mode: str, text_source: str, official: bool = False) -> dict[str, object]:
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


def run_general_transcript_workflow(*, input_dir: Path, output_root: Path = Path("data/media"), fixture_flags: dict[str, bool] | None = None, logger: RunLogger | None = None) -> dict[str, Any]:
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
    logger.event("INFO", "general_fusion.started", "general transcript workflow started", input_dir=input_dir, output_dir=output_dir)
    report_path = output_dir / "processing_report.json"
    input_hashes_before: dict[str, str] = {}
    resolution: TranscriptCombinationResolution | None = None
    try:
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

        if resolution.fusion_mode == "dual_source":
            fused = fuse_transcripts(structure_segments=parsed_ulisten.segments, text_segments=parsed_use.segments)
            records = [_from_fused(segment, mode="dual_source", text_source="usetranscribe_manual_export") for segment in fused.segments]
        elif resolution.fusion_mode == "official_dual":
            fused = fuse_transcripts(structure_segments=parsed_ulisten.segments, text_segments=parsed_official.segments)
            records = [_from_fused(segment, mode="official_dual", text_source="official_transcript", official=True) for segment in fused.segments]
        elif resolution.fusion_mode == "structure_degraded":
            fused = fuse_transcripts(structure_segments=parsed_ulisten.segments, text_segments=None)
            records = [_from_fused(segment, mode="structure_degraded", text_source="ulisten_raw_degraded") for segment in fused.segments]
            for record in records:
                record["needs_review"] = True
                record["review_reasons"] = ["secondary_source_missing"]
                record["alignment_method"] = "single_source_degraded"
                record["text_status"] = "raw_structure_only"
        elif resolution.fusion_mode == "text_single":
            source_fixture = resolution.sources["usetranscribe"].is_fixture
            records = _single_records(parsed_use.segments, mode="text_single", text_source="usetranscribe_format_fixture" if source_fixture else "usetranscribe_manual_export", structure_source="text_timeline")
        else:  # official_single
            source_fixture = resolution.sources["official_transcript"].is_fixture
            records = _single_records(parsed_official.segments, mode="official_single", text_source="official_transcript", structure_source="official_transcript", fixture=source_fixture)
        metadata = _resolution_metadata(resolution, media_id=media_id, youtube_url=youtube_url, input_dir=input_dir, fixture_flags=fixture_flags)
        metadata["limitations"] = list(dict.fromkeys(metadata["limitations"] + list(manifest.get("fixture_limitations") or [])))
        metadata["segment_count"] = len(records)
        metadata["speaker_review_count"] = sum(bool(record["speaker_needs_review"]) for record in records)
        outputs = write_general_outputs(output_dir=output_dir, records=records, metadata=metadata, fused_schema_path=Path(__file__).parents[2] / "schemas" / "transcript_fused.schema.json")
        input_hashes_after = {name: _sha256(input_dir / name) for name in input_hashes_before}
        if input_hashes_before != input_hashes_after:
            raise GeneralTranscriptWorkflowError("raw input hash changed during general fusion")
        report = {
            "status": "ok", "run_id": logger.run_id, "media_id": media_id, "fusion_mode": resolution.fusion_mode,
            "segment_count": len(records), "text_review_count": sum(bool(record["needs_review"]) for record in records),
            "speaker_review_count": sum(bool(record["speaker_needs_review"]) for record in records),
            "alignment_confidence_count": sum(record["alignment_confidence"] is not None for record in records),
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

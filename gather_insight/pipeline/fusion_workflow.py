from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from gather_insight.adapters.ulisten_parser import parse_ulisten_file
from gather_insight.adapters.usetranscribe_parser import parse_usetranscribe_file
from gather_insight.pipeline.ids import media_id_for_url
from gather_insight.pipeline.transcript_fuser import fuse_transcripts
from gather_insight.run_logging import RunLogger

from .fusion_outputs import write_fusion_outputs


class FusionWorkflowError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_fixture_texts(path: Path) -> dict[str, str]:
    texts: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("record_type") == "segment":
            texts[str(record["segment_id"])] = str(record["text_readable_fixture"])
    return texts


def _read_manifest(input_dir: Path) -> dict[str, Any]:
    path = input_dir / "manifest.json"
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FusionWorkflowError("manifest.json must contain an object")
    return value


def run_fusion_workflow(*, input_dir: Path, output_root: Path = Path("data/media"), use_fixture: bool = False, logger: RunLogger | None = None) -> dict[str, Any]:
    manifest = _read_manifest(input_dir)
    youtube_url = str(manifest.get("youtube_url") or "")
    canonical_video_id = str(manifest.get("canonical_youtube_video_id") or "")
    if not youtube_url and canonical_video_id:
        youtube_url = f"https://www.youtube.com/watch?v={canonical_video_id}"
    if not youtube_url:
        raise FusionWorkflowError("manifest must provide youtube_url or canonical_youtube_video_id")
    try:
        media_id, normalized_youtube_url = media_id_for_url(youtube_url)
    except ValueError as exc:
        raise FusionWorkflowError(str(exc)) from exc
    if canonical_video_id and media_id != f"yt_{canonical_video_id}":
        raise FusionWorkflowError("manifest canonical_youtube_video_id does not match youtube_url")
    media_dir = output_root / media_id
    fusion_dir = media_dir / "fusion"
    media_dir.mkdir(parents=True, exist_ok=True)
    logger = logger or RunLogger("fuse-transcript", global_log=output_root / "_logs" / "gather_insight.jsonl")
    logger.bind_media(media_id, media_dir)
    logger.event("INFO", "fusion.started", "dual-source fusion started", input_dir=input_dir, output_dir=fusion_dir, use_fixture=use_fixture)
    report_path = fusion_dir / "processing_report.json"
    input_ulisten = input_dir / "source_ulisten_raw.md"
    input_usetranscribe = input_dir / "source_usetranscribe_raw.md"
    fixture_path = input_dir / "transcript_fused_fixture.jsonl"
    input_hashes_before: dict[str, str] = {}
    try:
        if not input_ulisten.exists():
            raise FusionWorkflowError(f"missing required uListen source: {input_ulisten}")
        input_hashes_before["source_ulisten_raw.md"] = _sha256(input_ulisten)
        parsed_ulisten = parse_ulisten_file(
            path=input_ulisten,
            media_id=media_id,
            youtube_url=normalized_youtube_url,
            provider_id=str((manifest.get("ulisten_source") or {}).get("provider_page_id") or "") or None,
        )
        logger.event("INFO", "fusion.ulisten_parsed", "uListen source parsed", chapters=len(parsed_ulisten.chapters), segments=len(parsed_ulisten.segments), provider_id=(manifest.get("ulisten_source") or {}).get("provider_page_id"))
        text_segments = None
        fixture_texts = None
        source_state = "absent"
        if input_usetranscribe.exists():
            input_hashes_before["source_usetranscribe_raw.md"] = _sha256(input_usetranscribe)
            text_result = parse_usetranscribe_file(
                path=input_usetranscribe,
                media_id=media_id,
                youtube_url=normalized_youtube_url,
                video_duration_seconds=parsed_ulisten.chapters[-1].end_seconds,
            )
            text_segments = text_result.segments
            source_state = "present"
            logger.event("INFO", "fusion.usetranscribe_parsed", "UseTranscribe source parsed", segments=len(text_segments))
        elif use_fixture:
            if not fixture_path.exists():
                raise FusionWorkflowError("fixture mode requested but transcript_fused_fixture.jsonl is missing")
            input_hashes_before["transcript_fused_fixture.jsonl"] = _sha256(fixture_path)
            fixture_texts = _load_fixture_texts(fixture_path)
            source_state = "fixture_substitute"
            logger.event("WARNING", "fusion.fixture_mode", "using declared spacing reconstruction fixture; no alignment confidence will be generated", fixture_segments=len(fixture_texts))
        else:
            logger.event("WARNING", "fusion.degraded_mode", "UseTranscribe source is absent; confidence remains null")

        result = fuse_transcripts(structure_segments=parsed_ulisten.segments, text_segments=text_segments, fixture_texts=fixture_texts)
        mode = result.mode
        metadata = {
            "schema_version": "gather_insight_fusion_v1",
            "media_id": media_id,
            "canonical_youtube_video_id": canonical_video_id or media_id[3:],
            "youtube_url": normalized_youtube_url,
            "input_dir": str(input_dir),
            "fusion_mode": mode,
            "structure_source": "ulisten_manual_browser_copy",
            "text_source": "usetranscribe_manual_export" if mode == "dual_source" else ("spacing_reconstruction_fixture" if mode == "fixture" else "ulisten_raw_degraded"),
            "ulisten_source_state": "present",
            "usetranscribe_source_state": source_state,
            "fixture_text_used": mode == "fixture",
            "chapter_count": len(parsed_ulisten.chapters),
            "speaker_count": len({segment.speaker for segment in parsed_ulisten.segments}),
            "segment_count": len(result.segments),
            "provider_ids": {"ulisten": (manifest.get("ulisten_source") or {}).get("provider_page_id")},
            "limitations": (
                ["No source_usetranscribe_raw.md was supplied; this is degraded mode and alignment_confidence must remain null."]
                if mode == "degraded" else
                ["Readable fixture text is not a production UseTranscribe export; alignment_confidence remains null."]
                if mode == "fixture" else []
            ),
        }
        outputs = write_fusion_outputs(output_dir=fusion_dir, result=result, metadata=metadata, fused_schema_path=Path(__file__).parents[2] / "schemas" / "transcript_fused.schema.json")
        input_hashes_after = {name: _sha256(input_dir / name) for name in input_hashes_before}
        if input_hashes_before != input_hashes_after:
            raise FusionWorkflowError("raw input hash changed during fusion")
        report = {
            "status": "ok",
            "run_id": logger.run_id,
            "media_id": media_id,
            "fusion_mode": mode,
            "segment_count": len(result.segments),
            "review_count": sum(segment.needs_review for segment in result.segments),
            "alignment_confidence_count": sum(segment.alignment_confidence is not None for segment in result.segments),
            "input_hashes_before": input_hashes_before,
            "input_hashes_after": input_hashes_after,
            "outputs": outputs,
            "logs": logger.log_paths,
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        logger.event("INFO", "fusion.completed", "fusion outputs written", mode=mode, segment_count=len(result.segments), review_count=report["review_count"], outputs=outputs)
        return report
    except (OSError, ValueError, json.JSONDecodeError, FusionWorkflowError) as exc:
        logger.exception("fusion.failed", exc, input_dir=input_dir, output_dir=fusion_dir)
        failure = {"status": "failed", "run_id": logger.run_id, "media_id": media_id, "error": str(exc), "input_hashes_before": input_hashes_before, "logs": logger.log_paths}
        fusion_dir.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise FusionWorkflowError(str(exc)) from exc


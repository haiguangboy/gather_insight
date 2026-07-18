from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from gather_insight.run_logging import RunLogger
from gather_insight.adapters.base import sanitize_url

from .evidence_builder import build_evidence
from .ids import media_id_for_url
from .transcript_normalizer import chunk_segments, load_transcript
from .validators import dump_yaml, validate_document, validate_evidence_orphans, validate_records


class IngestError(RuntimeError):
    pass


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n" for record in records), encoding="utf-8")


def _write_if_absent(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def _review_template(media_id: str, evidence: list[dict[str, Any]]) -> str:
    rows = "\n".join(f"- [ ] `{item['evidence_id']}` — decision: `pending` — notes: " for item in evidence)
    return f"""# Review: {media_id}\n\n> All candidates are pending by default. This file is the human gate; do not treat generated candidates as accepted knowledge.\n\n## Evidence review\n\n{rows}\n\n## Decisions\n\n- reviewer: \n- reviewed_at: \n- high_value_items: \n- discarded_items: \n"""


def _default_source_checks(provider: str, transcript_file: Path, transcript_format: str, primary_url: str | None) -> dict[str, dict[str, Any]]:
    providers = ("official_transcript", "ulisten", "usetranscribe", "manual_markdown", "youtube_export")
    checks = {
        name: {
            "provider": name,
            "status": "not_configured",
            "available": False,
            "has_local_content": False,
        }
        for name in providers
    }
    checks[provider] = {
        "provider": provider,
        "status": "ready",
        "available": True,
        "has_local_content": True,
        "file": str(transcript_file),
        "url": primary_url,
        "transcript_format": transcript_format,
    }
    return checks


def ingest_media(*, url: str, transcript_file: Path, provider: str, output_root: Path, title: str | None = None, channel: str | None = None, language: str = "en", speaker_mode: str = "unknown", participants: list[str] | None = None, topics: list[str] | None = None, force_source: bool = False, transcript_format: str = "markdown", source_checks: dict[str, dict[str, Any]] | None = None, primary_source_url: str | None = None, logger: RunLogger | None = None) -> dict[str, Any]:
    try:
        media_id, normalized_url = media_id_for_url(url)
    except ValueError as exc:
        raise IngestError(str(exc)) from exc
    media_dir = output_root / media_id
    media_dir.mkdir(parents=True, exist_ok=True)
    logger = logger or RunLogger("ingest", global_log=output_root / "_logs" / "gather_insight.jsonl")
    logger.bind_media(media_id, media_dir)
    logger.event("INFO", "ingest.started", "media ingest started", source_url=normalized_url, provider=provider, transcript_file=transcript_file, transcript_format=transcript_format)
    report_path = media_dir / "processing_report.json"
    try:
        if not transcript_file.exists():
            raise IngestError(f"transcript file does not exist: {transcript_file}")
        raw, raw_segments = load_transcript(transcript_file, transcript_format)
        logger.event("INFO", "transcript.parsed", "transcript parsed", raw_segments=len(raw_segments), transcript_format=transcript_format, source_bytes=len(raw.encode("utf-8")))
        chunks = chunk_segments(raw_segments)
        logger.event("INFO", "transcript.chunked", "transcript converted to evidence-sized chunks", raw_segments=len(raw_segments), chunks=len(chunks))
        source_path = media_dir / "source.md"
        source_existed = source_path.exists()
        source_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        source_content = f"<!-- gather_insight_source_sha256: {source_hash} -->\n\n{raw.rstrip()}\n"
        existing_source = source_path.read_text(encoding="utf-8") if source_existed else None
        source_changed = existing_source is not None and existing_source != source_content
        if source_changed and not force_source:
            raise IngestError(f"{source_path} exists and differs; use --force-source only for source replacement")
        source_path.write_text(source_content, encoding="utf-8")
        logger.event("INFO", "source.written", "source transcript persisted", source_path=source_path, source_sha256=source_hash, replaced=source_changed)

        manifest_path = media_dir / "manifest.yaml"
        manifest: dict[str, Any] = {}
        if manifest_path.exists():
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        existing_participants = manifest.get("participants") or []
        resolved_participants = [{"name": name, "role": "unknown"} for name in (participants or [])] if participants else existing_participants
        resolved_topics = topics if topics else (manifest.get("topics") or [])
        manifest.update({
            "schema_version": "media_manifest_v1",
            "media_id": media_id,
            "media_type": "youtube_video" if media_id.startswith("yt_") else "web_page",
            "title": title if title is not None else manifest.get("title"),
            "source_url": normalized_url,
            "video_id": media_id[3:] if media_id.startswith("yt_") else None,
            "channel": channel if channel is not None else manifest.get("channel"),
            "participants": resolved_participants,
            "topics": resolved_topics,
            "source_resolution": {
                **(manifest.get("source_resolution") or {}),
                "primary_provider": provider,
                "primary_url": sanitize_url(primary_source_url) if primary_source_url else None,
                "checked": source_checks or _default_source_checks(provider, transcript_file, transcript_format, primary_source_url),
            },
            "processing": {
                **(manifest.get("processing") or {}),
                "status": "evidence_built",
                "transcript_language": language,
                "speaker_mode": speaker_mode,
                "created_at": (manifest.get("processing") or {}).get("created_at", str(date.today())),
                "updated_at": str(date.today()),
                "last_run_id": logger.run_id,
            },
        })
        schema_root = Path(__file__).parents[2] / "schemas"
        validate_document(manifest, schema_root / "media_manifest.schema.json", "manifest")
        dump_yaml(manifest_path, manifest)
        logger.event("INFO", "manifest.validated", "manifest passed schema validation", manifest_path=manifest_path)

        evidence = build_evidence(media_id, normalized_url, provider, chunks)
        validate_evidence_orphans(evidence)
        validate_records(evidence, schema_root / "media_evidence.schema.json", "evidence")
        evidence_path = media_dir / "evidence.jsonl"
        _write_jsonl(evidence_path, evidence)
        logger.event("INFO", "evidence.written", "evidence passed quality gates and was written", evidence_path=evidence_path, evidence_count=len(evidence))
        review_path = media_dir / "review.md"
        review_existed = review_path.exists()
        _write_if_absent(review_path, _review_template(media_id, evidence))
        logger.event("INFO", "review.ready", "human review gate is ready", review_path=review_path, preserved_existing=review_existed)
        warnings = ["speaker attribution is unknown or manually labeled; review before creating cards"] if any(item["needs_review"] for item in evidence) else []
        if force_source and source_existed and (media_dir / "review.md").exists():
            warnings.append("source was replaced explicitly; existing human review may need reconciliation")
        processing_report = {
            "status": "ok",
            "run_id": logger.run_id,
            "media_id": media_id,
            "input_file": str(transcript_file),
            "provider": provider,
            "transcript_format": transcript_format,
            "source_sha256": source_hash,
            "raw_segments": len(raw_segments),
            "evidence_count": len(evidence),
            "warnings": warnings,
            "logs": logger.log_paths,
        }
        report_path.write_text(json.dumps(processing_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        logger.event("INFO", "ingest.completed", "media ingest completed", report_path=report_path, evidence_count=len(evidence), warnings=warnings)
        return {"run_id": logger.run_id, "media_id": media_id, "output_dir": str(media_dir), "evidence_count": len(evidence), "status": "ok", "logs": logger.log_paths}
    except (ValueError, OSError, IngestError) as exc:
        logger.exception("ingest.failed", exc, provider=provider, transcript_file=transcript_file, transcript_format=transcript_format)
        failure = {"status": "failed", "run_id": logger.run_id, "media_id": media_id, "input_file": str(transcript_file), "provider": provider, "transcript_format": transcript_format, "error": str(exc), "exception_type": type(exc).__name__, "logs": logger.log_paths}
        report_path.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise IngestError(str(exc)) from exc

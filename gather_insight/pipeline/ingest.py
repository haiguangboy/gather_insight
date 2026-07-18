from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .evidence_builder import build_evidence
from .ids import media_id_for_url
from .transcript_normalizer import chunk_segments, load_markdown
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


def ingest_media(*, url: str, transcript_file: Path, provider: str, output_root: Path, title: str | None = None, channel: str | None = None, language: str = "en", speaker_mode: str = "unknown", participants: list[str] | None = None, topics: list[str] | None = None, force_source: bool = False) -> dict[str, Any]:
    if not transcript_file.exists():
        raise IngestError(f"transcript file does not exist: {transcript_file}")
    try:
        media_id, normalized_url = media_id_for_url(url)
    except ValueError as exc:
        raise IngestError(str(exc)) from exc
    media_dir = output_root / media_id
    media_dir.mkdir(parents=True, exist_ok=True)
    report_path = media_dir / "processing_report.json"
    try:
        raw, raw_segments = load_markdown(transcript_file)
        chunks = chunk_segments(raw_segments)
        source_path = media_dir / "source.md"
        source_existed = source_path.exists()
        source_content = f"<!-- gather_insight_source_sha256: {hashlib.sha256(raw.encode('utf-8')).hexdigest()} -->\n\n{raw.rstrip()}\n"
        if source_path.exists() and not force_source and source_path.read_text(encoding="utf-8") != source_content:
            raise IngestError(f"{source_path} exists and differs; use --force-source only for source replacement")
        source_path.write_text(source_content, encoding="utf-8")

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
                "primary_url": None,
                "checked": {"official_transcript": False, "ulisten": False, "usetranscribe": provider == "usetranscribe", "youtube_export": provider == "youtube_export"},
            },
            "processing": {
                **(manifest.get("processing") or {}),
                "status": "evidence_built",
                "transcript_language": language,
                "speaker_mode": speaker_mode,
                "created_at": (manifest.get("processing") or {}).get("created_at", str(date.today())),
                "updated_at": str(date.today()),
            },
        })
        schema_root = Path(__file__).parents[2] / "schemas"
        validate_document(manifest, schema_root / "media_manifest.schema.json", "manifest")
        dump_yaml(manifest_path, manifest)

        evidence = build_evidence(media_id, normalized_url, provider, chunks)
        validate_evidence_orphans(evidence)
        validate_records(evidence, schema_root / "media_evidence.schema.json", "evidence")
        evidence_path = media_dir / "evidence.jsonl"
        _write_jsonl(evidence_path, evidence)
        _write_if_absent(media_dir / "review.md", _review_template(media_id, evidence))
        warnings = ["speaker attribution is unknown or manually labeled; review before creating cards"] if any(item["needs_review"] for item in evidence) else []
        if force_source and source_existed and (media_dir / "review.md").exists():
            warnings.append("source was replaced explicitly; existing human review may need reconciliation")
        processing_report = {
            "status": "ok",
            "media_id": media_id,
            "input_file": str(transcript_file),
            "source_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "raw_segments": len(raw_segments),
            "evidence_count": len(evidence),
            "warnings": warnings,
        }
        report_path.write_text(json.dumps(processing_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"media_id": media_id, "output_dir": str(media_dir), "evidence_count": len(evidence), "status": "ok"}
    except (ValueError, OSError, IngestError) as exc:
        failure = {"status": "failed", "media_id": media_id, "input_file": str(transcript_file), "error": str(exc)}
        report_path.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise IngestError(str(exc)) from exc

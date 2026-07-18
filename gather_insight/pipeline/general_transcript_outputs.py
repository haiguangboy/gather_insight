from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .validators import validate_records


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")


def _time(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _markdown(records: list[dict[str, object]], metadata: dict[str, Any]) -> str:
    lines = [
        "# Transcript resolved",
        "",
        f"- media_id: `{metadata['media_id']}`",
        f"- fusion_mode: `{metadata['fusion_mode']}`",
        f"- structure_source: `{metadata.get('structure_source')}`",
        f"- text_source: `{metadata.get('text_source')}`",
        f"- segment_count: `{len(records)}`",
        "",
    ]
    for record in records:
        speaker = record.get("speaker") or "unknown"
        lines.extend([
            f"## {record['segment_id']} — {speaker} · [{_time(float(record['start_seconds']))}](<{record['youtube_url']}>)",
            "",
            f"- fusion_mode: `{record['fusion_mode']}`",
            f"- chapter: `{record.get('chapter')}`",
            f"- speaker_status: `{record['speaker_status']}`",
            f"- speaker_needs_review: `{record['speaker_needs_review']}`",
            f"- text_status: `{record['text_status']}`",
            f"- alignment_confidence: `{record['alignment_confidence']}`",
            "",
            str(record["text"]),
            "",
        ])
    return "\n".join(lines) + "\n"


def _review_queue(records: list[dict[str, object]]) -> str:
    review = [record for record in records if record.get("needs_review")]
    lines = ["# Review queue", "", f"- count: `{len(review)}`", ""]
    for record in review:
        lines.extend([
            f"## {record['segment_id']}", "",
            f"- timestamp: `{_time(float(record['start_seconds']))}`",
            f"- reasons: `{', '.join(record.get('review_reasons', []))}`",
            f"- youtube_url: <{record['youtube_url']}>`,".rstrip(","), "",
            str(record["text"]), "",
        ])
    if not review:
        lines.append("No general text review items.")
    return "\n".join(lines) + "\n"


def _speaker_review_queue(records: list[dict[str, object]]) -> str:
    pending = [record for record in records if record.get("speaker_needs_review")]
    lines = ["# Speaker review queue", "", f"- count: `{len(pending)}`", ""]
    for record in pending:
        lines.extend([
            f"## {record['segment_id']}", "",
            f"- current_speaker: `{record.get('speaker')}`",
            f"- timestamp: `{_time(float(record['start_seconds']))}`",
            f"- youtube_url: <{record['youtube_url']}>",
            "- action: verify speaker against the original video; do not infer automatically.",
            "",
        ])
    if not pending:
        lines.append("No speaker attribution review items.")
    return "\n".join(lines) + "\n"


def _report(records: list[dict[str, object]], metadata: dict[str, Any]) -> str:
    confidences = [record["alignment_confidence"] for record in records if record.get("alignment_confidence") is not None]
    lines = [
        "# Source resolution report",
        "",
        f"- media_id: `{metadata['media_id']}`",
        f"- fusion_mode: `{metadata['fusion_mode']}`",
        f"- structure_source: `{metadata.get('structure_source')}`",
        f"- text_source: `{metadata.get('text_source')}`",
        f"- segment_count: `{len(records)}`",
        f"- text_review_count: `{sum(bool(record.get('needs_review')) for record in records)}`",
        f"- speaker_review_count: `{sum(bool(record.get('speaker_needs_review')) for record in records)}`",
        f"- numeric_alignment_confidence_count: `{len(confidences)}`",
        f"- sources: `{json.dumps(metadata.get('sources', {}), ensure_ascii=False)}`",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in metadata.get("limitations", []))
    if not metadata.get("limitations"):
        lines.append("- none")
    return "\n".join(lines) + "\n"


def write_general_outputs(*, output_dir: Path, records: list[dict[str, object]], metadata: dict[str, Any], fused_schema_path: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    validate_records(records, fused_schema_path, "general transcript output")
    paths = {
        "transcript_fused_jsonl": output_dir / "transcript_fused.jsonl",
        "transcript_fused_markdown": output_dir / "transcript_fused.md",
        "source_resolution_report": output_dir / "source_resolution_report.md",
        "review_queue": output_dir / "review_queue.md",
        "speaker_review_queue": output_dir / "speaker_review_queue.md",
        "fusion_manifest": output_dir / "fusion_manifest.json",
    }
    _write_jsonl(paths["transcript_fused_jsonl"], records)
    paths["transcript_fused_markdown"].write_text(_markdown(records, metadata), encoding="utf-8")
    paths["source_resolution_report"].write_text(_report(records, metadata), encoding="utf-8")
    paths["review_queue"].write_text(_review_queue(records), encoding="utf-8")
    paths["speaker_review_queue"].write_text(_speaker_review_queue(records), encoding="utf-8")
    paths["fusion_manifest"].write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {key: str(path) for key, path in paths.items()}


from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .transcript_fuser import FusionResult, FusedSegment
from .validators import validate_records


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")


def _format_seconds(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _markdown_segment(segment: FusedSegment) -> str:
    conflicts = ", ".join(str(item.get("type")) for item in segment.conflicts) or "none"
    reasons = ", ".join(segment.review_reasons) or "none"
    return "\n".join([
        f"### {segment.segment_id} — {segment.speaker} · [{_format_seconds(segment.start_seconds)}](<{segment.youtube_url}>)",
        "",
        f"- chapter: {segment.chapter}",
        f"- interval: `{segment.start_seconds}`–`{segment.end_seconds}`",
        f"- fusion_mode: `{segment.fusion_mode}`",
        f"- text_source: `{segment.text_source}`",
        f"- alignment_confidence: `{segment.alignment_confidence}`",
        f"- needs_review: `{segment.needs_review}`",
        f"- review_reasons: `{reasons}`",
        f"- conflicts: `{conflicts}`",
        "",
        segment.text,
        "",
        "<details>",
        "<summary>uListen raw</summary>",
        "",
        segment.text_ulisten_raw,
        "",
        "</details>",
        "",
    ])


def _review_markdown(segments: list[FusedSegment], mode: str) -> str:
    review = [segment for segment in segments if segment.needs_review]
    lines = [
        "# Review queue",
        "",
        f"- fusion_mode: `{mode}`",
        f"- review_count: `{len(review)}`",
        "",
    ]
    if not review:
        lines.append("No review items.")
        return "\n".join(lines) + "\n"
    for segment in review:
        lines.extend([
            f"## {segment.segment_id} — {segment.speaker}",
            "",
            f"- chapter: {segment.chapter}",
            f"- timestamp: `{_format_seconds(segment.start_seconds)}`",
            f"- youtube_url: <{segment.youtube_url}>",
            f"- alignment_confidence: `{segment.alignment_confidence}`",
            f"- reasons: `{', '.join(segment.review_reasons)}`",
            f"- conflicts: `{json.dumps(segment.conflicts, ensure_ascii=False)}`",
            "",
            "### uListen raw",
            "",
            segment.text_ulisten_raw,
            "",
        ])
        if segment.text_usetranscribe_raw is not None:
            lines.extend(["### UseTranscribe candidate", "", segment.text_usetranscribe_raw, ""])
    return "\n".join(lines) + "\n"


def _alignment_report(*, result: FusionResult, metadata: dict[str, Any]) -> str:
    segments = result.segments
    chapters = {segment.chapter for segment in segments}
    speakers = {segment.speaker for segment in segments}
    confidence = [segment.alignment_confidence for segment in segments if segment.alignment_confidence is not None]
    conflict_counts = Counter(conflict["type"] for segment in segments for conflict in segment.conflicts)
    review_count = sum(segment.needs_review for segment in segments)
    lines = [
        "# Alignment report",
        "",
        f"- media_id: `{metadata['media_id']}`",
        f"- fusion_mode: `{result.mode}`",
        f"- structure_source: `{metadata['structure_source']}`",
        f"- text_source: `{metadata['text_source']}`",
        f"- chapters: `{len(chapters)}`",
        f"- segments: `{len(segments)}`",
        f"- review_count: `{review_count}`",
        f"- numeric_confidence_count: `{len(confidence)}`",
        f"- alignment_confidence_min: `{min(confidence) if confidence else None}`",
        f"- alignment_confidence_max: `{max(confidence) if confidence else None}`",
        f"- fusion_diagnostics: `{json.dumps(result.diagnostics.as_dict() if result.diagnostics else None, ensure_ascii=False)}`",
        f"- chapter_retention: `{metadata.get('chapter_count', len(chapters))}/{metadata.get('chapter_count', len(chapters))}`",
        f"- speaker_retention: `{len(speakers)}/{metadata.get('speaker_count', len(speakers))}`",
        "",
        "## Source state",
        "",
        f"- uListen: `{metadata.get('ulisten_source_state', 'present')}`",
        f"- UseTranscribe: `{metadata.get('usetranscribe_source_state', 'absent')}`",
        f"- fixture_text_used: `{metadata.get('fixture_text_used', False)}`",
        "",
        "## Conflict counts",
        "",
    ]
    if conflict_counts:
        lines.extend(f"- {key}: `{value}`" for key, value in sorted(conflict_counts.items()))
    else:
        lines.append("- none")
    lines.extend(["", "## Limitations", ""])
    for limitation in metadata.get("limitations", []):
        lines.append(f"- {limitation}")
    if not metadata.get("limitations"):
        lines.append("- none")
    return "\n".join(lines) + "\n"


def write_fusion_outputs(*, output_dir: Path, result: FusionResult, metadata: dict[str, Any], fused_schema_path: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [segment.as_dict() for segment in result.segments]
    validate_records(records, fused_schema_path, "transcript_fused")
    jsonl_path = output_dir / "transcript_fused.jsonl"
    markdown_path = output_dir / "transcript_fused.md"
    alignment_path = output_dir / "alignment_report.md"
    review_path = output_dir / "review_queue.md"
    manifest_path = output_dir / "fusion_manifest.json"
    _write_jsonl(jsonl_path, records)
    markdown = [
        "# Transcript fused",
        "",
        f"- media_id: `{metadata['media_id']}`",
        f"- fusion_mode: `{result.mode}`",
        f"- segment_count: `{len(records)}`",
        f"- alignment_confidence_is_numeric: `{any(record['alignment_confidence'] is not None for record in records)}`",
        "",
    ]
    for segment in result.segments:
        markdown.append(_markdown_segment(segment))
    markdown_path.write_text("\n".join(markdown), encoding="utf-8")
    alignment_path.write_text(_alignment_report(result=result, metadata=metadata), encoding="utf-8")
    review_path.write_text(_review_markdown(result.segments, result.mode), encoding="utf-8")
    manifest_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "transcript_fused_jsonl": str(jsonl_path),
        "transcript_fused_markdown": str(markdown_path),
        "alignment_report": str(alignment_path),
        "review_queue": str(review_path),
        "fusion_manifest": str(manifest_path),
    }

# Phase 6.6.1 — General workflow hardening

This patch keeps the YC `fusion_workflow.py` path and its source contract intact while hardening the independent general workflow.

## Identity validation

When both manifest fields are available, `canonical_youtube_video_id` must exactly equal the video ID parsed from `youtube_url`. A mismatch raises an explicit error and writes a failed `processing_report.json` under the parsed media package.

## Fixture provenance

Official transcript-format fixtures use `text_source: official_transcript_format_fixture` and `source_is_fixture: true` in both `official_single` and `official_dual`. The same boolean is emitted for the existing UseTranscribe-format fixture. Downstream publication/evidence stages must reject or separately gate records with `source_is_fixture: true`; this phase does not publish fixture-derived evidence.

## Dual-source diagnostics

`FusionResult.diagnostics` exposes four deterministic counters:

- `secondary_segment_reuse_count`: distinct secondary segment IDs assigned to more than one uListen speaker;
- `cross_speaker_boundary_count`: adjacent fused records with different speakers sharing a secondary segment;
- `adjacent_text_duplication_rate`: exact normalized-text duplicates among adjacent fused pairs;
- `unconsumed_secondary_segment_count`: secondary segment IDs not assigned to any uListen segment.

Cross-speaker reuse always adds `secondary_segment_reused_across_speakers` to the affected records and forces `needs_review: true`. The metrics are also written to general processing reports and the legacy alignment report.

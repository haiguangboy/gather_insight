# Phase 6.6 — General transcript source resolution

This phase is independent of the completed YC `fusion_workflow.py`. The YC dual-source acceptance path remains unchanged.

## State machine

| Available inputs | fusion_mode | structure source | text source |
|---|---|---|---|
| uListen + UseTranscribe | `dual_source` | uListen | UseTranscribe |
| uListen + official | `official_dual` | uListen | official transcript |
| official only | `official_single` | official transcript | official transcript |
| UseTranscribe only | `text_single` | timestamped text timeline | UseTranscribe |
| uListen only | `structure_degraded` | uListen | uListen raw text |
| none | `failed` | none | none |

If all three sources exist, official transcript outranks UseTranscribe as the text authority. If official and UseTranscribe exist without uListen, `official_single` is selected and UseTranscribe is recorded as unused.

## Input contract

The resolver checks these exact, backward-compatible filenames:

```text
source_ulisten_raw.md
source_usetranscribe_raw.md
source_official_transcript_raw.md
```

`manifest.json` must provide a YouTube URL or canonical YouTube video ID. UseTranscribe-only inputs whose last cue has no explicit end also require `duration_seconds`.

## Output contract

Every successful mode writes stable segment-oriented output under `data/media/<media_id>/general/`:

- `transcript_fused.jsonl`;
- `transcript_fused.md`;
- `source_resolution_report.md`;
- `review_queue.md` for text/alignment problems;
- `speaker_review_queue.md` for attribution only;
- `fusion_manifest.json`;
- `processing_report.json`.

Single-source modes always use `alignment_confidence: null` because no cross-source alignment occurred.

In `text_single`:

- `speaker` is `null`;
- `speaker_needs_review` is `true`;
- readable, timestamped text may still have `needs_review: false`;
- speaker attribution is handled separately and is never inferred by this phase.

`structure_degraded` preserves uListen speaker and chapter structure, but the raw joined text is marked `raw_structure_only` and requires review.

## Fixture safety

The Dario fixture is a UseTranscribe-format developer fixture built from the public YouTube caption baseline. Its manifest marks `fixture_flags.usetranscribe: true`, so output uses `text_source: usetranscribe_format_fixture`. It must not be cited as an actual UseTranscribe export.

Phase 6.6.1 extends this contract with record-level `source_is_fixture`, an official fixture-specific text source, canonical YouTube ID validation, and dual-source diagnostic counters. See `docs/PHASE_6_6_1.md`.

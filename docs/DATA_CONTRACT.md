# Data contract

## Media package

Every media package lives under `data/media/<media_id>/` and contains:

- `manifest.yaml`: source identity, resolution history, and processing state;
- `source.md`: immutable-by-default imported transcript plus a SHA-256 marker;
- `evidence.jsonl`: deterministic, timestamped evidence units;
- `review.md`: human-owned review gate, created once and never regenerated;
- `processing_report.json`: run status, counts, warnings, and source hash.
- `logs/<run_id>.jsonl`: append-only structured events for one media run (ignored by Git by default); the report stores its path.

The project-level `logs/gather_insight.jsonl` receives the same events, including source-resolution events emitted before a media directory is selected. Each record contains a UTC timestamp, severity, event name, run ID, media ID when known, sanitized context, and an exception traceback on failure. Transcript bodies, credentials, cookies, and full URL query strings are not logged.

## Identity

- YouTube media: `yt_<video_id>`;
- evidence: `<media_id>.ev_<NNNN>`;
- candidate: `<media_id>.candidate_<NNN>`.

Evidence IDs are regenerated deterministically from transcript order. Re-running identical input must not create duplicate IDs.

## Manual transcript contract

The canonical cue is:

```markdown
## [HH:MM:SS-HH:MM:SS] Speaker | Optional section

Original-language transcript text.
```

The pipeline preserves modality and qualification in the original text. Speaker labels in manual Markdown receive confidence `0.75` and remain reviewable; missing labels become `unknown` with confidence `0.0`.

## Candidate and export boundary

Candidate cards are Phase 3 assets. They must default to `pending`, bind at least one evidence ID, and distinguish `media_interview`, `system_derived`, and `external_expression`. Only accepted cards may enter the `read_papers` export bundle.

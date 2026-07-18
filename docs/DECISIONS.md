# Architecture decisions

## ADR-001 — Standard-library CLI with narrow dependencies

Status: accepted, 2026-07-18.

Use `argparse`, plain Python modules, YAML, JSONL, and JSON Schema. This keeps the Phase 1 path auditable and avoids a framework or database before query scale requires one.

## ADR-002 — Human-authored timestamped Markdown is the Phase 1 ingest boundary

Status: accepted, 2026-07-18.

The first executable boundary is already-normalized Markdown, not web scraping. It proves identity, provenance, chunking, validation, idempotency, and review behavior independently of unstable providers.

## ADR-003 — Source replacement is explicit; review files are human-owned

Status: accepted, 2026-07-18.

`source.md` changes require `--force-source`. `review.md` is generated only when absent. Derived evidence can be rebuilt deterministically, while manual review is never silently overwritten.

## ADR-004 — No automatic speaker certainty in Phase 1

Status: accepted, 2026-07-18.

Manual speaker labels receive confidence `0.75`; unknown labels receive `0.0`. High-value cards will require later human review instead of inheriting false certainty from transcript formatting.

## ADR-005 — Structured per-run logs with credential-safe context

Status: accepted, 2026-07-19.

Every CLI execution gets a unique `run_id`. Source resolution and ingest share the same append-only JSONL event stream, which is copied into the media package once the media ID is known. Runtime logs are locally retained but Git-ignored; the processing report keeps stable pointers and the final status.

## ADR-006 — Phase 2 adapters may return URL-only availability

Status: accepted, 2026-07-19.

Official transcript, uListen, and UseTranscribe pages may be unstable or unsuitable for automatic text scraping. An adapter can therefore report `url_only`. Resolution continues to a lower-priority local source, while the manifest preserves the higher-quality URL for later manual import.

## ADR-007 — Production fused JSONL is segment-only

Status: accepted, 2026-07-19.

The supplied fixture JSONL mixes manifest, chapter, and segment records. Production `transcript_fused.jsonl` contains only segment records so downstream evidence code can stream it without record-type branching. Aggregate metadata is written to `alignment_report.md` and `transcript_fused.md`.

## ADR-008 — Official transcript outranks UseTranscribe in general resolution

Status: accepted, 2026-07-19.

Phase 6.6 keeps the YC workflow unchanged and adds a separate general source-combination state machine. If uListen and both text sources are present, uListen remains the structure source and the official transcript becomes the text source. If no uListen exists but official and UseTranscribe are both present, `official_single` is selected and UseTranscribe is recorded as unused. UseTranscribe-only output remains anonymous and carries a separate speaker-review status rather than marking all readable text as generally unreviewed.

## ADR-009 — Fixture provenance is a record-level publication gate

Status: accepted, 2026-07-19.

General transcript records carry `source_is_fixture`, and fixture-specific `text_source` values remain distinct from production sources. This keeps readable fixtures useful for parser and workflow tests without allowing downstream evidence or publication code to treat them as production provenance. Dual-source diagnostics remain aggregate output, while only the cross-speaker secondary-segment reuse condition changes record review state.

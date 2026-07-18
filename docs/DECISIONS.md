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


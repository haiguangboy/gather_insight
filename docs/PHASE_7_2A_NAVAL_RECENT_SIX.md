# Phase 7.2A: Naval Recent Six Sequential Corpus

This phase ingests one fixed official-site snapshot: the six contiguous Naval archive entries from `Live in the Future` through `Sell the Truth`, discovered on 2026-07-19. It does not crawl older pages, download media, substitute third-party transcripts, or run ASR.

## Source order and cursor

`source_index.jsonl` preserves the official newest-to-oldest site order. Sections, reports, positions, and trends use oldest-to-newest chronological order. `ingestion_cursor.json` records both ends of the processed interval and points to `Nothing Ever Happens Is Over` (2026-05-04) without fetching it.

The source list is a checked-in constant rather than a discovery query. A title or canonical-URL mismatch fails loudly. This makes the snapshot reproducible and prevents a later archive edit from silently changing the six-item experiment.

## Official source contract

Each source directory contains immutable `raw/source_raw.html` plus fetch metadata. A rerun reads the cache and makes no HTTP request. The parser recognizes WordPress transcript headings and paragraphs, starts a turn only from a source-provided `Name:` label, and conservatively inherits that speaker only through the contiguous turn. Editorial material without a label remains `unknown`.

`Live in the Future` is an important negative source result: the official page contains a short description but no official transcript body. The page is ingested and cached, but no audio speech, speaker claim, or fabricated transcript is derived from it.

## Source families and independence

The three serialized pages and the full `AI Industrial Revolution` page share:

- `source_family_id = naval_frontier_founders_industrial_2026`
- `independence_group_id = naval_frontier_founders_industrial_2026`

Section-level exact/near duplicate clusters retain every page's provenance while selecting one canonical content atom. Page repetition within that family never increments independent evidence count. `Sell the Truth` and `Live in the Future` are separate families and independence groups.

## Claims and synthesis

Source claims are evidence sentences copied verbatim from an explicitly attributed official transcript turn. This intentionally favors entailment and auditability over editorial elegance. Canonical claims are non-destructive duplicate views; original source claims remain.

Theme trends and industry implications are marked as review-required system syntheses. They link source claim and evidence IDs, report independent family count, and cannot pose as a speaker quotation. The current implementation uses deterministic parsing, text hashing, conservative similarity, and rule-based claim/theme classification. It makes no DeepSeek or local-LLM call in the canonical run.

## Run

```bash
python3 -m gather_insight ingest-naval-recent-six \
  --output-dir input/corpora/naval_recent_six

# Verify the checked-in cache without network access.
python3 -m gather_insight ingest-naval-recent-six \
  --output-dir input/corpora/naval_recent_six \
  --offline
```

The six official HTML pages and public derived corpus are intentionally committed for this pilot. Environment files, model caches, and API responses remain ignored.

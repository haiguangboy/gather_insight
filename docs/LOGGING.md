# Logging and diagnosis

Every command creates a UTC `run_id` such as `20260718T220244Z_2a0a3e44`.

Two append-only JSONL streams are used:

- `logs/gather_insight.jsonl`: project-wide events, including source resolution before a media ID is bound;
- `data/media/<media_id>/logs/<run_id>.jsonl`: the complete event history for one media run.

Runtime JSONL files are ignored by Git. The durable `processing_report.json` stores the run ID, result, warning list, exception type, and log paths.

## Event sequence

Successful ingest normally emits:

```text
source.checked
source.selected
ingest.started
transcript.parsed
transcript.chunked
source.written
manifest.validated
evidence.written
review.ready
ingest.completed
```

Failures emit `source.unresolved` or `ingest.failed`. `ingest.failed` includes the exception type and traceback.

## Common diagnosis commands

```bash
# Find all errors
rg '"level":"ERROR"' logs data/media

# Follow one run across global and media logs
rg 'RUN_ID' logs data/media

# Inspect source fallback decisions
rg 'source\.(checked|selected|unresolved)' logs/gather_insight.jsonl

# Inspect the durable latest result for a media item
python3 -m json.tool data/media/MEDIA_ID/processing_report.json
```

## Data safety

The logger records counts, paths, provider states, hashes, and exception diagnostics. It does not record transcript bodies. URL query strings are removed except the public YouTube `v` identifier. Token-, secret-, password-, authorization-, and cookie-shaped fields are replaced with `<redacted>`.

Dual-source fusion additionally emits `fusion.started`, `fusion.ulisten_parsed`, `fusion.usetranscribe_parsed`, `fusion.degraded_mode`, `fusion.fixture_mode`, `fusion.completed`, and `fusion.failed`. The processing report records input hashes before and after the run so accidental raw-source modification can be diagnosed.

Phase 6.6 general resolution emits `transcript_source.checked`, `transcript_source.resolved`, `general_fusion.started`, `general_fusion.completed`, and `general_fusion.failed`.

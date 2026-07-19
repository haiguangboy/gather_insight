# GatherInsight

GatherInsight is an evidence-first pipeline for turning long-form interviews, podcasts, speeches, and official transcripts into traceable media evidence packages. It keeps source text, evidence, candidate judgments, and accepted knowledge separate.

The implemented scope is Phase 0/1/2 of [`gather_insight_system_spec.md`](gather_insight_system_spec.md): baseline fixtures, schemas, deterministic ingest, human review boundaries, source-priority resolution, VTT/SRT import, and structured diagnostics.

## Quick start

```bash
python3 -m gather_insight ingest \
  --url "https://www.youtube.com/watch?v=x2VHFgyawPE" \
  --transcript-file tests/fixtures/manual_transcript.md \
  --title "Example interview" \
  --participant "Guest Name"
```

The command writes `data/media/<media_id>/manifest.yaml`, `source.md`, `evidence.jsonl`, `review.md`, `processing_report.json`, and a per-run JSONL log. Re-running the same input is data-idempotent while every run receives a unique `run_id`. A changed source is rejected unless `--force-source` is explicit, and an existing human `review.md` is never overwritten.

`--provider auto` is the default. It checks `--official-file`, `--ulisten-file`, `--usetranscribe-file`, `--transcript-file`, and `--youtube-export-file` in source-policy order. `resolve-sources` performs the checks without ingesting. URL-only hints are recorded but require a human export before they can become the selected text source.

## Dual-source fusion

For the YC Paper Club fixture:

```bash
python3 -m gather_insight fuse-transcript \
  --input-dir tests/fixtures/yc_paper_club
```

With the supplied bundle this intentionally runs degraded mode: no real `source_usetranscribe_raw.md` exists, so all `alignment_confidence` values remain `null`. To test the declared spacing fixture explicitly:

```bash
python3 -m gather_insight fuse-transcript \
  --input-dir tests/fixtures/yc_paper_club \
  --use-fixture
```

Outputs are written under `data/media/<media_id>/fusion/`: `transcript_fused.jsonl`, `transcript_fused.md`, `alignment_report.md`, `review_queue.md`, `fusion_manifest.json`, and `processing_report.json`.

For general source combinations, including UseTranscribe-only videos without uListen:

```bash
python3 -m gather_insight fuse-general \
  --input-dir tests/fixtures/dario_bloomberg_text_single
```

This writes to `data/media/<media_id>/general/` and separates text review from speaker-attribution review. See `docs/PHASE_6_6_SOURCE_RESOLUTION.md` for the six-mode state machine.

Phase 6.9 Vecalign-style local BGE-M3 alignment:

```bash
python3 -m gather_insight fuse-general \
  --input-dir <input_dir> \
  --semantic-mode local_semantic \
  --alignment-algorithm vecalign \
  --alignment-score-mode margin
```

Use `--alignment-score-mode raw_cosine` for the raw-cosine baseline. Phase 6.8 remains available with `--alignment-algorithm phase_6_8_beam`. Vecalign/SentAlign modes never call DeepSeek or Qwen.

## Manual transcript format

```markdown
# Interview title

## [00:10-00:32] Host | Opening

Question text.

## [00:32-01:05] Guest | Opening

Answer text.
```

Inline cues such as `[01:05] Guest: answer text` are also accepted, but ranged cues are preferred because evidence needs an end timestamp.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

No audio, video, Whisper, database, login automation, or paid API is required.

# GatherInsight

GatherInsight is an evidence-first pipeline for turning long-form interviews, podcasts, speeches, and official transcripts into traceable media evidence packages. It keeps source text, evidence, candidate judgments, and accepted knowledge separate.

The implemented scope is Phase 0/1 of [`gather_insight_system_spec.md`](gather_insight_system_spec.md): baseline fixtures, schemas, manual Markdown ingest, deterministic evidence construction, validation, and a human review gate.

## Quick start

```bash
python3 -m gather_insight ingest \
  --url "https://www.youtube.com/watch?v=x2VHFgyawPE" \
  --transcript-file tests/fixtures/manual_transcript.md \
  --provider manual_markdown \
  --title "Example interview" \
  --participant "Guest Name"
```

The command writes `data/media/<media_id>/manifest.yaml`, `source.md`, `evidence.jsonl`, `review.md`, and `processing_report.json`. Re-running the same input is idempotent. A changed source is rejected unless `--force-source` is explicit, and an existing human `review.md` is never overwritten.

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


# Dual-source transcript contract

## Authority split

- uListen is the structure authority: chapter, speaker, segment boundaries, timestamps, and paper links.
- UseTranscribe is the readable-text authority when a real `source_usetranscribe_raw.md` exists.
- YouTube is the conflict-resolution source and the only source of the canonical video ID.

For the YC fixture, `media_id` is always `yt_wE1ZgJdt4uM`. The uListen page suffix `gSNFJbgoaHI` is stored only as `provider_id`.

## Parsed segment stream

Both parsers produce a common segment shape validated by `schemas/transcript_segment.schema.json`. uListen segments have a speaker and chapter; UseTranscribe segments use `speaker: null` unless the source explicitly supplies a speaker.

## Fused stream

Production `transcript_fused.jsonl` is segment-only JSONL. It does not embed manifest or chapter records. Reports and Markdown carry aggregate metadata.

Three modes are legal:

- `dual_source`: real uListen and real UseTranscribe; confidence is numeric;
- `degraded`: UseTranscribe is absent; text remains uListen raw and confidence is `null`;
- `fixture`: a declared readable fixture is used for structural regression only; confidence is `null` and every segment requires review.

Fixture text must never be relabeled as `usetranscribe_manual_export`.

## Immutability

Raw inputs are opened read-only. Outputs are written to a separate directory. Integration tests hash every input before and after a workflow run.


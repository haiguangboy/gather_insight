# Source resolution report

- media_id: `yt_x2VHFgyawPE`
- fusion_mode: `text_single`
- structure_source: `text_timeline`
- text_source: `usetranscribe`
- segment_count: `5`
- text_review_count: `0`
- speaker_review_count: `5`
- numeric_alignment_confidence_count: `0`
- fusion_diagnostics: `null`
- sources: `{"ulisten": {"provider": "ulisten", "filename": "source_ulisten_raw.md", "path": "tests/fixtures/dario_bloomberg_text_single/source_ulisten_raw.md", "status": "missing", "available": false, "is_fixture": false}, "usetranscribe": {"provider": "usetranscribe", "filename": "source_usetranscribe_raw.md", "path": "tests/fixtures/dario_bloomberg_text_single/source_usetranscribe_raw.md", "status": "fixture", "available": true, "is_fixture": true}, "official_transcript": {"provider": "official_transcript", "filename": "source_official_transcript_raw.md", "path": "tests/fixtures/dario_bloomberg_text_single/source_official_transcript_raw.md", "status": "missing", "available": false, "is_fixture": false}}`

## Limitations

- Speaker attribution is unavailable and must remain null or unknown until reviewed.
- source_usetranscribe_raw.md is a UseTranscribe-format developer fixture, not a fetched provider export.
- Text was selected from the public YouTube caption baseline solely to exercise text_single behavior.
- Do not publish or cite this fixture as a UseTranscribe transcript.

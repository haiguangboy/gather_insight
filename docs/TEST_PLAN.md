# Test plan

Phase 0/1 tests cover:

- YouTube URL normalization and stable IDs;
- timestamp parsing and formatting;
- Markdown cue parsing and bounded semantic grouping;
- valid YouTube timestamp links;
- evidence uniqueness and interval validity;
- JSON Schema validation;
- repeat-ingest idempotency;
- preservation of a human-edited `review.md`;
- refusal to overwrite a changed source without an explicit flag.

The Dario golden directory tracks high-value claims and the required attribution boundary for “5x coding ≠ 5x company.” Later phases will add speaker precision, claim recall, and insight precision evaluation.

## Dual-source transcript acceptance

The YC Paper Club workflow additionally verifies:

- seven chapters and all six speakers are retained;
- all 115 segments have unique deterministic IDs and YouTube timestamp links;
- degraded and fixture modes keep every `alignment_confidence` as `null`;
- a placeholder file is never mistaken for real `source_usetranscribe_raw.md`;
- numeric and model-name conflicts appear in `review_queue.md`;
- five core outputs are byte-identical across repeated runs;
- every input file hash is unchanged after the workflow;
- missing uListen input creates an explicit failure report and structured error log.

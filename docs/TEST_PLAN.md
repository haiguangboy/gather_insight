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


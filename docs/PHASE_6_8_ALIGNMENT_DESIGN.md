# Phase 6.8 — Constrained monotonic semantic alignment

## Scope

Phase 6.8 changes only `dual_source` and `official_dual` text allocation. Single-source modes, including the accepted Dario `text_single` path, do not invoke semantic alignment.

The implementation has three layers:

1. deterministic segmentation, anchors, time windows, entity extraction, penalties, and monotonic constraints;
2. local Ollama BGE-M3 semantic vectors;
3. optional DeepSeek candidate judgment for a bounded set of ambiguous or speaker-boundary cases.

No Qwen model is used in this phase. No model may generate or rewrite final transcript text.

## Semantic units

`semantic_unit_segmenter.py` converts every coarse secondary segment into sentence, clause, or event units. Sentence punctuation is preferred, followed by semicolons/colons and conservative conjunction boundaries for overlong clauses. Events such as `[applause]`, `[laughter]`, and `[music]` remain independent units.

Every unit retains:

- source secondary segment ID;
- exact text slice;
- canonical parsed-corpus character and token offsets;
- proportional approximate timestamps;
- unit type and boundary confidence.

Final readable text is assembled only from these source slices.

## uListen alignment text

`alignment_text_builder.py` produces non-authoritative `text_ulisten_alignment` for scoring. It protects speaker/chapter/reference terms, inserts deterministic punctuation/case/number boundaries, and optionally uses `wordninja` for conservative English spacing recovery.

The original `text_ulisten_raw` is never replaced. Alignment text is written only to the private trace and is explicitly marked non-authoritative.

## Candidate scoring

All weights live in semantic alignment configuration:

```text
0.45 semantic similarity
0.20 lexical anchors
0.15 entity consistency
0.10 time prior
0.10 sequence context
- configured penalties
```

Penalties cover length mismatch, time-window deviation, low-information phrases, and numeric/model/negation/protected-term conflicts. Time filters and biases candidates but never directly copies a whole coarse segment.

BGE-M3 embeds uListen alignment texts and semantic units. A multi-unit candidate uses a length-weighted, L2-normalized pool of its unit vectors. This bounds embedding work while still using BGE-M3 for every semantic comparison.

## Global monotonic path

A beam-search dynamic program advances through structure segments and secondary units. Each path may:

- match one structure segment to up to six consecutive units;
- skip a structure segment and fallback;
- skip secondary units and leave them unallocated.

The secondary cursor only moves forward. Unit and character reuse are impossible by construction. Candidate windows and beam width are configurable.

Near-equal nested candidates are reduced to a conservative common unit interval when that interval remains above the unchanged acceptance threshold. Disjoint ambiguity falls back.

## Speaker boundaries and fallback

Different speakers never share semantic units or character ranges. Low-confidence same-source boundaries are reviewed. Unresolved judge cases, judge call-limit cases, critical entity/negation conflicts, low scores, and non-monotonic judge choices all fallback to uListen raw text and remain in review.

Unused units are written to `unallocated_secondary.jsonl`. Detailed candidates and decisions are written to `alignment_trace.jsonl`; formal fused JSONL keeps only allocation IDs, source offsets, component scores, boundary confidence, and fallback state.

## Semantic providers and caches

`semantic_scorer.py` provides:

- Ollama embedding scorer;
- deterministic test scorer;
- explicit degraded lexical scorer;
- DeepSeek boundary judge;
- deterministic mock judge;
- JSONL hash caches.

Ollama cache keys include text SHA-256, model name and digest, normalization, dimension, semantic-unit version, and alignment-text version. Vectors are L2-normalized when configured.

DeepSeek reads `DEEPSEEK_API_KEY` only from the environment. It receives one structure segment, short neighbor context, and at most five source-derived candidates. Flash with thinking is tried first; invalid/abstain responses may escalate to Pro. Invalid and abstain results are cached so repeated runs remain deterministic and do not repeatedly spend API calls.

Runtime cache/API counters live in `processing_report.json`. Stable outputs omit runtime-only counters so cache cold/warm state does not break output idempotency.

## read_papers reference

The following implementation patterns were adapted from `haiguangboy/read_papers`:

- Ollama `/api/embed` batch requests;
- BGE-M3 defaults and empty query/passage prefixes;
- L2 vector normalization;
- text/model hash cache invalidation;
- environment-first `DEEPSEEK_API_KEY`;
- Flash + thinking with Pro escalation;
- deterministic mock backends.

GatherInsight-specific code is new: semantic-unit character projection, uListen alignment text, monotonic beam path, speaker-boundary hard constraints, transcript fallback, trace output, and allocation diagnostics. Neither project imports the other. A small provider/cache library could be extracted later, but no shared repository is created in this phase.

# Phase 7.0: No-uListen Trend-Mode Ablation

## Decision

GatherInsight now distinguishes two transcript operating modes:

- `high_quality_structure_mode`: uListen structure plus a readable transcript, using Vecalign raw cosine as the current baseline.
- `dual_text_trend_mode`: two non-uListen transcript sources, optimized for ordered reading, coverage, provenance, conflict retention, and high-recall trend discovery. It does not claim human-grade segment or speaker boundaries.

Trend discovery, candidate evidence, and exact attribution are evaluated separately. Character-perfect alignment is not a prerequisite for trend discovery.

## Blind experiment contract

The Phase 7.0 blind runner refuses to start when its input directory contains:

- `source_ulisten_raw.md`;
- a filename containing `ulisten`;
- `transcript_fused.jsonl`;
- `alignment_trace.jsonl`;
- `unallocated_secondary.jsonl`.

The no-uListen output is hashed and frozen before the comparison command is allowed to read Result B. The comparison command verifies every frozen output hash.

## Private YC inputs

The isolated private input directory contains only:

1. UseTranscribe manual export, SHA-256 `7f9db260106f4eb529bb6f244aee1de009a6216382d0291bc5eba1c0d4e6f9e9`;
2. YouTube `en-orig` automatic WebVTT captions, SHA-256 `233428ff8c10174833a8e19fd4bc3ce6f61df6d13f9a6f7d2b2ce614dbfe292a`;
3. a private manifest containing YouTube platform chapters and presenter names.

The YouTube caption was acquired directly from the video with `yt-dlp`; it was not derived from uListen or a GatherInsight fusion output.

The sources have normalized sequence similarity `0.999690` and shared 8-gram rate `0.999039`. They are therefore highly likely to share the same upstream caption or ASR signal. The experiment measures the contribution of uListen structure, but it is not evidence that two independent ASR systems correct one another.

## Fusion flow

1. Remove rolling duplication from YouTube automatic captions while retaining raw cue ranges.
2. Split both transcripts into conservative semantic units.
3. Align the two text sequences with the existing Vecalign raw-cosine DP and local Ollama `bge-m3:latest` embeddings.
4. Preserve monotonic order, gaps, both source ranges, agreement scores, and conflicts.
5. Use the readable UseTranscribe text for matched records; retain meaningful target-only gaps separately.
6. Freeze all blind outputs.
7. Only then load Result B, its meaningful unallocated content, and its conflicts for the upper-layer comparison.

No DeepSeek, Qwen, transcript rewriting, new alignment algorithm, or uListen-derived boundary is used in the blind run.

## Speaker contract

YouTube platform chapters provide section-level presenters. Records away from chapter boundaries use:

- `speaker_status=section_inferred`;
- `attribution_scope=section`;
- `speaker_confidence=0.82`;
- `exact_quote_allowed=false`.

Short records near chapter boundaries use `boundary_uncertain`. The opening section without a named presenter remains `unknown`. Future audio/video confirmation may upgrade a record to `audio_confirmed`; the current Phase 7.0 run does not do so.

## Real YC results

### Dual-text transcript

- UseTranscribe segments: 62
- cleaned YouTube caption segments: 1,883 from 3,771 rolling cues
- source A semantic units: 743
- source B semantic units: 2,471
- fused path records: 741
- matched records: 734
- source B character consumption: 98.9706%
- meaningful unmerged records: 1
- exact adjacent duplication: 0
- character reuse: 0
- monotonic violations: 0
- conflict records: 13
- BGE-M3 active and non-degraded

Speaker status:

- section inferred: 691 records
- boundary uncertain: 44 records
- unknown: 6 records
- exact quote allowed: 0 records

### High-value candidates

- no-uListen high-recall candidates: 155
- uListen-supported candidates from the same extractor: 90
- strict one-to-one block matches: 42
- strict one-to-one recall proxy: 46.67%
- topic/time recall proxy: 96.67%
- topic/time precision proxy: 100%
- non-consensus recall proxy: 33.33%

All eight detected technical routes appear in both modes:

- speculative decoding and verification;
- diffusion planning and MPC;
- world models and latent planning;
- data scaling;
- data-limited pretraining under abundant compute;
- generalization theory and PAC-Bayes;
- model/training efficiency;
- failure modes and boundary conditions.

The resulting trend-route set does not change materially without uListen. The low strict block-match score mainly reflects different segmentation and candidate granularity; the topic/time metric is the more useful high-recall measurement here. Neither metric is a substitute for human candidate gold labels.

## Remaining omissions and errors

Two meaningful uListen-supported candidate blocks were not independently recovered under the same topic/time label:

- overlapping the next speculative draft round with verification;
- downstream benchmark behavior when optimizing IID validation loss.

A third reported omission is an extractor classification false positive in the introductory community discussion, not a missing technical result.

Both transcript sources preserve common ASR errors, including short examples such as `cash hit rate` for cache hit rate, `word model` for world model, `collision` for condition, and distorted person/model names. High source agreement cannot correct a shared upstream error.

The conflict queue found 11 entity disagreements and 2 negation disagreements. No numeric source conflict was detected, but 13 no-uListen candidates contain numbers requiring verification. Absence of disagreement is not proof that a number is correct when the sources share an upstream signal.

## Layered acceptance

- **Trend discovery: A for this YC experiment.** The major technical routes and trend implications remain stable, meaningful gaps are retained, and no broad topic drift was observed.
- **Candidate evidence: B.** Source ranges and timestamps are available, but non-consensus recall and shared-ASR errors require focused verification of final candidates.
- **Exact attribution / quotation: C.** Section-level speakers are useful for trend candidates, but no no-uListen record is automatically authorized for exact quotation.

As a general production claim, `dual_text_trend_mode` remains **B** until it is also tested with two genuinely independent low-cost transcript providers. It is already sufficient for high-recall trend discovery under the two-pass policy: retain everything cheaply, then verify the small final candidate set carefully.

## Commands

```bash
python3 -m gather_insight fuse-no-ulisten-trend \
  --input-dir input/phase_7_0_blind_inputs/yc \
  --output-dir input/phase_7_0_outputs/blind_yc_final \
  --semantic-mode local_semantic \
  --semantic-config config/semantic_alignment.example.yaml \
  --semantic-cache-root input/phase_7_0_private_cache

python3 -m gather_insight compare-phase7-trend \
  --blind-output-dir input/phase_7_0_outputs/blind_yc_final \
  --ulisten-result-dir input/phase_6_9_outputs/raw_final2/yt_wE1ZgJdt4uM/general \
  --output-dir input/phase_7_0_outputs/comparison_yc_final
```

Complete transcripts, HTML, candidate JSONL, conflict rows, traces, caches, and comparison outputs remain under the gitignored `input/` tree.

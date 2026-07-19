# Phase 6.9 — Vecalign/SentAlign real YC acceptance

Date: 2026-07-19

Full provider transcripts, embeddings, paths, fused output, and unallocated semantic units remain in Git-ignored local directories. This committed report contains only aggregate metrics and truncated samples.

## Implementation and backend

- Source sequence: 115 uListen structure segments.
- Target sequence: 743 sentence/conservative-clause/event units from the real UseTranscribe export.
- Embedding backend: local Ollama `bge-m3:latest`, 1024 dimensions, L2 normalized.
- Model digest: `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`.
- DeepSeek: disabled.
- Qwen: not used.
- DP state: `(i, j)`, the number of source and target units consumed.
- Final operations enabled: `1:1` through `1:6`, `2:1`, `3:1`, legal many-to-many operations with total size at most seven, plus `1:0` and `0:1` gaps.
- Time is a legal search band only. It does not choose the text.
- Acceptance thresholds remain 0.65/0.85.

The implementation decision and upstream license/dependency review are in `PHASE_6_9_EXISTING_ALIGNMENT_REVIEW.md`.

## Real comparison

| Metric | Phase 6.8 local beam | Vecalign raw cosine | Vecalign margin | SentAlign-style margin |
|---|---:|---:|---:|---:|
| Readable assignment | 91/115 | 114/115 | 100/115 | 102/115 |
| Readable assignment rate | 79.13% | 99.13% | 86.96% | 88.70% |
| No-review segments | 5 | 5 | 1 | 1 |
| Needs review | 110 | 110 | 114 | 114 |
| Fallbacks | 24 | 1 | 15 | 13 |
| Semantic units allocated | 278 | 659 | 596 | 607 |
| Accepted character consumption | 42.24% | 90.47% | 82.36% | 83.14% |
| Unallocated characters | 40,544 | 6,690 | 12,383 | 11,834 |
| Cross-speaker boundary anomalies | 12/12 review/fallback | 8/12 coarse-source overlap | 8/12 coarse-source overlap | 9/12 coarse-source overlap |
| Secondary character reuse | 0 | 0 | 0 | 0 |
| Monotonic violations | 0 | 0 | 0 | 0 |
| Cross-speaker shared characters | 0 | 0 | 0 | 0 |
| Exact adjacent duplication | 0 | 0 | 0 | 0 |
| Partial adjacent duplication | 0.0333 | 0.0177 | 0 | 0 |

Vecalign raw cosine substantially increases source-character consumption without lowering the acceptance threshold. Margin scoring changes the global path, but conservative confidence calibration rejects 15 paths whose raw cosine is below 0.65. This avoids the initial, invalid result where percentile-normalized margin values made every segment appear `>=0.85`.

## Exact path operations

Vecalign raw cosine selected:

- `1:1`: 1;
- `1:2`: 2;
- `1:3`: 1;
- `1:4`: 1;
- `1:5`: 10;
- `1:6`: 100;
- `0:1`: 81;
- total path steps: 196.

Vecalign margin selected:

- `1:3`: 1;
- `1:4`: 1;
- `1:5`: 2;
- `1:6`: 111;
- `0:1`: 60;
- total path steps: 175.

SentAlign-style margin selected a nearly identical but not byte-identical full-DP path: 61 target gaps, one `1:3`, one `1:4`, three `1:5`, and 110 `1:6` operations. The SentAlign score recurrence uses its published merge exponent/free-concatenation rule and a 0.4 gap cutoff; its post-path LaBSE-specific re-embedding stack was not imported.

## Confidence and review

Vecalign raw cosine:

- `>=0.85`: 7;
- `0.65–0.85`: 107;
- fallback/null confidence: 1.

Primary review reasons are not hidden:

- negation conflict: 36;
- coarse secondary segment used on both sides of a speaker change: 23 records;
- explicit speaker-boundary overlap: 15 records;
- model-name conflict: 12;
- protected-term conflict: 12;
- numeric conflict: 6.

Margin-normalized score is used for path selection, but formal confidence is the conservative minimum of normalized margin and raw cosine. Margin therefore cannot manufacture high-confidence records solely through percentile scaling.

## Speaker boundaries

Raw-cosine boundary audit:

| Time | Transition | Result |
|---|---|---|
| 3:43 | Francois → Tanishq | anomaly; same coarse secondary segment |
| 3:44 | Tanishq → Francois | fallback/no shared accepted text |
| 3:49 | Francois → Tanishq | no coarse overlap |
| 17:32 | Tanishq → Francois | anomaly |
| 18:33 | Francois → Guangyao | no coarse overlap |
| 29:50 | Guangyao → Francois | anomaly |
| 30:18 | Francois → Isaac | anomaly |
| 43:15 | Isaac → Francois | anomaly |
| 43:52 | Francois → Akshay | anomaly |
| 50:19 | Akshay → Francois | anomaly |
| 51:24 | Francois → Konwoo | anomaly |
| 1:06:20 | Konwoo → Francois | no coarse overlap |

No semantic unit or character is shared. The remaining issue is boundary ownership inside the same coarse UseTranscribe segment. Eight of twelve boundaries still require human review, so the speaker-boundary acceptance target is not met.

## Manual golden status

The repository now contains a deterministic evaluator for alignment precision/recall/F1, character-overlap precision/recall/F1, wrong-speaker assignments, boundary accuracy, and fallback accuracy. Its tests use hand-authored gold.

There is no independently human-annotated YC character-range golden file in the supplied private inputs. This report therefore does **not** fabricate alignment precision/recall/F1 from the system's own output or from its 0.65/0.85 thresholds. Those metrics remain `N/A` until the 52-item audit set is annotated independently:

- 12 speaker switches;
- 20 ordinary talk segments;
- 10 short/repeated phrases;
- 10 Phase 6.8 fallbacks.

The twelve boundary cases above were manually inspected for the narrower boundary-overlap diagnosis, but they are not sufficient to claim full alignment or character-overlap F1. This missing independent golden alone prevents an A/B acceptance claim.

## Meaningful unallocated text

Raw cosine leaves 84 units / 6,690 characters unallocated. Long examples include truncated passages about:

- why over-parameterized PAC-Bayes bounds become loose and vacuous;
- observation-versus-state notation in real systems;
- compute per data point increasing roughly 4× year over year;
- data-scaling-law experiments up to 1.7B pre-training tokens;
- speculative-decoding verification dependencies;
- rethinking the stack under a new algorithmic regime.

These remain in `unallocated_secondary.jsonl`; they are not silently attached to neighboring speakers.

## Improved and worst cases

Phase 6.8 fallbacks that become readable under raw-cosine DP include truncated samples from:

- `seg_0025`: precomputation and fast-forwarding inference;
- `seg_0048`: action-proposal ranking at policy deployment;
- `seg_0050`: fixed-reward single-task evaluation;
- `seg_0067`: representation-collapse local minima;
- `seg_0072`: open-loop world-model prediction;
- `seg_0085`: over-parameterization and benign overfitting;
- `seg_0095`: data constraints and scaling motivation;
- `seg_0107`: roughly 5× data-efficiency result;
- `seg_0109`: amortizing test-time compute during training;
- `seg_0111`: distillation and continued-training settings.

Highest-priority failures/reviews include:

- `seg_0012`: fallback at the one-second Tanishq/Francois turn;
- `seg_0011`: only “All right” at a repeated short-turn boundary;
- `seg_0035/0036`: numeric/model conflicts around a speaker change;
- `seg_0052/0053/0054`: Google DeepMind closing, host introduction, and Isaac opening share coarse source segments;
- `seg_0080/0081`: applause/closing versus next host introduction;
- `seg_0082/0083`: “Welcome Akshay”, applause, and opening remarks;
- `seg_0092/0093`: no-free-lunch conclusion versus host transition;
- `seg_0094/0095`: host introduction versus Konwoo opening, with numeric/model conflicts.

These errors are preserved in the review queue.

## Runtime, immutability, and idempotency

- Initial cold BGE embedding: 858 texts, 14 Ollama batches, 196.54 seconds. Correcting the alignment-text version in the cache key caused one expected one-off refresh; all later runs were cache hits.
- Warm raw-cosine DP: 6.82 seconds.
- Warm margin DP: 9.39 seconds.
- Warm SentAlign-style DP: 9.15 seconds.
- Stable margin output hashes were identical on repeated runs.
- uListen SHA-256 remained `1c2131f4bea69e96d145fe244f525c589b6994f8faa8427675593554d17a84b6`.
- UseTranscribe SHA-256 remained `7f9db260106f4eb529bb6f244aee1de009a6216382d0291bc5eba1c0d4e6f9e9`.

## Dario regression

Dario remains unchanged in `text_single` mode:

- 149 segments;
- 0 text-review items;
- 149 speaker-review items;
- speaker is null for 100%;
- alignment confidence is null for 100%;
- `source_is_fixture=false` for 100%;
- final end time is 4204 seconds;
- input SHA-256 remains `d6d0c4e914d65938e66d574b51380b9b50655946aa7eb1bf2a4e650949d14a64`.

No semantic aligner is invoked for Dario.

## Tests

```text
Ran 81 tests in 0.695s
OK
```

New coverage includes standard DP operations and gaps, raw/margin comparison, deterministic mock scoring, SentAlign-style recurrence selection, workflow integration, idempotency, unallocated target text, speaker-character hard constraints, and golden metric calculation.

## Conclusion

**Phase 6.9 YC result: C — alignment remains unreliable for evidence extraction.**

The mature DP formulation materially improves readable allocation and character consumption while preserving all hard safety constraints. It does not solve speaker-boundary ownership: raw cosine still has eight abnormal switch points, margin has eight, and SentAlign-style margin has nine. Independent 52-item character-range gold is also absent, so precision/recall/F1 cannot be claimed honestly.

The correct next action is not another custom alignment algorithm. It is to annotate the independent YC golden set, use it to compare upstream Vecalign/SentAlign parameters and speaker-block partitioning, and only then decide whether a small adapter correction is justified.

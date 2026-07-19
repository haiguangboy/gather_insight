# Phase 7.1 Real YC Report

## Result

Phase 7.1 is usable as a high-recall, evidence-bound value layer. The no-uListen path retained all 25 claims in the current private YC golden draft, every produced claim has source evidence, and meaningful unmerged text participates in extraction. The result is ready for limited Phase 7.2 theme aggregation, but the golden draft still needs independent reviewer freeze and risk-sensitive candidates still need verification.

This report contains aggregate statistics and short descriptions only. Full provider transcripts, claims, evidence, model judgments, review pages, and golden labels remain under gitignored `input/` paths.

## Inputs and isolation

- `dual_text_trend_mode` uses only the frozen Phase 7.0 no-uListen result, its meaningful-unmerged record, conflict queue, and source hashes.
- `high_quality_structure_mode` uses the frozen Result B transcript, meaningful unallocated text, conflict queue, and its uListen/UseTranscribe source hashes.
- Phase 7.1 did not rerun or tune transcript alignment.
- No model was allowed to alter transcript or evidence text.

## Real-run output

| Metric | dual_text_trend_mode | high_quality_structure_mode |
|---|---:|---:|
| Canonical transcript records | 741 | 115 |
| Meaningful-unmerged inputs | 1 | 30 |
| High-recall seeds | 308 | 248 |
| Claims | 285 | 227 |
| Evidence records | 266 | 129 |
| Theme assignments | 285 | 227 |
| Claim relations | 119 | 252 |
| Trend candidates | 89 | 106 |
| Verification queue | 285 | 227 |
| Claims from meaningful-unmerged | 1 | 22 |
| Evidence traceability | 100% | 100% |
| Unsupported claims | 0 | 0 |
| Entity-risk claims | 45 | 98 |
| Numeric-risk claims | 52 | 92 |
| Negation-risk claims | 27 | 79 |

DeepSeek `deepseek-v4-flash` with thinking judged only the top 32 evidence-bound candidates in each mode, in four cached batches. It did not generate claims or evidence. The final rerun used four cache hits per mode and made zero new API calls. Qwen was not used.

## Private golden evaluation

The draft contains 25 items: five macro-route claims, five non-consensus claims, five failure/boundary claims, five quantitative/entity-sensitive claims, and five hidden assumptions.

| Metric | dual_text_trend_mode | high_quality_structure_mode |
|---|---:|---:|
| Overall claim recall | 100% | 100% |
| Non-consensus recall | 100% | 100% |
| Failure-mode recall | 100% | 100% |
| Quantitative claim recall | 100% | 100% |
| Boundary-condition recall | 100% | 100% |
| Meaningful omission rate | 0% | 0% |
| Evidence traceability | 100% | 100% |
| Unsupported claim count | 0 | 0 |
| Claim precision proxy | 8.77% | 11.01% |
| Wrong-speaker gold matches | 25 | 4 |
| Entity-risk detection recall | 50.00% | 85.71% |
| Numeric-risk detection recall | 70.00% | 100% |
| Negation-risk detection recall | 36.36% | 72.73% |

The low precision proxy is expected from the deliberately high-recall first pass: it divides matched gold items by every candidate and is not a human precision score. A human review sample is still required to measure true precision. The no-uListen speaker count also reflects the stricter golden speaker requirement: section-level inference is sufficient for trend discovery but deliberately fails exact-attribution evaluation.

The 100% recall result is promising but not yet a final external benchmark. The golden is a private reviewer draft selected from available YC evidence, so selection bias is possible. It should be independently reviewed and frozen before future algorithms are compared against it.

## High-value findings recovered

The value layer surfaced the following families of claims:

- speculative decoding is constrained by sequential verification, while parallel drafting/verification changes the useful route;
- model-predictive control quality depends jointly on dynamics-model error and planner behavior, with errors compounding over long horizons;
- latent world-model planning can offer large speed gains, but representation mismatch and regularization are material boundary conditions;
- robotics/video-only learning remains constrained by data and action grounding rather than only model scale;
- under data-limited and compute-rich conditions, conventional scaling recipes can overfit or approach an asymptote, changing the optimal training strategy;
- smaller-model ensembles and distillation can outperform a single larger model under specific resource/data constraints;
- downstream transfer may depend on IID-like assumptions that validation loss alone does not reveal;
- several numeric claims—model sizes, speedups, investment, data growth, and compute ratios—are potentially decision-changing but require source verification.

These claims are summaries. Exact wording remains in private evidence records and is linked to time ranges and source hashes.

## Failure analysis

An earlier extraction pass missed three draft-gold items even though their supporting text was present: a small-model ensemble result, a data-growth-versus-compute-growth signal, and an IID downstream-transfer condition. The cause was value extraction and topic labeling, not transcript omission. The added atomic risk-sensitive pass recovered all three without changing transcript alignment.

Remaining weaknesses are concentrated in:

- overly broad high-recall candidates that need reject/merge review;
- ASR entity spellings and specialist terms;
- no-uListen section-level speaker attribution;
- negation and entity risk detection, especially in the dual-text path;
- exact numerical claims whose two transcript sources may share the same upstream caption error.

No evidence-free hallucinated claim was produced (`unsupported_claim_count=0`).

## Meaningful-unmerged handling

Meaningful-unmerged input is canonicalized alongside normal transcript records and is not filtered out by value extraction. It generated one claim in `dual_text_trend_mode` and 22 claims in `high_quality_structure_mode`. Such claims are explicitly marked, placed in the verification queue, and never granted exact-quotation permission automatically.

## Verification policy

Claims can enter a long-term theme library when they have clear evidence, adequate context, and no unresolved numeric/entity/negation or attribution risk. Route-change mechanisms, failure modes, and boundary conditions can enter as provisional research claims with their verification status preserved.

The following still require video or paper review before exact use:

- numeric speedup, parameter-count, investment, growth-rate, and compute-ratio claims;
- person, company, paper, and model names with ASR risk;
- claims whose conclusion changes under a negation;
- section-inferred speakers or chapter-boundary statements;
- any claim intended as an exact quotation.

## Phase 7.0 comparison

Phase 7.0 used a coarse proxy candidate layer and recovered only part of the non-consensus set. The Phase 7.1 draft-golden non-consensus recall is 100%, materially above the earlier proxy result, because Phase 7.1 extracts atomic evidence-bound claims and treats meaningful-unmerged text as a first-class source. Because the golden is not yet independently frozen, this comparison is directional rather than a final benchmark.

## Layered rating

- Trend discovery / high-value recall: **A**. The current draft golden is fully recalled, meaningful-unmerged content participates, and no unsupported claim exists.
- Candidate evidence: **B**. Traceability is complete, but candidate precision, risk detection, and exact speaker requirements still need bounded review.
- Exact attribution / quotation: **C** for no-uListen and **B** for Result B. Exact speaker, entities, numbers, negation, and quotations remain verification tasks.
- Readiness for Phase 7.2 cross-source theme aggregation: **B**. The data contracts are ready for limited aggregation with verification state preserved; independently freezing the golden and reviewing top claims should precede treating aggregated conclusions as publishable facts.


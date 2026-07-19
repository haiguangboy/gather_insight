# Phase 7.1.1: Claim Consolidation and Human Quality Gate

Phase 7.1.1 is a review layer over Phase 7.1 outputs. It does not change transcript alignment, candidate extraction, `claims.jsonl`, or `evidence.jsonl`.

## Immutable layers

```text
claims.jsonl / evidence.jsonl       machine candidates and verbatim evidence
        │
        ├── review_decisions.jsonl  human decisions, entailment and verification
        ├── claim_merges.jsonl      parent candidate → canonical claim mappings
        ├── accepted_claims.jsonl   only claims allowed into Phase 7.2
        └── rejected_claims.jsonl   rejected candidates and reasons
```

The generated private page covers the 89 `dual_text_trend_mode` trend candidates. Algorithm names and machine scores are hidden by default. A reviewer can assign:

- `accept`, `reject_low_value`, `reject_incorrect`, `reject_unsupported`, `reject_duplicate`;
- `merge_into`;
- `needs_boundary_expansion`, `needs_context`, `needs_entity_verification`, `needs_numeric_verification`, `needs_negation_verification`, `needs_speaker_verification`.

The reviewer also records entailment (`fully_supported`, `supported_with_missing_condition`, `partially_supported`, `overgeneralized`, `contradicted`, `unrelated`), condition preservation, verification status, risk tags, notes, and review seconds.

## Golden review and freeze

`generate-phase711-golden-review` creates a private 50-slot package:

- the existing 25-item draft;
- 10 independent-important slots;
- 10 hard-negative slots;
- 5 ordinary-background overestimate slots.

The package stores `system_output_hidden=true`, reviewer/version fields, and change history. `freeze-phase711-golden` rejects incomplete packages and requires 40–50 completed items with the three independent category minimums. Until a human completes and freezes this package, the existing draft remains a draft and its recall cannot be treated as a final benchmark.

## Commands

```bash
python3 -m gather_insight generate-phase711-review \
  --media-root input/media/<media_id>/dual_text_trend_mode

python3 -m gather_insight finalize-phase711-review \
  --media-root input/media/<media_id>/dual_text_trend_mode \
  --decisions <downloaded_review_decisions.jsonl>

python3 -m gather_insight generate-phase711-golden-review \
  --draft <private_golden_draft.jsonl> \
  --output-dir <private_golden_review_dir>

python3 -m gather_insight freeze-phase711-golden \
  --reviewed <completed_golden_review.jsonl> \
  --output <frozen_golden.jsonl> \
  --reviewer <reviewer-id> \
  --golden-version yc_claim_golden_v2
```

## Metrics

The finalizer reports candidate acceptance, actual precision, low-value and incorrect rejection, duplicate and merge rates, candidates per canonical claim, entailment accuracy, condition preservation, wrong-speaker accepted claims, accepted-claim verification, and average human review time. These metrics are intentionally unavailable while decisions are blank; no placeholder acceptance or precision is fabricated.

Only `accepted_claims.jsonl` may be consumed by Phase 7.2. The current private YC package is therefore **pending human review**, and Phase 7.2 remains gated.


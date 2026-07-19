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

The golden work is split into two tasks.

### Phase 7.1.1a: review and freeze the existing golden

The current gate reviews the 25 populated `existing_reviewer_draft` rows. Empty authoring templates do not count as pending, do not enter the frozen output, and do not block freezing. All populated existing rows must be explicitly `approve`, `edit`, or `exclude`; the resulting `yc_claim_golden_v2.jsonl` must contain 20–25 approved/edited positives.

Freeze produces:

- `yc_claim_golden_v2.jsonl`;
- `golden_review_decisions.jsonl`;
- `golden_freeze_report.md`.

### Phase 7.1.1b: optional independent expansion

`generate-phase711-golden-review` also provides 25 optional authoring slots:

- the existing 25-item draft;
- 10 independent-important slots;
- 10 hard-negative slots;
- 5 ordinary-background overestimate slots.

These slots are displayed in a separate collapsed section. Completely empty slots are ignored. A partially filled slot is rejected loudly so incomplete evidence cannot enter a later expansion. Phase 7.1.1b is not a prerequisite for the Phase 7.2 gate.

The package stores `system_output_hidden=true`, reviewer/version fields, and change history. Until all 25 populated existing rows are reviewed and the positive subset is frozen, the existing draft remains a draft and its recall cannot be treated as a final benchmark.

## Commands

```bash
python3 -m gather_insight generate-phase711-review \
  --media-root input/media/<media_id>/dual_text_trend_mode

python3 -m gather_insight finalize-phase711-review \
  --media-root input/media/<media_id>/dual_text_trend_mode \
  --decisions <downloaded_review_decisions.jsonl>

python3 -m gather_insight generate-phase711-golden-review \
  --draft <private_golden_draft.jsonl> \
  --output-dir <private_golden_review_dir> \
  --reviewed <existing_golden_review_completed.jsonl>

python3 -m gather_insight adapt-phase711-golden-review \
  --input <legacy_golden_review_completed.jsonl> \
  --output <v2_compatible_review.jsonl> \
  --reviewer <reviewer-id>

python3 -m gather_insight freeze-phase711-golden \
  --reviewed <completed_golden_review.jsonl> \
  --output <frozen_golden.jsonl> \
  --reviewer <reviewer-id> \
  --golden-version yc_claim_golden_v2
```

The adaptation command is only for a reviewer-confirmed legacy export. It preserves the source file, converts populated legacy `pending` defaults to `approve`, normalizes completely empty expansion rows to `optional`, records change history, and produces an adaptation report before freeze.

## Metrics

The finalizer reports candidate acceptance, actual precision, low-value and incorrect rejection, duplicate and merge rates, candidates per canonical claim, entailment accuracy, condition preservation, wrong-speaker accepted claims, accepted-claim verification, and average human review time. These metrics are intentionally unavailable while decisions are blank; no placeholder acceptance or precision is fabricated.

Only `accepted_claims.jsonl` may be consumed by Phase 7.2. The current private YC package is therefore **pending human review**, and Phase 7.2 remains gated.

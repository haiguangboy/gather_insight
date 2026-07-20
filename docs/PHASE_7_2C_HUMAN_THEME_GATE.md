# Phase 7.2C.1 Human Theme Gate

Phase 7.2C is a strict human gate over the frozen Phase 7.2B package. It does
not fetch sources, rerun theme recall, alter Phase 7.2A raw material, or promote
machine-pending records automatically.

## Prepare the review package

```bash
python3 -m gather_insight prepare-phase72c-theme \
  --theme-dir knowledge/themes/ai_execution_commoditization_judgment_scarcity \
  --corpus-dir input/corpora/naval_recent_six
```

This creates three Gate A review pages and a claim-local P0 preview:

- `views/theme_claim_review.html` — all 30 theme canonical claims;
- `views/theme_relation_review.html` — all 10 relation candidates;
- `views/theme_insight_review.html` — all seven system syntheses;
- `views/p0_verification_review.html` — claim-local preview only; the active
  queue is regenerated after Gate A.

Preparation adds separate publication-family, speaker, organization, domain,
and evidence-type independence counts. Publication-family count is explicitly
not treated as independent industry corroboration.

P0 tokens must occur in the final claim and its direct supporting source claim
or local evidence span. Numbers or entities found only in a long linked section
do not create P0 work.

## Gate A

Review claims, insights, and relations first:

```bash
python3 -m gather_insight finalize-phase72c-gate-a \
  --claim-decisions /path/to/theme_claim_review_decisions.jsonl \
  --relation-decisions /path/to/relation_review_decisions.jsonl \
  --insight-decisions /path/to/insight_review_decisions.jsonl
```

Gate A writes provisional accepted assets and derives
`active_p0_verification_queue.jsonl`. Risks belonging to rejected, deferred, or
removed claims no longer block the theme. A relation whose parent was rejected
becomes `rejected_parent_claim` without additional relation review.

## Gate B and provisional freeze

The browser pages download four decision JSONLs. Finalization rejects incomplete
ID sets, pending decisions, unsupported accepted claims, unreviewed relation
direction, accepted insights whose supporting claims were rejected, and
deferred P0 verification.

```bash
python3 -m gather_insight finalize-phase72c-theme \
  --verification-decisions /path/to/p0_verification_decisions.jsonl
```

Every active P0 has two separate statuses: source fidelity checks what the
official source says and whether the claim preserves attribution, numbers,
negation, entities, and conditions; external fact status records whether the
speaker's real-world assertion has independent support.

Completed source fidelity permits `theme_judgment_v1` with status
`human_reviewed_provisional` even when external facts remain `not_checked`.
Those facts remain in `external_verification_queue.jsonl`. Publication drafts
are generated only when factual publication readiness is `ready`. An unchecked
external assertion may qualify only when the human final wording explicitly
frames it as a named speaker view or a provisional hypothesis; the system does
not add that qualification automatically.
The calibrated leading statement begins:

> 本批Naval及嘉宾语料共同指向一个值得进一步验证的判断……

Human-reviewed publication candidates remain drafts; the CLI never publishes.

# Phase 7.2C Human Theme Gate

Phase 7.2C is a strict human gate over the frozen Phase 7.2B package. It does
not fetch sources, rerun theme recall, alter Phase 7.2A raw material, or promote
machine-pending records automatically.

## Prepare the review package

```bash
python3 -m gather_insight prepare-phase72c-theme \
  --theme-dir knowledge/themes/ai_execution_commoditization_judgment_scarcity \
  --corpus-dir input/corpora/naval_recent_six
```

This creates four review pages and matching JSONL templates:

- `views/theme_claim_review.html` — all 30 theme canonical claims;
- `views/theme_relation_review.html` — all 10 relation candidates;
- `views/theme_insight_review.html` — all seven system syntheses;
- `views/p0_verification_review.html` — all conclusion-relevant P0 items.

Preparation adds separate publication-family, speaker, organization, domain,
and evidence-type independence counts. Publication-family count is explicitly
not treated as independent industry corroboration.

## Human decisions and finalization

The browser pages download four decision JSONLs. Finalization rejects incomplete
ID sets, pending decisions, unsupported accepted claims, unreviewed relation
direction, accepted insights whose supporting claims were rejected, and
deferred P0 verification.

```bash
python3 -m gather_insight finalize-phase72c-theme \
  --claim-decisions /path/to/theme_claim_review_decisions.jsonl \
  --relation-decisions /path/to/relation_review_decisions.jsonl \
  --insight-decisions /path/to/insight_review_decisions.jsonl \
  --verification-decisions /path/to/p0_verification_decisions.jsonl
```

Only a passing gate creates `theme_judgment_v1.json` and publication candidates.
The calibrated leading statement begins:

> 本批Naval及嘉宾语料共同指向一个值得进一步验证的判断……

Human-reviewed publication candidates remain drafts; the CLI never publishes.

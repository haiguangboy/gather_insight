# Phase 7.2B: Theme-Centric Consolidation Pilot

Theme: `ai_execution_commoditization_judgment_scarcity`

This workflow reads only the frozen Phase 7.2A Naval recent-six corpus. It does not fetch a seventh page, read audio, run ASR, modify raw HTML, use outside facts, or treat the description-only `Live in the Future` page as transcript support.

## Pipeline

1. Load the 566 Phase 7.2A canonical claims, canonical evidence, source-family relationships, and verification queue.
2. Exclude unknown-speaker and `Live in the Future` description records from claim support.
3. Embed seven concrete theme questions and all eligible claim-plus-evidence contexts with local Ollama `bge-m3:latest`.
4. Select a balanced high-recall set across all seven subthemes. Add bounded frame anchors so broad semantic categories do not swallow narrower mechanisms.
5. Ask DeepSeek Flash with thinking to judge only boundary relevance, bounded clusters, candidate claim relations, and seven evidence-linked synthesis hypotheses.
6. Reject invalid response fields, unrelated/contradicted consolidations, and ambiguous frame senses such as statistical “data distribution” being mistaken for business distribution.
7. Preserve source claims and evidence unchanged. Theme claims and insights are derived, review-pending records.

## Independence

The Frontier Founders serialized pages and compilation retain one independence group. `Sell the Truth` has weight one. `Live in the Future` has weight zero for this theme because no official transcript exists. Independent evidence is counted by source family, never page count.

## Model contract

- BGE-M3 provides semantic recall and frame similarity only; similarity is not logical support.
- DeepSeek receives bounded claims and evidence excerpts. It cannot add facts, repair source text, infer speakers, or produce publishable status.
- Invalid numeric confidence, missing IDs, invalid enum values, and malformed JSON are rejected and counted.
- API responses and embeddings are hash-cached under ignored cache directories. Canonical theme outputs exclude volatile call/cache/timing counters, so cached reruns are byte-identical.
- No Qwen model is used.

## Human gate

Every theme claim, relation, person position, and insight remains `pending`. The two HTML pages export independent JSONL decisions. No output is accepted or publishable until a reviewer checks entailment, conditions, speaker attribution, relation direction, and P0 verification items.

## Run

```bash
python3 -m gather_insight build-phase72b-theme \
  --corpus-dir input/corpora/naval_recent_six \
  --output-dir knowledge/themes/ai_execution_commoditization_judgment_scarcity \
  --semantic-mode local_semantic \
  --judge-backend deepseek \
  --config config/phase_7_2b.example.yaml
```

Tests use `mock_semantic` plus the deterministic mock judge and require no network, Ollama, or API key.

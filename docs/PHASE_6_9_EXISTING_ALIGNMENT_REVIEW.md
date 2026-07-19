# Phase 6.9 Existing Alignment Review

Date: 2026-07-19

## Scope and sources reviewed

This review precedes the Phase 6.9 implementation. The implementation must use an established parallel-document alignment formulation rather than another GatherInsight-specific beam search.

Primary sources:

- Brian Thompson and Philipp Koehn, [“Vecalign: Improved Sentence Alignment in Linear Time and Space”](https://aclanthology.org/D19-1136/), EMNLP-IJCNLP 2019.
- Official Vecalign implementation: [thompsonb/vecalign](https://github.com/thompsonb/vecalign), current package version 2.0.0.
- Steinthor Steingrimsson, Hrafn Loftsson, and Andy Way, [“SentAlign: Accurate and Scalable Sentence Alignment”](https://aclanthology.org/2023.emnlp-demo.22/), EMNLP 2023 System Demonstrations.
- Official SentAlign implementation: [steinst/SentAlign](https://github.com/steinst/SentAlign).
- Mikel Artetxe and Holger Schwenk, [“Margin-based Parallel Corpus Mining with Multilingual Sentence Embeddings”](https://aclanthology.org/P19-1309/), ACL 2019.
- Glow-TTS Monotonic Alignment Search was considered only as confirmation that monotonic paths can be enforced by dynamic programming. Its duration-model objective and token/acoustic-frame lattice are not reused for transcript sentence alignment.

## Vecalign

### Input and output

Vecalign consumes two documents already split into lines and embeddings for every allowed consecutive line overlap. For example, supporting a 1:3 transition requires an embedding for the concatenation of the three adjacent target lines. The official CLI receives source and target text files plus binary float32 embedding files.

Its output is an ordered path of source-index lists and target-index lists, optionally with an alignment cost, for example `([6], [6, 7, 8])` or `([], [22])`. Empty sides represent insertion/deletion gaps.

### DP state and operations

The DP state is a document position `(i, j)`: the number of source and target lines consumed. A transition `(n, m)` consumes `n` adjacent source lines and `m` adjacent target lines. The official implementation generates every positive `(n, m)` for which `n + m <= alignment_max_size`, then adds `(1, 0)` and `(0, 1)` gaps.

The paper's coarse resolutions use only `1:1`, `1:0`, and `0:1`. The final resolution may use the configured many-to-many operations. The official traceback therefore natively represents `1:1`, `1:N`, `N:1`, `N:M`, source gaps, and target gaps.

### Scoring

For a candidate block `(x, y)`, Vecalign embeds the concatenated source and target text. It minimizes a normalized cosine distance. The distance is normalized against uniformly sampled document embeddings to reduce global cosine-scale inconsistency, then multiplied by `nSents(x) * nSents(y)` so that the DP does not prefer unnecessary many-to-many merges. The insertion/deletion cost is selected from a percentile of sampled 1:1 costs instead of being an uncalibrated fixed constant.

### Complexity

A full sentence-alignment DP is `O(NM)`. Vecalign recursively downsamples both documents, solves a coarse alignment, upsamples the path, and searches only a fixed-width corridor around it. With fixed corridor width `w`, the paper derives `O((N + M)w)` time and space, conventionally described as linear in document length.

### License and dependencies

The official code is Apache License 2.0. Vecalign 2.0.0 requires Python 3.11+, NumPy 1.26.4+, Cython 3.1+, a C compiler, and Python development headers. Its packaged Bleualign evaluation data is separately GPL-2.0 and must not be vendored into GatherInsight.

## SentAlign

### Differences from Vecalign

SentAlign retains the sentence-embedding plus monotonic path formulation but does not use Vecalign's recursive FastDTW-style corridor. For documents below a configurable graph-size limit, it evaluates all paths in the `N x M` graph. For very large documents, it recursively chooses high-confidence 1:1 anchors and divides the graph into smaller independent chunks.

SentAlign uses LaBSE cosine similarity and maximizes cumulative path score. At each node it evaluates all allowed concatenations on both sides. When no candidate reaches the minimum semantic threshold, insertion/deletion edges receive the minimum threshold score. Merge-count and excessive-length penalties discourage unnecessarily large alignments.

After traceback, SentAlign readjusts the path. It tries to replace `N:M` merges with smaller higher-scoring pairs, then tries attaching adjacent null sentences only when the merge improves semantic similarity. This explicitly implements the minimal-parallel-pair objective described by Vecalign.

### Supported operations

The paper names substitution `1:1`, expansion `1:N`, contraction `N:1`, insertion `0:1`, deletion `1:0`, and merging `N:M`. The implementation's `max-concatenations` setting permits up to the configured number of consecutive sentences on either side.

### Complexity

The normal search is quadratic, `O(NM)` for fixed maximum concatenation sizes. Its divide-and-conquer hard-anchor scheme is described as reducing very large document alignment toward `O(n log n)`, subject to the cost of anchor discovery and chunk balance.

### License and dependencies

The official code is Apache License 2.0. The published environment pins NumPy 1.22.1, Transformers 4.22.2, and Cython 0.29.27 and also requires Torch/LaBSE model loading. Several pathfinding modules are Cython. Direct integration would introduce a second embedding stack and old binary dependencies that GatherInsight does not need.

## Margin-normalized cosine

Raw cosine values are not globally calibrated and are susceptible to hubness. Artetxe and Schwenk define a bidirectional neighborhood baseline for candidate `(x, y)`:

`neighbor_mean = (sum(cos(x, NN_k(x))) + sum(cos(y, NN_k(y)))) / (2k)`

They compare three scores:

- absolute: `cos(x, y)`;
- distance margin: `cos(x, y) - neighbor_mean`;
- ratio margin: `cos(x, y) / neighbor_mean`.

Phase 6.9 will retain raw cosine as an explicit baseline and use bidirectional margin normalization as the primary confidence score. The neighborhood is restricted to the legal time/sequence search band; it is not drawn from an unrelated global corpus.

## GatherInsight mapping

The source document is the ordered uListen structure sequence. Each source item retains `segment_id`, speaker, chapter, time interval, `text_ulisten_raw`, protected terms, and non-authoritative alignment text.

The target document is the ordered sequence of sentences/conservative clauses derived from UseTranscribe or official transcript. Each target item retains semantic-unit ID, original secondary segment ID, exact source character and token spans, approximate time interval, and original text.

An alignment path consumes contiguous items on both sides. The final readable text is always extracted from the union of the selected target character ranges. Embeddings, DP scores, time priors, and conflict checks may choose a range but may never generate or rewrite the transcript.

Speaker blocks are a GatherInsight adaptation around the standard aligner, not a new path algorithm. Long continuous same-speaker regions are aligned as ordinary parallel-document blocks. Small windows around speaker changes are aligned jointly so insertions such as “thank you”, introductions, or applause may remain target gaps. A target character range can be assigned only once and never to two speakers.

## Reuse decision

The official CLIs will not be called directly in production:

- Vecalign expects external overlap files and a compiled NumPy/Cython extension, while GatherInsight already owns normalized BGE-M3 embeddings and character provenance.
- SentAlign loads LaBSE through Torch/Transformers and uses multiple Cython modules, which would duplicate the embedding layer and add incompatible historical dependency pins.
- Neither CLI exposes GatherInsight's exact source-character ranges, speaker-boundary output contract, or current deterministic mock scorer.

The selected approach is a faithful, small Python adaptation of the published DP recurrence for this transcript scale:

1. Use the established `(i, j)` lattice and fixed transition set, never a beam or greedy per-segment search.
2. Use Vecalign-style minimal-pair costs, percentile-calibrated gaps, and raw-cosine versus margin-score experiments. The default final-resolution overlap permits `1:1` through `1:6`, matching Vecalign's configurable overlap input and the observed YC ratio of about six target sentences per structure segment.
3. Provide a SentAlign-style maximum-score/readjustment experiment behind a separate algorithm value if the same input/output adapter can support it without importing LaBSE.
4. Use the existing `SemanticScorer` solely to obtain BGE-M3 or deterministic mock embeddings.
5. Keep Phase 6.8 available as `phase_6_8_beam`; add `vecalign` without deleting or silently changing the baseline.

The YC input is roughly `115 x 743` before sentence-unit consolidation, under 100,000 lattice positions. Full banded DP with a small fixed transition set is tractable and avoids reproducing Vecalign's Cython FastDTW machinery prematurely. If later documents reach thousands or tens of thousands of units, the Apache-2.0 Vecalign sparse corridor implementation is the preferred next reuse step. This scalability choice does not change the scoring or transition contract introduced in Phase 6.9.

## Minimal GatherInsight-specific extensions

Only these extensions are permitted:

- time-derived DP band and weak obvious-misalignment penalty;
- source speaker-block metadata and boundary reporting;
- hard rejection/review for number, model-name, protected-term, or negation conflicts;
- projection from target units back to immutable source character ranges;
- diagnostics, golden evaluation, and stable IDs.

These are required by transcript provenance and speaker attribution. They do not add new alignment operations or replace the upstream DP objective.

# Phase 6.8 — Real YC regression report

Date: 2026-07-19

Full provider transcripts, embeddings, judge caches, traces, unallocated units, and fused output remain in Git-ignored local directories. This report contains aggregate metrics and truncated examples only.

## Backends

- Embedding backend: Ollama `bge-m3:latest`.
- Model digest: `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`.
- Vector dimension: 1024; L2 normalization enabled.
- Hybrid judge: `deepseek-v4-flash`, thinking enabled, temperature 0; escalation `deepseek-v4-pro`.
- Local Qwen: not used.
- Acceptance thresholds remain 0.65/0.85.

## Phase 6.7 versus Phase 6.8

| Metric | Phase 6.7 legacy | lexical_only | local_semantic | hybrid_semantic |
|---|---:|---:|---:|---:|
| Readable text assigned | 66/115 | 3/115 | 91/115 | 76/115 |
| Assignment rate | 57.39% | 2.61% | 79.13% | 66.09% |
| No-review segments | 1/115 | 2/115 | 5/115 | 4/115 |
| Needs review | 114 | 113 | 110 | 111 |
| `>=0.85` | 9 | 3 | 5 | 4 |
| `0.65–0.85` | 57 | 0 | 86 | 72 |
| `<0.65` | 49 | 0 | 0 | 0 |
| Null confidence/fallback | 0 | 112 | 24 | 39 |
| Secondary reuse | 8 | 0 | 0 | 0 |
| Cross-speaker shared unit boundary | 11 | 0 | 0 | 0 |
| Exact adjacent duplication rate | 0.0351 | 0 | 0 | 0 |
| Partial adjacent duplication rate | not measured | 0 | 0.033333 | 0.04 |
| Monotonic violations | not measured | 0 | 0 | 0 |
| Cross-speaker shared characters | not measured | 0 | 0 | 0 |
| Character reuse rate | not measured | 0 | 0 | 0 |

All modes preserve 7/7 chapters, 6/6 speakers, and 115/115 structure segments. Input SHA-256 values are unchanged.

## Semantic-unit allocation

| Metric | local_semantic | hybrid_semantic |
|---|---:|---:|
| Semantic units | 743 | 743 |
| Allocated units | 278 | 234 |
| Unallocated units | 465 | 509 |
| Character consumption rate | 42.24% | 37.65% |
| Unallocated characters | 40,544 | 43,762 |
| Unconsumed coarse secondary segments | 5 | 12 |
| Mean semantic similarity | 0.815352 | 0.819698 |
| Median semantic similarity | 0.814112 | 0.817464 |
| Fallbacks | 24 | 39 |

Local fallback distribution:

- `ambiguous_candidate_unresolved`: 23;
- `no_reliable_monotonic_candidate`: 1.

Final hybrid fallback distribution:

- `judge_call_limit_reached`: 34;
- `ambiguous_candidate_unresolved`: 4;
- `no_reliable_monotonic_candidate`: 1.

The hybrid result is intentionally conservative: unresolved candidates beyond the configured four-case judge budget are fallback, not silently accepted.

## DeepSeek experiment

The final cold hybrid run attempted four Flash cases. All four required Pro escalation and ultimately abstained or failed strict validation.

- Flash/Pro API calls: 8;
- judge abstains: 4;
- escalations: 4;
- judge API time: 100.299 seconds;
- prompt tokens: 11,620;
- completion/reasoning tokens: 8,503;
- provider-reported dollar cost: unavailable;
- new no-review segments compared with local: 0;
- readable assignments compared with local: -15.

The warm rerun used cached judgments and made zero API calls. Stable output files were byte-identical.

DeepSeek did not demonstrate quality gain over BGE-M3 local alignment in this experiment. The production recommendation remains `local_semantic` until the ambiguity payload, call budget, and strict JSON behavior are improved.

## Speaker boundaries

All hard constraints pass:

- shared semantic units across speakers: 0;
- shared characters across speakers: 0;
- monotonic violations: 0.

However, all 12 real speaker switches still have review or fallback on one or both sides. In the final hybrid run both sides fallback at every switch because the bounded judge budget cannot safely adjudicate all high-risk boundaries.

| Boundary | Transition | Result |
|---|---|---|
| 3:43 | Francois → Tanishq | both fallback/review |
| 3:44 | Tanishq → Francois | both fallback/review |
| 3:49 | Francois → Tanishq | both fallback/review |
| 17:32 | Tanishq → Francois | both fallback/review |
| 18:33 | Francois → Guangyao | both fallback/review |
| 29:50 | Guangyao → Francois | both fallback/review |
| 30:18 | Francois → Isaac | both fallback/review |
| 43:15 | Isaac → Francois | both fallback/review |
| 43:52 | Francois → Akshay | both fallback/review |
| 50:19 | Akshay → Francois | both fallback/review |
| 51:24 | Francois → Konwoo | both fallback/review |
| 1:06:20 | Konwoo → Francois | both fallback/review |

This is safer than Phase 6.7 cross-speaker text reuse, but it does not meet the A/B usability target.

## Most improved local-semantic segments

Samples are truncated. These records changed from uListen fallback in Phase 6.7 to source-derived readable text.

| Segment | Time | Speaker | Result |
|---|---:|---|---|
| `seg_0052` | 29:26 | Guangyao | readable, no review; `We do multi-step diffusion action proposals...` |
| `seg_0049` | 26:43 | Guangyao | readable, no review; `Um also contrasting with a few of the representative...` |
| `seg_0036` | 17:32 | Francois | readable/review; `Okay, so for this next paper...` |
| `seg_0037` | 17:56 | Francois | readable/review; `we have these amazing video models...` |
| `seg_0108` | 1:02:34 | Konwoo | readable/review; `these recipes require a lot of training compute...` |
| `seg_0034` | 16:23 | Tanishq | readable/review; `a bunch of inference algorithms and inference engines...` |
| `seg_0040` | 19:50 | Guangyao | readable/review; `an action proposal which proposes a sequence of actions...` |
| `seg_0041` | 20:17 | Guangyao | readable/review; `there are a couple of problems we need to address...` |
| `seg_0042` | 20:57 | Guangyao | readable/review; `related works in the literature...` |
| `seg_0043` | 21:53 | Guangyao | readable/review; `use a planner to select the actions...` |
| `seg_0054` | 30:18 | Isaac | readable/review; `Thanks a lot. All right, guys...` |
| `seg_0073` | 40:30 | Isaac | readable/review; `how does this actually affect the policy...` |
| `seg_0074` | 40:47 | Isaac | readable/review; `I want the world to look like this...` |
| `seg_0076` | 41:58 | Isaac | readable/review; `a really cool capability of world models...` |
| `seg_0077` | 42:11 | Isaac | readable/review; `teleport the tea into a different location...` |
| `seg_0092` | 50:00 | Akshay | readable/review; `working on this problem is a really good bet...` |
| `seg_0110` | 1:04:02 | Konwoo | readable/review; `only chasing IID validation loss...` |
| `seg_0010` | 3:20 | Francois | readable/review; `solve six birds with one stone...` |
| `seg_0011` | 3:43 | Tanishq | readable/review; `Yeah, I got you.` |
| `seg_0021` | 8:37 | Tanishq | readable/review; `Verification means doing one forward pass...` |

## Twenty highest-priority remaining local fallbacks

These are all safe fallbacks, mostly caused by disjoint boundary ambiguity:

`seg_0008`, `seg_0009`, `seg_0012`, `seg_0017`, `seg_0018`, `seg_0020`, `seg_0025`, `seg_0030`, `seg_0035`, `seg_0038`, `seg_0039`, `seg_0048`, `seg_0050`, `seg_0067`, `seg_0072`, `seg_0082`, `seg_0083`, `seg_0085`, `seg_0095`, `seg_0101`.

Notable transition samples include `Okay. Welcome, Akshay.`, `[clapping]`, and speaker introductions. These remain fallback instead of being assigned by timestamp alone.

## Remaining conflicts and duplicates

Local and final hybrid accepted records contain no numeric, model-name, or negation conflicts; those paths fallback. Remaining accepted conflicts are protected-term reviews only:

- local: 12;
- hybrid: 10.

Examples of remaining partial adjacent similarity in the final hybrid output:

- `seg_0021/seg_0022`: 0.4188;
- `seg_0104/seg_0105`: 0.3829;
- `seg_0103/seg_0104`: 0.3586.

No adjacent text is exactly duplicated.

## Alignment trace example

Truncated private trace shape:

```json
{
  "segment_id": "yt_wE1ZgJdt4uM.seg_0049",
  "alignment_text_method": "conservative_spacing_wordninja",
  "alignment_text_is_authoritative": false,
  "selected_candidate": {
    "unit_ids": ["...unit_0003", "...unit_0004"],
    "alignment_score": 0.86,
    "semantic_similarity": 0.84,
    "lexical_anchor_score": 0.82
  },
  "fallback_reason": null,
  "judge_decision": null
}
```

The formal `text` is sliced from the source units; no generated judge text enters the fused transcript.

## Runtime and idempotency

- BGE-M3 cold embedding: 858 texts, 14 Ollama batches, 187.997 seconds.
- Cached local run: 30.958 seconds.
- Final hybrid cold judge run with cached embeddings: 132.933 seconds, including 100.299 seconds API time.
- Hybrid warm run: approximately 32 seconds and zero API calls.
- Embedding and judge cache state is excluded from stable manifests but retained in processing reports.
- Transcript, Markdown, review queues, manifest, trace, and unallocated output are byte-identical on repeated warm runs.
- Original input SHA-256 remains unchanged.

## Dario regression

Dario remains `text_single` with 149 segments, 0 text-review records, 149 speaker-review records, all confidence values null, and all fixture flags false. No semantic backend or judge is invoked.

## Test result

```text
Ran 73 tests in 0.477s
OK
```

The suite includes deterministic semantic scoring/judging, coarse-to-fine allocation, speaker transitions, repeated common phrases, paraphrases, filler deletion, entity/number/negation conflicts, missing/extra content, character projection, hard no-reuse/no-backtracking constraints, degraded backend behavior, input immutability, and output idempotency. Tests do not require Ollama, DeepSeek, or external network access.

## Conclusion

**Phase 6.8 remains C.**

The implementation solves the dangerous failure modes from Phase 6.7: no repeated characters, no reused semantic units, no cross-speaker shared text, no backward path, and no exact adjacent duplication. Local semantic readable allocation improves from 57.39% to 79.13%.

It does not meet B because only 5/115 local records are review-free and all 12 speaker boundaries remain anomalous. Hybrid DeepSeek judgment did not improve quality and was slower and more conservative. YC must not enter evidence extraction.

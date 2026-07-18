# Dario / Bloomberg Phase 0 evaluation

## Baseline

- Media ID: `yt_x2VHFgyawPE`
- Canonical timeline: YouTube
- Retrieved variant: English YouTube caption track via `yt-dlp`
- Metadata observed on 2026-07-18: title “Inside the Mind of Anthropic CEO Dario Amodei | The Circuit | Extended Interview”, channel Bloomberg Originals, duration 4204 seconds, upload date 2026-06-17
- Golden set: 23 high-value claims, 23 evidence units, 3 insight records

## Quality observations

| Dimension | YouTube caption baseline |
|---|---|
| Timestamp coverage | Strong; every golden item has a direct link |
| Speaker labels | Absent; host/guest turns require manual Q&A review |
| Text completeness | Broad coverage, with ASR disfluencies and occasional word errors |
| Section structure | Absent in caption file |
| Claim recall | Sufficient to recover software moats, jobs, organization, governance, cyber, and capability-timeline claims |
| Publication suitability | Evidence only; not suitable as a polished transcript |

## Attribution guardrail

“5x coding ≠ 5x company.” is stored in `gold_insights.jsonl` as an `external_expression` with `is_verbatim_speaker_quote: false`. It is a high-density compression supported by multiple Dario evidence units, not a Dario quote.

## Remaining Phase 0 comparison

The comparison harness is ready, but official transcript, uListen, and UseTranscribe variants have not yet been supplied or licensed for repository storage. When available, evaluate the same 23 claims for:

- evidence coverage;
- speaker attribution precision;
- high-value claim recall;
- insight recall and precision;
- timestamp link completeness;
- hallucination rate.

The source priority remains official transcript → uListen → UseTranscribe → manual Markdown → YouTube export. This baseline does not override that policy.


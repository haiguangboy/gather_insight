# Phase 6.7 — Real source acceptance

Date: 2026-07-19

This report was produced from private, manually acquired provider exports. Full source transcripts and full fused output remain local and are not included in Git. Only aggregate statistics and truncated failure samples appear below.

## Input and execution checks

- Private input root: `input/phase_6_7_real_inputs/` (Git-ignored).
- Both `source_usetranscribe_raw.md` files existed and were non-empty.
- Neither manifest contained `fixture_flags`.
- YC resolved to `dual_source`; Dario resolved to `text_single`.
- Input SHA-256 values were identical before and after every run.
- The supplied runner and the individual `python3 -m gather_insight fuse-general` commands completed successfully after adding support for the real provider's `[[timestamp]](url)` cue syntax.

## YC Paper Club — real dual source

### Structure retention

| Item | uListen input | fused output | retention |
|---|---:|---:|---:|
| Chapters | 7 | 7 | 100% |
| Speakers | 6 | 6 | 100% |
| Segments | 115 | 115 | 100% |

The structure contract is preserved, but text alignment quality is not acceptable for downstream evidence extraction.

### Text adoption and confidence

- UseTranscribe text automatically selected: 66/115 segments (57.39%).
- Automatically selected and free of review flags: 1/115 segments (0.87%).
- `needs_review`: 114/115 segments (99.13%).
- Normal word-boundary heuristic: 70/115 segments (60.87%).
- Canonical readable-secondary coverage, measured by `text_source=usetranscribe_manual_export`: 66/115 (57.39%).

| Alignment band | Count | Ratio |
|---|---:|---:|
| `>= 0.85` | 9 | 7.83% |
| `0.65–0.85` | 57 | 49.57% |
| `< 0.65` | 49 | 42.61% |

Only `yt_wE1ZgJdt4uM.seg_0087` at 46:09 was both high-confidence and free of review flags.

### Review and conflict distribution

Counts are non-exclusive because one record can have several reasons.

| Reason | Count |
|---|---:|
| `alignment_below_0.65` | 49 |
| `alignment_between_0.65_and_0.85` | 57 |
| `secondary_segment_reused_across_speakers` | 29 |
| `numeric_conflict` | 9 |
| `model_name_conflict` | 32 |
| `negation_conflict` | 86 |
| `protected_term_conflict` | 45 |

The conflict counts are too high to interpret as 172 independent transcription errors. They are primarily evidence that coarse UseTranscribe chunks are being compared against, and sometimes copied into, multiple smaller uListen segments.

### Fusion diagnostics

| Metric | Value |
|---|---:|
| `secondary_segment_reuse_count` | 8 |
| `cross_speaker_boundary_count` | 11 |
| `adjacent_text_duplication_rate` | 0.0351 |
| `unconsumed_secondary_segment_count` | 0 |

There are 62 UseTranscribe segments versus 115 uListen segments. Median segment duration is 50.5 seconds for UseTranscribe and 36 seconds for uListen; maximum UseTranscribe duration is 252 seconds. The current overlap rule therefore assigns one coarse secondary segment to several structure records, including records belonging to different speakers.

### Priority manual review — 20 segments

Samples are deliberately truncated.

| # | Segment | Time | Speaker | Confidence | Main reason | Truncated sample |
|---:|---|---:|---|---:|---|---|
| 1 | `seg_0035` | 17:01 | Tanishq Kumar | 0.5977 | all four conflict classes; cross-speaker reuse | `Um,andsoyougetnumbersgoingup,andyoualsogettheability...` |
| 2 | `seg_0037` | 17:56 | Francois Chaubard | 0.4911 | model/negation/protected term; reuse | `Iwaslike,"Thisisdefinitelylike...predictinglikeTHhorizon...` |
| 3 | `seg_0036` | 17:32 | Francois Chaubard | 0.5881 | model/negation/protected term; reuse | `Allright.Thatwasawesome.Okay,soforthisnextpaper...` |
| 4 | `seg_0054` | 30:18 | Isaac Ward | 0.4932 | negation/protected term; reuse | `Yeah.Thanksalot.[audience applauding]Allright,guys...` |
| 5 | `seg_0040` | 19:50 | Guangyao (Stannis) Zhou | 0.5186 | negation/protected term; reuse | `Sowe'regoingto,uh,demonstratesomeofthese...` |
| 6 | `seg_0041` | 20:17 | Guangyao (Stannis) Zhou | 0.5470 | negation/protected term; reuse | `Sowhatis,uh,diffusionmodelpredictivecontrol?...` |
| 7 | `seg_0043` | 21:53 | Guangyao (Stannis) Zhou | 0.5667 | negation/protected term; reuse | `But,uh,youcanalsodoMPC...useaplannertoselecttheactions...` |
| 8 | `seg_0039` | 18:58 | Guangyao (Stannis) Zhou | 0.5792 | negation/protected term; reuse | `But,uh,youcanprobablyseealotof...verysimilarideas...` |
| 9 | `seg_0034` | 16:23 | Tanishq Kumar | 0.5811 | model/negation; reuse | `Well,yougettheprivilegeofwatchinganumbergoup...` |
| 10 | `seg_0092` | 50:00 | Akshay Vegesna | 0.5975 | negation/protected term; reuse | `SoI,Ithinkthatthisis...areallygoodbettomake...` |
| 11 | `seg_0042` | 20:57 | Guangyao (Stannis) Zhou | 0.6098 | negation/protected term; reuse | `Essentially,wecanjustuseaverysimple...sampling-basedplanner...` |
| 12 | `seg_0112` | 1:05:38 | Konwoo Kim | 0.6569 | model/negation/protected term; reuse | `and you can still retain a lot of the benefits through distillation...` |
| 13 | `seg_0011` | 3:43 | Tanishq Kumar | 0.4127 | low alignment; reuse | `It'sallyours.` |
| 14 | `seg_0083` | 43:52 | Akshay Vegesna | 0.4178 | low alignment; reuse | `[clapping]` |
| 15 | `seg_0082` | 43:49 | Francois Chaubard | 0.4399 | low alignment; reuse | `Okay.Welcome,Akshay.` |
| 16 | `seg_0012` | 3:44 | Francois Chaubard | 0.4440 | low alignment; reuse | `Doyouwantmetopulliton?Yeah,Igotyou.` |
| 17 | `seg_0038` | 18:33 | Guangyao (Stannis) Zhou | 0.4999 | low alignment; reuse | `Hi,everyone.I'mStannis...GoogleDeepMind...` |
| 18 | `seg_0010` | 3:20 | Francois Chaubard | 0.5711 | low alignment; reuse | `Andso,uh,Iwantedtokinda...pulltogetherthiscommunity...` |
| 19 | `seg_0013` | 3:49 | Tanishq Kumar | 0.6609 | negation/protected term; reuse | `And so thank you very much Har...five great papers...` |
| 20 | `seg_0014` | 4:09 | Tanishq Kumar | 0.6827 | negation/protected term; reuse | `And so thank you very much Har...five great papers...` |

### Speaker-switch windows

All 12 speaker transitions have an anomaly inside the ±5 second inspection window. Eleven share a secondary segment across speakers.

| Window | Transition | Segments | Shared secondary | Anomaly |
|---|---|---|---|---|
| 3:38–3:48 | Francois → Tanishq | `0010/0011` | Use `seg_0005` | reuse; both `<0.65`; conflict |
| 3:39–3:49 | Tanishq → Francois | `0011/0012` | Use `seg_0005` | reuse; both `<0.65`; conflict |
| 3:44–3:54 | Francois → Tanishq | `0012/0013` | Use `seg_0005` | reuse; left `<0.65`; conflict |
| 17:27–17:37 | Tanishq → Francois | `0035/0036` | Use `seg_0020` | reuse; both `<0.65`; conflict |
| 18:28–18:38 | Francois → Guangyao | `0037/0038` | Use `seg_0021` | reuse; both `<0.65`; conflict |
| 29:45–29:55 | Guangyao → Francois | `0052/0053` | Use `seg_0026` | reuse; left `<0.65`; conflict |
| 30:13–30:23 | Francois → Isaac | `0053/0054` | Use `seg_0026` | reuse; right `<0.65`; conflict |
| 43:10–43:20 | Isaac → Francois | `0080/0081` | Use `seg_0039` | reuse; left `<0.65`; conflict |
| 43:47–43:57 | Francois → Akshay | `0082/0083` | Use `seg_0040` | reuse; both `<0.65`; conflict |
| 50:14–50:24 | Akshay → Francois | `0092/0093` | Use `seg_0045` | reuse; left `<0.65`; conflict |
| 51:19–51:29 | Francois → Konwoo | `0094/0095` | none | conflict |
| 1:06:15–1:06:25 | Konwoo → Francois | `0112/0113` | Use `seg_0061` | reuse; conflict; partial duplicate |

### Required real failure samples

- Cross-speaker reuse: UseTranscribe `seg_0005` is assigned across Francois/Tanishq transitions around 3:43–3:49. Affected fused records are correctly forced into review.
- Local, non-identical duplication: fused `seg_0013/seg_0014` share a long prefix while having normalized sequence similarity 0.7128. Similar cases occur at `0029/0030`, `0050/0051`, and `0078/0079`.
- Numeric/professional-term conflict: fused `seg_0035` contains numeric, model-name, negation, and protected-term conflicts simultaneously.
- Low similarity with high time overlap: `seg_0001` has text similarity 0.1295, time overlap 1.0, and confidence 0.4712. There are 39 records with similarity below 0.4 and overlap at least 0.8.
- High similarity with obvious time misalignment: no record met similarity `>=0.8` and overlap `<0.5`.
- Long unconsumed secondary segment: none; all 62 secondary segments were consumed. This is not a positive quality signal because coarse segments were frequently reused.

## Dario Bloomberg — real text single source

| Metric | Result |
|---|---:|
| Parsed segments | 149 |
| Video duration | 4204 seconds |
| Covered range | 7–4204 seconds |
| Uncovered range | 0–7 seconds |
| Empty text | 0 |
| Abnormally short text | 0 |
| `speaker=null` | 149/149 (100%) |
| `speaker_needs_review=true` | 149/149 (100%) |
| Non-null `alignment_confidence` | 0 |
| `source_is_fixture=true` | 0 |
| Last cue start | 4180 seconds |
| Last `end_seconds` | 4204 seconds |

“Abnormally short” was defined as fewer than five word tokens or fewer than 20 non-whitespace characters.

The source contains title and summary material before `## Transcript`; none was copied into output. No `Section Insights` heading existed in this export, and no such text appeared in parsed output. The final segment end was correctly inferred from manifest `duration_seconds=4204`.

Input SHA-256 remained:

- Dario UseTranscribe: `d6d0c4e914d65938e66d574b51380b9b50655946aa7eb1bf2a4e650949d14a64`.
- YC uListen: `1c2131f4bea69e96d145fe244f525c589b6994f8faa8427675593554d17a84b6`.
- YC UseTranscribe: `7f9db260106f4eb529bb6f244aee1de009a6216382d0291bc5eba1c0d4e6f9e9`.

Repeated runs produced byte-identical core outputs for both media: JSONL, transcript Markdown, source-resolution report, text review queue, speaker review queue, and fusion manifest. `processing_report.json` intentionally contains a new run ID and log path per execution and is excluded from the byte-identity comparison.

## Tests

```text
Ran 60 tests in 0.257s
OK
```

New regression coverage verifies real `[[timestamp]](url)` exports, excludes pre-transcript summary text, and confirms that `python3 -m gather_insight` propagates a failing CLI exit status to shell scripts.

## Acceptance conclusion

- Dario `text_single`: **A — transcript parsing is suitable for the next text-processing stage**, while speaker attribution remains explicitly pending by contract.
- YC `dual_source`: **C — the current fusion algorithm is not reliable enough for evidence extraction**.
- Overall Phase 6.7: **C** because the dual-source path is a core requirement and only 1/115 YC records is both automatically adopted and free of review flags.

Do not increase coverage by lowering thresholds. The required next correction is finer allocation of coarse secondary text across uListen boundaries, especially at speaker transitions, followed by another real-source acceptance run.

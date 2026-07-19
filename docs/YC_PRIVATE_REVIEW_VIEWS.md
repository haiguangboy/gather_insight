# YC private review views

The review-view generator reads the private YC provider inputs and four existing alignment outputs. It does not run or tune an alignment algorithm.

Generate the local pages:

```bash
python3 -m gather_insight generate-yc-review-views \
  --input-dir input/phase_6_7_real_inputs/yc \
  --output-dir input/yc_review_views_private \
  --phase6-8-dir input/phase_6_7_real_inputs/phase_6_8_runs/local_final \
  --vecalign-raw-dir input/phase_6_9_outputs/raw_final2 \
  --vecalign-margin-dir input/phase_6_9_outputs/margin_final3 \
  --sentalign-margin-dir input/phase_6_9_outputs/sentalign_final3
```

The output directory is under the gitignored `input/` tree. It contains the continuous reading view, the blind A/B/C/D alignment review page, the editable JSONL template, and a manifest with input hashes and the recommended first 30 segments.

The browser page downloads completed rows as `yc_alignment_review_completed.jsonl`. Convert those rows into the fixed private 52-item golden label format with:

```bash
python3 -m gather_insight convert-yc-review \
  --package-dir input/yc_golden_v1_private \
  --review input/yc_review_views_private/yc_alignment_review_completed.jsonl \
  --output input/yc_golden_v1_private/labels.reviewed.jsonl \
  --reviewer REVIEWER_ID \
  --annotation-version yc_annotation_v1
```

The completed review file and formal labels must remain private and gitignored.

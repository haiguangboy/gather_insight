import json
import tempfile
import unittest
from pathlib import Path

from gather_insight.pipeline.phase711_human_gate import adapt_phase711_golden_review, finalize_phase711_review, freeze_phase711_golden, generate_phase711_golden_review, generate_phase711_review
from gather_insight.pipeline.phase71_workflow import prepare_phase71_canonical, run_phase71_extraction


FIXTURE = Path(__file__).parents[1] / "fixtures" / "phase71_public"


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class Phase711HumanGateTests(unittest.TestCase):
    def test_blind_review_page_and_template_cover_all_trend_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            media_root = Path(directory) / "media"
            prepare_phase71_canonical(input_dir=FIXTURE, manifest_path=FIXTURE / "manifest.json", media_root=media_root, mode="dual_text_trend_mode", source_input_dir=FIXTURE)
            extraction = run_phase71_extraction(media_root=media_root, judge_backend="mock")
            result = generate_phase711_review(media_root=media_root)
            rows = read_jsonl(Path(result["review_template"]))
            page = Path(result["review_html"]).read_text(encoding="utf-8")
            self.assertEqual(len(rows), extraction["trend_candidate_count"])
            self.assertIn("Algorithm identity and machine scores are hidden", page)
            self.assertNotIn("importance_score", page)
            self.assertTrue(all(row["decision"] == "" for row in rows))

    def test_human_decisions_materialize_immutable_accepted_rejected_and_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            media_root = Path(directory) / "media"
            prepare_phase71_canonical(input_dir=FIXTURE, manifest_path=FIXTURE / "manifest.json", media_root=media_root, mode="dual_text_trend_mode", source_input_dir=FIXTURE)
            run_phase71_extraction(media_root=media_root, judge_backend="mock")
            review = generate_phase711_review(media_root=media_root)
            rows = read_jsonl(Path(review["review_template"]))
            claims_before = (media_root / "intelligence" / "claims.jsonl").read_bytes()
            evidence_before = (media_root / "intelligence" / "evidence.jsonl").read_bytes()
            for index, row in enumerate(rows):
                row.update({"decision": "accept" if index == 0 else "reject_low_value", "entailment_label": "fully_supported" if index == 0 else "unrelated", "condition_preservation": "preserved" if index == 0 else "not_applicable", "verification_status": "verified" if index == 0 else "rejected", "reviewer": "tester", "reviewed_at": "2026-07-19T00:00:00Z", "review_seconds": 10})
            decisions = Path(directory) / "decisions.jsonl"
            decisions.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            report = finalize_phase711_review(media_root=media_root, decisions_path=decisions)
            self.assertEqual(report["metrics"]["reviewed_candidate_count"], len(rows))
            self.assertEqual(report["canonical_claim_count"], 1)
            self.assertIn("exact_attribution_requirement_unmet_accepted_claim_count", report["metrics"])
            self.assertNotIn("wrong_speaker_accepted_claim_count", report["metrics"])
            self.assertEqual(len(read_jsonl(media_root / "intelligence" / "accepted_claims.jsonl")), 1)
            self.assertEqual(len(read_jsonl(media_root / "intelligence" / "rejected_claims.jsonl")), len(rows) - 1)
            self.assertEqual(claims_before, (media_root / "intelligence" / "claims.jsonl").read_bytes())
            self.assertEqual(evidence_before, (media_root / "intelligence" / "evidence.jsonl").read_bytes())

    def test_existing_golden_freezes_without_optional_slots_after_all_populated_are_reviewed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = read_jsonl(FIXTURE / "golden.jsonl")
            draft_rows = [{**source[index % len(source)], "gold_id": f"gold_{index:03d}"} for index in range(25)]
            draft = root / "draft.jsonl"
            draft.write_text("".join(json.dumps(row) + "\n" for row in draft_rows), encoding="utf-8")
            package = generate_phase711_golden_review(draft_path=draft, output_dir=root / "golden_review")
            rows = read_jsonl(Path(package["review_template"]))
            self.assertEqual(len(rows), 50)
            self.assertTrue(all(row["system_output_hidden"] for row in rows))
            existing = [row for row in rows if row["selection_source"] == "existing_reviewer_draft"]
            for index, row in enumerate(existing):
                row.update({"review_action": "approve" if index < 22 else "exclude" if index == 22 else "pending", "reviewer": "tester", "system_output_hidden": True, "change_history": [{"action": "review"}]})
            reviewed = root / "reviewed.jsonl"
            reviewed.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "pending=2"):
                freeze_phase711_golden(reviewed_path=reviewed, output_path=root / "frozen.jsonl", reviewer="tester", golden_version="gold_v2")
            existing[-2]["review_action"] = "approve"
            existing[-1]["review_action"] = "exclude"
            reviewed.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            result = freeze_phase711_golden(reviewed_path=reviewed, output_path=root / "frozen.jsonl", reviewer="tester", golden_version="gold_v2")
            self.assertEqual(result["populated_existing_count"], 25)
            self.assertEqual(result["empty_template_ignored_count"], 25)
            self.assertEqual(result["frozen_count"], 23)
            self.assertTrue(result["system_output_hidden"])

    def test_half_filled_optional_slot_is_rejected_instead_of_silently_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = read_jsonl(Path(generate_phase711_golden_review(draft_path=FIXTURE / "golden.jsonl", output_dir=root / "golden_review")["review_template"]))
            optional = next(row for row in rows if row["selection_source"] == "independent_important")
            optional["gold_claim"] = "Half-filled optional claim"
            reviewed = root / "reviewed.jsonl"
            reviewed.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "partially filled incomplete"):
                freeze_phase711_golden(reviewed_path=reviewed, output_path=root / "frozen.jsonl", reviewer="tester", golden_version="gold_v2")

    def test_legacy_review_adaptation_promotes_confirmed_pending_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "legacy.jsonl"
            rows = [{"selection_source": "existing_reviewer_draft", "gold_claim": "A", "supporting_text": "Evidence", "supporting_time_range": [1, 2], "claim_type": "fact", "expected_theme": "test", "review_action": "pending", "expected_risks": ["未必"]}, {"selection_source": "independent_important", "gold_claim": "", "supporting_text": "", "supporting_time_range": [None, None], "review_action": "pending"}]
            source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            before = source.read_bytes()
            output = root / "adapted.jsonl"
            result = adapt_phase711_golden_review(input_path=source, output_path=output, reviewer="tester")
            adapted = read_jsonl(output)
            self.assertEqual(result["legacy_pending_promoted_to_approve"], 1)
            self.assertEqual(adapted[0]["review_action"], "approve")
            self.assertEqual(adapted[0]["expected_risks"], [])
            self.assertEqual(adapted[0]["epistemic_status"], "uncertain")
            self.assertEqual(adapted[1]["review_action"], "optional")
            self.assertEqual(source.read_bytes(), before)
            self.assertNotIn(str(root), result["source"])


if __name__ == "__main__":
    unittest.main()

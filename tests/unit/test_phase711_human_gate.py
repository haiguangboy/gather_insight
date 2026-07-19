import json
import tempfile
import unittest
from pathlib import Path

from gather_insight.pipeline.phase711_human_gate import finalize_phase711_review, freeze_phase711_golden, generate_phase711_golden_review, generate_phase711_review
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
            self.assertEqual(len(read_jsonl(media_root / "intelligence" / "accepted_claims.jsonl")), 1)
            self.assertEqual(len(read_jsonl(media_root / "intelligence" / "rejected_claims.jsonl")), len(rows) - 1)
            self.assertEqual(claims_before, (media_root / "intelligence" / "claims.jsonl").read_bytes())
            self.assertEqual(evidence_before, (media_root / "intelligence" / "evidence.jsonl").read_bytes())

    def test_golden_review_is_blind_and_freeze_requires_complete_40_to_50_items(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = generate_phase711_golden_review(draft_path=FIXTURE / "golden.jsonl", output_dir=root / "golden_review")
            rows = read_jsonl(Path(package["review_template"]))
            self.assertEqual(len(rows), 28)
            self.assertTrue(all(row["system_output_hidden"] for row in rows))
            # The public fixture has only three draft items; add enough synthetic
            # existing positives to exercise the 40-50-item freeze contract.
            while len(rows) < 50:
                rows.append({**rows[0], "review_item_id": f"extra.{len(rows)}", "gold_id": f"extra_{len(rows)}", "selection_source": "existing_reviewer_draft"})
            for index, row in enumerate(rows):
                row.update({"review_action": "approve", "gold_claim": row.get("gold_claim") or f"Claim {index}", "supporting_text": row.get("supporting_text") or f"Evidence {index}", "supporting_time_range": [float(index), float(index + 1)], "claim_type": row.get("claim_type") or "fact", "value_types": row.get("value_types") or ["trend_signal"], "expected_theme": row.get("expected_theme") or "test", "why_valuable": row.get("why_valuable") or "Independent review", "speaker_requirement": row.get("speaker_requirement") or "section", "verification_requirement": row.get("verification_requirement") or "none", "reviewer": "tester", "system_output_hidden": True, "change_history": [{"action": "approve"}]})
            reviewed = root / "reviewed.jsonl"
            reviewed.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            result = freeze_phase711_golden(reviewed_path=reviewed, output_path=root / "frozen.jsonl", reviewer="tester", golden_version="gold_v2")
            self.assertEqual(result["item_count"], 50)
            self.assertTrue(result["system_output_hidden"])


if __name__ == "__main__":
    unittest.main()

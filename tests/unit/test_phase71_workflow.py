import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gather_insight.pipeline.phase71_evaluator import evaluate_phase71
from gather_insight.pipeline.phase71_workflow import prepare_phase71_canonical, run_phase71_extraction


FIXTURE = Path(__file__).parents[1] / "fixtures" / "phase71_public"


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class Phase71WorkflowTests(unittest.TestCase):
    def test_claims_keep_verbatim_evidence_and_meaningful_unmerged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media_root = root / "media" / "yt_phase71test" / "dual_text_trend_mode"
            result = prepare_phase71_canonical(input_dir=FIXTURE, manifest_path=FIXTURE / "manifest.json", media_root=media_root, mode="dual_text_trend_mode", source_input_dir=FIXTURE)
            self.assertEqual(result["record_count"], 3)
            extraction = run_phase71_extraction(media_root=media_root, judge_backend="mock")
            claims = read_jsonl(media_root / "intelligence" / "claims.jsonl")
            evidence = read_jsonl(media_root / "intelligence" / "evidence.jsonl")
            self.assertGreaterEqual(extraction["claim_count"], 3)
            self.assertEqual(extraction["unsupported_claim_count"], 0)
            self.assertEqual(extraction["evidence_traceability_rate"], 1.0)
            self.assertGreaterEqual(extraction["claims_from_meaningful_unmerged"], 1)
            evidence_by_id = {item["evidence_id"]: item for item in evidence}
            for claim in claims:
                self.assertTrue(claim["evidence_ids"])
                self.assertIn(evidence_by_id[claim["evidence_ids"][0]]["source_text"], " ".join(item["source_text"] for item in evidence))
            review = (media_root / "views" / "claim_review.html").read_text(encoding="utf-8")
            self.assertIn("Download review JSONL", review)
            self.assertIn("meaningful_unmerged", review)
            self.assertTrue((media_root / "reports" / "media_brief.md").exists())

    def test_outputs_are_idempotent_and_evaluator_reports_risk_recall(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media_root = root / "media"
            prepare_phase71_canonical(input_dir=FIXTURE, manifest_path=FIXTURE / "manifest.json", media_root=media_root, mode="dual_text_trend_mode", source_input_dir=FIXTURE)
            run_phase71_extraction(media_root=media_root, judge_backend="mock")
            first = {str(path.relative_to(media_root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in media_root.rglob("*") if path.is_file()}
            run_phase71_extraction(media_root=media_root, judge_backend="mock")
            second = {str(path.relative_to(media_root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in media_root.rglob("*") if path.is_file()}
            self.assertEqual(first, second)
            evaluation = evaluate_phase71(golden_path=FIXTURE / "golden.jsonl", claims_path=media_root / "intelligence" / "claims.jsonl", evidence_path=media_root / "intelligence" / "evidence.jsonl")
            self.assertGreaterEqual(evaluation["metrics"]["all"]["claim_recall"], 2 / 3)
            self.assertEqual(evaluation["unsupported_claim_count"], 0)
            self.assertEqual(evaluation["evidence_traceability_rate"], 1.0)
            self.assertGreater(evaluation["numeric_risk_detection_recall"], 0)

    def test_evaluator_separates_exact_attribution_from_speaker_name_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            golden = root / "golden.jsonl"
            claims = root / "claims.jsonl"
            evidence = root / "evidence.jsonl"
            golden.write_text("".join(json.dumps(row) + "\n" for row in [
                {"gold_id": "g1", "gold_claim": "Alpha mechanism", "supporting_text": "Alpha mechanism", "supporting_time_range": [0, 10], "expected_theme": "alpha", "speaker_requirement": "exact", "expected_speaker": "Alice", "expected_risks": ["speaker"], "value_types": [], "category": "test"},
                {"gold_id": "g2", "gold_claim": "Beta mechanism", "supporting_text": "Beta mechanism", "supporting_time_range": [20, 30], "expected_theme": "beta", "speaker_requirement": "exact", "expected_risks": [], "value_types": [], "category": "test"},
            ]), encoding="utf-8")
            claims.write_text("".join(json.dumps(row) + "\n" for row in [
                {"claim_id": "c1", "claim": "Alpha mechanism", "themes": ["alpha"], "source_time_start": 0, "source_time_end": 10, "speaker": "Bob", "speaker_status": "source_provided", "evidence_ids": ["e1"]},
                {"claim_id": "c2", "claim": "Beta mechanism", "themes": ["beta"], "source_time_start": 20, "source_time_end": 30, "speaker": "Alice", "speaker_status": "section_inferred", "evidence_ids": ["e2"]},
            ]), encoding="utf-8")
            evidence.write_text("".join(json.dumps({"evidence_id": f"e{i}", "source_record_ids": [f"r{i}"], "source_text": "text", "source_ranges": [{"char_start": 0, "char_end": 4}], "source_hashes": {"source": "hash"}}) + "\n" for i in (1, 2)), encoding="utf-8")
            result = evaluate_phase71(golden_path=golden, claims_path=claims, evidence_path=evidence)
            self.assertEqual(result["speaker_name_mismatch_count"], 1)
            self.assertEqual(result["exact_attribution_requirement_unmet_count"], 1)
            self.assertNotIn("wrong_speaker_high_value_claim_count", result)

    def test_evaluator_rejects_invalid_expected_risk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            golden = root / "golden.jsonl"
            golden.write_text(json.dumps({"gold_id": "g1", "expected_risks": ["未必"]}) + "\n", encoding="utf-8")
            empty = root / "empty.jsonl"
            empty.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid expected_risks"):
                evaluate_phase71(golden_path=golden, claims_path=empty, evidence_path=empty)


if __name__ == "__main__":
    unittest.main()

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from gather_insight.pipeline.no_ulisten_trend_workflow import (
    _parse_rolling_vtt,
    _speaker_info,
    compare_phase7_trend,
    run_no_ulisten_trend,
)
from gather_insight.pipeline.trend_candidate_extractor import detect_text_conflicts, extract_high_value_candidates


URL = "https://www.youtube.com/watch?v=wE1ZgJdt4uM"


class NoUlistenTrendWorkflowTests(unittest.TestCase):
    def test_rolling_caption_repeats_are_removed(self):
        raw = """WEBVTT

00:00:01.000 --> 00:00:03.000
Hello everyone.

00:00:03.000 --> 00:00:05.000
Hello everyone. Welcome to the paper club.

00:00:05.000 --> 00:00:06.000
Welcome to the paper club.
"""
        segments = _parse_rolling_vtt(raw, "yt_wE1ZgJdt4uM")
        self.assertEqual([segment.text for segment in segments], ["Hello everyone.", "Welcome to the paper club."])

    def test_section_speaker_is_inferred_but_not_quote_authorized(self):
        chapters = [{"start_seconds": 10, "end_seconds": 100, "title": "Paper", "speaker": "Alice"}]
        ordinary = _speaker_info(chapters, 30, 40, "The model improves inference throughput substantially.")
        boundary = _speaker_info(chapters, 10, 12, "All right. Welcome.")
        self.assertEqual(ordinary["speaker_status"], "section_inferred")
        self.assertFalse(ordinary["exact_quote_allowed"])
        self.assertEqual(boundary["speaker_status"], "boundary_uncertain")

    def test_conflicts_and_high_value_candidate_are_retained(self):
        conflicts = detect_text_conflicts("The model is not 4x faster.", "The model is 8x faster.")
        self.assertIn("numeric_conflict", {item["type"] for item in conflicts})
        self.assertIn("negation_conflict", {item["type"] for item in conflicts})
        candidates = extract_high_value_candidates([{
            "record_id": "r1", "start_seconds": 1, "end_seconds": 10,
            "text": "Speculative decoding only works if verification accepts the draft tokens.",
            "source_ranges": [], "source_agreement": "high", "conflicts": conflicts,
            "speaker": "Alice", "speaker_status": "section_inferred", "speaker_confidence": 0.8,
            "exact_quote_allowed": False,
        }], media_id="yt_test", source_mode="no_ulisten")
        self.assertTrue(candidates)
        self.assertTrue(candidates[0]["needs_verification"])
        self.assertFalse(candidates[0]["exact_quote_allowed"])

    def test_blind_run_rejects_ulisten_and_full_mock_run_freezes_before_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "input"
            input_dir.mkdir()
            manifest = {
                "media_id": "yt_wE1ZgJdt4uM", "youtube_url": URL, "duration_seconds": 30,
                "blind_input_contract": {"ulisten_allowed": False},
                "youtube_metadata": {"chapters": [{"start_seconds": 0, "end_seconds": 30, "title": "Speculative decoding", "speaker": "Alice"}]},
            }
            (input_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (input_dir / "source_usetranscribe_raw.md").write_text(
                f"[[00:00]]({URL})\nSpeculative decoding requires verification of draft tokens.\n\n[[00:15]]({URL}&t=15s)\nThe method is not always faster.\n",
                encoding="utf-8",
            )
            (input_dir / "source_youtube_auto_caption_raw.en-orig.vtt").write_text(
                "WEBVTT\n\n00:00:00.000 --> 00:00:12.000\nSpeculative decoding needs draft token verification.\n\n00:00:15.000 --> 00:00:25.000\nThe method is not always faster.\n",
                encoding="utf-8",
            )
            (input_dir / "source_ulisten_raw.md").write_text("forbidden", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "uListen"):
                run_no_ulisten_trend(input_dir=input_dir, output_dir=root / "blocked", semantic_config={"mode": "mock_semantic"})
            (input_dir / "source_ulisten_raw.md").unlink()
            blind_dir = root / "blind"
            result = run_no_ulisten_trend(input_dir=input_dir, output_dir=blind_dir, semantic_config={"mode": "mock_semantic"})
            self.assertTrue((blind_dir / "blind_freeze_manifest.json").exists())
            self.assertGreater(result["record_count"], 0)
            self.assertTrue(all(not row["exact_quote_allowed"] for row in _read_jsonl(blind_dir / "no_ulisten_fused.jsonl")))
            first_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in blind_dir.iterdir() if path.is_file()}
            run_no_ulisten_trend(input_dir=input_dir, output_dir=blind_dir, semantic_config={"mode": "mock_semantic"})
            second_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in blind_dir.iterdir() if path.is_file()}
            self.assertEqual(first_hashes, second_hashes)
            supported = root / "supported"
            supported.mkdir()
            (supported / "transcript_fused.jsonl").write_text(json.dumps({
                "segment_id": "yt_wE1ZgJdt4uM.seg_0001", "start_seconds": 0, "end_seconds": 20,
                "text": "Speculative decoding requires verification of draft tokens.", "speaker": "Alice",
                "alignment_confidence": 0.9, "needs_review": False, "conflicts": [],
                "secondary_char_start": 0, "secondary_char_end": 60,
            }) + "\n", encoding="utf-8")
            comparison = compare_phase7_trend(blind_output_dir=blind_dir, ulisten_result_dir=supported, output_dir=root / "comparison")
            self.assertTrue(comparison["blind_output_frozen"])
            self.assertTrue((root / "comparison" / "no_ulisten_trend_comparison.md").exists())


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


if __name__ == "__main__":
    unittest.main()

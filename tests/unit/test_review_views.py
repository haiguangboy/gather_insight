import json
import tempfile
import unittest
from pathlib import Path

from gather_insight.pipeline.golden_annotation import convert_review_to_golden
from gather_insight.pipeline.review_views import _review_priorities


class ReviewViewsTests(unittest.TestCase):
    def test_fixed_golden_segment_is_included_when_not_in_review(self):
        records = {
            "yt_wE1ZgJdt4uM.seg_0089": {"needs_review": False},
            "yt_wE1ZgJdt4uM.seg_0090": {"needs_review": True},
        }
        order, tags, _recommended = _review_priorities(records, {"yt_wE1ZgJdt4uM.seg_0089"})
        self.assertIn("yt_wE1ZgJdt4uM.seg_0089", order)
        self.assertIn("fixed golden set", tags["yt_wE1ZgJdt4uM.seg_0089"])
        self.assertIn("yt_wE1ZgJdt4uM.seg_0090", order)

    def test_completed_review_converts_to_formal_golden_label(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "package"
            package.mkdir()
            item = {
                "item_id": "yc_golden_v1.001.ordinary",
                "category": "ordinary",
                "structure_segment_ids": ["yt_wE1ZgJdt4uM.seg_0014"],
                "structure_segments": [{"speaker": "Alice"}],
                "target_units": [
                    {"unit_id": "unit-1", "raw_char_start": 100, "raw_char_end": 130},
                ],
            }
            (package / "items.jsonl").write_text(json.dumps(item) + "\n", encoding="utf-8")
            review = root / "review.jsonl"
            review.write_text(
                json.dumps({
                    "item_type": "segment",
                    "segment_id": "yt_wE1ZgJdt4uM.seg_0014",
                    "verdict": "boundary_adjustment",
                    "current_char_start": 101,
                    "current_char_end": 126,
                    "corrected_char_start": 100,
                    "corrected_char_end": 130,
                    "transition_owner": "uncertain",
                    "reviewer_note": "checked against source",
                }) + "\n",
                encoding="utf-8",
            )
            output = root / "labels.jsonl"
            result = convert_review_to_golden(
                package_dir=package,
                review_path=review,
                output_path=output,
                reviewer="reviewer-1",
                annotation_version="yc_annotation_v1",
            )
            label = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["label_count"], 1)
            self.assertEqual(label["status"], "correct_alignment")
            self.assertEqual(label["ranges"][0]["char_start"], 100)
            self.assertEqual(label["ranges"][0]["char_end"], 130)
            self.assertEqual(label["ranges"][0]["unit_ids"], ["unit-1"])
            self.assertEqual(label["reviewer"], "reviewer-1")


if __name__ == "__main__":
    unittest.main()

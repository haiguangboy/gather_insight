import unittest

from gather_insight.pipeline.alignment_evaluation import evaluate_alignment


class AlignmentEvaluationTests(unittest.TestCase):
    def test_alignment_character_boundary_and_fallback_metrics(self):
        records = [
            {"segment_id": "s1", "semantic_unit_ids": ["u1", "u2"], "secondary_char_start": 0, "secondary_char_end": 10, "text_source": "secondary"},
            {"segment_id": "s2", "semantic_unit_ids": [], "secondary_char_start": None, "secondary_char_end": None, "text_source": "ulisten_raw_review_fallback"},
        ]
        golden = [
            {"segment_id": "s1", "semantic_unit_ids": ["u1"], "secondary_char_ranges": [[0, 5]], "speaker_boundary": True, "should_fallback": False},
            {"segment_id": "s2", "semantic_unit_ids": [], "secondary_char_ranges": [], "should_fallback": True},
        ]
        result = evaluate_alignment(records, golden)
        self.assertEqual(result.alignment_precision, 0.5)
        self.assertEqual(result.alignment_recall, 1.0)
        self.assertEqual(result.character_overlap_precision, 0.5)
        self.assertEqual(result.character_overlap_recall, 1.0)
        self.assertEqual(result.speaker_boundary_accuracy, 0.0)
        self.assertEqual(result.fallback_accuracy, 1.0)


if __name__ == "__main__":
    unittest.main()

import unittest

from gather_insight.pipeline.vecalign_alignment import align_vecalign

from .test_semantic_alignment import secondary, structure


class VecalignAlignmentTests(unittest.TestCase):
    def _config(self, **overrides):
        return {
            "mode": "mock_semantic",
            "alignment_algorithm": "vecalign",
            "score_mode": "margin",
            "time_padding_seconds": 20,
            "max_alignment_size": 4,
            "max_source_concatenations": 3,
            "max_target_concatenations": 3,
            "accept_threshold": 0.5,
            **overrides,
        }

    def test_full_dp_handles_one_to_one_and_one_to_many_without_reuse(self):
        structures = [
            structure(1, "Alice", 0, 10, "Alpha begins."),
            structure(2, "Alice", 10, 20, "Beta continues."),
            structure(3, "Alice", 20, 30, "Gamma ends."),
        ]
        result = align_vecalign(
            structure_segments=structures,
            secondary_segments=[secondary(1, 0, 30, "Alpha begins. Beta continues. Gamma ends.")],
            config_value=self._config(),
        )
        self.assertEqual(result.diagnostics["monotonic_violation_count"], 0)
        self.assertEqual(result.diagnostics["secondary_character_reuse_rate"], 0.0)
        self.assertEqual(result.diagnostics["cross_speaker_shared_character_count"], 0)
        self.assertEqual(result.diagnostics["allocated_semantic_unit_count"], 3)
        self.assertEqual([record["text"] for record in result.records], ["Alpha begins.", "Beta continues.", "Gamma ends."])
        self.assertEqual(result.diagnostics["one_to_one_count"], 3)

    def test_gap_is_explicit_and_unallocated_target_is_not_hidden(self):
        result = align_vecalign(
            structure_segments=[structure(1, "Alice", 0, 10, "Present sentence.")],
            secondary_segments=[secondary(1, 0, 10, "Present sentence."), secondary(2, 100, 110, "Extra unrelated material.")],
            config_value=self._config(time_padding_seconds=3),
        )
        self.assertGreaterEqual(result.diagnostics["gap_count"], 1)
        self.assertGreater(result.diagnostics["unallocated_semantic_unit_count"], 0)
        self.assertTrue(result.unallocated_units)

    def test_raw_and_margin_scores_are_explicit_and_deterministic(self):
        kwargs = dict(
            structure_segments=[structure(1, "Alice", 0, 10, "We purchase an automobile.")],
            secondary_segments=[secondary(1, 0, 10, "We buy a car.")],
        )
        raw = align_vecalign(**kwargs, config_value=self._config(score_mode="raw_cosine"))
        margin = align_vecalign(**kwargs, config_value=self._config(score_mode="margin"))
        self.assertEqual(raw.diagnostics["score_normalization"], "raw_cosine")
        self.assertEqual(margin.diagnostics["score_normalization"], "bidirectional_margin_normalized")
        self.assertEqual(raw.trace, align_vecalign(**kwargs, config_value=self._config(score_mode="raw_cosine")).trace)

    def test_speaker_boundary_never_shares_character_ranges(self):
        result = align_vecalign(
            structure_segments=[
                structure(1, "Alice", 0, 10, "Thank you."),
                structure(2, "Bob", 10, 20, "Welcome and new topic."),
            ],
            secondary_segments=[secondary(1, 0, 20, "Thank you. Welcome and new topic.")],
            config_value=self._config(),
        )
        ids = [set(record.get("semantic_unit_ids", [])) for record in result.records]
        self.assertFalse(ids[0] & ids[1])
        self.assertEqual(result.diagnostics["cross_speaker_shared_character_count"], 0)

    def test_sentalign_name_uses_same_standard_lattice_contract(self):
        result = align_vecalign(
            structure_segments=[structure(1, "Alice", 0, 10, "Alpha begins.")],
            secondary_segments=[secondary(1, 0, 10, "Alpha begins.")],
            config_value=self._config(alignment_algorithm="sentalign"),
        )
        self.assertEqual(result.config.algorithm, "sentalign")
        self.assertEqual(result.records[0]["alignment_method"], "sentalign_monotonic_dp")
        self.assertEqual(result.diagnostics["monotonic_violation_count"], 0)


if __name__ == "__main__":
    unittest.main()

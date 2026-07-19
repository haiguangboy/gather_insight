import unittest

from gather_insight.adapters.ulisten_parser import UlistenSegment
from gather_insight.adapters.usetranscribe_parser import UseTranscribeSegment
from gather_insight.pipeline.semantic_alignment import align_semantically, allocation_record


MEDIA_ID = "yt_semanticTest"
URL = "https://www.youtube.com/watch?v=semanticTest"


def structure(number: int, speaker: str, start: float, end: float, text: str) -> UlistenSegment:
    return UlistenSegment(
        segment_id=f"{MEDIA_ID}.seg_{number:04d}", media_id=MEDIA_ID, provider="ulisten", provider_id="provider",
        speaker=speaker, chapter="Semantic Test", chapter_index=1, chapter_start_seconds=0, chapter_end_seconds=120,
        reference_url="https://example.test/Semantic-Test", start_seconds=start, end_seconds=end,
        timestamp="0:00", end_timestamp="0:10", text=text, text_raw=text, youtube_url=f"{URL}&t={int(start)}s",
    )


def secondary(number: int, start: float, end: float, text: str) -> UseTranscribeSegment:
    return UseTranscribeSegment(
        segment_id=f"{MEDIA_ID}.secondary_{number:04d}", media_id=MEDIA_ID, provider="usetranscribe", provider_id=None,
        speaker=None, chapter=None, chapter_index=None, chapter_start_seconds=None, chapter_end_seconds=None,
        reference_url=None, start_seconds=start, end_seconds=end, timestamp="0:00", end_timestamp="0:30",
        text=text, text_raw=text, youtube_url=f"{URL}&t={int(start)}s",
    )


def config(**overrides):
    return {
        "mode": "mock_semantic",
        "time_padding_seconds": 20,
        "candidate_top_k": 10,
        "beam_width": 20,
        "max_units_per_match": 3,
        "max_secondary_skip_units": 5,
        "accept_threshold": 0.55,
        "auto_threshold": 0.8,
        "ambiguity_margin_threshold": 0.03,
        **overrides,
    }


class SemanticAlignmentTests(unittest.TestCase):
    def test_one_coarse_secondary_segment_allocates_to_three_fine_segments(self):
        structures = [
            structure(1, "Alice", 0, 10, "Alpha begins."),
            structure(2, "Alice", 10, 20, "Beta continues."),
            structure(3, "Alice", 20, 30, "Gamma ends."),
        ]
        result = align_semantically(structure_segments=structures, secondary_segments=[secondary(1, 0, 30, "Alpha begins. Beta continues. Gamma ends.")], config_value=config())
        self.assertEqual(len(result.allocations), 3)
        self.assertEqual(result.diagnostics["secondary_character_reuse_rate"], 0)
        self.assertEqual(result.diagnostics["monotonic_violation_count"], 0)
        self.assertEqual(result.diagnostics["allocated_semantic_unit_count"], 3)

    def test_two_speakers_never_share_units_or_characters(self):
        result = align_semantically(
            structure_segments=[structure(1, "Alice", 0, 10, "Thank you."), structure(2, "Bob", 10, 20, "Welcome Bob. New topic starts.")],
            secondary_segments=[secondary(1, 0, 20, "Thank you. Welcome Bob. New topic starts.")],
            config_value=config(),
        )
        unit_sets = [set(allocation.candidate.unit_ids) if allocation.candidate else set() for allocation in result.allocations]
        self.assertFalse(unit_sets[0] & unit_sets[1])
        self.assertEqual(result.diagnostics["cross_speaker_shared_character_count"], 0)
        self.assertEqual(result.diagnostics["cross_speaker_boundary_count"], 0)

    def test_repeated_common_phrases_remain_monotonic(self):
        result = align_semantically(
            structure_segments=[structure(1, "Alice", 0, 15, "Okay. Alpha details."), structure(2, "Alice", 15, 30, "Okay. Beta details.")],
            secondary_segments=[secondary(1, 0, 30, "Okay. Alpha details. Okay. Beta details.")],
            config_value=config(),
        )
        starts = [allocation.candidate.unit_start for allocation in result.allocations if allocation.candidate]
        self.assertEqual(starts, sorted(starts))
        self.assertEqual(result.diagnostics["monotonic_violation_count"], 0)

    def test_semantic_paraphrase_can_align_with_deterministic_scorer(self):
        result = align_semantically(
            structure_segments=[structure(1, "Alice", 0, 10, "We purchase an automobile.")],
            secondary_segments=[secondary(1, 0, 10, "We buy a car.")],
            config_value=config(),
        )
        self.assertIsNotNone(result.allocations[0].candidate)

    def test_filler_deletion_does_not_force_fallback(self):
        result = align_semantically(
            structure_segments=[structure(1, "Alice", 0, 10, "Um we uh train the model quickly.")],
            secondary_segments=[secondary(1, 0, 10, "We train the model quickly.")],
            config_value=config(),
        )
        self.assertIsNotNone(result.allocations[0].candidate)

    def test_numeric_model_and_negation_conflicts_fallback_safely(self):
        cases = [
            ("We use 5 GPUs.", "We use 6 GPUs."),
            ("GPT-3 is selected.", "GPT-4 is selected."),
            ("The model does not improve.", "The model improves."),
        ]
        for left, right in cases:
            with self.subTest(left=left):
                result = align_semantically(structure_segments=[structure(1, "Alice", 0, 10, left)], secondary_segments=[secondary(1, 0, 10, right)], config_value=config())
                self.assertIsNone(result.allocations[0].candidate)
                self.assertEqual(result.allocations[0].fallback_reason, "critical_entity_or_negation_conflict")

    def test_missing_structure_and_extra_secondary_are_explicit(self):
        result = align_semantically(
            structure_segments=[structure(1, "Alice", 0, 10, "Present text."), structure(2, "Alice", 10, 20, "Missing sentence about zebras.")],
            secondary_segments=[secondary(1, 0, 10, "Present text."), secondary(2, 30, 40, "Extra unrelated secondary content.")],
            config_value=config(time_padding_seconds=5),
        )
        self.assertTrue(any(allocation.candidate is None for allocation in result.allocations))
        self.assertGreater(result.diagnostics["unallocated_semantic_unit_count"], 0)

    def test_formal_record_projects_original_unit_text_without_generation(self):
        result = align_semantically(structure_segments=[structure(1, "Alice", 0, 10, "Readable sentence.")], secondary_segments=[secondary(1, 0, 10, "Readable sentence.")], config_value=config())
        allocation = result.allocations[0]
        record = allocation_record(allocation, result.units, text_source="usetranscribe_manual_export", official=False, source_is_fixture=False)
        self.assertEqual(record["text"], allocation.candidate.text)
        self.assertEqual(record["allocation_method"], "constrained_monotonic_semantic_alignment")
        self.assertTrue(record["source_text_consumed_once"])
        self.assertFalse(record["alignment_text_is_authoritative"])

    def test_mock_mode_is_deterministic(self):
        arguments = dict(structure_segments=[structure(1, "Alice", 0, 10, "Alpha sentence.")], secondary_segments=[secondary(1, 0, 10, "Alpha sentence.")], config_value=config())
        first = align_semantically(**arguments)
        second = align_semantically(**arguments)
        self.assertEqual(first.trace, second.trace)
        self.assertEqual(first.diagnostics, second.diagnostics)


if __name__ == "__main__":
    unittest.main()

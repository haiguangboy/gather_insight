import json
import unittest
from pathlib import Path

from gather_insight.adapters.ulisten_parser import UlistenSegment, parse_ulisten_file
from gather_insight.adapters.usetranscribe_parser import UseTranscribeSegment
from gather_insight.pipeline.transcript_fuser import fuse_transcripts, normalized_text_similarity


ROOT = Path(__file__).parents[1] / "fixtures" / "yc_paper_club"
MEDIA_ID = "yt_wE1ZgJdt4uM"
YOUTUBE_URL = "https://www.youtube.com/watch?v=wE1ZgJdt4uM"


def structure(text: str = "Themodeluses5H100s.", chapter: str = "Alice — Model Paper") -> UlistenSegment:
    return UlistenSegment(
        segment_id=f"{MEDIA_ID}.seg_0001", media_id=MEDIA_ID, provider="ulisten", provider_id="provider",
        speaker="Alice", chapter=chapter, chapter_index=1, chapter_start_seconds=0, chapter_end_seconds=20,
        reference_url=None, start_seconds=0, end_seconds=20, timestamp="0:00", end_timestamp="0:20",
        text=text, text_raw=text, youtube_url=f"{YOUTUBE_URL}&t=0s",
    )


def secondary(text: str, start: float = 0, end: float = 20) -> UseTranscribeSegment:
    return UseTranscribeSegment(
        segment_id=f"{MEDIA_ID}.seg_0001", media_id=MEDIA_ID, provider="usetranscribe", provider_id=None,
        speaker=None, chapter=None, chapter_index=None, chapter_start_seconds=None, chapter_end_seconds=None,
        reference_url=None, start_seconds=start, end_seconds=end, timestamp="0:00", end_timestamp="0:20",
        text=text, text_raw=text, youtube_url=f"{YOUTUBE_URL}&t=0s",
    )


class TranscriptFuserTests(unittest.TestCase):
    def test_spacing_only_difference_is_auto_accepted(self):
        result = fuse_transcripts(structure_segments=[structure()], text_segments=[secondary("The model uses 5 H100s.")])
        item = result.segments[0]
        self.assertEqual(item.text, "The model uses 5 H100s.")
        self.assertGreaterEqual(item.alignment_confidence, 0.85)
        self.assertFalse(item.needs_review)

    def test_three_second_tolerance_finds_nearby_segment(self):
        result = fuse_transcripts(structure_segments=[structure("Hello")], text_segments=[secondary("Hello", 21, 22)], tolerance_seconds=3)
        self.assertIsNotNone(result.segments[0].alignment_confidence)
        self.assertNotIn("no_time_match", result.segments[0].review_reasons)

    def test_low_alignment_keeps_ulisten_text_and_reviews_candidate(self):
        item = fuse_transcripts(structure_segments=[structure("Original critical claim")], text_segments=[secondary("Completely unrelated sentence")]).segments[0]
        self.assertEqual(item.text, "Original critical claim")
        self.assertEqual(item.text_source, "ulisten_raw_review_fallback")
        self.assertTrue(item.needs_review)
        self.assertIn("alignment_below_0.65", item.review_reasons)

    def test_numeric_and_model_conflicts_are_not_silent(self):
        item = fuse_transcripts(structure_segments=[structure("We use 5 H100s and GPT-3.")], text_segments=[secondary("We use 6 H200s and GPT-4.")]).segments[0]
        types = {conflict["type"] for conflict in item.conflicts}
        self.assertIn("numeric_conflict", types)
        self.assertIn("model_name_conflict", types)
        self.assertTrue(item.needs_review)

    def test_degraded_and_fixture_modes_never_invent_confidence(self):
        degraded = fuse_transcripts(structure_segments=[structure()], text_segments=None).segments[0]
        fixture = fuse_transcripts(structure_segments=[structure()], text_segments=None, fixture_texts={f"{MEDIA_ID}.seg_0001": "Readable fixture"}).segments[0]
        self.assertIsNone(degraded.alignment_confidence)
        self.assertEqual(degraded.fusion_mode, "degraded")
        self.assertIsNone(fixture.alignment_confidence)
        self.assertEqual(fixture.text_source, "spacing_reconstruction_fixture")
        self.assertTrue(fixture.needs_review)

    def test_full_fixture_preserves_all_structure(self):
        parsed = parse_ulisten_file(path=ROOT / "source_ulisten_raw.md", media_id=MEDIA_ID, youtube_url=YOUTUBE_URL, provider_id="gSNFJbgoaHI")
        fixture_rows = [json.loads(line) for line in (ROOT / "transcript_fused_fixture.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        fixture_texts = {row["segment_id"]: row["text_readable_fixture"] for row in fixture_rows if row.get("record_type") == "segment"}
        result = fuse_transcripts(structure_segments=parsed.segments, text_segments=None, fixture_texts=fixture_texts)
        self.assertEqual(len(result.segments), 115)
        self.assertEqual(len({segment.segment_id for segment in result.segments}), 115)
        self.assertTrue(all(segment.alignment_confidence is None for segment in result.segments))
        self.assertEqual({segment.speaker for segment in result.segments}, {segment.speaker for segment in parsed.segments})
        self.assertEqual({segment.chapter for segment in result.segments}, {chapter.title for chapter in parsed.chapters})

    def test_similarity_removes_spaces_and_punctuation(self):
        self.assertEqual(normalized_text_similarity("Hello,world!", "Hello world"), 1.0)


if __name__ == "__main__":
    unittest.main()

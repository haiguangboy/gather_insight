import unittest
from dataclasses import replace

from gather_insight.adapters.usetranscribe_parser import UseTranscribeSegment
from gather_insight.pipeline.semantic_unit_segmenter import canonical_secondary_text, segment_secondary_text


MEDIA_ID = "yt_semanticTest"
URL = "https://www.youtube.com/watch?v=semanticTest"


def secondary(text: str) -> UseTranscribeSegment:
    return UseTranscribeSegment(
        segment_id=f"{MEDIA_ID}.seg_0001", media_id=MEDIA_ID, provider="usetranscribe", provider_id=None,
        speaker=None, chapter=None, chapter_index=None, chapter_start_seconds=None, chapter_end_seconds=None,
        reference_url=None, start_seconds=0, end_seconds=40, timestamp="0:00", end_timestamp="0:40",
        text=text, text_raw=text, youtube_url=URL,
    )


class SemanticUnitSegmenterTests(unittest.TestCase):
    def test_sentence_clause_event_and_character_mapping(self):
        text = "First sentence. [applause] Second clause: more detail; final detail!"
        units = segment_secondary_text([secondary(text)])
        self.assertGreaterEqual(len(units), 5)
        self.assertIn("event", {unit.unit_type for unit in units})
        canonical = canonical_secondary_text([secondary(text)])
        for unit in units:
            self.assertEqual(canonical[unit.original_char_start:unit.original_char_end], unit.text)
            self.assertLessEqual(unit.original_char_start, unit.original_char_end)
        self.assertEqual([unit.original_char_start for unit in units], sorted(unit.original_char_start for unit in units))

    def test_long_clause_splits_only_at_word_boundaries(self):
        text = "This is a deliberately long clause with many words and details, and it continues with another independent explanation that should be split conservatively without cutting any individual word apart."
        units = segment_secondary_text([secondary(text)], max_unit_chars=90)
        self.assertGreaterEqual(len(units), 2)
        self.assertEqual(" ".join(unit.text for unit in units).replace("  ", " "), text.replace(", and", " and"))


if __name__ == "__main__":
    unittest.main()

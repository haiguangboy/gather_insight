import unittest
from pathlib import Path

from gather_insight.pipeline.evidence_builder import format_timestamp, youtube_timestamp_url
from gather_insight.pipeline.transcript_normalizer import chunk_segments, load_markdown, load_transcript, parse_markdown, parse_timestamp


FIXTURE = Path(__file__).parent / "fixtures" / "manual_transcript.md"
VTT_FIXTURE = Path(__file__).parent / "fixtures" / "youtube_export.vtt"


class TranscriptTests(unittest.TestCase):
    def test_timestamp_parser(self):
        self.assertEqual(parse_timestamp("15:08"), 908)
        self.assertEqual(parse_timestamp("01:15:08.5"), 4508.5)
        self.assertEqual(format_timestamp(908), "15:08")

    def test_parse_and_chunk(self):
        _, segments = load_markdown(FIXTURE)
        self.assertEqual(len(segments), 5)
        chunks = chunk_segments(segments)
        self.assertTrue(all(chunk.end_seconds >= chunk.start_seconds for chunk in chunks))
        self.assertEqual(chunks[0].speaker, "Host")

    def test_youtube_link(self):
        self.assertEqual(
            youtube_timestamp_url("https://www.youtube.com/watch?v=abc123", 908),
            "https://www.youtube.com/watch?v=abc123&t=908s",
        )

    def test_inline_cue_end_is_inferred(self):
        segments = parse_markdown("[00:10] Guest: First.\n[00:25] Guest: Second.")
        self.assertEqual(segments[0].end_seconds, 25)
        self.assertEqual(segments[1].end_seconds, 40)

    def test_vtt_voice_labels_and_unknown_speaker(self):
        _, segments = load_transcript(VTT_FIXTURE, "vtt")
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0].speaker, "Host")
        self.assertEqual(segments[1].speaker, "Guest")
        self.assertEqual(segments[2].speaker, "unknown")


if __name__ == "__main__":
    unittest.main()

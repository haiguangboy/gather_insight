import tempfile
import unittest
from pathlib import Path

from gather_insight.adapters.usetranscribe_parser import parse_usetranscribe_file, parse_usetranscribe_markdown


MEDIA_ID = "yt_wE1ZgJdt4uM"
YOUTUBE_URL = "https://www.youtube.com/watch?v=wE1ZgJdt4uM"


class UseTranscribeParserTests(unittest.TestCase):
    def test_common_markdown_cues_and_inferred_end_times(self):
        raw = """# Transcript\n\n[0:00](https://youtube.test?t=0) Opening text.\ncontinues here.\n\n## [0:12 - 0:30] Second segment.\n\n1:00:00 Final long timestamp segment.\n"""
        result = parse_usetranscribe_markdown(raw=raw, media_id=MEDIA_ID, youtube_url=YOUTUBE_URL, video_duration_seconds=3660)
        self.assertEqual(len(result.segments), 3)
        self.assertEqual(result.segments[0].end_seconds, 12)
        self.assertEqual(result.segments[1].end_seconds, 30)
        self.assertEqual(result.segments[2].start_seconds, 3600)
        self.assertEqual(result.segments[2].end_seconds, 3660)
        self.assertIn("continues here", result.segments[0].text)

    def test_speaker_is_never_invented(self):
        result = parse_usetranscribe_markdown(raw="[0:00] Alice: This text may look like a speaker label.", media_id=MEDIA_ID, youtube_url=YOUTUBE_URL, video_duration_seconds=10)
        self.assertIsNone(result.segments[0].speaker)
        self.assertEqual(result.segments[0].text, "Alice: This text may look like a speaker label.")

    def test_final_open_segment_requires_duration(self):
        with self.assertRaises(ValueError):
            parse_usetranscribe_markdown(raw="[0:00] Text", media_id=MEDIA_ID, youtube_url=YOUTUBE_URL, video_duration_seconds=None)

    def test_production_filename_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            wrong = Path(directory) / "download.md"
            wrong.write_text("[0:00] Text", encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_usetranscribe_file(path=wrong, media_id=MEDIA_ID, youtube_url=YOUTUBE_URL, video_duration_seconds=10)

    def test_file_parser_accepts_required_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source_usetranscribe_raw.md"
            path.write_text("[0:00] Text", encoding="utf-8")
            result = parse_usetranscribe_file(path=path, media_id=MEDIA_ID, youtube_url=YOUTUBE_URL, video_duration_seconds=10)
            self.assertEqual(result.segments[0].end_seconds, 10)


if __name__ == "__main__":
    unittest.main()

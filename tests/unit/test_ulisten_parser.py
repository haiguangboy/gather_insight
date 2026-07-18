import unittest
from pathlib import Path

from gather_insight.adapters.ulisten_parser import parse_ulisten_file, parse_ulisten_markdown


ROOT = Path(__file__).parents[1] / "fixtures" / "yc_paper_club"
MEDIA_ID = "yt_wE1ZgJdt4uM"
YOUTUBE_URL = "https://www.youtube.com/watch?v=wE1ZgJdt4uM"


class UlistenParserTests(unittest.TestCase):
    def test_real_fixture_chapters_segments_and_long_timestamp(self):
        result = parse_ulisten_file(path=ROOT / "source_ulisten_raw.md", media_id=MEDIA_ID, youtube_url=YOUTUBE_URL, provider_id="gSNFJbgoaHI")
        self.assertEqual(len(result.chapters), 7)
        self.assertEqual(len(result.segments), 115)
        self.assertEqual(result.chapters[3].title, "Guangyao (Stannis) Zhou — Diffusion-MPC")
        self.assertEqual(result.chapters[3].reference_url, "https://arxiv.org/abs/2410.05364")
        self.assertEqual(result.chapters[-1].end_seconds, 4036)
        self.assertEqual(result.chapters[-1].end_timestamp, "1:07:16")
        self.assertEqual(result.segments[-1].end_seconds, 4036)

    def test_provider_id_does_not_change_youtube_primary_key(self):
        result = parse_ulisten_file(path=ROOT / "source_ulisten_raw.md", media_id=MEDIA_ID, youtube_url=YOUTUBE_URL, provider_id="gSNFJbgoaHI")
        self.assertTrue(all(segment.segment_id.startswith("yt_wE1ZgJdt4uM.seg_") for segment in result.segments))
        self.assertTrue(all(segment.provider_id == "gSNFJbgoaHI" for segment in result.segments))
        self.assertTrue(all("wE1ZgJdt4uM&t=" in segment.youtube_url for segment in result.segments))

    def test_speaker_transitions_and_parenthesized_speaker_are_preserved(self):
        result = parse_ulisten_file(path=ROOT / "source_ulisten_raw.md", media_id=MEDIA_ID, youtube_url=YOUTUBE_URL)
        transitions = sum(a.speaker != b.speaker for a, b in zip(result.segments, result.segments[1:]))
        self.assertEqual(transitions, 12)
        stannis = [segment for segment in result.segments if segment.speaker == "Guangyao (Stannis) Zhou"]
        self.assertEqual(len(stannis), 15)

    def test_empty_body_is_not_silently_dropped(self):
        raw = """0:00 - 0:10\n#### Intro\n\nSpeaker0:00\n\nSpeaker0:05\nSome words\n"""
        result = parse_ulisten_markdown(raw=raw, media_id=MEDIA_ID, youtube_url=YOUTUBE_URL)
        self.assertEqual(len(result.segments), 2)
        self.assertEqual(result.segments[0].text_raw, "")
        self.assertEqual(result.segments[0].end_seconds, 5)
        self.assertEqual(result.segments[1].end_seconds, 10)

    def test_duplicate_timestamps_keep_both_segments(self):
        raw = """0:00 - 0:10\n#### Intro\n\nA0:00\nFirst\n\nB0:00\nSecond\n"""
        result = parse_ulisten_markdown(raw=raw, media_id=MEDIA_ID, youtube_url=YOUTUBE_URL)
        self.assertEqual(len(result.segments), 2)
        self.assertEqual(result.segments[0].start_seconds, result.segments[1].start_seconds)
        self.assertEqual(result.segments[0].text_raw, "First")
        self.assertEqual(result.segments[1].text_raw, "Second")

    def test_non_youtube_primary_media_id_rejected(self):
        with self.assertRaises(ValueError):
            parse_ulisten_markdown(raw="0:00 - 0:01\n#### Intro\n\nA0:00\nText", media_id="web_example", youtube_url=YOUTUBE_URL)


if __name__ == "__main__":
    unittest.main()

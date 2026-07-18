import unittest

from gather_insight.pipeline.ids import URLParseError, evidence_id, media_id_for_url, normalize_media_url


class IdTests(unittest.TestCase):
    def test_youtube_variants_normalize(self):
        expected = "https://www.youtube.com/watch?v=x2VHFgyawPE"
        for value in [
            "https://youtu.be/x2VHFgyawPE?t=10",
            "https://m.youtube.com/watch?v=x2VHFgyawPE&feature=share",
            "https://www.youtube.com/shorts/x2VHFgyawPE",
            "https://www.youtube.com/embed/x2VHFgyawPE",
        ]:
            self.assertEqual(normalize_media_url(value), expected)
            self.assertEqual(media_id_for_url(value)[0], "yt_x2VHFgyawPE")

    def test_invalid_url_rejected(self):
        with self.assertRaises(URLParseError):
            normalize_media_url("not-a-url")

    def test_evidence_id(self):
        self.assertEqual(evidence_id("yt_demo123", 17), "yt_demo123.ev_0017")


if __name__ == "__main__":
    unittest.main()


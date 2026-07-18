import json
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).parents[1] / "fixtures" / "yc_paper_club"


class FusionFixtureContractTests(unittest.TestCase):
    def test_bundle_manifest_uses_youtube_primary_key(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["media_id"], "yt_wE1ZgJdt4uM")
        self.assertEqual(manifest["canonical_youtube_video_id"], "wE1ZgJdt4uM")
        self.assertEqual(manifest["ulisten_source"]["provider_page_id"], "gSNFJbgoaHI")
        self.assertNotEqual(manifest["ulisten_source"]["provider_page_id"], manifest["canonical_youtube_video_id"])

    def test_fixture_is_explicitly_non_production(self):
        records = [json.loads(line) for line in (ROOT / "transcript_fused_fixture.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        counts = Counter(record["record_type"] for record in records)
        self.assertEqual(counts, {"manifest": 1, "chapter": 7, "segment": 115})
        segments = [record for record in records if record["record_type"] == "segment"]
        self.assertTrue(all(record["text_source"] == "spacing_reconstruction_fixture" for record in segments))
        self.assertTrue(all(record["alignment_confidence"] is None for record in segments))
        self.assertTrue(all(record["needs_review"] is True for record in segments))
        self.assertEqual(len({record["segment_id"] for record in segments}), 115)

    def test_real_usetranscribe_file_is_absent(self):
        self.assertFalse((ROOT / "source_usetranscribe_raw.md").exists())
        self.assertTrue((ROOT / "source_usetranscribe_raw.PLACEHOLDER.md").exists())


if __name__ == "__main__":
    unittest.main()

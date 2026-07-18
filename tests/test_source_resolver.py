import tempfile
import unittest
from pathlib import Path

from gather_insight.adapters.base import SourceHint
from gather_insight.pipeline.source_resolver import SourceResolutionError, resolve_source


FIXTURE = Path(__file__).parent / "fixtures" / "manual_transcript.md"


class SourceResolverTests(unittest.TestCase):
    def test_ready_official_source_wins(self):
        resolved = resolve_source({
            "official_transcript": SourceHint("official_transcript", FIXTURE, "https://example.com/transcript?token=secret"),
            "manual_markdown": SourceHint("manual_markdown", FIXTURE),
        })
        self.assertEqual(resolved.selected.provider, "official_transcript")

    def test_url_only_source_does_not_block_lower_ready_source(self):
        resolved = resolve_source({
            "official_transcript": SourceHint("official_transcript", url="https://example.com/transcript"),
            "manual_markdown": SourceHint("manual_markdown", FIXTURE),
        })
        self.assertEqual(resolved.selected.provider, "manual_markdown")
        self.assertEqual(resolved.checks[0].status, "url_only")

    def test_failed_higher_source_degrades(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.md"
            resolved = resolve_source({
                "ulisten": SourceHint("ulisten", missing),
                "manual_markdown": SourceHint("manual_markdown", FIXTURE),
            })
            self.assertEqual(resolved.selected.provider, "manual_markdown")
            self.assertEqual(resolved.checks[1].status, "failed")

    def test_url_only_without_local_source_requires_manual_action(self):
        with self.assertRaises(SourceResolutionError) as caught:
            resolve_source({"usetranscribe": SourceHint("usetranscribe", url="https://example.com/transcript")})
        self.assertIn("download/export", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

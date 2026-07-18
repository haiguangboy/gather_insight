import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gather_insight.pipeline.fusion_workflow import run_fusion_workflow
from gather_insight.run_logging import RunLogger


FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "yc_paper_club"


def hashes(directory: Path, names: list[str]) -> dict[str, str]:
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in names}


class FusionWorkflowIntegrationTests(unittest.TestCase):
    def test_fixture_input_degrades_without_fabricating_confidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = hashes(FIXTURE_DIR, ["source_ulisten_raw.md", "manifest.json", "transcript_fused_fixture.jsonl"])
            report = run_fusion_workflow(input_dir=FIXTURE_DIR, output_root=root / "data", logger=RunLogger("test-fuse", root / "global.jsonl", "degraded_run"))
            after = hashes(FIXTURE_DIR, ["source_ulisten_raw.md", "manifest.json", "transcript_fused_fixture.jsonl"])
            self.assertEqual(before, after)
            self.assertEqual(report["fusion_mode"], "degraded")
            self.assertEqual(report["alignment_confidence_count"], 0)
            output = root / "data" / "yt_wE1ZgJdt4uM" / "fusion"
            records = [json.loads(line) for line in (output / "transcript_fused.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 115)
            self.assertTrue(all(record["alignment_confidence"] is None for record in records))
            self.assertTrue(all(record["fusion_mode"] == "degraded" for record in records))
            self.assertEqual((output / "review_queue.md").read_text(encoding="utf-8").count("\n## yt_"), 115)
            self.assertIn("No source_usetranscribe_raw.md", (output / "alignment_report.md").read_text(encoding="utf-8"))

    def test_fixture_mode_is_explicit_and_still_null_confidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = run_fusion_workflow(input_dir=FIXTURE_DIR, output_root=root / "data", use_fixture=True, logger=RunLogger("test-fuse", root / "global.jsonl", "fixture_run"))
            self.assertEqual(report["fusion_mode"], "fixture")
            self.assertEqual(report["alignment_confidence_count"], 0)
            output = root / "data" / "yt_wE1ZgJdt4uM" / "fusion"
            records = [json.loads(line) for line in (output / "transcript_fused.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records[0]["text_source"], "spacing_reconstruction_fixture")
            self.assertIn("fixture", (output / "alignment_report.md").read_text(encoding="utf-8").lower())

    def test_real_two_source_fixture_fuses_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "manifest.json").write_text(json.dumps({
                "media_id": "yt_wE1ZgJdt4uM", "canonical_youtube_video_id": "wE1ZgJdt4uM",
                "youtube_url": "https://www.youtube.com/watch?v=wE1ZgJdt4uM",
                "ulisten_source": {"provider_page_id": "gSNFJbgoaHI"},
            }), encoding="utf-8")
            (input_dir / "source_ulisten_raw.md").write_text("0:00 - 0:20\n#### Intro\n\nAlice0:00\nThemodeluses5H100s.\n", encoding="utf-8")
            (input_dir / "source_usetranscribe_raw.md").write_text("[0:00 - 0:20] The model uses 5 H100s.\n", encoding="utf-8")
            before = hashes(input_dir, ["manifest.json", "source_ulisten_raw.md", "source_usetranscribe_raw.md"])
            first = run_fusion_workflow(input_dir=input_dir, output_root=root / "data", logger=RunLogger("test-fuse", root / "global-1.jsonl", "dual_run_1"))
            output = root / "data" / "yt_wE1ZgJdt4uM" / "fusion"
            first_jsonl = (output / "transcript_fused.jsonl").read_text(encoding="utf-8")
            second = run_fusion_workflow(input_dir=input_dir, output_root=root / "data", logger=RunLogger("test-fuse", root / "global-2.jsonl", "dual_run_2"))
            second_jsonl = (output / "transcript_fused.jsonl").read_text(encoding="utf-8")
            after = hashes(input_dir, ["manifest.json", "source_ulisten_raw.md", "source_usetranscribe_raw.md"])
            self.assertEqual(first["fusion_mode"], "dual_source")
            self.assertEqual(first["alignment_confidence_count"], 1)
            self.assertEqual(first_jsonl, second_jsonl)
            self.assertEqual(before, after)
            record = json.loads(first_jsonl)
            self.assertEqual(record["text"], "The model uses 5 H100s.")
            self.assertGreaterEqual(record["alignment_confidence"], 0.85)
            self.assertEqual(second["segment_count"], 1)


if __name__ == "__main__":
    unittest.main()

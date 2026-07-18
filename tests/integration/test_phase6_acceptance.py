import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gather_insight.adapters.ulisten_parser import parse_ulisten_file
from gather_insight.pipeline.fusion_workflow import FusionWorkflowError, run_fusion_workflow
from gather_insight.pipeline.validators import validate_records
from gather_insight.run_logging import RunLogger


FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "yc_paper_club"
MEDIA_ID = "yt_wE1ZgJdt4uM"
YOUTUBE_URL = "https://www.youtube.com/watch?v=wE1ZgJdt4uM"
SCHEMA = Path(__file__).parents[2] / "schemas" / "transcript_fused.schema.json"


def tree_hashes(directory: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


class Phase6AcceptanceTests(unittest.TestCase):
    def test_yc_degraded_acceptance_metrics_and_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = tree_hashes(FIXTURE_DIR)
            report = run_fusion_workflow(input_dir=FIXTURE_DIR, output_root=root / "data", logger=RunLogger("acceptance", root / "global.jsonl", "acceptance_degraded"))
            after = tree_hashes(FIXTURE_DIR)
            self.assertEqual(before, after)
            output = root / "data" / MEDIA_ID / "fusion"
            records = [json.loads(line) for line in (output / "transcript_fused.jsonl").read_text(encoding="utf-8").splitlines()]
            validate_records(records, SCHEMA, "acceptance transcript_fused")
            parsed = parse_ulisten_file(path=FIXTURE_DIR / "source_ulisten_raw.md", media_id=MEDIA_ID, youtube_url=YOUTUBE_URL, provider_id="gSNFJbgoaHI")
            self.assertEqual(len(records), 115)
            self.assertEqual({record["chapter"] for record in records}, {chapter.title for chapter in parsed.chapters})
            self.assertEqual({record["speaker"] for record in records}, {segment.speaker for segment in parsed.segments})
            self.assertEqual(len({record["segment_id"] for record in records}), 115)
            self.assertTrue(all(record["segment_id"] == f"{MEDIA_ID}.seg_{index:04d}" for index, record in enumerate(records, 1)))
            self.assertTrue(all(record["youtube_url"] == f"{YOUTUBE_URL}&t={int(record['start_seconds'])}s" for record in records))
            self.assertTrue(all(record["alignment_confidence"] is None for record in records))
            self.assertTrue(all(record["needs_review"] for record in records))
            self.assertEqual(report["review_count"], 115)
            self.assertFalse((FIXTURE_DIR / "source_usetranscribe_raw.md").exists())
            self.assertEqual(json.loads((output / "fusion_manifest.json").read_text(encoding="utf-8"))["usetranscribe_source_state"], "absent")

    def test_all_core_outputs_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "data" / MEDIA_ID / "fusion"
            run_fusion_workflow(input_dir=FIXTURE_DIR, output_root=root / "data", logger=RunLogger("acceptance", root / "global-1.jsonl", "idempotent_1"))
            names = ["transcript_fused.jsonl", "transcript_fused.md", "alignment_report.md", "review_queue.md", "fusion_manifest.json"]
            first = {name: (output / name).read_bytes() for name in names}
            run_fusion_workflow(input_dir=FIXTURE_DIR, output_root=root / "data", logger=RunLogger("acceptance", root / "global-2.jsonl", "idempotent_2"))
            second = {name: (output / name).read_bytes() for name in names}
            self.assertEqual(first, second)

    def test_numeric_and_model_conflict_reaches_review_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "manifest.json").write_text(json.dumps({
                "canonical_youtube_video_id": "wE1ZgJdt4uM",
                "youtube_url": YOUTUBE_URL,
                "ulisten_source": {"provider_page_id": "gSNFJbgoaHI"},
            }), encoding="utf-8")
            (input_dir / "source_ulisten_raw.md").write_text("0:00 - 0:10\n#### Model Test\n\nAlice0:00\nWeuse5H100sandGPT-3.\n", encoding="utf-8")
            (input_dir / "source_usetranscribe_raw.md").write_text("[0:00 - 0:10] We use 6 H200s and GPT-4.\n", encoding="utf-8")
            report = run_fusion_workflow(input_dir=input_dir, output_root=root / "data", logger=RunLogger("acceptance", root / "global.jsonl", "conflict_run"))
            output = root / "data" / MEDIA_ID / "fusion"
            record = json.loads((output / "transcript_fused.jsonl").read_text(encoding="utf-8"))
            conflict_types = {conflict["type"] for conflict in record["conflicts"]}
            self.assertEqual(report["review_count"], 1)
            self.assertIn("numeric_conflict", conflict_types)
            self.assertIn("model_name_conflict", conflict_types)
            review = (output / "review_queue.md").read_text(encoding="utf-8")
            self.assertIn("numeric_conflict", review)
            self.assertIn("model_name_conflict", review)
            self.assertIn("Weuse5H100sandGPT-3.", review)
            self.assertIn("We use 6 H200s and GPT-4.", review)

    def test_missing_ulisten_source_fails_loudly_with_report_and_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "manifest.json").write_text(json.dumps({"canonical_youtube_video_id": "wE1ZgJdt4uM", "youtube_url": YOUTUBE_URL}), encoding="utf-8")
            with self.assertRaises(FusionWorkflowError):
                run_fusion_workflow(input_dir=input_dir, output_root=root / "data", logger=RunLogger("acceptance", root / "global.jsonl", "missing_ulisten"))
            media_dir = root / "data" / MEDIA_ID
            report = json.loads((media_dir / "fusion" / "processing_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertIn("missing required uListen source", report["error"])
            log_text = (media_dir / "logs" / "missing_ulisten.jsonl").read_text(encoding="utf-8")
            self.assertIn('"event":"fusion.failed"', log_text)


if __name__ == "__main__":
    unittest.main()

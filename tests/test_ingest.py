import json
import tempfile
import unittest
from pathlib import Path

import yaml

from gather_insight.pipeline.ingest import IngestError, ingest_media


FIXTURE = Path(__file__).parent / "fixtures" / "manual_transcript.md"
URL = "https://www.youtube.com/watch?v=x2VHFgyawPE"


class IngestTests(unittest.TestCase):
    def test_repeat_ingest_is_idempotent_and_review_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = ingest_media(url=URL, transcript_file=FIXTURE, provider="manual_markdown", output_root=root)
            media_dir = root / first["media_id"]
            evidence_before = (media_dir / "evidence.jsonl").read_text(encoding="utf-8")
            review = media_dir / "review.md"
            review.write_text(review.read_text(encoding="utf-8") + "\nHuman note.\n", encoding="utf-8")
            second = ingest_media(url=URL, transcript_file=FIXTURE, provider="manual_markdown", output_root=root)
            self.assertNotEqual(first["run_id"], second["run_id"])
            self.assertEqual(first["media_id"], second["media_id"])
            self.assertEqual(first["evidence_count"], second["evidence_count"])
            self.assertEqual(evidence_before, (media_dir / "evidence.jsonl").read_text(encoding="utf-8"))
            self.assertIn("Human note.", review.read_text(encoding="utf-8"))
            records = [json.loads(line) for line in evidence_before.splitlines()]
            self.assertEqual(len({item["evidence_id"] for item in records}), len(records))

    def test_changed_source_requires_explicit_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ingest_media(url=URL, transcript_file=FIXTURE, provider="manual_markdown", output_root=root)
            changed = root / "changed.md"
            changed.write_text(FIXTURE.read_text(encoding="utf-8") + "\n## [02:16-02:30] Guest\n\nNew text.\n", encoding="utf-8")
            with self.assertRaises(IngestError):
                ingest_media(url=URL, transcript_file=changed, provider="manual_markdown", output_root=root)
            report = json.loads((root / "yt_x2VHFgyawPE" / "processing_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            media_logs = list((root / "yt_x2VHFgyawPE" / "logs").glob("*.jsonl"))
            self.assertTrue(media_logs)
            self.assertIn('"event":"ingest.failed"', "".join(path.read_text(encoding="utf-8") for path in media_logs))

    def test_human_manifest_fields_survive_repeat_ingest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ingest_media(
                url=URL,
                transcript_file=FIXTURE,
                provider="manual_markdown",
                output_root=root,
                participants=["Guest"],
                topics=["ai_software_company_bottlenecks"],
            )
            ingest_media(url=URL, transcript_file=FIXTURE, provider="manual_markdown", output_root=root)
            manifest = yaml.safe_load((root / "yt_x2VHFgyawPE" / "manifest.yaml").read_text(encoding="utf-8"))
            self.assertEqual(manifest["participants"][0]["name"], "Guest")
            self.assertEqual(manifest["topics"], ["ai_software_company_bottlenecks"])


if __name__ == "__main__":
    unittest.main()

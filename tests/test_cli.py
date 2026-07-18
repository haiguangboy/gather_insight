import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import yaml

from gather_insight.cli import main


URL = "https://www.youtube.com/watch?v=x2VHFgyawPE"
VTT_FIXTURE = Path(__file__).parent / "fixtures" / "youtube_export.vtt"


class CliTests(unittest.TestCase):
    def test_unresolved_source_writes_durable_failure_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                status = main(["ingest", "--url", URL, "--output-root", str(root / "media"), "--log-file", str(root / "global.jsonl")])
            self.assertEqual(status, 2)
            media_dir = root / "media" / "yt_x2VHFgyawPE"
            report = json.loads((media_dir / "processing_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["stage"], "source_resolution")
            self.assertIn('"event":"source.unresolved"', next((media_dir / "logs").glob("*.jsonl")).read_text(encoding="utf-8"))

    def test_auto_ingest_selects_youtube_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                status = main([
                    "ingest", "--url", URL,
                    "--youtube-export-file", str(VTT_FIXTURE),
                    "--output-root", str(root / "media"),
                    "--log-file", str(root / "global.jsonl"),
                ])
            self.assertEqual(status, 0)
            manifest = yaml.safe_load((root / "media" / "yt_x2VHFgyawPE" / "manifest.yaml").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_resolution"]["primary_provider"], "youtube_export")
            self.assertEqual(manifest["source_resolution"]["checked"]["youtube_export"]["status"], "ready")


if __name__ == "__main__":
    unittest.main()

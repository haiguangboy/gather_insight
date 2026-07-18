import json
import tempfile
import unittest
from pathlib import Path

from gather_insight.run_logging import RunLogger


class RunLoggingTests(unittest.TestCase):
    def test_logs_are_jsonl_replayed_to_media_and_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logger = RunLogger("test", global_log=root / "global.jsonl", run_id="test_run")
            logger.event("INFO", "source.checked", "checking https://example.com/t?a=1&token=secret", source_url="https://example.com/t?a=1&token=secret", authorization="Bearer abc")
            logger.bind_media("yt_demo123", root / "media")
            logger.event("INFO", "done", "ok")
            global_records = [json.loads(line) for line in (root / "global.jsonl").read_text(encoding="utf-8").splitlines()]
            media_records = [json.loads(line) for line in (root / "media" / "logs" / "test_run.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(global_records), 2)
            self.assertEqual(len(media_records), 2)
            serialized = json.dumps(global_records)
            self.assertNotIn("secret", serialized)
            self.assertNotIn("Bearer abc", serialized)
            self.assertEqual(global_records[0]["context"]["authorization"], "<redacted>")


if __name__ == "__main__":
    unittest.main()

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from gather_insight.cli import main
from gather_insight.pipeline.general_transcript_workflow import GeneralTranscriptWorkflowError, run_general_transcript_workflow
from gather_insight.pipeline.source_resolver import resolve_transcript_combination
from gather_insight.run_logging import RunLogger


DARIO_FIXTURE = Path(__file__).parents[1] / "fixtures" / "dario_bloomberg_text_single"
MEDIA_ID = "yt_x2VHFgyawPE"
YOUTUBE_URL = "https://www.youtube.com/watch?v=x2VHFgyawPE"


def manifest() -> str:
    return json.dumps({"canonical_youtube_video_id": "x2VHFgyawPE", "youtube_url": YOUTUBE_URL, "duration_seconds": 4204})


def ulisten() -> str:
    return "0:00 - 0:10\n#### Intro\n\nHost0:00\nHello from structure.\n"


def use() -> str:
    return "[0:00 - 0:10] Hello from readable text.\n"


def official() -> str:
    return "## [0:00-0:10] Dario Amodei\n\nOfficial readable text.\n"


class GeneralSourceModeTests(unittest.TestCase):
    def _resolution(self, directory: Path, **sources):
        (directory / "manifest.json").write_text(manifest(), encoding="utf-8")
        for name, content in sources.items():
            (directory / name).write_text(content, encoding="utf-8")
        return resolve_transcript_combination(input_dir=directory)

    def test_state_machine_covers_all_declared_modes(self):
        cases = [
            ({"source_ulisten_raw.md": ulisten(), "source_usetranscribe_raw.md": use()}, "dual_source"),
            ({"source_ulisten_raw.md": ulisten(), "source_official_transcript_raw.md": official()}, "official_dual"),
            ({"source_official_transcript_raw.md": official()}, "official_single"),
            ({"source_usetranscribe_raw.md": use()}, "text_single"),
            ({"source_ulisten_raw.md": ulisten()}, "structure_degraded"),
            ({}, "failed"),
        ]
        for sources, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                resolution = self._resolution(Path(directory), **sources)
                self.assertEqual(resolution.fusion_mode, expected)

    def test_official_wins_when_no_structure_source(self):
        with tempfile.TemporaryDirectory() as directory:
            resolution = self._resolution(Path(directory), **{"source_official_transcript_raw.md": official(), "source_usetranscribe_raw.md": use()})
            self.assertEqual(resolution.fusion_mode, "official_single")
            self.assertIn("usetranscribe", resolution.unused_sources)

    def test_dario_text_single_keeps_speaker_anonymous_and_text_usable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = hashlib.sha256((DARIO_FIXTURE / "source_usetranscribe_raw.md").read_bytes()).hexdigest()
            report = run_general_transcript_workflow(input_dir=DARIO_FIXTURE, output_root=root / "data", logger=RunLogger("test-general", root / "global.jsonl", "dario_text_single"))
            after = hashlib.sha256((DARIO_FIXTURE / "source_usetranscribe_raw.md").read_bytes()).hexdigest()
            output = root / "data" / MEDIA_ID / "general"
            records = [json.loads(line) for line in (output / "transcript_fused.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(report["fusion_mode"], "text_single")
            self.assertEqual(len(records), 5)
            self.assertTrue(all(record["speaker"] is None for record in records))
            self.assertTrue(all(record["speaker_needs_review"] for record in records))
            self.assertTrue(all(record["needs_review"] is False for record in records))
            self.assertTrue(all(record["alignment_confidence"] is None for record in records))
            self.assertTrue(all(record["source_is_fixture"] is True for record in records))
            self.assertTrue(all(record["text_status"] == "readable" for record in records))
            self.assertTrue(all(record["youtube_url"].startswith(YOUTUBE_URL + "&t=") for record in records))
            self.assertEqual([record["segment_id"] for record in records], [f"{MEDIA_ID}.seg_{index:04d}" for index in range(1, 6)])
            self.assertEqual(before, after)
            speaker_queue = (output / "speaker_review_queue.md").read_text(encoding="utf-8")
            self.assertEqual(speaker_queue.count("\n## yt_"), 5)
            stable_names = ["transcript_fused.jsonl", "transcript_fused.md", "source_resolution_report.md", "review_queue.md", "speaker_review_queue.md", "fusion_manifest.json"]
            first_outputs = {name: (output / name).read_bytes() for name in stable_names}
            run_general_transcript_workflow(input_dir=DARIO_FIXTURE, output_root=root / "data", logger=RunLogger("test-general", root / "global-2.jsonl", "dario_text_single_2"))
            second_outputs = {name: (output / name).read_bytes() for name in stable_names}
            self.assertEqual(first_outputs, second_outputs)

    def test_cli_text_single_example(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                status = main(["fuse-general", "--input-dir", str(DARIO_FIXTURE), "--output-root", str(root / "data"), "--log-file", str(root / "global.jsonl")])
            self.assertEqual(status, 0)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["fusion_mode"], "text_single")

    def test_ulisten_only_is_not_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "manifest.json").write_text(manifest(), encoding="utf-8")
            (input_dir / "source_ulisten_raw.md").write_text(ulisten(), encoding="utf-8")
            report = run_general_transcript_workflow(input_dir=input_dir, output_root=root / "data", logger=RunLogger("test-general", root / "global.jsonl", "structure_only"))
            self.assertEqual(report["fusion_mode"], "structure_degraded")
            record = json.loads((root / "data" / MEDIA_ID / "general" / "transcript_fused.jsonl").read_text(encoding="utf-8"))
            self.assertTrue(record["needs_review"])
            self.assertIsNone(record["alignment_confidence"])
            review_queue = (root / "data" / MEDIA_ID / "general" / "review_queue.md").read_text(encoding="utf-8")
            self.assertIn(f"- youtube_url: <{YOUTUBE_URL}&t=0s>", review_queue)
            self.assertNotIn(">`", review_queue)

    def test_official_single_can_preserve_source_speaker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "manifest.json").write_text(manifest(), encoding="utf-8")
            (input_dir / "source_official_transcript_raw.md").write_text(official(), encoding="utf-8")
            report = run_general_transcript_workflow(input_dir=input_dir, output_root=root / "data", logger=RunLogger("test-general", root / "global.jsonl", "official_single"))
            record = json.loads((root / "data" / MEDIA_ID / "general" / "transcript_fused.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(report["fusion_mode"], "official_single")
            self.assertEqual(record["speaker"], "Dario Amodei")
            self.assertFalse(record["speaker_needs_review"])
            self.assertIsNone(record["alignment_confidence"])
            self.assertFalse(record["source_is_fixture"])

    def test_official_single_fixture_provenance_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "input"
            input_dir.mkdir()
            fixture_manifest = json.loads(manifest())
            fixture_manifest["fixture_flags"] = {"official_transcript": True}
            (input_dir / "manifest.json").write_text(json.dumps(fixture_manifest), encoding="utf-8")
            (input_dir / "source_official_transcript_raw.md").write_text(official(), encoding="utf-8")

            run_general_transcript_workflow(input_dir=input_dir, output_root=root / "data", logger=RunLogger("test-general", root / "global.jsonl", "official_single_fixture"))

            record = json.loads((root / "data" / MEDIA_ID / "general" / "transcript_fused.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(record["fusion_mode"], "official_single")
            self.assertEqual(record["text_source"], "official_transcript_format_fixture")
            self.assertTrue(record["source_is_fixture"])
            self.assertIsNone(record["alignment_confidence"])

    def test_official_dual_fixture_provenance_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "input"
            input_dir.mkdir()
            fixture_manifest = json.loads(manifest())
            fixture_manifest["fixture_flags"] = {"official_transcript": True}
            (input_dir / "manifest.json").write_text(json.dumps(fixture_manifest), encoding="utf-8")
            (input_dir / "source_ulisten_raw.md").write_text(ulisten(), encoding="utf-8")
            (input_dir / "source_official_transcript_raw.md").write_text("## [0:00-0:10] Narrator\n\nHello from structure.\n", encoding="utf-8")

            report = run_general_transcript_workflow(input_dir=input_dir, output_root=root / "data", logger=RunLogger("test-general", root / "global.jsonl", "official_dual_fixture"))

            record = json.loads((root / "data" / MEDIA_ID / "general" / "transcript_fused.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(record["fusion_mode"], "official_dual")
            self.assertEqual(record["text_source"], "official_transcript_format_fixture")
            self.assertTrue(record["source_is_fixture"])
            self.assertEqual(report["fusion_diagnostics"]["secondary_segment_reuse_count"], 0)

    def test_dual_modes_keep_ulisten_speaker_and_compute_confidence(self):
        cases = [
            ("source_usetranscribe_raw.md", "[0:00 - 0:10] Hello from structure.\n", "dual_source"),
            ("source_official_transcript_raw.md", "## [0:00-0:10] Narrator\n\nHello from structure.\n", "official_dual"),
        ]
        for filename, text, expected_mode in cases:
            with self.subTest(mode=expected_mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                input_dir = root / "input"
                input_dir.mkdir()
                (input_dir / "manifest.json").write_text(manifest(), encoding="utf-8")
                (input_dir / "source_ulisten_raw.md").write_text(ulisten(), encoding="utf-8")
                (input_dir / filename).write_text(text, encoding="utf-8")
                report = run_general_transcript_workflow(input_dir=input_dir, output_root=root / "data", logger=RunLogger("test-general", root / "global.jsonl", expected_mode))
                record = json.loads((root / "data" / MEDIA_ID / "general" / "transcript_fused.jsonl").read_text(encoding="utf-8"))
                self.assertEqual(report["fusion_mode"], expected_mode)
                self.assertEqual(record["speaker"], "Host")
                self.assertFalse(record["speaker_needs_review"])
                self.assertIsNotNone(record["alignment_confidence"])
                self.assertEqual(set(report["fusion_diagnostics"]), {
                    "secondary_segment_reuse_count",
                    "cross_speaker_boundary_count",
                    "adjacent_text_duplication_rate",
                    "unconsumed_secondary_segment_count",
                })

    def test_manifest_video_id_mismatch_fails_loudly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "input"
            input_dir.mkdir()
            mismatch = json.loads(manifest())
            mismatch["canonical_youtube_video_id"] = "differentVideoId"
            (input_dir / "manifest.json").write_text(json.dumps(mismatch), encoding="utf-8")
            (input_dir / "source_usetranscribe_raw.md").write_text(use(), encoding="utf-8")

            with self.assertRaisesRegex(GeneralTranscriptWorkflowError, "canonical_youtube_video_id does not match youtube_url video_id"):
                run_general_transcript_workflow(input_dir=input_dir, output_root=root / "data", logger=RunLogger("test-general", root / "global.jsonl", "id_mismatch"))

            report = json.loads((root / "data" / MEDIA_ID / "general" / "processing_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["fusion_mode"], "failed")
            self.assertIn("differentVideoId", report["error"])
            self.assertIn("x2VHFgyawPE", report["error"])

    def test_all_sources_missing_returns_failed_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "manifest.json").write_text(manifest(), encoding="utf-8")
            with self.assertRaises(GeneralTranscriptWorkflowError):
                run_general_transcript_workflow(input_dir=input_dir, output_root=root / "data", logger=RunLogger("test-general", root / "global.jsonl", "all_missing"))
            report = json.loads((root / "data" / MEDIA_ID / "general" / "processing_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["fusion_mode"], "failed")
            self.assertIn("all transcript sources are missing", report["error"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from gather_insight.pipeline.naval_recent_six import SOURCES, parse_naval_html, run_naval_recent_six


def _page(title: str, transcript: bool = True) -> bytes:
    body = '<p class="wp-block-paragraph">Official program description only.</p>'
    if transcript:
        body += '''
        <h2 class="wp-block-heading"><strong>Build and Judge</strong></h2>
        <p class="wp-block-paragraph"><strong>Naval:</strong> AI agents make execution cheaper, but judgment still determines what should be built.</p>
        <p class="wp-block-paragraph">If the result cannot be verified, the team must keep a human accountable.</p>
        <p class="wp-block-paragraph"><strong>Nivi:</strong> Does that change how a startup should recruit?</p>
        <p class="wp-block-paragraph"><strong>Guillermo:</strong> We now build software factories that multiply engineering output.</p>
        '''
    return f'<html><body><h1 class="blog-title">{title}</h1>{body}</body></html>'.encode()


class NavalRecentSixTest(unittest.TestCase):
    def test_parser_preserves_speaker_turns_and_html_ranges(self) -> None:
        source = SOURCES[1]
        raw = _page(source.title).decode()
        rows, metadata = parse_naval_html(raw, source, "a" * 64)
        self.assertEqual(metadata["transcript_status"], "official_transcript_present")
        self.assertEqual([row["speaker"] for row in rows], ["unknown", "Naval Ravikant", "Nivi", "Guillermo Rauch"])
        self.assertIn("human accountable", rows[1]["text"])
        self.assertLess(rows[1]["html_range"]["char_start"], rows[1]["html_range"]["char_end"])

    def test_fixed_six_cache_overlap_traceability_and_idempotency(self) -> None:
        calls: list[str] = []

        def fetch(url: str):
            calls.append(url)
            source = next(item for item in SOURCES if item.url == url)
            return _page(source.title, transcript=source.source_id != "naval_live_in_future_2026"), 200, url

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "naval_recent_six"
            first = run_naval_recent_six(output_dir=root, fetcher=fetch)
            self.assertEqual(first["ingested_sources"], 6)
            self.assertEqual(first["skipped_sources"], 0)
            self.assertEqual(first["transcript_absent_sources"], ["naval_live_in_future_2026"])
            self.assertEqual(len(calls), 6)
            self.assertGreater(first["exact_duplicate_sections"], 0)
            self.assertEqual(first["duplicate_evidence_mistakenly_counted_as_independent"], 0)
            self.assertEqual(first["unsupported_claim_count"], 0)
            self.assertEqual(first["evidence_traceability"], 1.0)
            sections = [json.loads(line) for line in (root / "canonical" / "sections.jsonl").read_text().splitlines()]
            evidence = [json.loads(line) for line in (root / "canonical" / "evidence.jsonl").read_text().splitlines()]
            self.assertLess(len(evidence), len(sections))
            self.assertTrue(any(len(row["source_ids"]) > 1 and row["independent_source_family_count"] == 1 for row in evidence))
            manifest = json.loads((root / "manifest.json").read_text())
            self.assertEqual(manifest["expected_source_ids"], [source.source_id for source in SOURCES])
            cursor = json.loads((root / "ingestion_cursor.json").read_text())
            self.assertEqual(cursor["next_older_published_at"], "2026-05-04")
            self.assertEqual(cursor["next_older_url"], "https://nav.al/over")
            relations = [json.loads(line) for line in (root / "source_relations.jsonl").read_text().splitlines()]
            self.assertEqual(len(relations), 6)
            self.assertTrue(all(row["independence_group_id"] == "naval_frontier_founders_industrial_2026" for row in relations))
            before = {path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob("*") if path.is_file()}

            def forbidden_fetch(_url: str):
                raise AssertionError("cached rerun must not fetch")

            second = run_naval_recent_six(output_dir=root, fetcher=forbidden_fetch, offline=True)
            after = {path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob("*") if path.is_file()}
            self.assertEqual(first, second)
            self.assertEqual(before, after)
            self.assertIn("system_synthesis", (root / "reports" / "recent_six_industry_insights.md").read_text())
            self.assertIn("Download review JSONL", (root / "views" / "trend_insight_review.html").read_text())

            section_schema = json.loads(Path("schemas/phase_7_2a_section.schema.json").read_text())
            for line in (root / "canonical" / "sections.jsonl").read_text().splitlines():
                jsonschema.validate(json.loads(line), section_schema)

    def test_title_mismatch_fails_loudly(self) -> None:
        source = SOURCES[0]
        with self.assertRaisesRegex(ValueError, "title mismatch"):
            parse_naval_html('<h1 class="blog-title">Wrong</h1>', source, "a" * 64)


if __name__ == "__main__":
    unittest.main()

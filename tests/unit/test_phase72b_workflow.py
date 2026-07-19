from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from gather_insight.pipeline.phase72b_judge import MockThemeJudge, _bounded_number
from gather_insight.pipeline.phase72b_workflow import INPUT_FILES, _string_list, run_phase72b_theme
from gather_insight.pipeline.semantic_scorer import DeterministicTestScorer


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


class Phase72BWorkflowTests(unittest.TestCase):
    def test_invalid_model_scalars_are_not_coerced(self) -> None:
        self.assertIsNone(_bounded_number("high"))
        self.assertEqual(_bounded_number(0.8), 0.8)
        self.assertEqual(_string_list("Requires verification."), ["Requires verification."])

    def _corpus(self, root: Path) -> Path:
        corpus = root / "corpus"
        raw = corpus / "sources" / "source_a" / "raw" / "source_raw.html"
        raw.parent.mkdir(parents=True)
        raw.write_text("<html>immutable official source</html>")
        source_rows = [
            {"source_id": "source_a", "source_family_id": "naval_frontier_founders_industrial_2026", "independence_group_id": "naval_frontier_founders_industrial_2026", "title": "A", "published_at": "2026-05-27"},
            {"source_id": "source_b", "source_family_id": "naval_sell_truth_2026", "independence_group_id": "naval_sell_truth_2026", "title": "B", "published_at": "2026-05-11"},
        ]
        _write_jsonl(corpus / "source_index.jsonl", source_rows)
        _write_jsonl(corpus / "source_relations.jsonl", [])
        _write_jsonl(corpus / "canonical/sections.jsonl", [{"section_id": "s1"}])
        evidence = []
        canonical = []
        source_claims = []
        texts = [
            ("Naval Ravikant", "AI agents make writing code and trying alternatives much cheaper.", "software_production", "source_a", "naval_frontier_founders_industrial_2026"),
            ("Naval Ravikant", "Choosing the right problem creates a much larger difference than implementation speed.", "judgment", "source_a", "naval_frontier_founders_industrial_2026"),
            ("Guillermo Rauch", "Experienced architects get more leverage because they can give better feedback to agents.", "leverage", "source_a", "naval_frontier_founders_industrial_2026"),
            ("Blake Scholl", "Hardware designs still require physical testing and manufacturing iteration.", "hardware_engineering", "source_a", "naval_frontier_founders_industrial_2026"),
            ("Max Hodak", "The model reflects the judgment and domain knowledge the user brings.", "judgment", "source_a", "naval_frontier_founders_industrial_2026"),
            ("Naval Ravikant", "Small teams can build more companies rather than eliminating all work.", "startup_organization", "source_a", "naval_frontier_founders_industrial_2026"),
            ("Naval Ravikant", "Truthful and credible communication is the basis of durable persuasion.", "truth_and_credibility", "source_b", "naval_sell_truth_2026"),
            ("Nivi", "Does cheaper execution make judgment more important?", "judgment", "source_a", "naval_frontier_founders_industrial_2026"),
        ]
        for index, (speaker, text, theme, source_id, family) in enumerate(texts, 1):
            eid = f"e{index}"
            cid = f"c{index}"
            sid = f"sc{index}"
            evidence.append({"evidence_id": eid, "speaker": speaker, "source_text": text, "source_url": "https://nav.al/test", "source_ids": [source_id]})
            source_claims.append({"claim_id": sid, "claim": text, "speaker": speaker, "source_id": source_id, "source_family_id": family, "independence_group_id": family, "evidence_ids": [eid], "themes": [theme], "published_at": "2026-05-27", "claim_type": "open_question" if text.endswith("?") else "opinion", "attribution_scope": "host_question" if speaker == "Nivi" else "speaker_direct_claim"})
            canonical.append({"claim_id": cid, "parent_claim_ids": [sid], "claim": text, "speaker": speaker, "source_ids": [source_id], "source_family_ids": [family], "independence_group_ids": [family], "evidence_ids": [eid], "themes": [theme], "published_at": "2026-05-27", "claim_type": "open_question" if text.endswith("?") else "opinion", "attribution_scope": "host_question" if speaker == "Nivi" else "speaker_direct_claim", "value_types": ["trend_signal"], "importance_score": 0.8})
        # A forbidden description-only source claim must never enter the theme.
        canonical.append({"claim_id": "live", "parent_claim_ids": [], "claim": "Naval with founders living in the future.", "speaker": "unknown", "source_ids": ["naval_live_in_future_2026"], "source_family_ids": ["naval_live_in_the_future_2026"], "independence_group_ids": ["naval_live_in_the_future_2026"], "evidence_ids": ["e1"], "themes": ["future_of_work"], "published_at": "2026-07-02", "claim_type": "opinion", "attribution_scope": "host_summary", "value_types": ["trend_signal"], "importance_score": 0.5})
        _write_jsonl(corpus / "canonical/evidence.jsonl", evidence)
        _write_jsonl(corpus / "canonical/duplicate_content_clusters.jsonl", [])
        _write_jsonl(corpus / "intelligence/source_claims.jsonl", source_claims)
        _write_jsonl(corpus / "intelligence/canonical_claims.jsonl", canonical)
        _write_jsonl(corpus / "intelligence/theme_assignments.jsonl", [])
        _write_jsonl(corpus / "intelligence/person_positions.jsonl", [])
        _write_jsonl(corpus / "intelligence/trend_candidates.jsonl", [])
        _write_jsonl(corpus / "intelligence/insight_candidates.jsonl", [])
        _write_jsonl(corpus / "intelligence/verification_queue.jsonl", [{"queue_id": "q1", "claim_id": "c2", "priority": "P0", "reasons": ["negation"], "status": "pending"}])
        for relative in INPUT_FILES:
            self.assertTrue((corpus / relative).exists(), relative)
        return corpus

    def test_mock_theme_package_is_traceable_pending_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            corpus = self._corpus(root)
            output = root / "theme"
            scorer = DeterministicTestScorer(semantic_unit_version="phase_7_2b_v1", alignment_text_version="test")
            before_raw = hashlib.sha256((corpus / "sources/source_a/raw/source_raw.html").read_bytes()).hexdigest()
            first = run_phase72b_theme(corpus_dir=corpus, output_dir=output, semantic_mode="mock_semantic", judge_backend="mock", scorer=scorer, judge=MockThemeJudge())
            self.assertEqual(first["live_in_future_claim_count"], 0)
            self.assertGreater(first["theme_candidate_claim_count"], 0)
            self.assertLessEqual(first["theme_canonical_claim_count"], 60)
            claims = [json.loads(line) for line in (output / "theme_canonical_claims.jsonl").read_text().splitlines()]
            self.assertTrue(all(row["review_status"] == "pending" and row["evidence_ids"] for row in claims))
            self.assertTrue(all(row["parent_source_claim_ids"] for row in claims))
            insights = [json.loads(line) for line in (output / "insight_candidates.jsonl").read_text().splitlines()]
            self.assertTrue(all(row["attribution_scope"] == "system_synthesis" and row["publishability"] == "not_publishable_before_human_review" for row in insights))
            self.assertIn("Download theme claim review JSONL", (output / "views/theme_claim_review.html").read_text())
            self.assertIn("Current Judgment Draft", (output / "reports/current_judgment_draft.md").read_text())
            self.assertEqual(before_raw, hashlib.sha256((corpus / "sources/source_a/raw/source_raw.html").read_bytes()).hexdigest())
            before = {path.relative_to(output): hashlib.sha256(path.read_bytes()).hexdigest() for path in output.rglob("*") if path.is_file()}
            second = run_phase72b_theme(corpus_dir=corpus, output_dir=output, semantic_mode="mock_semantic", judge_backend="mock", scorer=DeterministicTestScorer(semantic_unit_version="phase_7_2b_v1", alignment_text_version="test"), judge=MockThemeJudge())
            after = {path.relative_to(output): hashlib.sha256(path.read_bytes()).hexdigest() for path in output.rglob("*") if path.is_file()}
            self.assertEqual(first, second)
            self.assertEqual(before, after)
            schema = json.loads(Path("schemas/phase_7_2b_theme_claim.schema.json").read_text())
            for row in claims:
                jsonschema.validate(row, schema)

    def test_missing_frozen_input_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "cannot run without frozen"):
                run_phase72b_theme(corpus_dir=Path(temp), output_dir=Path(temp) / "out", semantic_mode="mock_semantic", judge_backend="mock", scorer=DeterministicTestScorer(semantic_unit_version="v", alignment_text_version="v"), judge=MockThemeJudge())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from gather_insight.pipeline.phase72c_human_gate import finalize_phase72c_theme, prepare_phase72c_theme


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class Phase72CHumanGateTests(unittest.TestCase):
    def _package(self, root: Path) -> tuple[Path, Path]:
        corpus, theme = root / "corpus", root / "theme"
        raw = corpus / "sources/a/raw/source_raw.html"
        raw.parent.mkdir(parents=True)
        raw.write_text("<html>immutable</html>", encoding="utf-8")
        source_claims = [
            {"claim_id": "sc1", "claim": "AI agents make implementation cheaper.", "speaker": "Naval Ravikant", "attribution_scope": "speaker_direct_claim", "claim_type": "causal_claim", "themes": ["software_production"]},
            {"claim_id": "sc2", "claim": "Humans still choose which problem deserves effort.", "speaker": "Guillermo Rauch", "attribution_scope": "speaker_direct_claim", "claim_type": "opinion", "themes": ["judgment"]},
            {"claim_id": "sc3", "claim": "Physical products still require testing.", "speaker": "Blake Scholl", "attribution_scope": "speaker_personal_experience", "claim_type": "personal_experience", "themes": ["hardware_engineering"]},
        ]
        evidence = [
            {"evidence_id": "e1", "speaker": "Naval Ravikant", "source_text": "AI agents make implementation cheaper.", "numeric_risks": [], "source_url": "https://nav.al/a"},
            {"evidence_id": "e2", "speaker": "Guillermo Rauch", "source_text": "Humans still choose which problem deserves effort.", "numeric_risks": [], "source_url": "https://nav.al/a"},
            {"evidence_id": "e3", "speaker": "Blake Scholl", "source_text": "Physical products still require testing.", "numeric_risks": ["10x"], "source_url": "https://nav.al/a"},
        ]
        _write_jsonl(corpus / "intelligence/source_claims.jsonl", source_claims)
        _write_jsonl(corpus / "canonical/evidence.jsonl", evidence)
        claims = [
            {"schema_version": "phase_7_2b_v1", "theme_claim_id": "tc1", "statement": "AI lowers execution cost.", "subtheme": "falling_execution_costs", "claim_type": "causal_claim", "value_types": ["trend_signal"], "parent_source_claim_ids": ["sc1"], "parent_canonical_claim_ids": ["c1"], "evidence_ids": ["e1"], "speakers": ["Naval Ravikant"], "source_ids": ["a"], "source_family_ids": ["family_a"], "independent_source_family_count": 1, "first_seen_at": "2026-01-01", "last_seen_at": "2026-01-01", "conditions": [], "limitations": [], "counter_claim_ids": [], "entailment_status": "fully_supported", "verification_status": "official_text_only", "review_status": "pending", "model_and_prompt_version": "test"},
            {"schema_version": "phase_7_2b_v1", "theme_claim_id": "tc2", "statement": "Problem choice remains scarce.", "subtheme": "persistent_human_scarcities", "claim_type": "opinion", "value_types": ["trend_signal"], "parent_source_claim_ids": ["sc2"], "parent_canonical_claim_ids": ["c2"], "evidence_ids": ["e2"], "speakers": ["Guillermo Rauch"], "source_ids": ["a"], "source_family_ids": ["family_a"], "independent_source_family_count": 1, "first_seen_at": "2026-01-01", "last_seen_at": "2026-01-01", "conditions": [], "limitations": [], "counter_claim_ids": [], "entailment_status": "fully_supported", "verification_status": "official_text_only", "review_status": "pending", "model_and_prompt_version": "test"},
        ]
        relation = {"schema_version": "phase_7_2b_v1", "relation_id": "r1", "relation_type": "causes", "source_claim_id": "tc1", "target_claim_id": "tc2", "rationale": "Cheaper execution changes the relative bottleneck.", "supporting_evidence_ids": ["e1", "e2"], "confidence": 0.8, "review_status": "pending"}
        insight = {"schema_version": "phase_7_2b_v1", "insight_id": "i1", "statement": "Cheaper execution may increase the relative importance of judgment.", "insight_type": "causal_synthesis", "attribution_scope": "system_synthesis", "supporting_theme_claim_ids": ["tc1", "tc2"], "supporting_source_claim_ids": ["sc1", "sc2"], "evidence_ids": ["e1", "e2"], "speakers": ["Naval Ravikant", "Guillermo Rauch"], "independent_source_family_count": 1, "source_family_ids": ["family_a"], "causal_chain": ["execution falls", "judgment matters relatively more"], "conditions": [], "counterevidence": [], "unresolved_questions": [], "uncertainty": "one publication family", "confidence": 0.7, "inference_method": "test", "verification_status": "pending", "review_status": "pending", "publishability": "not_publishable_before_human_review"}
        _write_jsonl(theme / "theme_canonical_claims.jsonl", claims)
        _write_jsonl(theme / "theme_claim_relations.jsonl", [relation])
        _write_jsonl(theme / "insight_candidates.jsonl", [insight])
        _write_jsonl(theme / "verification_queue.jsonl", [{"queue_id": "q1", "priority": "P0", "conclusion_impact": "high", "reasons": ["negation"], "theme_claim_ids": ["tc2"], "insight_ids": ["i1"]}])
        (theme / "source_manifest.json").write_text(json.dumps({"input_files": {"source_index.jsonl": "sha"}}), encoding="utf-8")
        _write_jsonl(theme / "revision_history.jsonl", [{"revision_id": "rev1"}])
        return corpus, theme

    def test_prepare_keeps_pending_and_adds_independence_and_review_views(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            corpus, theme = self._package(Path(temp))
            raw = corpus / "sources/a/raw/source_raw.html"
            before = hashlib.sha256(raw.read_bytes()).hexdigest()
            result = prepare_phase72c_theme(theme_dir=theme, corpus_dir=corpus)
            self.assertEqual(result["status"], "pending_human_review")
            self.assertEqual(result["p0_verification_count"], 1)
            claims = _rows(theme / "theme_canonical_claims.jsonl")
            self.assertTrue(all(row["review_status"] == "pending" for row in claims))
            self.assertTrue(all(row["independent_publication_family_count"] == 1 for row in claims))
            self.assertIn("speaker_opinion", claims[0]["evidence_types"])
            insights = _rows(theme / "insight_candidates.jsonl")
            self.assertIn("system_inference", insights[0]["evidence_types"])
            self.assertIn("Download insight_review_decisions.jsonl", (theme / "views/theme_insight_review.html").read_text())
            self.assertIn("shifts_bottleneck_to", (theme / "views/theme_relation_review.html").read_text())
            self.assertFalse((theme / "accepted_theme_claims.jsonl").exists())
            self.assertEqual(before, hashlib.sha256(raw.read_bytes()).hexdigest())
            first_hashes = {path.relative_to(theme): hashlib.sha256(path.read_bytes()).hexdigest() for path in theme.rglob("*") if path.is_file()}
            prepare_phase72c_theme(theme_dir=theme, corpus_dir=corpus)
            second_hashes = {path.relative_to(theme): hashlib.sha256(path.read_bytes()).hexdigest() for path in theme.rglob("*") if path.is_file()}
            self.assertEqual(first_hashes, second_hashes)

    def test_finalize_rejects_pending_human_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            corpus, theme = self._package(Path(temp))
            prepare_phase72c_theme(theme_dir=theme, corpus_dir=corpus)
            with self.assertRaisesRegex(ValueError, "missing or invalid"):
                finalize_phase72c_theme(theme_dir=theme, corpus_dir=corpus, claim_decisions_path=theme / "theme_claim_review_decisions.template.jsonl", relation_decisions_path=theme / "relation_review_decisions.template.jsonl", insight_decisions_path=theme / "insight_review_decisions.template.jsonl", verification_decisions_path=theme / "p0_verification_decisions.template.jsonl")

    def test_complete_human_gate_freezes_only_accepted_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            corpus, theme = self._package(Path(temp))
            prepare_phase72c_theme(theme_dir=theme, corpus_dir=corpus)
            claims = _rows(theme / "theme_claim_review_decisions.template.jsonl")
            for row in claims:
                row.update({"decision": "accept", "entailment_status": "fully_supported", "epistemic_status": "directly_supported", "speaker_attribution_correct": True, "conditions_preserved": True, "claim_scope_valid": True, "support_independence_sufficient": True, "reviewer": "tester", "reviewed_at": "2026-07-20T00:00:00Z"})
            relations = _rows(theme / "relation_review_decisions.template.jsonl")
            relations[0].update({"decision": "edit", "final_relation_type": "shifts_bottleneck_to", "direction_correct": True, "reviewer": "tester", "reviewed_at": "2026-07-20T00:00:00Z"})
            insights = _rows(theme / "insight_review_decisions.template.jsonl")
            insights[0].update({"decision": "accept_with_edit", "epistemic_status": "supported_synthesis", "support_scope": "this fixed Naval corpus", "conditions_preserved": True, "causal_chain_valid": True, "independent_support_sufficient": False, "verification_required": True, "reviewer": "tester", "reviewed_at": "2026-07-20T00:00:00Z"})
            verification = _rows(theme / "p0_verification_decisions.template.jsonl")
            verification[0].update({"decision": "verified_from_official_text", "verification_note": "Confirmed against the official evidence excerpt.", "reviewer": "tester", "reviewed_at": "2026-07-20T00:00:00Z"})
            paths = []
            for name, rows in (("claims.jsonl", claims), ("relations.jsonl", relations), ("insights.jsonl", insights), ("verification.jsonl", verification)):
                path = theme / name
                _write_jsonl(path, rows)
                paths.append(path)
            result = finalize_phase72c_theme(theme_dir=theme, corpus_dir=corpus, claim_decisions_path=paths[0], relation_decisions_path=paths[1], insight_decisions_path=paths[2], verification_decisions_path=paths[3])
            self.assertEqual(result["status"], "frozen")
            self.assertEqual(_rows(theme / "accepted_relations.jsonl")[0]["relation_type"], "shifts_bottleneck_to")
            judgment = json.loads((theme / "theme_judgment_v1.json").read_text())
            jsonschema.validate(judgment, json.loads(Path("schemas/phase_7_2c_theme_judgment.schema.json").read_text()))
            self.assertIn("本批Naval及嘉宾语料共同指向", judgment["calibrated_statement"])
            self.assertTrue((theme / "reports/website_topic_draft.md").exists())


if __name__ == "__main__":
    unittest.main()

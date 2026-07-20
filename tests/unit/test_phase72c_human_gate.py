from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from gather_insight.pipeline.phase72c_human_gate import finalize_phase72c_gate_a, finalize_phase72c_theme, prepare_phase72c_theme


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
            {"claim_id": "sc1", "claim": "AI agents make implementation cheaper.", "speaker": "Naval Ravikant", "source_id": "a", "source_section_ids": ["s1"], "published_at": "2026-01-01", "attribution_scope": "speaker_direct_claim", "claim_type": "causal_claim", "themes": ["software_production"]},
            {"claim_id": "sc2", "claim": "Problem choice is not commoditized.", "speaker": "Guillermo Rauch", "source_id": "a", "source_section_ids": ["s2"], "published_at": "2026-01-01", "attribution_scope": "speaker_direct_claim", "claim_type": "causal_claim", "themes": ["judgment"]},
        ]
        evidence = [
            {"evidence_id": "e1", "speaker": "Naval Ravikant", "source_text": "AI agents make implementation cheaper. Another unrelated sentence says 10x.", "numeric_risks": ["10x"], "entity_risks": [], "source_section_ids": ["s1"], "source_url": "https://nav.al/a"},
            {"evidence_id": "e2", "speaker": "Guillermo Rauch", "source_text": "Problem choice is not commoditized.", "numeric_risks": [], "entity_risks": [], "source_section_ids": ["s2"], "source_url": "https://nav.al/a"},
        ]
        sections = [
            {"section_id": "s0", "source_id": "a", "section_order": 0, "speaker": "Nivi", "text": "What changes when execution gets cheap?", "title": "A", "published_at": "2026-01-01", "source_url": "https://nav.al/a"},
            {"section_id": "s1", "source_id": "a", "section_order": 1, "speaker": "Naval Ravikant", "text": "AI agents make implementation cheaper.", "title": "A", "published_at": "2026-01-01", "source_url": "https://nav.al/a"},
            {"section_id": "s2", "source_id": "a", "section_order": 2, "speaker": "Guillermo Rauch", "text": "Problem choice is not commoditized.", "title": "A", "published_at": "2026-01-01", "source_url": "https://nav.al/a"},
        ]
        _write_jsonl(corpus / "intelligence/source_claims.jsonl", source_claims)
        _write_jsonl(corpus / "canonical/evidence.jsonl", evidence)
        _write_jsonl(corpus / "canonical/sections.jsonl", sections)
        common = {"schema_version": "phase_7_2b_v1", "value_types": ["trend_signal"], "source_ids": ["a"], "source_family_ids": ["family_a"], "independent_source_family_count": 1, "first_seen_at": "2026-01-01", "last_seen_at": "2026-01-01", "conditions": [], "limitations": [], "counter_claim_ids": [], "entailment_status": "fully_supported", "verification_status": "official_text_only", "review_status": "pending", "model_and_prompt_version": "test"}
        claims = [
            {**common, "theme_claim_id": "tc1", "statement": "AI lowers execution cost.", "subtheme": "falling_execution_costs", "claim_type": "causal_claim", "parent_source_claim_ids": ["sc1"], "parent_canonical_claim_ids": ["c1"], "evidence_ids": ["e1"], "speakers": ["Naval Ravikant"]},
            {**common, "theme_claim_id": "tc2", "statement": "Problem choice is not commoditized.", "subtheme": "persistent_human_scarcities", "claim_type": "causal_claim", "parent_source_claim_ids": ["sc2"], "parent_canonical_claim_ids": ["c2"], "evidence_ids": ["e2"], "speakers": ["Guillermo Rauch"]},
        ]
        relation = {"schema_version": "phase_7_2b_v1", "relation_id": "r1", "relation_type": "causes", "source_claim_id": "tc1", "target_claim_id": "tc2", "rationale": "Cheaper execution changes the relative bottleneck.", "supporting_evidence_ids": ["e1", "e2"], "confidence": 0.8, "review_status": "pending"}
        insight = {"schema_version": "phase_7_2b_v1", "insight_id": "i1", "statement": "Cheaper execution may increase the relative importance of judgment.", "insight_type": "causal_synthesis", "attribution_scope": "system_synthesis", "supporting_theme_claim_ids": ["tc1", "tc2"], "supporting_source_claim_ids": ["sc1", "sc2"], "evidence_ids": ["e1", "e2"], "speakers": ["Naval Ravikant", "Guillermo Rauch"], "independent_source_family_count": 1, "source_family_ids": ["family_a"], "causal_chain": ["execution falls", "judgment matters relatively more"], "conditions": [], "counterevidence": [], "unresolved_questions": [], "uncertainty": "one publication family", "confidence": 0.7, "inference_method": "test", "verification_status": "pending", "review_status": "pending", "publishability": "not_publishable_before_human_review"}
        _write_jsonl(theme / "theme_canonical_claims.jsonl", claims)
        _write_jsonl(theme / "theme_claim_relations.jsonl", [relation])
        _write_jsonl(theme / "insight_candidates.jsonl", [insight])
        _write_jsonl(theme / "verification_queue.jsonl", [{"queue_id": "old-context-p0", "priority": "P0", "conclusion_impact": "high", "reasons": ["numeric"], "theme_claim_ids": ["tc1"], "insight_ids": ["i1"]}])
        (theme / "source_manifest.json").write_text(json.dumps({"input_files": {"source_index.jsonl": "sha"}}), encoding="utf-8")
        _write_jsonl(theme / "revision_history.jsonl", [{"revision_id": "rev1"}])
        return corpus, theme

    def _gate_a_decisions(self, theme: Path) -> tuple[Path, Path, Path]:
        claims = _rows(theme / "theme_claim_review_decisions.template.jsonl")
        for row in claims:
            row.update({"decision": "accept", "entailment_status": "fully_supported", "epistemic_status": "directly_supported", "speaker_attribution_correct": True, "conditions_preserved": True, "claim_scope_valid": True, "support_independence_sufficient": True, "reviewer": "tester", "reviewed_at": "2026-07-20T00:00:00Z"})
        relations = _rows(theme / "relation_review_decisions.template.jsonl")
        relations[0].update({"decision": "edit", "final_relation_type": "shifts_bottleneck_to", "direction_correct": True, "reviewer": "tester", "reviewed_at": "2026-07-20T00:00:00Z"})
        insights = _rows(theme / "insight_review_decisions.template.jsonl")
        insights[0].update({"decision": "accept_with_edit", "epistemic_status": "supported_synthesis", "support_scope": "this fixed Naval corpus", "conditions_preserved": True, "causal_chain_valid": True, "independent_support_sufficient": False, "verification_required": True, "reviewer": "tester", "reviewed_at": "2026-07-20T00:00:00Z"})
        paths = []
        for name, rows in (("claims.jsonl", claims), ("relations.jsonl", relations), ("insights.jsonl", insights)):
            path = theme / name
            _write_jsonl(path, rows)
            paths.append(path)
        return tuple(paths)  # type: ignore[return-value]

    def test_prepare_is_claim_local_short_and_does_not_mutate_phase72b_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            corpus, theme = self._package(Path(temp))
            raw = corpus / "sources/a/raw/source_raw.html"
            original_claim_hash = hashlib.sha256((theme / "theme_canonical_claims.jsonl").read_bytes()).hexdigest()
            result = prepare_phase72c_theme(theme_dir=theme, corpus_dir=corpus)
            self.assertEqual(result["status"], "gate_a_pending")
            self.assertEqual(result["original_p0_count"], 1)
            self.assertEqual(result["claim_local_p0_count"], 1)
            p0 = _rows(theme / "claim_local_p0_verification_queue.jsonl")
            p0_schema = json.loads(Path("schemas/phase_7_2c_p0_verification.schema.json").read_text())
            jsonschema.validate(p0[0], p0_schema)
            self.assertEqual(p0[0]["risk_token"], "not")
            self.assertNotIn("10x", json.dumps(p0))
            self.assertLessEqual(len(p0[0]["direct_support_excerpt"]), 3)
            self.assertTrue(p0[0]["local_context"]["previous_turn"])
            self.assertEqual(original_claim_hash, hashlib.sha256((theme / "theme_canonical_claims.jsonl").read_bytes()).hexdigest())
            self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(), hashlib.sha256(b"<html>immutable</html>").hexdigest())
            first_hashes = {path.relative_to(theme): hashlib.sha256(path.read_bytes()).hexdigest() for path in theme.rglob("*") if path.is_file()}
            prepare_phase72c_theme(theme_dir=theme, corpus_dir=corpus)
            second_hashes = {path.relative_to(theme): hashlib.sha256(path.read_bytes()).hexdigest() for path in theme.rglob("*") if path.is_file()}
            self.assertEqual(first_hashes, second_hashes)

    def test_gate_a_rejects_pending_and_auto_rejects_relation_with_rejected_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            corpus, theme = self._package(Path(temp))
            prepare_phase72c_theme(theme_dir=theme, corpus_dir=corpus)
            with self.assertRaisesRegex(ValueError, "missing or invalid"):
                finalize_phase72c_gate_a(theme_dir=theme, corpus_dir=corpus, claim_decisions_path=theme / "theme_claim_review_decisions.template.jsonl", relation_decisions_path=theme / "relation_review_decisions.template.jsonl", insight_decisions_path=theme / "insight_review_decisions.template.jsonl")
            claims = _rows(theme / "theme_claim_review_decisions.template.jsonl")
            for row in claims:
                row.update({"decision": "accept", "entailment_status": "fully_supported", "epistemic_status": "directly_supported", "speaker_attribution_correct": True, "conditions_preserved": True, "claim_scope_valid": True, "support_independence_sufficient": True, "reviewer": "tester", "reviewed_at": "2026-07-20T00:00:00Z"})
            claims[1]["decision"] = "reject_unsupported"
            insights = _rows(theme / "insight_review_decisions.template.jsonl")
            insights[0].update({"decision": "defer_for_more_evidence", "reviewer": "tester", "reviewed_at": "2026-07-20T00:00:00Z"})
            relations = _rows(theme / "relation_review_decisions.template.jsonl")
            for name, rows in (("c.jsonl", claims), ("i.jsonl", insights), ("r.jsonl", relations)):
                _write_jsonl(theme / name, rows)
            result = finalize_phase72c_gate_a(theme_dir=theme, corpus_dir=corpus, claim_decisions_path=theme / "c.jsonl", relation_decisions_path=theme / "r.jsonl", insight_decisions_path=theme / "i.jsonl")
            self.assertEqual(result["auto_rejected_parent_relation_count"], 1)
            self.assertEqual(result["active_p0_count"], 0)
            self.assertEqual(_rows(theme / "provisionally_rejected_relations.jsonl")[0]["review_status"], "rejected_parent_claim")

    def test_gate_b_freezes_provisional_without_claiming_external_fact_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            corpus, theme = self._package(Path(temp))
            prepare_phase72c_theme(theme_dir=theme, corpus_dir=corpus)
            paths = self._gate_a_decisions(theme)
            gate_a = finalize_phase72c_gate_a(theme_dir=theme, corpus_dir=corpus, claim_decisions_path=paths[0], relation_decisions_path=paths[1], insight_decisions_path=paths[2])
            self.assertEqual(gate_a["active_p0_count"], 1)
            verification = _rows(theme / "p0_verification_decisions.template.jsonl")
            verification[0].update({"source_fidelity_status": "verified", "external_fact_status": "not_checked", "verification_note": "Official source preserves the negation; external economics claim was not checked.", "reviewer": "tester", "reviewed_at": "2026-07-20T00:00:00Z"})
            path = theme / "verification.jsonl"
            _write_jsonl(path, verification)
            result = finalize_phase72c_theme(theme_dir=theme, corpus_dir=corpus, verification_decisions_path=path)
            self.assertEqual(result["status"], "human_reviewed_provisional")
            self.assertEqual(result["theme_asset_readiness"], "ready")
            self.assertEqual(result["factual_publication_readiness"], "needs_external_verification")
            self.assertFalse(result["publication_candidates_generated"])
            judgment = json.loads((theme / "theme_judgment_v1.json").read_text())
            jsonschema.validate(judgment, json.loads(Path("schemas/phase_7_2c_theme_judgment.schema.json").read_text()))
            self.assertEqual(judgment["status"], "human_reviewed_provisional")
            self.assertIn("external factual verification is incomplete", judgment["evidence_scope"])
            self.assertFalse((theme / "reports/website_topic_draft.md").exists())
            first_hashes = {path.relative_to(theme): hashlib.sha256(path.read_bytes()).hexdigest() for path in theme.rglob("*") if path.is_file()}
            finalize_phase72c_theme(theme_dir=theme, corpus_dir=corpus, verification_decisions_path=path)
            second_hashes = {path.relative_to(theme): hashlib.sha256(path.read_bytes()).hexdigest() for path in theme.rglob("*") if path.is_file()}
            self.assertEqual(first_hashes, second_hashes)

    def test_unchecked_external_fact_can_publish_only_when_human_frames_hypothesis(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            corpus, theme = self._package(Path(temp))
            prepare_phase72c_theme(theme_dir=theme, corpus_dir=corpus)
            claims_path, relations_path, insights_path = self._gate_a_decisions(theme)
            claims = _rows(claims_path)
            claims[1]["final_statement"] = "Guillermo suggests that problem choice may not be commoditized."
            claims[1]["epistemic_status"] = "hypothesis"
            _write_jsonl(claims_path, claims)
            finalize_phase72c_gate_a(theme_dir=theme, corpus_dir=corpus, claim_decisions_path=claims_path, relation_decisions_path=relations_path, insight_decisions_path=insights_path)
            verification = _rows(theme / "p0_verification_decisions.template.jsonl")
            verification[0].update({"source_fidelity_status": "verified", "external_fact_status": "not_checked", "verification_note": "Source wording confirmed; kept as a named hypothesis.", "reviewer": "tester", "reviewed_at": "2026-07-20T00:00:00Z"})
            path = theme / "verification.jsonl"
            _write_jsonl(path, verification)
            result = finalize_phase72c_theme(theme_dir=theme, corpus_dir=corpus, verification_decisions_path=path)
            self.assertEqual(result["factual_publication_readiness"], "ready")
            self.assertTrue(result["publication_candidates_generated"])
            self.assertTrue((theme / "reports/website_topic_draft.md").exists())


if __name__ == "__main__":
    unittest.main()

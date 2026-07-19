"""Phase 7.2C human gate, epistemic calibration, and publication freeze.

The module deliberately separates preparation from finalization.  Preparation
adds deterministic evidence-independence metadata and creates review forms.  It
never changes ``pending`` into ``accepted``.  Finalization requires complete
human decision files and only then materializes accepted assets and publication
drafts.
"""

from __future__ import annotations

import hashlib
import html
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "phase_7_2c_v1"
THEME_SLUG = "ai_execution_commoditization_judgment_scarcity"
RELATION_TYPES = {
    "exact_duplicate", "near_duplicate", "restates", "supports", "refines", "expands", "narrows",
    "prerequisite_of", "causes", "consequence_of", "example_of", "limits", "contradicts",
    "tension_with", "unrelated", "enables", "shifts_bottleneck_to",
    "increases_relative_importance_of", "coexists_with", "conditional_on",
}
EVIDENCE_TYPES = {
    "speaker_opinion", "personal_experience", "engineering_case", "company_practice",
    "quantitative_data", "external_fact", "research_result", "system_inference",
}
CLAIM_DECISIONS = {
    "accept", "edit", "merge", "split", "reject_low_value", "reject_overgeneralized",
    "reject_unsupported", "defer",
}
INSIGHT_DECISIONS = {"accept", "accept_with_edit", "split", "reject", "defer_for_more_evidence"}
RELATION_DECISIONS = {"accept", "edit", "reject"}
VERIFICATION_DECISIONS = {
    "verified_from_official_text", "corrected", "rejected", "not_applicable", "defer_for_external_check",
}
EPISTEMIC_STATUSES = {
    "directly_supported", "supported_synthesis", "provisional", "hypothesis", "contested", "insufficient_evidence",
}
_PERSON_ORGANIZATION = {
    "Guillermo Rauch": "Vercel",
    "Blake Scholl": "Boom Supersonic",
    "Max Hodak": "Science Corp",
    "Nivi": "Naval Podcast",
}
_SUBTHEME_DOMAIN = {
    "falling_execution_costs": "software_and_ai",
    "persistent_human_scarcities": "human_judgment_and_trust",
    "leverage_distribution": "organization_and_work",
    "software_value_migration": "software_economics",
    "software_to_industry": "industrial_engineering",
    "new_bottlenecks": "regulation_and_institutions",
    "internal_tensions": "cross_domain_synthesis",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"required JSONL does not exist: {path}")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"JSONL row must be an object at {path}:{number}")
        rows.append(value)
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_hashes(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): _sha256(path) for path in sorted(root.rglob("*")) if path.is_file()}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value) for value in values if str(value).strip()})


def _evidence_types(source_claims: list[dict[str, Any]], evidence: list[dict[str, Any]], subtheme: str) -> list[str]:
    result: set[str] = set()
    joined = " ".join(str(row.get("claim") or "") for row in source_claims).lower()
    for row in source_claims:
        scope = str(row.get("attribution_scope") or "")
        claim_type = str(row.get("claim_type") or "")
        speaker = str(row.get("speaker") or "")
        if scope == "speaker_personal_experience" or claim_type == "personal_experience" or any(token in str(row.get("claim") or "").lower() for token in ("i built", "we built", "at our company", "in my experience")):
            result.add("personal_experience")
        if speaker in {"Guillermo Rauch", "Blake Scholl", "Max Hodak"} and subtheme in {"falling_execution_costs", "software_value_migration", "software_to_industry", "new_bottlenecks"}:
            result.add("engineering_case")
        if speaker in {"Guillermo Rauch", "Blake Scholl", "Max Hodak"} and any(token in joined for token in ("we use", "we build", "production", "company", "factory", "manufactur", "clinical")):
            result.add("company_practice")
        if claim_type == "fact":
            result.add("external_fact")
        if claim_type in {"opinion", "prediction", "causal_claim", "normative_claim", "strategic_advice", "open_question"}:
            result.add("speaker_opinion")
    if any(row.get("numeric_risks") for row in evidence):
        result.add("quantitative_data")
    if any(row.get("research_result") for row in source_claims):
        result.add("research_result")
    return sorted(result or {"speaker_opinion"})


def _claim_independence(
    claim: dict[str, Any], source_claim_by_id: dict[str, dict[str, Any]], evidence_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    parents = [source_claim_by_id[row_id] for row_id in claim.get("parent_source_claim_ids", []) if row_id in source_claim_by_id]
    evidence = [evidence_by_id[row_id] for row_id in claim.get("evidence_ids", []) if row_id in evidence_by_id]
    speakers = _unique(row.get("speaker", "") for row in parents if row.get("speaker") not in {None, "", "unknown"})
    organizations = _unique(_PERSON_ORGANIZATION.get(speaker, "") for speaker in speakers)
    domains = {_SUBTHEME_DOMAIN.get(str(claim.get("subtheme") or ""), str(claim.get("subtheme") or "unknown"))}
    for row in parents:
        for theme in row.get("themes", []):
            if theme in {"hardware_engineering", "manufacturing", "vertical_integration"}:
                domains.add("industrial_engineering")
            elif theme in {"regulation", "institutional_change"}:
                domains.add("regulation_and_institutions")
            elif theme in {"truth_and_credibility", "persuasion_and_sales"}:
                domains.add("commercial_trust")
            elif theme in {"software_production", "ai_coding_agents", "token_economics"}:
                domains.add("software_and_ai")
    types = _evidence_types(parents, evidence, str(claim.get("subtheme") or ""))
    families = _unique(claim.get("source_family_ids", []))
    return {
        "independent_publication_family_count": len(families),
        "independent_speaker_count": len(speakers),
        "independent_organization_count": len(organizations),
        "independent_domain_count": len(domains),
        "independent_evidence_type_count": len(types),
        "independent_speakers": speakers,
        "independent_organizations": organizations,
        "independent_domains": sorted(domains),
        "evidence_types": types,
        "independence_note": "Publication families measure publication independence only; they are not automatically independent industry evidence.",
    }


def _insight_independence(insight: dict[str, Any], claim_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    claims = [claim_by_id[row_id] for row_id in insight.get("supporting_theme_claim_ids", []) if row_id in claim_by_id]
    fields = {
        "independent_publication_family_count": len({family for row in claims for family in row.get("source_family_ids", [])}),
        "independent_speaker_count": len({speaker for row in claims for speaker in row.get("independent_speakers", [])}),
        "independent_organization_count": len({org for row in claims for org in row.get("independent_organizations", [])}),
        "independent_domain_count": len({domain for row in claims for domain in row.get("independent_domains", [])}),
        "independent_evidence_type_count": len({kind for row in claims for kind in row.get("evidence_types", [])} | {"system_inference"}),
        "independent_speakers": _unique(speaker for row in claims for speaker in row.get("independent_speakers", [])),
        "independent_organizations": _unique(org for row in claims for org in row.get("independent_organizations", [])),
        "independent_domains": _unique(domain for row in claims for domain in row.get("independent_domains", [])),
        "evidence_types": _unique(["system_inference", *[kind for row in claims for kind in row.get("evidence_types", [])]]),
        "independence_note": "Cross-family support is publication diversity, not proof of independent industry validation.",
    }
    return fields


def _select_html(name: str, values: Iterable[str], *, class_name: str, blank: bool = True, selected: str | None = None) -> str:
    options = '<option value=""></option>' if blank else ""
    options += "".join(f'<option value="{html.escape(value)}"{" selected" if value == selected else ""}>{html.escape(value)}</option>' for value in values)
    return f'<label>{html.escape(name)}<select class="{class_name}">{options}</select></label>'


def _download_script(record_type: str, file_name: str, fields: list[tuple[str, str, str]]) -> str:
    assignments = []
    for key, selector, kind in fields:
        if kind == "bool":
            assignments.append(f'row.{key}=card.querySelector("{selector}").value===""?null:card.querySelector("{selector}").value==="true";')
        elif kind == "lines":
            assignments.append(f'row.{key}=card.querySelector("{selector}").value.split("\\n").map(x=>x.trim()).filter(Boolean);')
        else:
            assignments.append(f'row.{key}=card.querySelector("{selector}").value;')
    return (
        f'<button onclick="downloadReview()">Download {html.escape(file_name)}</button>'
        '<script>function downloadReview(){const reviewer=document.getElementById("reviewer").value.trim();'
        'if(!reviewer){alert("Reviewer is required");return}const reviewedAt=new Date().toISOString();'
        'const rows=[...document.querySelectorAll("article")].map(card=>{const row=JSON.parse(card.dataset.row);'
        + "".join(assignments) +
        f'row.record_type="{record_type}";row.reviewer=reviewer;row.reviewed_at=reviewedAt;return row}});'
        'const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([rows.map(x=>JSON.stringify(x)).join("\\n")+"\\n"],{type:"application/jsonl"}));'
        f'a.download="{file_name}";a.click()}}</script>'
    )


def _page(title: str, summary: str, cards: list[str], script: str) -> str:
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>' + html.escape(title) + '</title>'
        '<style>body{font:14px/1.55 system-ui;max-width:1180px;margin:24px auto;color:#20242a}.top{position:sticky;top:0;background:#fff;z-index:5;border-bottom:1px solid #bbb;padding:10px}.warning{background:#fff3cd;padding:10px}.card{border:1px solid #bbb;border-radius:8px;padding:16px;margin:18px 0}.evidence{white-space:pre-wrap;background:#f5f5f5;padding:10px}.form{display:grid;grid-template-columns:1fr 1fr;gap:10px}.form label{display:grid;gap:4px}.wide{grid-column:1/-1}textarea{min-height:70px}details{margin:10px 0}.risk{color:#8a3100}.pending{border-left:5px solid #d69e00}</style></head><body>'
        f'<div class="top"><h1>{html.escape(title)}</h1><p class="warning">{html.escape(summary)}</p><label>Reviewer <input id="reviewer"></label> {script}</div>'
        + "".join(cards) + '</body></html>'
    )


def _claim_review_page(claims: list[dict[str, Any]], source_claim_by_id: dict[str, dict[str, Any]], evidence_by_id: dict[str, dict[str, Any]]) -> str:
    cards = []
    for index, claim in enumerate(claims, 1):
        evidence = [evidence_by_id[row_id] for row_id in claim.get("evidence_ids", []) if row_id in evidence_by_id]
        parents = [source_claim_by_id[row_id] for row_id in claim.get("parent_source_claim_ids", []) if row_id in source_claim_by_id]
        row = {"schema_version": SCHEMA_VERSION, "theme_claim_id": claim["theme_claim_id"], "decision": "", "final_statement": claim["statement"], "merge_into": "", "split_statements": [], "entailment_status": "", "speaker_attribution_correct": None, "conditions_preserved": None, "claim_scope_valid": None, "support_independence_sufficient": None, "epistemic_status": "", "verification_risks": [], "reviewer_note": "", "reviewer": "", "reviewed_at": ""}
        cards.append(
            f'<article class="card pending" data-row="{html.escape(json.dumps(row, ensure_ascii=False), quote=True)}"><h2>{index:02d}. {html.escape(claim["statement"])}</h2>'
            f'<p>{html.escape(claim["subtheme"])} · speakers: {html.escape(", ".join(claim.get("speakers", [])))} · publication families: {claim["independent_publication_family_count"]} · speakers: {claim["independent_speaker_count"]} · organizations: {claim["independent_organization_count"]} · domains: {claim["independent_domain_count"]} · evidence types: {html.escape(", ".join(claim["evidence_types"]))}</p>'
            f'<p><strong>Conditions:</strong> {html.escape("; ".join(claim.get("conditions", [])) or "none recorded")}</p><p><strong>Limitations:</strong> {html.escape("; ".join(claim.get("limitations", [])) or "none recorded")}</p>'
            '<details><summary>Parent source claims</summary><div class="evidence">' + html.escape("\n\n".join(f'{row.get("speaker")}: {row.get("claim")}' for row in parents)) + '</div></details>'
            '<details><summary>Official evidence</summary><div class="evidence">' + html.escape("\n\n".join(f'{row.get("speaker")}: {row.get("source_text")}' for row in evidence)) + '</div></details>'
            '<div class="form">' + _select_html("decision", sorted(CLAIM_DECISIONS), class_name="decision") +
            '<label>final statement<textarea class="statement">' + html.escape(claim["statement"]) + '</textarea></label>' +
            '<label>merge into theme claim ID<input class="merge"></label><label>split statements (one per line)<textarea class="splits"></textarea></label>' +
            _select_html("entailment", ["fully_supported", "supported_with_missing_condition", "partially_supported", "overgeneralized", "contradicted", "unrelated"], class_name="entailment") +
            _select_html("epistemic status", sorted(EPISTEMIC_STATUSES), class_name="epistemic") +
            _select_html("speaker attribution correct", ["true", "false"], class_name="speaker") +
            _select_html("conditions preserved", ["true", "false"], class_name="conditions") +
            _select_html("claim scope valid", ["true", "false"], class_name="scope") +
            _select_html("support independence sufficient", ["true", "false"], class_name="independence") +
            '<label>verification risks (one per line)<textarea class="risks"></textarea></label><label>reviewer note<textarea class="note"></textarea></label></div></article>'
        )
    fields = [("decision", ".decision", "str"), ("final_statement", ".statement", "str"), ("merge_into", ".merge", "str"), ("split_statements", ".splits", "lines"), ("entailment_status", ".entailment", "str"), ("epistemic_status", ".epistemic", "str"), ("speaker_attribution_correct", ".speaker", "bool"), ("conditions_preserved", ".conditions", "bool"), ("claim_scope_valid", ".scope", "bool"), ("support_independence_sufficient", ".independence", "bool"), ("verification_risks", ".risks", "lines"), ("reviewer_note", ".note", "str")]
    return _page("Phase 7.2C Theme Claim Review", "Review all 30 canonical theme claims. No pending item is accepted automatically.", cards, _download_script("theme_claim", "theme_claim_review_decisions.jsonl", fields))


def _insight_review_page(insights: list[dict[str, Any]], claim_by_id: dict[str, dict[str, Any]], evidence_by_id: dict[str, dict[str, Any]]) -> str:
    cards = []
    for index, insight in enumerate(insights, 1):
        claims = [claim_by_id[row_id] for row_id in insight.get("supporting_theme_claim_ids", []) if row_id in claim_by_id]
        evidence = [evidence_by_id[row_id] for row_id in insight.get("evidence_ids", []) if row_id in evidence_by_id]
        row = {"schema_version": SCHEMA_VERSION, "insight_id": insight["insight_id"], "decision": "", "final_statement": insight["statement"], "split_statements": [], "insight_type": insight["insight_type"], "epistemic_status": "", "support_scope": "", "conditions_preserved": None, "causal_chain_valid": None, "independent_support_sufficient": None, "verification_required": None, "reviewer_note": "", "reviewer": "", "reviewed_at": ""}
        cards.append(
            f'<article class="card pending" data-row="{html.escape(json.dumps(row, ensure_ascii=False), quote=True)}"><h2>{index}. {html.escape(insight["statement"])}</h2>'
            f'<p>system synthesis · families: {insight["independent_publication_family_count"]} · speakers: {insight["independent_speaker_count"]} · organizations: {insight["independent_organization_count"]} · domains: {insight["independent_domain_count"]}</p>'
            f'<p><strong>Causal chain:</strong> {html.escape(" → ".join(insight.get("causal_chain", [])))}</p><p><strong>Conditions:</strong> {html.escape("; ".join(insight.get("conditions", [])))}</p>'
            '<details><summary>Supporting theme claims</summary><div class="evidence">' + html.escape("\n".join(f'{row["theme_claim_id"]}: {row["statement"]}' for row in claims)) + '</div></details>'
            '<details><summary>Official evidence</summary><div class="evidence">' + html.escape("\n\n".join(str(row.get("source_text") or "") for row in evidence)) + '</div></details>'
            '<div class="form">' + _select_html("decision", sorted(INSIGHT_DECISIONS), class_name="decision") +
            '<label>final statement<textarea class="statement">' + html.escape(insight["statement"]) + '</textarea></label><label>split statements<textarea class="splits"></textarea></label>' +
            _select_html("insight type", ["repeated_speaker_position", "cross_source_pattern", "causal_synthesis", "industry_implication", "organizational_implication", "unresolved_tension", "hypothesis"], class_name="type", blank=False, selected=insight["insight_type"]) +
            _select_html("epistemic status", sorted(EPISTEMIC_STATUSES), class_name="epistemic") +
            '<label>support scope<input class="scope" placeholder="e.g. this Naval corpus only"></label>' +
            _select_html("conditions preserved", ["true", "false"], class_name="conditions") +
            _select_html("causal chain valid", ["true", "false"], class_name="causal") +
            _select_html("independent support sufficient", ["true", "false"], class_name="independence") +
            _select_html("verification required", ["true", "false"], class_name="verification") +
            '<label class="wide">reviewer note<textarea class="note"></textarea></label></div></article>'
        )
    fields = [("decision", ".decision", "str"), ("final_statement", ".statement", "str"), ("split_statements", ".splits", "lines"), ("insight_type", ".type", "str"), ("epistemic_status", ".epistemic", "str"), ("support_scope", ".scope", "str"), ("conditions_preserved", ".conditions", "bool"), ("causal_chain_valid", ".causal", "bool"), ("independent_support_sufficient", ".independence", "bool"), ("verification_required", ".verification", "bool"), ("reviewer_note", ".note", "str")]
    return _page("Phase 7.2C Insight Review", "Review the seven system syntheses. The page never converts pending into accepted.", cards, _download_script("insight", "insight_review_decisions.jsonl", fields))


def _relation_review_page(relations: list[dict[str, Any]], claim_by_id: dict[str, dict[str, Any]]) -> str:
    cards = []
    for index, relation in enumerate(relations, 1):
        left, right = claim_by_id[relation["source_claim_id"]], claim_by_id[relation["target_claim_id"]]
        row = {"schema_version": SCHEMA_VERSION, "relation_id": relation["relation_id"], "decision": "", "final_relation_type": relation["relation_type"], "direction_correct": None, "final_rationale": relation["rationale"], "reviewer_note": "", "reviewer": "", "reviewed_at": ""}
        cards.append(
            f'<article class="card pending" data-row="{html.escape(json.dumps(row, ensure_ascii=False), quote=True)}"><h2>{index}. {html.escape(relation["relation_type"])}</h2>'
            f'<p><strong>Source:</strong> {html.escape(left["statement"])}</p><p><strong>Target:</strong> {html.escape(right["statement"])}</p><p><strong>Rationale:</strong> {html.escape(relation["rationale"])}</p>'
            '<div class="form">' + _select_html("decision", sorted(RELATION_DECISIONS), class_name="decision") +
            _select_html("final relation", sorted(RELATION_TYPES), class_name="type", blank=False, selected=relation["relation_type"]) +
            _select_html("direction correct", ["true", "false"], class_name="direction") +
            '<label>final rationale<textarea class="rationale">' + html.escape(relation["rationale"]) + '</textarea></label><label class="wide">reviewer note<textarea class="note"></textarea></label></div></article>'
        )
    fields = [("decision", ".decision", "str"), ("final_relation_type", ".type", "str"), ("direction_correct", ".direction", "bool"), ("final_rationale", ".rationale", "str"), ("reviewer_note", ".note", "str")]
    return _page("Phase 7.2C Relation Review", "Check causal overreach, mere topical similarity, relation direction, and bottleneck-shift alternatives.", cards, _download_script("relation", "relation_review_decisions.jsonl", fields))


def _verification_review_page(rows: list[dict[str, Any]], claim_by_id: dict[str, dict[str, Any]], evidence_by_id: dict[str, dict[str, Any]]) -> str:
    cards = []
    for index, queue in enumerate(rows, 1):
        claims = [claim_by_id[row_id] for row_id in queue.get("theme_claim_ids", []) if row_id in claim_by_id]
        evidence_ids = _unique(eid for claim in claims for eid in claim.get("evidence_ids", []))
        evidence = [evidence_by_id[row_id] for row_id in evidence_ids if row_id in evidence_by_id]
        row = {"schema_version": SCHEMA_VERSION, "queue_id": queue["queue_id"], "decision": "", "corrected_value": "", "checked_evidence_ids": evidence_ids, "verification_note": "", "reviewer": "", "reviewed_at": ""}
        cards.append(
            f'<article class="card pending" data-row="{html.escape(json.dumps(row, ensure_ascii=False), quote=True)}"><h2>{index}. {html.escape(queue["queue_id"])}</h2>'
            f'<p class="risk">Risks: {html.escape(", ".join(queue.get("reasons", [])))} · conclusion impact: {html.escape(queue.get("conclusion_impact", ""))}</p>'
            + (f'<p><strong>Verification question:</strong> {html.escape(queue["verification_question"])}</p>' if queue.get("verification_question") else '') +
            '<p><strong>Theme claims:</strong> ' + html.escape(" | ".join(row["statement"] for row in claims)) + '</p><div class="evidence">' + html.escape("\n\n".join(str(row.get("source_text") or "") for row in evidence)) + '</div>'
            '<div class="form">' + _select_html("decision", sorted(VERIFICATION_DECISIONS), class_name="decision") +
            '<label>corrected value/wording<input class="corrected"></label><label class="wide">verification note<textarea class="note"></textarea></label></div></article>'
        )
    fields = [("decision", ".decision", "str"), ("corrected_value", ".corrected", "str"), ("verification_note", ".note", "str")]
    return _page("Phase 7.2C P0 Verification", "Verify only conclusion-changing P0 numeric, negation, entity, attribution, software-scarcity, small-team, testing, and regulation claims.", cards, _download_script("p0_verification", "p0_verification_decisions.jsonl", fields))


def _decision_templates(theme_dir: Path, claims: list[dict[str, Any]], relations: list[dict[str, Any]], insights: list[dict[str, Any]], p0: list[dict[str, Any]]) -> None:
    _write_jsonl(theme_dir / "theme_claim_review_decisions.template.jsonl", ({"schema_version": SCHEMA_VERSION, "record_type": "theme_claim", "theme_claim_id": row["theme_claim_id"], "decision": "", "final_statement": row["statement"], "merge_into": "", "split_statements": [], "entailment_status": "", "speaker_attribution_correct": None, "conditions_preserved": None, "claim_scope_valid": None, "support_independence_sufficient": None, "epistemic_status": "", "verification_risks": [], "reviewer_note": "", "reviewer": "", "reviewed_at": ""} for row in claims))
    _write_jsonl(theme_dir / "relation_review_decisions.template.jsonl", ({"schema_version": SCHEMA_VERSION, "record_type": "relation", "relation_id": row["relation_id"], "decision": "", "final_relation_type": row["relation_type"], "direction_correct": None, "final_rationale": row["rationale"], "reviewer_note": "", "reviewer": "", "reviewed_at": ""} for row in relations))
    _write_jsonl(theme_dir / "insight_review_decisions.template.jsonl", ({"schema_version": SCHEMA_VERSION, "record_type": "insight", "insight_id": row["insight_id"], "decision": "", "final_statement": row["statement"], "split_statements": [], "insight_type": row["insight_type"], "epistemic_status": "", "support_scope": "", "conditions_preserved": None, "causal_chain_valid": None, "independent_support_sufficient": None, "verification_required": None, "reviewer_note": "", "reviewer": "", "reviewed_at": ""} for row in insights))
    _write_jsonl(theme_dir / "p0_verification_decisions.template.jsonl", ({"schema_version": SCHEMA_VERSION, "record_type": "p0_verification", "queue_id": row["queue_id"], "decision": "", "corrected_value": "", "checked_evidence_ids": [], "verification_note": "", "reviewer": "", "reviewed_at": ""} for row in p0))


def _p0_scope(verification: list[dict[str, Any]], claims: list[dict[str, Any]], insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retain upstream P0 and add explicit conclusion-changing epistemic checks."""
    rows = [dict(row) for row in verification if row.get("priority") == "P0"]
    claim_by_suffix = {row["theme_claim_id"].split(".")[-1]: row for row in claims}
    judgment_claim = claim_by_suffix.get("claim_008_judgment_and_taste")
    if judgment_claim and not any(judgment_claim["theme_claim_id"] in row.get("theme_claim_ids", []) for row in rows):
        rows.append({
            "schema_version": SCHEMA_VERSION,
            "queue_id": "verify.phase72c.ai_judgment_taste_creativity_scope",
            "priority": "P0",
            "conclusion_impact": "high",
            "reasons": ["negation", "epistemic_scope", "speaker_attribution"],
            "theme_claim_ids": [judgment_claim["theme_claim_id"]],
            "insight_ids": [row["insight_id"] for row in insights if judgment_claim["theme_claim_id"] in row.get("supporting_theme_claim_ids", [])],
            "status": "pending",
            "review_status": "pending",
            "theme_slug": THEME_SLUG,
            "verification_question": "Does the official evidence support the bounded current-observation claim, or does it overstate that AI categorically lacks judgment, taste, or creativity?",
        })
    return sorted(rows, key=lambda row: row["queue_id"])


def prepare_phase72c_theme(*, theme_dir: Path, corpus_dir: Path) -> dict[str, Any]:
    """Enrich frozen Phase 7.2B records and generate the four human review packages."""
    before = _tree_hashes(corpus_dir)
    claims = _read_jsonl(theme_dir / "theme_canonical_claims.jsonl")
    relations = _read_jsonl(theme_dir / "theme_claim_relations.jsonl")
    insights = _read_jsonl(theme_dir / "insight_candidates.jsonl")
    verification = _read_jsonl(theme_dir / "verification_queue.jsonl")
    source_claims = _read_jsonl(corpus_dir / "intelligence/source_claims.jsonl")
    evidence = _read_jsonl(corpus_dir / "canonical/evidence.jsonl")
    source_claim_by_id = {row["claim_id"]: row for row in source_claims}
    evidence_by_id = {row["evidence_id"]: row for row in evidence}
    enriched_claims = [{**row, **_claim_independence(row, source_claim_by_id, evidence_by_id)} for row in claims]
    claim_by_id = {row["theme_claim_id"]: row for row in enriched_claims}
    enriched_insights = [{**row, **_insight_independence(row, claim_by_id)} for row in insights]
    p0 = _p0_scope(verification, enriched_claims, enriched_insights)
    _write_jsonl(theme_dir / "theme_canonical_claims.jsonl", enriched_claims)
    _write_jsonl(theme_dir / "insight_candidates.jsonl", enriched_insights)
    _decision_templates(theme_dir, enriched_claims, relations, enriched_insights, p0)
    views = theme_dir / "views"
    views.mkdir(parents=True, exist_ok=True)
    (views / "theme_claim_review.html").write_text(_claim_review_page(enriched_claims, source_claim_by_id, evidence_by_id), encoding="utf-8")
    (views / "theme_insight_review.html").write_text(_insight_review_page(enriched_insights, claim_by_id, evidence_by_id), encoding="utf-8")
    (views / "theme_relation_review.html").write_text(_relation_review_page(relations, claim_by_id), encoding="utf-8")
    (views / "p0_verification_review.html").write_text(_verification_review_page(p0, claim_by_id, evidence_by_id), encoding="utf-8")
    reports = theme_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    distribution = {
        "publication_families": dict(sorted(Counter(row["independent_publication_family_count"] for row in enriched_claims).items())),
        "speakers": dict(sorted(Counter(row["independent_speaker_count"] for row in enriched_claims).items())),
        "organizations": dict(sorted(Counter(row["independent_organization_count"] for row in enriched_claims).items())),
        "domains": dict(sorted(Counter(row["independent_domain_count"] for row in enriched_claims).items())),
        "evidence_types": dict(sorted(Counter(row["independent_evidence_type_count"] for row in enriched_claims).items())),
    }
    (reports / "evidence_independence_report.md").write_text(
        "# Evidence Independence Report\n\nStatus: **pre-review deterministic inventory**\n\n"
        "Two publication families do not automatically constitute two independent industry observations. Counts below distinguish publication, speaker, organization, domain, and evidence-type diversity.\n\n```json\n"
        + json.dumps(distribution, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
    (reports / "human_gate_report.md").write_text(
        f"# Phase 7.2C Human Gate Report\n\nStatus: **pending human review**\n\n- theme claims awaiting decisions: {len(enriched_claims)}\n- relations awaiting decisions: {len(relations)}\n- insights awaiting decisions: {len(enriched_insights)}\n- P0 verification items awaiting decisions: {len(p0)}\n- accepted assets: 0\n- theme judgment frozen: no\n- publication drafts generated: no\n\nPending records are not accepted automatically.\n", encoding="utf-8")
    (reports / "publication_readiness_report.md").write_text(
        "# Publication Readiness Report\n\nRating: **BLOCKED — human gate incomplete**\n\nThe corpus package is ready for review, but publication candidates must not be generated until all 30 theme claims, 10 relations, 7 insights, and conclusion-changing P0 items have explicit human decisions.\n", encoding="utf-8")
    after = _tree_hashes(corpus_dir)
    if before != after:
        raise ValueError("Phase 7.2C preparation modified frozen Phase 7.2A corpus")
    return {"status": "pending_human_review", "theme_claim_count": len(enriched_claims), "relation_count": len(relations), "insight_count": len(enriched_insights), "p0_verification_count": len(p0), "phase72a_input_unchanged": True, "theme_dir": str(theme_dir)}


def _validate_complete(rows: list[dict[str, Any]], expected: set[str], id_key: str, allowed: set[str], kind: str) -> dict[str, dict[str, Any]]:
    ids = [str(row.get(id_key) or "") for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{kind} decisions contain duplicate {id_key}")
    missing, extra = sorted(expected - set(ids)), sorted(set(ids) - expected)
    if missing or extra:
        raise ValueError(f"{kind} human gate requires exact record set; missing={len(missing)} extra={len(extra)}")
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        record_id = str(row[id_key])
        decision = str(row.get("decision") or "")
        if decision not in allowed:
            raise ValueError(f"{kind} decision is missing or invalid for {record_id}: {decision!r}")
        if not str(row.get("reviewer") or "").strip() or not str(row.get("reviewed_at") or "").strip():
            raise ValueError(f"{kind} decision lacks reviewer/reviewed_at for {record_id}")
        output[record_id] = row
    return output


def _accepted_claims(claims: list[dict[str, Any]], decisions: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, list[str]]]:
    accepted, rejected, merges = [], [], []
    mapping: dict[str, list[str]] = {}
    by_id = {row["theme_claim_id"]: row for row in claims}
    for claim in claims:
        decision = decisions[claim["theme_claim_id"]]
        action = decision["decision"]
        final_statement = str(decision.get("final_statement") or "").strip()
        if action in {"accept", "edit"}:
            if decision.get("entailment_status") not in {"fully_supported", "supported_with_missing_condition", "partially_supported"}:
                raise ValueError(f"accepted claim needs supported entailment_status: {claim['theme_claim_id']}")
            if decision.get("epistemic_status") not in EPISTEMIC_STATUSES:
                raise ValueError(f"accepted claim needs epistemic_status: {claim['theme_claim_id']}")
            for field in ("speaker_attribution_correct", "conditions_preserved", "claim_scope_valid", "support_independence_sufficient"):
                if decision.get(field) is not True:
                    raise ValueError(f"accepted claim requires {field}=true: {claim['theme_claim_id']}")
            if not final_statement:
                raise ValueError(f"accepted claim lacks final_statement: {claim['theme_claim_id']}")
            accepted_id = claim["theme_claim_id"]
            accepted.append({**claim, "schema_version": SCHEMA_VERSION, "statement": final_statement, "review_status": "accepted", "epistemic_status": decision.get("epistemic_status"), "human_review": decision})
            mapping[claim["theme_claim_id"]] = [accepted_id]
        elif action == "split":
            if decision.get("entailment_status") not in {"fully_supported", "supported_with_missing_condition", "partially_supported"} or decision.get("epistemic_status") not in EPISTEMIC_STATUSES:
                raise ValueError(f"split claim needs supported entailment and epistemic status: {claim['theme_claim_id']}")
            for field in ("speaker_attribution_correct", "conditions_preserved", "claim_scope_valid", "support_independence_sufficient"):
                if decision.get(field) is not True:
                    raise ValueError(f"split claim requires {field}=true: {claim['theme_claim_id']}")
            statements = [str(row).strip() for row in decision.get("split_statements", []) if str(row).strip()]
            if len(statements) < 2:
                raise ValueError(f"split claim needs at least two statements: {claim['theme_claim_id']}")
            mapping[claim["theme_claim_id"]] = []
            for index, statement in enumerate(statements, 1):
                accepted_id = f"{claim['theme_claim_id']}.split_{index:02d}"
                accepted.append({**claim, "schema_version": SCHEMA_VERSION, "theme_claim_id": accepted_id, "statement": statement, "review_status": "accepted", "split_from": claim["theme_claim_id"], "epistemic_status": decision.get("epistemic_status"), "human_review": decision})
                mapping[claim["theme_claim_id"]].append(accepted_id)
        elif action == "merge":
            target = str(decision.get("merge_into") or "")
            if not target or target not in by_id:
                raise ValueError(f"merge claim needs valid merge_into: {claim['theme_claim_id']}")
            mapping[claim["theme_claim_id"]] = [target]
            merges.append({"schema_version": SCHEMA_VERSION, "source_theme_claim_id": claim["theme_claim_id"], "target_theme_claim_id": target, "reviewer": decision["reviewer"], "reviewed_at": decision["reviewed_at"], "reviewer_note": decision.get("reviewer_note", "")})
        else:
            mapping[claim["theme_claim_id"]] = []
            rejected.append({**claim, "schema_version": SCHEMA_VERSION, "review_status": action, "human_review": decision})
    accepted_ids = {row["theme_claim_id"] for row in accepted}
    accepted_by_id = {row["theme_claim_id"]: row for row in accepted}
    for merge in merges:
        if merge["target_theme_claim_id"] not in accepted_ids:
            raise ValueError(f"merge target is not accepted/edited: {merge['target_theme_claim_id']}")
        source = by_id[merge["source_theme_claim_id"]]
        target = accepted_by_id[merge["target_theme_claim_id"]]
        for field in ("parent_source_claim_ids", "parent_canonical_claim_ids", "evidence_ids", "speakers", "source_ids", "source_family_ids", "conditions", "limitations", "counter_claim_ids", "independent_speakers", "independent_organizations", "independent_domains", "evidence_types"):
            target[field] = _unique([*target.get(field, []), *source.get(field, [])])
        target["merged_from_theme_claim_ids"] = _unique([*target.get("merged_from_theme_claim_ids", []), source["theme_claim_id"]])
        target["first_seen_at"] = min(str(target.get("first_seen_at") or "9999-12-31"), str(source.get("first_seen_at") or "9999-12-31"))
        target["last_seen_at"] = max(str(target.get("last_seen_at") or "0000-01-01"), str(source.get("last_seen_at") or "0000-01-01"))
        target["independent_source_family_count"] = len(target["source_family_ids"])
        target["independent_publication_family_count"] = len(target["source_family_ids"])
        target["independent_speaker_count"] = len(target["independent_speakers"])
        target["independent_organization_count"] = len(target["independent_organizations"])
        target["independent_domain_count"] = len(target["independent_domains"])
        target["independent_evidence_type_count"] = len(target["evidence_types"])
    return sorted(accepted, key=lambda row: row["theme_claim_id"]), rejected, merges, mapping


def _accepted_relations(relations: list[dict[str, Any]], decisions: dict[str, dict[str, Any]], claim_mapping: dict[str, list[str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted, rejected = [], []
    for relation in relations:
        decision = decisions[relation["relation_id"]]
        if decision["decision"] == "reject":
            rejected.append({**relation, "schema_version": SCHEMA_VERSION, "review_status": "rejected", "human_review": decision})
            continue
        relation_type = str(decision.get("final_relation_type") or "")
        if relation_type not in RELATION_TYPES:
            raise ValueError(f"invalid final relation type for {relation['relation_id']}: {relation_type}")
        if decision.get("direction_correct") not in {True, False}:
            raise ValueError(f"accepted relation needs direction review: {relation['relation_id']}")
        source_ids = claim_mapping.get(relation["source_claim_id"], [])
        target_ids = claim_mapping.get(relation["target_claim_id"], [])
        if not source_ids or not target_ids:
            rejected.append({**relation, "schema_version": SCHEMA_VERSION, "review_status": "rejected_parent_claim", "human_review": decision})
            continue
        source_id, target_id = source_ids[0], target_ids[0]
        if decision.get("direction_correct") is False:
            source_id, target_id = target_id, source_id
        accepted.append({**relation, "schema_version": SCHEMA_VERSION, "relation_type": relation_type, "source_claim_id": source_id, "target_claim_id": target_id, "rationale": str(decision.get("final_rationale") or relation["rationale"]), "review_status": "accepted", "human_review": decision})
    return accepted, rejected


def _accepted_insights(insights: list[dict[str, Any]], decisions: dict[str, dict[str, Any]], claim_mapping: dict[str, list[str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted, rejected = [], []
    for insight in insights:
        decision = decisions[insight["insight_id"]]
        action = decision["decision"]
        if action in {"reject", "defer_for_more_evidence"}:
            rejected.append({**insight, "schema_version": SCHEMA_VERSION, "review_status": action, "human_review": decision})
            continue
        if decision.get("epistemic_status") not in EPISTEMIC_STATUSES:
            raise ValueError(f"accepted insight needs epistemic_status: {insight['insight_id']}")
        if not str(decision.get("support_scope") or "").strip():
            raise ValueError(f"accepted insight needs support_scope: {insight['insight_id']}")
        for field in ("conditions_preserved", "causal_chain_valid", "independent_support_sufficient", "verification_required"):
            if decision.get(field) not in {True, False}:
                raise ValueError(f"accepted insight needs {field}: {insight['insight_id']}")
        supporting = _unique(accepted_id for original in insight.get("supporting_theme_claim_ids", []) for accepted_id in claim_mapping.get(original, []))
        if len(supporting) < 2:
            raise ValueError(f"accepted insight lacks two accepted supporting claims: {insight['insight_id']}")
        statements = [str(decision.get("final_statement") or "").strip()]
        if action == "split":
            statements = [str(row).strip() for row in decision.get("split_statements", []) if str(row).strip()]
            if len(statements) < 2:
                raise ValueError(f"split insight needs at least two statements: {insight['insight_id']}")
        for index, statement in enumerate(statements, 1):
            if not statement:
                raise ValueError(f"accepted insight lacks final_statement: {insight['insight_id']}")
            insight_id = insight["insight_id"] if action != "split" else f"{insight['insight_id']}.split_{index:02d}"
            accepted.append({**insight, "schema_version": SCHEMA_VERSION, "insight_id": insight_id, "statement": statement, "insight_type": decision.get("insight_type") or insight["insight_type"], "supporting_theme_claim_ids": supporting, "epistemic_status": decision.get("epistemic_status"), "support_scope": decision.get("support_scope"), "review_status": "accepted", "publishability": "publication_candidate_only", "human_review": decision})
    return accepted, rejected


def _write_publication_candidates(theme_dir: Path, claims: list[dict[str, Any]], insights: list[dict[str, Any]]) -> None:
    reports = theme_dir / "reports"
    claim_lines = "\n".join(f'- {row["statement"]} (`{row["theme_claim_id"]}`)' for row in claims)
    insight_lines = "\n".join(f'- {row["statement"]} (`{row["insight_id"]}`)' for row in insights)
    caveat = "本批Naval及嘉宾语料共同指向一个值得进一步验证的判断："
    website = f"# AI执行商品化与判断稀缺性\n\n{caveat}\n\n## 已审核洞见\n\n{insight_lines}\n\n## 已审核主题观点\n\n{claim_lines}\n\n> Publication candidate only. No automatic publication.\n"
    (reports / "website_topic_draft.md").write_text(website, encoding="utf-8")
    (reports / "wechat_article_draft.md").write_text(f"# 当执行能力变便宜，什么会变得更贵？\n\n{caveat}\n\n{insight_lines}\n\n## 证据边界\n\n本文只使用已通过人工质量门的主题观点；它不把同一场对谈的重复页面视为独立行业证据，也不把系统综合判断伪装成人物原话。\n", encoding="utf-8")
    _write_jsonl(reports / "xiaohongshu_slices.jsonl", ({"schema_version": SCHEMA_VERSION, "slice_id": f"{THEME_SLUG}.slice_{index:02d}", "title": "执行变便宜后，判断为什么更稀缺？", "body": row["statement"], "supporting_insight_id": row["insight_id"], "status": "publication_candidate_only"} for index, row in enumerate(insights, 1)))


def finalize_phase72c_theme(
    *, theme_dir: Path, corpus_dir: Path, claim_decisions_path: Path, relation_decisions_path: Path,
    insight_decisions_path: Path, verification_decisions_path: Path,
) -> dict[str, Any]:
    """Strictly freeze accepted assets after complete human review and P0 verification."""
    before = _tree_hashes(corpus_dir)
    claims = _read_jsonl(theme_dir / "theme_canonical_claims.jsonl")
    relations = _read_jsonl(theme_dir / "theme_claim_relations.jsonl")
    insights = _read_jsonl(theme_dir / "insight_candidates.jsonl")
    p0 = _p0_scope(_read_jsonl(theme_dir / "verification_queue.jsonl"), claims, insights)
    claim_decisions = _validate_complete(_read_jsonl(claim_decisions_path), {row["theme_claim_id"] for row in claims}, "theme_claim_id", CLAIM_DECISIONS, "theme claim")
    relation_decisions = _validate_complete(_read_jsonl(relation_decisions_path), {row["relation_id"] for row in relations}, "relation_id", RELATION_DECISIONS, "relation")
    insight_decisions = _validate_complete(_read_jsonl(insight_decisions_path), {row["insight_id"] for row in insights}, "insight_id", INSIGHT_DECISIONS, "insight")
    verification_decisions = _validate_complete(_read_jsonl(verification_decisions_path), {row["queue_id"] for row in p0}, "queue_id", VERIFICATION_DECISIONS, "P0 verification")
    for queue_id, decision in verification_decisions.items():
        if not str(decision.get("verification_note") or "").strip():
            raise ValueError(f"P0 verification needs a verification_note: {queue_id}")
        if decision["decision"] == "corrected" and not str(decision.get("corrected_value") or "").strip():
            raise ValueError(f"corrected P0 verification needs corrected_value: {queue_id}")
    accepted_claims, rejected_claims, merges, claim_mapping = _accepted_claims(claims, claim_decisions)
    accepted_relations, rejected_relations = _accepted_relations(relations, relation_decisions, claim_mapping)
    accepted_insights, rejected_insights = _accepted_insights(insights, insight_decisions, claim_mapping)
    unresolved_p0 = [row_id for row_id, row in verification_decisions.items() if row["decision"] == "defer_for_external_check"]
    if unresolved_p0:
        raise ValueError(f"P0 verification is not complete; deferred={len(unresolved_p0)}")
    p0_by_id = {row["queue_id"]: row for row in p0}
    for queue_id, decision in verification_decisions.items():
        if decision["decision"] != "rejected":
            continue
        accepted_affected = [accepted_id for original_id in p0_by_id[queue_id].get("theme_claim_ids", []) for accepted_id in claim_mapping.get(original_id, [])]
        if accepted_affected:
            raise ValueError(f"P0 verification rejected evidence for accepted claims: {queue_id} -> {accepted_affected}")
    if not accepted_claims or not accepted_insights:
        raise ValueError("human gate cannot freeze without at least one accepted claim and insight")
    _write_jsonl(theme_dir / "theme_claim_review_decisions.jsonl", claim_decisions.values())
    _write_jsonl(theme_dir / "relation_review_decisions.jsonl", relation_decisions.values())
    _write_jsonl(theme_dir / "insight_review_decisions.jsonl", insight_decisions.values())
    _write_jsonl(theme_dir / "p0_verification_decisions.jsonl", verification_decisions.values())
    _write_jsonl(theme_dir / "accepted_theme_claims.jsonl", accepted_claims)
    _write_jsonl(theme_dir / "rejected_theme_claims.jsonl", rejected_claims)
    _write_jsonl(theme_dir / "theme_claim_merges.jsonl", merges)
    _write_jsonl(theme_dir / "accepted_relations.jsonl", accepted_relations)
    _write_jsonl(theme_dir / "rejected_relations.jsonl", rejected_relations)
    _write_jsonl(theme_dir / "accepted_insights.jsonl", accepted_insights)
    _write_jsonl(theme_dir / "rejected_insights.jsonl", rejected_insights)
    manifest = json.loads((theme_dir / "source_manifest.json").read_text(encoding="utf-8"))
    frozen_at = _now()
    judgment = {
        "schema_version": SCHEMA_VERSION,
        "theme_slug": THEME_SLUG,
        "judgment_version": "theme_judgment_v1",
        "status": "human_reviewed_publication_candidate",
        "frozen_at": frozen_at,
        "corpus_snapshot": {"source_corpus": "input/corpora/naval_recent_six", "input_files": manifest.get("input_files", {})},
        "calibrated_statement": "本批Naval及嘉宾语料共同指向一个值得进一步验证的判断：AI降低部分执行成本时，问题选择、架构、验证、现实约束与责任的相对重要性可能上升。",
        "accepted_claim_ids": [row["theme_claim_id"] for row in accepted_claims],
        "accepted_insight_ids": [row["insight_id"] for row in accepted_insights],
        "accepted_relation_ids": [row["relation_id"] for row in accepted_relations],
        "unresolved_tensions": [row["statement"] for row in accepted_insights if row.get("insight_type") == "unresolved_tension"],
        "confidence": "provisional_human_reviewed",
        "evidence_scope": "Six fixed Naval pages; two transcript-bearing publication families; repeated pages are deweighted; no external corroboration.",
        "known_limitations": ["Publication-family diversity is not independent industry validation.", "Most industrial mechanisms originate from one Frontier Founders conversation.", "Live in the Future has no official transcript and supplies no claim support."],
        "predictions_expected_observations": ["If the judgment is robust, later independent sources should report rising verification, architecture, regulatory, or accountability effort as generation costs fall."],
        "conditions_that_would_weaken_or_overturn": ["Independent evidence shows execution cost declines without increased verification or judgment burden.", "Productivity gains are evenly distributed regardless of domain judgment.", "Software scarcity remains the dominant constraint despite abundant generation."],
    }
    (theme_dir / "theme_judgment_v1.json").write_text(json.dumps(judgment, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    revision_path = theme_dir / "revision_history.jsonl"
    revisions = _read_jsonl(revision_path)
    revisions.append({"schema_version": SCHEMA_VERSION, "revision_id": f"{THEME_SLUG}.revision_{len(revisions)+1:03d}", "created_at": frozen_at, "operation": "phase_7_2c_human_gate_freeze", "accepted_claim_count": len(accepted_claims), "accepted_relation_count": len(accepted_relations), "accepted_insight_count": len(accepted_insights), "review_status": "human_reviewed"})
    _write_jsonl(revision_path, revisions)
    reports = theme_dir / "reports"
    reports.mkdir(exist_ok=True)
    insight_lines = "\n".join(f'- {row["statement"]} (`{row["insight_id"]}`)' for row in accepted_insights)
    (reports / "current_judgment_v1.md").write_text(f'# Current Judgment v1\n\n> {judgment["calibrated_statement"]}\n\n## Accepted insights\n\n{insight_lines}\n\n## Evidence scope\n\n{judgment["evidence_scope"]}\n\n## What would weaken it\n\n' + "\n".join(f'- {row}' for row in judgment["conditions_that_would_weaken_or_overturn"]) + "\n", encoding="utf-8")
    decision_counts = Counter(row["decision"] for row in claim_decisions.values())
    relation_counts = Counter(row["decision"] for row in relation_decisions.values())
    insight_counts = Counter(row["decision"] for row in insight_decisions.values())
    (reports / "human_gate_report.md").write_text("# Phase 7.2C Human Gate Report\n\nStatus: **passed**\n\n```json\n" + json.dumps({"claim_decisions": decision_counts, "relation_decisions": relation_counts, "insight_decisions": insight_counts, "accepted_theme_claim_count": len(accepted_claims), "accepted_relation_count": len(accepted_relations), "accepted_insight_count": len(accepted_insights), "p0_verified_count": len(verification_decisions)}, ensure_ascii=False, indent=2, default=dict) + "\n```\n", encoding="utf-8")
    (reports / "publication_readiness_report.md").write_text("# Publication Readiness Report\n\nRating: **candidate ready for editorial review; not published**\n\nAll machine-pending assets used by the drafts passed explicit human decisions and conclusion-changing P0 verification. Editorial fact-checking and final source-link review remain required.\n", encoding="utf-8")
    _write_publication_candidates(theme_dir, accepted_claims, accepted_insights)
    if before != _tree_hashes(corpus_dir):
        raise ValueError("Phase 7.2C finalization modified frozen Phase 7.2A corpus")
    return {"status": "frozen", "accepted_theme_claim_count": len(accepted_claims), "rejected_theme_claim_count": len(rejected_claims), "theme_claim_merge_count": len(merges), "accepted_relation_count": len(accepted_relations), "rejected_relation_count": len(rejected_relations), "accepted_insight_count": len(accepted_insights), "rejected_or_deferred_insight_count": len(rejected_insights), "p0_verified_count": len(verification_decisions), "publication_readiness": "candidate_ready_for_editorial_review", "theme_judgment": str(theme_dir / "theme_judgment_v1.json")}

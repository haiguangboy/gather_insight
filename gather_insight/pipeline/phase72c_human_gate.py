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
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .review_sync import sync_review_bundle


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
    "verified", "corrected", "rejected", "not_applicable",
}
SOURCE_FIDELITY_STATUSES = {"pending", "verified", "corrected", "rejected", "not_applicable"}
EXTERNAL_FACT_STATUSES = {"not_required", "not_checked", "verified", "contradicted", "insufficient_evidence"}
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


def _sync_phase72c_review(theme_dir: Path, review_sync_root: Path | None, *, gate: str) -> Path:
    relative_files = [
        ("views/theme_claim_review.html", "views/theme_claim_review.html"),
        ("views/theme_insight_review.html", "views/theme_insight_review.html"),
        ("views/theme_relation_review.html", "views/theme_relation_review.html"),
        ("views/p0_verification_review.html", "views/p0_verification_review.html"),
        ("theme_claim_review_decisions.template.jsonl", "templates/theme_claim_review_decisions.template.jsonl"),
        ("insight_review_decisions.template.jsonl", "templates/insight_review_decisions.template.jsonl"),
        ("relation_review_decisions.template.jsonl", "templates/relation_review_decisions.template.jsonl"),
        ("p0_verification_decisions.template.jsonl", "templates/p0_verification_decisions.template.jsonl"),
        ("claim_local_p0_verification_queue.jsonl", "data/claim_local_p0_verification_queue.jsonl"),
        ("active_p0_verification_queue.jsonl", "data/active_p0_verification_queue.jsonl"),
        ("external_verification_queue.jsonl", "data/external_verification_queue.jsonl"),
        ("reports/human_gate_report.md", "reports/human_gate_report.md"),
        ("reports/publication_readiness_report.md", "reports/publication_readiness_report.md"),
        ("reports/evidence_independence_report.md", "reports/evidence_independence_report.md"),
    ]
    return sync_review_bundle(
        bundle_slug="phase_7_2c_1_naval_theme_gate",
        files=[(theme_dir / source, target) for source, target in relative_files],
        root=review_sync_root,
        title=f"Phase 7.2C.1 Naval Theme Gate — {gate}",
    )


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


def _highlight(text: str, token: str) -> str:
    escaped = html.escape(text)
    if not token:
        return escaped
    return re.sub(re.escape(html.escape(token)), lambda match: f'<mark>{match.group(0)}</mark>', escaped, flags=re.IGNORECASE)


def _highlight_tokens(text: str, tokens: list[str]) -> str:
    output = html.escape(text)
    escaped_tokens = [re.escape(html.escape(token)) for token in sorted({token for token in tokens if token}, key=len, reverse=True)]
    if not escaped_tokens:
        return output
    return re.sub("|".join(escaped_tokens), lambda match: f'<mark>{match.group(0)}</mark>', output, flags=re.IGNORECASE)


def _verification_review_page(rows: list[dict[str, Any]], claim_by_id: dict[str, dict[str, Any]], evidence_by_id: dict[str, dict[str, Any]], *, active: bool) -> str:
    cards = []
    for index, queue in enumerate(rows, 1):
        claims = [claim_by_id[row_id] for row_id in queue.get("theme_claim_ids", []) if row_id in claim_by_id]
        evidence_ids = list(queue.get("risk_evidence_ids", []))
        evidence = [evidence_by_id[row_id] for row_id in evidence_ids if row_id in evidence_by_id]
        row = {"schema_version": SCHEMA_VERSION, "queue_id": queue["queue_id"], "source_fidelity_status": "pending", "external_fact_status": queue.get("external_fact_status", "not_checked"), "corrected_value": "", "checked_evidence_ids": evidence_ids, "verification_note": "", "reviewer": "", "reviewed_at": ""}
        direct = queue.get("direct_support_excerpt", [])[:3]
        context = queue.get("local_context", {})
        metadata = queue.get("source_metadata", {})
        tokens = list(queue.get("risk_tokens") or [queue.get("risk_token", "")])
        cards.append(
            f'<article class="card pending" data-row="{html.escape(json.dumps(row, ensure_ascii=False), quote=True)}"><h2>{index}. {html.escape(queue["queue_id"])}</h2>'
            f'<p class="risk">Risk: {html.escape(queue.get("risk_type", ""))} · token: <mark>{html.escape(queue.get("risk_token", ""))}</mark> · conclusion impact: {html.escape(queue.get("conclusion_impact", ""))}</p>'
            f'<p><strong>Why conclusion-changing:</strong> {html.escape(queue.get("why_conclusion_changing", ""))}</p>'
            + (f'<p><strong>Verification question:</strong> {html.escape(queue["verification_question"])}</p>' if queue.get("verification_question") else '') +
            '<p><strong>Theme claim:</strong> ' + html.escape(" | ".join(row["statement"] for row in claims)) + '</p>'
            f'<p><strong>Speaker/source/date:</strong> {html.escape(str(metadata.get("speaker") or "unknown"))} · {html.escape(str(metadata.get("source_title") or metadata.get("source_id") or ""))} · {html.escape(str(metadata.get("published_at") or ""))}</p>'
            '<h3>Direct supporting excerpt</h3><div class="evidence">' + "<br><br>".join(_highlight_tokens(str(text), tokens) for text in direct) + '</div>'
            '<h3>Adjacent-turn context</h3><div class="evidence"><strong>Previous:</strong> ' + html.escape(str(context.get("previous_turn") or "not available")) + '<br><br><strong>Current:</strong> ' + _highlight_tokens(str(context.get("current_turn") or ""), tokens) + '<br><br><strong>Next:</strong> ' + html.escape(str(context.get("next_turn") or "not available")) + '</div>'
            '<details><summary>Full linked evidence and section</summary><div class="evidence">' + html.escape("\n\n".join(str(row.get("source_text") or "") for row in evidence)) + '</div></details>'
            '<div class="form">' + _select_html("source fidelity status", ["pending", "verified", "corrected", "rejected", "not_applicable"], class_name="source", blank=False, selected="pending") +
            _select_html("external fact status", ["not_required", "not_checked", "verified", "contradicted", "insufficient_evidence"], class_name="external", blank=False, selected=str(queue.get("external_fact_status", "not_checked"))) +
            '<label>corrected value/wording<input class="corrected"></label><label class="wide">verification note<textarea class="note"></textarea></label></div></article>'
        )
    fields = [("source_fidelity_status", ".source", "str"), ("external_fact_status", ".external", "str"), ("corrected_value", ".corrected", "str"), ("verification_note", ".note", "str")]
    title = "Phase 7.2C Active P0 Verification" if active else "Phase 7.2C Claim-local P0 Preview"
    summary = "Gate B verifies source fidelity separately from external factual support. Only claim-local risk spans are shown by default." if active else "Preview only. Complete Gate A first; rejected or rewritten claims will be removed before this queue becomes active."
    return _page(title, summary, cards, _download_script("p0_verification", "p0_verification_decisions.jsonl", fields))


def _decision_templates(theme_dir: Path, claims: list[dict[str, Any]], relations: list[dict[str, Any]], insights: list[dict[str, Any]], p0: list[dict[str, Any]]) -> None:
    _write_jsonl(theme_dir / "theme_claim_review_decisions.template.jsonl", ({"schema_version": SCHEMA_VERSION, "record_type": "theme_claim", "theme_claim_id": row["theme_claim_id"], "decision": "", "final_statement": row["statement"], "merge_into": "", "split_statements": [], "entailment_status": "", "speaker_attribution_correct": None, "conditions_preserved": None, "claim_scope_valid": None, "support_independence_sufficient": None, "epistemic_status": "", "verification_risks": [], "reviewer_note": "", "reviewer": "", "reviewed_at": ""} for row in claims))
    _write_jsonl(theme_dir / "relation_review_decisions.template.jsonl", ({"schema_version": SCHEMA_VERSION, "record_type": "relation", "relation_id": row["relation_id"], "decision": "", "final_relation_type": row["relation_type"], "direction_correct": None, "final_rationale": row["rationale"], "reviewer_note": "", "reviewer": "", "reviewed_at": ""} for row in relations))
    _write_jsonl(theme_dir / "insight_review_decisions.template.jsonl", ({"schema_version": SCHEMA_VERSION, "record_type": "insight", "insight_id": row["insight_id"], "decision": "", "final_statement": row["statement"], "split_statements": [], "insight_type": row["insight_type"], "epistemic_status": "", "support_scope": "", "conditions_preserved": None, "causal_chain_valid": None, "independent_support_sufficient": None, "verification_required": None, "reviewer_note": "", "reviewer": "", "reviewed_at": ""} for row in insights))
    _write_p0_template(theme_dir, p0)


def _write_p0_template(theme_dir: Path, p0: list[dict[str, Any]]) -> None:
    _write_jsonl(theme_dir / "p0_verification_decisions.template.jsonl", ({"schema_version": SCHEMA_VERSION, "record_type": "p0_verification", "queue_id": row["queue_id"], "source_fidelity_status": "pending", "external_fact_status": row.get("external_fact_status", "not_checked"), "corrected_value": "", "checked_evidence_ids": row.get("risk_evidence_ids", []), "verification_note": "", "reviewer": "", "reviewed_at": ""} for row in p0))


_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?:%|x)?(?!\w)", re.IGNORECASE)
_POLARITY_TERMS = ("not", "no", "never", "without", "lack", "cannot", "can't", "declin", "decreas", "reduc", "less", "scarcity", "abundan")


def _sentences(text: str) -> list[str]:
    return [row.strip() for row in re.split(r"(?<=[.!?])\s+|\n+", text) if row.strip()]


def _local_context(source_claim: dict[str, Any], sections_by_id: dict[str, dict[str, Any]], ordered_sections: dict[str, list[dict[str, Any]]]) -> tuple[dict[str, str], dict[str, str]]:
    section_ids = source_claim.get("source_section_ids", [])
    section = next((sections_by_id[row_id] for row_id in section_ids if row_id in sections_by_id), None)
    if not section:
        return {}, {"speaker": source_claim.get("speaker", "unknown"), "source_id": source_claim.get("source_id", ""), "published_at": source_claim.get("published_at", "")}
    sequence = ordered_sections.get(section["source_id"], [])
    position = next((index for index, row in enumerate(sequence) if row["section_id"] == section["section_id"]), -1)
    current_text = str(section.get("text") or "")
    needle = str(source_claim.get("claim") or "")
    found = current_text.lower().find(needle.lower()) if needle else -1
    current_excerpt = current_text[max(0, found - 500):found + len(needle) + 500] if found >= 0 else current_text[:1000]
    previous_text = str(sequence[position - 1].get("text") or "") if position > 0 else ""
    next_text = str(sequence[position + 1].get("text") or "") if 0 <= position < len(sequence) - 1 else ""
    context = {
        "previous_turn": previous_text[-600:],
        "current_turn": current_excerpt,
        "next_turn": next_text[:600],
    }
    metadata = {"speaker": section.get("speaker", source_claim.get("speaker", "unknown")), "source_id": section.get("source_id", ""), "source_title": section.get("title", ""), "published_at": section.get("published_at", ""), "source_url": section.get("source_url", "")}
    return context, metadata


def _risk_spans(tokens: list[str], source_claims: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    source_ids, evidence_ids, spans = [], [], []
    for row in source_claims:
        text = str(row.get("claim") or "")
        matches = [match for token in tokens if (match := re.search(re.escape(token), text, re.IGNORECASE))]
        if matches:
            source_ids.append(row["claim_id"])
            for match in matches:
                spans.append({"source_claim_id": row["claim_id"], "char_start": match.start(), "char_end": match.end(), "text": text})
    for row in evidence:
        text = str(row.get("source_text") or "")
        matches = [match for token in tokens if (match := re.search(re.escape(token), text, re.IGNORECASE))]
        if matches:
            evidence_ids.append(row["evidence_id"])
            for match in matches:
                spans.append({"evidence_id": row["evidence_id"], "char_start": match.start(), "char_end": match.end(), "text": text[max(0, match.start()-120):match.end()+120]})
    return _unique(source_ids), _unique(evidence_ids), spans


def _contains_polarity(text: str, term: str) -> bool:
    if term in {"declin", "decreas", "reduc", "abundan"}:
        return term in text.lower()
    if term == "lack":
        return bool(re.search(r"\black\w*\b", text, re.IGNORECASE))
    return bool(re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE))


def _claim_local_p0(
    claims: list[dict[str, Any]], insights: list[dict[str, Any]], source_claim_by_id: dict[str, dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]], sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    insight_claim_ids = {claim_id for row in insights for claim_id in row.get("supporting_theme_claim_ids", [])}
    explicit_core_suffixes = {"claim_008_judgment_and_taste", "claim_019_pure_software_scarcity", "claim_017_small_teams", "claim_018_more_firms_not_less_work", "claim_026_physical_testing", "claim_029_regulatory_bottleneck"}
    sections_by_id = {row["section_id"]: row for row in sections}
    ordered: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sections:
        ordered[row["source_id"]].append(row)
    for rows in ordered.values():
        rows.sort(key=lambda row: row.get("section_order", 0))
    queue: list[dict[str, Any]] = []
    for claim in claims:
        if claim["theme_claim_id"] not in insight_claim_ids and not any(claim["theme_claim_id"].endswith(suffix) for suffix in explicit_core_suffixes):
            continue
        statement = str(claim.get("statement") or "")
        lowered = statement.lower()
        parents = [source_claim_by_id[row_id] for row_id in claim.get("parent_source_claim_ids", []) if row_id in source_claim_by_id]
        evidence = [evidence_by_id[row_id] for row_id in claim.get("evidence_ids", []) if row_id in evidence_by_id]
        risks: list[dict[str, Any]] = []
        statement_numbers = _NUMBER_RE.findall(statement)
        quantitative_paraphrase = bool(re.search(r"orders? of magnitude|\b(times|fold|percent(?:age)?)\b", lowered))
        if statement_numbers or quantitative_paraphrase:
            candidates = statement_numbers or _unique(token for row in parents for token in _NUMBER_RE.findall(str(row.get("claim") or "")))
            if candidates:
                risks.append({"risk_type": "numeric", "risk_token": " / ".join(candidates), "search_tokens": candidates, "why": "The final theme statement contains or summarizes a quantity whose value, magnitude, or boundary condition can change the conclusion."})
        for term in _POLARITY_TERMS:
            if _contains_polarity(statement, term) and any(_contains_polarity(str(row.get("claim") or ""), term) for row in parents):
                risks.append({"risk_type": "negation", "risk_token": term, "search_tokens": [term], "why": "The final statement preserves a negation or directional claim that can reverse or materially narrow the conclusion."})
        for token in _unique(entity for row in evidence for entity in row.get("entity_risks", []) if str(entity).lower() in lowered):
            if any(str(token).lower() in str(row.get("claim") or "").lower() for row in parents):
                risks.append({"risk_type": "entity", "risk_token": token, "search_tokens": [token], "why": "The named person, company, model, paper, or technical entity appears in the final statement and affects its meaning."})
        if claim["theme_claim_id"].endswith("claim_008_judgment_and_taste"):
            risks = [row for row in risks if row["risk_type"] != "negation"]
            risks.append({"risk_type": "epistemic_scope", "risk_token": "lacks judgment / taste / creativity", "search_tokens": ["taste", "judgment", "creativity", "don't have"], "why": "A categorical claim that AI lacks judgment, taste, or creativity may overgeneralize a bounded current observation."})
        if claim["theme_claim_id"].endswith("claim_019_pure_software_scarcity"):
            risks = [row for row in risks if row["risk_type"] != "negation"]
            risks.append({"risk_type": "epistemic_scope", "risk_token": "reducing pure-software scarcity", "search_tokens": ["pure software dead", "pure software", "software developed fairly quickly"], "why": "The final statement turns a speculative question and good-enough-software observation into a directional scarcity claim."})
        if claim["theme_claim_id"].endswith("claim_017_small_teams"):
            risks.append({"risk_type": "causal_scope", "risk_token": "AI enables smaller teams", "search_tokens": ["smaller team", "small team", "fewer people"], "why": "The final statement links AI leverage to team-size reduction; source fidelity must preserve whether this is observation, prediction, or general causal claim."})
        if claim["theme_claim_id"].endswith("claim_026_physical_testing"):
            risks.append({"risk_type": "causal_scope", "risk_token": "physical testing remains a bottleneck", "search_tokens": ["physical testing", "test", "hardware"], "why": "The role of physical testing is part of the core bottleneck-shift chain and must not be inferred from unrelated hardware context."})
        if claim["theme_claim_id"].endswith("claim_029_regulatory_bottleneck"):
            risks.append({"risk_type": "causal_scope", "risk_token": "regulation becomes a bottleneck", "search_tokens": ["regulation", "regulatory", "FAA", "FDA"], "why": "The claim connects faster technical execution to regulatory constraint; its direction and scope can change the industrial conclusion."})
        seen: set[tuple[str, str]] = set()
        for risk in risks:
            risk_type, token, why = risk["risk_type"], risk["risk_token"], risk["why"]
            key = (risk_type, token.lower())
            if key in seen:
                continue
            seen.add(key)
            search_tokens = list(risk.get("search_tokens") or [token])
            source_ids, evidence_ids, spans = _risk_spans(search_tokens, parents, evidence)
            if risk_type != "epistemic_scope" and not source_ids:
                continue
            direct_parents = [row for row in parents if row["claim_id"] in source_ids] or parents[:1]
            direct_excerpt = [sentence for row in direct_parents for sentence in _sentences(str(row.get("claim") or "")) if any(search.lower() in sentence.lower() for search in search_tokens)][:3]
            if not direct_excerpt:
                direct_excerpt = [str(row.get("claim") or "") for row in direct_parents[:3]]
            context, metadata = _local_context(direct_parents[0], sections_by_id, ordered) if direct_parents else ({}, {})
            digest = hashlib.sha256(f'{claim["theme_claim_id"]}|{risk_type}|{token}'.encode()).hexdigest()[:10]
            external_required = (
                risk_type in {"causal_scope", "epistemic_scope"}
                or (risk_type == "numeric" and claim.get("claim_type") != "open_question")
                or (risk_type == "negation" and claim.get("claim_type") != "open_question")
                or claim.get("claim_type") in {"fact", "prediction", "causal_claim", "technical_mechanism", "engineering_constraint", "institutional_claim", "geopolitical_claim"}
            )
            queue.append({"schema_version": SCHEMA_VERSION, "queue_id": f"verify.phase72c.local.{digest}", "theme_slug": THEME_SLUG, "theme_claim_ids": [claim["theme_claim_id"]], "insight_ids": [row["insight_id"] for row in insights if claim["theme_claim_id"] in row.get("supporting_theme_claim_ids", [])], "risk_source_claim_ids": source_ids, "risk_evidence_ids": evidence_ids or claim.get("evidence_ids", [])[:1], "risk_text_spans": spans, "risk_token": token, "risk_tokens": search_tokens, "risk_type": risk_type, "conclusion_impact": "high", "why_conclusion_changing": why, "direct_support_excerpt": direct_excerpt, "local_context": context, "source_metadata": metadata, "source_fidelity_status": "pending", "external_fact_status": "not_checked" if external_required else "not_required", "external_verification_required": external_required, "review_status": "pending"})
    return sorted(queue, key=lambda row: (row["theme_claim_ids"][0], row["risk_type"], row["risk_token"].lower()))


def prepare_phase72c_theme(*, theme_dir: Path, corpus_dir: Path, review_sync_root: Path | None = None) -> dict[str, Any]:
    """Generate Gate A plus claim-local P0 previews without mutating Phase 7.2A/B facts."""
    before = _tree_hashes(corpus_dir)
    claims = _read_jsonl(theme_dir / "theme_canonical_claims.jsonl")
    relations = _read_jsonl(theme_dir / "theme_claim_relations.jsonl")
    insights = _read_jsonl(theme_dir / "insight_candidates.jsonl")
    verification = _read_jsonl(theme_dir / "verification_queue.jsonl")
    source_claims = _read_jsonl(corpus_dir / "intelligence/source_claims.jsonl")
    evidence = _read_jsonl(corpus_dir / "canonical/evidence.jsonl")
    sections = _read_jsonl(corpus_dir / "canonical/sections.jsonl")
    source_claim_by_id = {row["claim_id"]: row for row in source_claims}
    evidence_by_id = {row["evidence_id"]: row for row in evidence}
    enriched_claims = [{**row, **_claim_independence(row, source_claim_by_id, evidence_by_id)} for row in claims]
    claim_by_id = {row["theme_claim_id"]: row for row in enriched_claims}
    enriched_insights = [{**row, **_insight_independence(row, claim_by_id)} for row in insights]
    p0 = _claim_local_p0(enriched_claims, enriched_insights, source_claim_by_id, evidence_by_id, sections)
    judgment_claim_ids = [row["theme_claim_id"] for row in enriched_claims if row["theme_claim_id"].endswith("claim_008_judgment_and_taste")]
    missing_judgment_scope = bool(judgment_claim_ids) and not any(any(claim_id in row.get("theme_claim_ids", []) for claim_id in judgment_claim_ids) for row in verification if row.get("priority") == "P0")
    original_p0_count = sum(row.get("priority") == "P0" for row in verification) + int(missing_judgment_scope)
    _write_jsonl(theme_dir / "claim_local_p0_verification_queue.jsonl", p0)
    _decision_templates(theme_dir, enriched_claims, relations, enriched_insights, p0)
    views = theme_dir / "views"
    views.mkdir(parents=True, exist_ok=True)
    (views / "theme_claim_review.html").write_text(_claim_review_page(enriched_claims, source_claim_by_id, evidence_by_id), encoding="utf-8")
    (views / "theme_insight_review.html").write_text(_insight_review_page(enriched_insights, claim_by_id, evidence_by_id), encoding="utf-8")
    (views / "theme_relation_review.html").write_text(_relation_review_page(relations, claim_by_id), encoding="utf-8")
    (views / "p0_verification_review.html").write_text(_verification_review_page(p0, claim_by_id, evidence_by_id, active=False), encoding="utf-8")
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
    upstream_p0 = [row for row in verification if row.get("priority") == "P0"]
    local_claim_ids = {claim_id for row in p0 for claim_id in row.get("theme_claim_ids", [])}
    false_positive_rows = [row for row in upstream_p0 if not set(row.get("theme_claim_ids", [])) & local_claim_ids]
    covered_upstream_rows = [row for row in upstream_p0 if set(row.get("theme_claim_ids", [])) & local_claim_ids]
    local_rows_replacing_upstream = [row for row in p0 if any(set(old.get("theme_claim_ids", [])) & set(row.get("theme_claim_ids", [])) for old in covered_upstream_rows)]
    false_positive_count = len(false_positive_rows)
    collapsed_duplicate_count = max(0, len(covered_upstream_rows) - len(local_rows_replacing_upstream))
    total_reduction = max(0, original_p0_count - len(p0))
    claim_by_id_for_report = {row["theme_claim_id"]: row for row in enriched_claims}
    false_positive_examples = [{"queue_id": row["queue_id"], "theme_claim_ids": row.get("theme_claim_ids", []), "old_reasons": row.get("reasons", []), "theme_statements": [claim_by_id_for_report[claim_id]["statement"] for claim_id in row.get("theme_claim_ids", []) if claim_id in claim_by_id_for_report]} for row in false_positive_rows[:8]]
    (reports / "human_gate_report.md").write_text(
        f"# Phase 7.2C.1 Human Gate Workload Report\n\nStatus: **Gate A pending**\n\n- theme claims awaiting Gate A: {len(enriched_claims)}\n- relations awaiting Gate A: {len(relations)}\n- insights awaiting Gate A: {len(enriched_insights)}\n- original P0 count: {original_p0_count}\n- claim-local P0 preview count: {len(p0)}\n- excluded context-derived false positives: {false_positive_count}\n- collapsed duplicate/redundant P0 cards: {collapsed_duplicate_count}\n- total preview workload reduction: {total_reduction}\n- maximum P0 workload reduction: {round(total_reduction / max(1, original_p0_count) * 100, 1)}%\n- estimated verification time saved at 2–4 minutes/card: {total_reduction * 2}–{total_reduction * 4} minutes\n- active P0 after Gate A: pending human decisions; cannot exceed {len(p0)}\n- P0 removed because claims are rejected/deferred/merged away: pending Gate A\n- source-fidelity verification count: pending Gate A\n- external verification pending count: pending Gate A\n- accepted assets: 0\n- theme judgment frozen: no\n\n## False-positive examples\n\n```json\n{json.dumps(false_positive_examples, ensure_ascii=False, indent=2)}\n```\n\nGate A is reviewed first. Claim-local P0 does not block claim review and is activated only for provisionally accepted final statements.\n", encoding="utf-8")
    (reports / "publication_readiness_report.md").write_text(
        "# Publication Readiness Report\n\n- theme_asset_readiness: **blocked** (Gate A incomplete)\n- factual_publication_readiness: **blocked**\n\nGate A precedes verification. External factual verification is distinct from source fidelity and is not required to freeze a clearly provisional theme asset.\n", encoding="utf-8")
    after = _tree_hashes(corpus_dir)
    if before != after:
        raise ValueError("Phase 7.2C preparation modified frozen Phase 7.2A corpus")
    sync_dir = _sync_phase72c_review(theme_dir, review_sync_root, gate="Gate A pending")
    return {"status": "gate_a_pending", "theme_claim_count": len(enriched_claims), "relation_count": len(relations), "insight_count": len(enriched_insights), "original_p0_count": original_p0_count, "claim_local_p0_count": len(p0), "excluded_false_positive_count": false_positive_count, "collapsed_duplicate_p0_count": collapsed_duplicate_count, "total_p0_workload_reduction": total_reduction, "active_p0_count": None, "phase72a_input_unchanged": True, "phase72b_records_unchanged": True, "theme_dir": str(theme_dir), "review_sync_dir": str(sync_dir)}


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
            rejected_status = "rejected_parent_claim" if decision.get("reviewer_note") == "rejected_parent_claim" else "rejected"
            rejected.append({**relation, "schema_version": SCHEMA_VERSION, "review_status": rejected_status, "human_review": decision})
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


def _relation_gate_decisions(
    rows: list[dict[str, Any]], relations: list[dict[str, Any]], claim_mapping: dict[str, list[str]], resolved_at: str,
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    by_id = {str(row.get("relation_id") or ""): row for row in rows}
    expected = {row["relation_id"] for row in relations}
    if set(by_id) != expected:
        raise ValueError(f"relation Gate A requires exact record set; missing={len(expected-set(by_id))} extra={len(set(by_id)-expected)}")
    auto_rejected: set[str] = set()
    output: dict[str, dict[str, Any]] = {}
    for relation in relations:
        row = by_id[relation["relation_id"]]
        parent_rejected = not claim_mapping.get(relation["source_claim_id"]) or not claim_mapping.get(relation["target_claim_id"])
        if parent_rejected:
            auto_rejected.add(relation["relation_id"])
            output[relation["relation_id"]] = {**row, "decision": "reject", "reviewer": row.get("reviewer") or "system_parent_gate", "reviewed_at": row.get("reviewed_at") or resolved_at, "reviewer_note": row.get("reviewer_note") or "rejected_parent_claim"}
            continue
        if row.get("decision") not in RELATION_DECISIONS:
            raise ValueError(f"relation decision is missing or invalid for accepted parents: {relation['relation_id']}")
        if not str(row.get("reviewer") or "").strip() or not str(row.get("reviewed_at") or "").strip():
            raise ValueError(f"relation decision lacks reviewer/reviewed_at: {relation['relation_id']}")
        output[relation["relation_id"]] = row
    return output, auto_rejected


def finalize_phase72c_gate_a(
    *, theme_dir: Path, corpus_dir: Path, claim_decisions_path: Path, relation_decisions_path: Path,
    insight_decisions_path: Path, review_sync_root: Path | None = None,
) -> dict[str, Any]:
    """Materialize provisional assets first, then derive their active claim-local P0."""
    before = _tree_hashes(corpus_dir)
    claims = _read_jsonl(theme_dir / "theme_canonical_claims.jsonl")
    relations = _read_jsonl(theme_dir / "theme_claim_relations.jsonl")
    insights = _read_jsonl(theme_dir / "insight_candidates.jsonl")
    claim_decisions = _validate_complete(_read_jsonl(claim_decisions_path), {row["theme_claim_id"] for row in claims}, "theme_claim_id", CLAIM_DECISIONS, "theme claim")
    insight_decisions = _validate_complete(_read_jsonl(insight_decisions_path), {row["insight_id"] for row in insights}, "insight_id", INSIGHT_DECISIONS, "insight")
    accepted_claims, rejected_claims, merges, claim_mapping = _accepted_claims(claims, claim_decisions)
    gate_a_at = max([str(row.get("reviewed_at") or "") for row in [*claim_decisions.values(), *insight_decisions.values()]] or ["1970-01-01T00:00:00Z"])
    relation_decisions, auto_parent_rejections = _relation_gate_decisions(_read_jsonl(relation_decisions_path), relations, claim_mapping, gate_a_at)
    accepted_relations, rejected_relations = _accepted_relations(relations, relation_decisions, claim_mapping)
    accepted_insights, rejected_insights = _accepted_insights(insights, insight_decisions, claim_mapping)
    for row in accepted_claims:
        row["review_status"] = "provisionally_accepted"
    for row in accepted_relations:
        row["review_status"] = "provisionally_accepted"
    for row in accepted_insights:
        row["review_status"] = "provisionally_accepted"
        row["publishability"] = "not_publishable_before_gate_b"
    _write_jsonl(theme_dir / "theme_claim_review_decisions.jsonl", claim_decisions.values())
    _write_jsonl(theme_dir / "relation_review_decisions.jsonl", relation_decisions.values())
    _write_jsonl(theme_dir / "insight_review_decisions.jsonl", insight_decisions.values())
    _write_jsonl(theme_dir / "provisionally_accepted_theme_claims.jsonl", accepted_claims)
    _write_jsonl(theme_dir / "provisionally_rejected_theme_claims.jsonl", rejected_claims)
    _write_jsonl(theme_dir / "theme_claim_merges.jsonl", merges)
    _write_jsonl(theme_dir / "provisionally_accepted_relations.jsonl", accepted_relations)
    _write_jsonl(theme_dir / "provisionally_rejected_relations.jsonl", rejected_relations)
    _write_jsonl(theme_dir / "provisionally_accepted_insights.jsonl", accepted_insights)
    _write_jsonl(theme_dir / "provisionally_rejected_insights.jsonl", rejected_insights)
    source_claims = _read_jsonl(corpus_dir / "intelligence/source_claims.jsonl")
    evidence = _read_jsonl(corpus_dir / "canonical/evidence.jsonl")
    sections = _read_jsonl(corpus_dir / "canonical/sections.jsonl")
    source_claim_by_id = {row["claim_id"]: row for row in source_claims}
    evidence_by_id = {row["evidence_id"]: row for row in evidence}
    active_p0 = _claim_local_p0(accepted_claims, accepted_insights, source_claim_by_id, evidence_by_id, sections)
    _write_jsonl(theme_dir / "active_p0_verification_queue.jsonl", active_p0)
    external_queue = [{**row, "external_fact_status": "not_checked"} for row in active_p0 if row.get("external_verification_required")]
    _write_jsonl(theme_dir / "external_verification_queue.jsonl", external_queue)
    _write_p0_template(theme_dir, active_p0)
    claim_by_id = {row["theme_claim_id"]: row for row in accepted_claims}
    (theme_dir / "views/p0_verification_review.html").write_text(_verification_review_page(active_p0, claim_by_id, evidence_by_id, active=True), encoding="utf-8")
    preview_path = theme_dir / "claim_local_p0_verification_queue.jsonl"
    preview_count = len(_read_jsonl(preview_path)) if preview_path.exists() else 0
    removed_count = max(0, preview_count - len(active_p0))
    reports = theme_dir / "reports"
    claim_counts = Counter(row["decision"] for row in claim_decisions.values())
    insight_counts = Counter(row["decision"] for row in insight_decisions.values())
    relation_counts = Counter("rejected_parent_claim" if row_id in auto_parent_rejections else row["decision"] for row_id, row in relation_decisions.items())
    (reports / "human_gate_report.md").write_text(
        "# Phase 7.2C.1 Human Gate Workload Report\n\nStatus: **Gate A complete; Gate B pending**\n\n```json\n" +
        json.dumps({"claim_decisions": claim_counts, "insight_decisions": insight_counts, "relation_decisions": relation_counts, "provisionally_accepted_claims": len(accepted_claims), "provisionally_accepted_insights": len(accepted_insights), "provisionally_accepted_relations": len(accepted_relations), "claim_local_p0_preview_count": preview_count, "active_p0_count": len(active_p0), "p0_removed_after_gate_a": removed_count, "source_fidelity_verification_count": len(active_p0), "external_verification_pending_count": len(external_queue)}, ensure_ascii=False, indent=2, default=dict) +
        "\n```\n\nRelations whose parent claims were removed are recorded as `rejected_parent_claim` without additional semantic review.\n", encoding="utf-8")
    (reports / "publication_readiness_report.md").write_text(f"# Publication Readiness Report\n\n- theme_asset_readiness: **blocked** (Gate B source fidelity pending: {len(active_p0)})\n- factual_publication_readiness: **blocked**\n- external verification pending: {len(external_queue)}\n\nExternal verification does not block a provisional theme freeze, but it blocks unqualified factual publication.\n", encoding="utf-8")
    if before != _tree_hashes(corpus_dir):
        raise ValueError("Phase 7.2C Gate A modified frozen Phase 7.2A corpus")
    sync_dir = _sync_phase72c_review(theme_dir, review_sync_root, gate="Gate B active P0")
    return {"status": "gate_a_complete_gate_b_pending", "provisionally_accepted_theme_claim_count": len(accepted_claims), "provisionally_accepted_relation_count": len(accepted_relations), "provisionally_accepted_insight_count": len(accepted_insights), "auto_rejected_parent_relation_count": len(auto_parent_rejections), "claim_local_p0_preview_count": preview_count, "active_p0_count": len(active_p0), "p0_removed_after_gate_a": removed_count, "external_verification_pending_count": len(external_queue), "phase72a_input_unchanged": True, "review_sync_dir": str(sync_dir)}


def _write_publication_candidates(theme_dir: Path, claims: list[dict[str, Any]], insights: list[dict[str, Any]]) -> None:
    reports = theme_dir / "reports"
    claim_lines = "\n".join(f'- {row["statement"]} (`{row["theme_claim_id"]}`)' for row in claims)
    insight_lines = "\n".join(f'- {row["statement"]} (`{row["insight_id"]}`)' for row in insights)
    caveat = "本批Naval及嘉宾语料共同指向一个值得进一步验证的判断："
    website = f"# AI执行商品化与判断稀缺性\n\n{caveat}\n\n## 已审核洞见\n\n{insight_lines}\n\n## 已审核主题观点\n\n{claim_lines}\n\n> Publication candidate only. No automatic publication.\n"
    (reports / "website_topic_draft.md").write_text(website, encoding="utf-8")
    (reports / "wechat_article_draft.md").write_text(f"# 当执行能力变便宜，什么会变得更贵？\n\n{caveat}\n\n{insight_lines}\n\n## 证据边界\n\n本文只使用已通过人工质量门的主题观点；它不把同一场对谈的重复页面视为独立行业证据，也不把系统综合判断伪装成人物原话。\n", encoding="utf-8")
    _write_jsonl(reports / "xiaohongshu_slices.jsonl", ({"schema_version": SCHEMA_VERSION, "slice_id": f"{THEME_SLUG}.slice_{index:02d}", "title": "执行变便宜后，判断为什么更稀缺？", "body": row["statement"], "supporting_insight_id": row["insight_id"], "status": "publication_candidate_only"} for index, row in enumerate(insights, 1)))


def _qualified_as_view_or_hypothesis(claim: dict[str, Any]) -> bool:
    status = str(claim.get("epistemic_status") or "")
    statement = str(claim.get("statement") or "").lower()
    if status in {"hypothesis", "provisional"}:
        return True
    markers = ("according to", "argues that", "suggests that", "questions whether", "may ", "might ", "could ", "待验证", "认为", "推测", "可能")
    return any(marker in statement for marker in markers)


def _validate_verification_decisions(rows: list[dict[str, Any]], p0: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    expected = {row["queue_id"] for row in p0}
    ids = [str(row.get("queue_id") or "") for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError(f"Gate B requires exactly the active P0 set; missing={len(expected-set(ids))} extra={len(set(ids)-expected)}")
    output = {}
    for row in rows:
        queue_id = row["queue_id"]
        source_status = str(row.get("source_fidelity_status") or "")
        external_status = str(row.get("external_fact_status") or "")
        if source_status not in SOURCE_FIDELITY_STATUSES or source_status == "pending":
            raise ValueError(f"active P0 source_fidelity_status is incomplete for {queue_id}: {source_status!r}")
        if external_status not in EXTERNAL_FACT_STATUSES:
            raise ValueError(f"invalid external_fact_status for {queue_id}: {external_status!r}")
        if not str(row.get("reviewer") or "").strip() or not str(row.get("reviewed_at") or "").strip() or not str(row.get("verification_note") or "").strip():
            raise ValueError(f"active P0 needs reviewer, reviewed_at, and verification_note: {queue_id}")
        if source_status == "corrected" and not str(row.get("corrected_value") or "").strip():
            raise ValueError(f"corrected source fidelity needs corrected_value: {queue_id}")
        output[queue_id] = row
    return output


def finalize_phase72c_theme(*, theme_dir: Path, corpus_dir: Path, verification_decisions_path: Path) -> dict[str, Any]:
    """Freeze a human-reviewed provisional theme; external facts may remain unchecked."""
    before = _tree_hashes(corpus_dir)
    accepted_claims = _read_jsonl(theme_dir / "provisionally_accepted_theme_claims.jsonl")
    accepted_relations = _read_jsonl(theme_dir / "provisionally_accepted_relations.jsonl")
    accepted_insights = _read_jsonl(theme_dir / "provisionally_accepted_insights.jsonl")
    p0 = _read_jsonl(theme_dir / "active_p0_verification_queue.jsonl")
    verification_decisions = _validate_verification_decisions(_read_jsonl(verification_decisions_path), p0)
    rejected_source = [queue_id for queue_id, row in verification_decisions.items() if row["source_fidelity_status"] == "rejected"]
    if rejected_source:
        raise ValueError(f"source fidelity rejected active accepted claims; return to Gate A: {rejected_source}")
    p0_by_id = {row["queue_id"]: row for row in p0}
    claim_statuses: dict[str, list[str]] = defaultdict(list)
    for queue_id, decision in verification_decisions.items():
        for claim_id in p0_by_id[queue_id].get("theme_claim_ids", []):
            claim_statuses[claim_id].append(decision["source_fidelity_status"])
    for claim in accepted_claims:
        statuses = claim_statuses.get(claim["theme_claim_id"], [])
        claim["verification_status"] = "source_fidelity_corrected" if "corrected" in statuses else "source_fidelity_verified" if statuses else "source_fidelity_not_applicable"
        claim["review_status"] = "accepted_provisional"
    for row in accepted_relations:
        row["review_status"] = "accepted_provisional"
    for row in accepted_insights:
        row["review_status"] = "accepted_provisional"
        row["publishability"] = "provisional_theme_asset_only"
    external_queue = []
    for queue_id, queue in p0_by_id.items():
        decision = verification_decisions[queue_id]
        if decision["external_fact_status"] in {"not_checked", "insufficient_evidence", "contradicted"}:
            external_queue.append({**queue, "source_fidelity_status": decision["source_fidelity_status"], "external_fact_status": decision["external_fact_status"], "verification_note": decision["verification_note"], "reviewer": decision["reviewer"], "reviewed_at": decision["reviewed_at"]})
    _write_jsonl(theme_dir / "p0_verification_decisions.jsonl", verification_decisions.values())
    _write_jsonl(theme_dir / "accepted_theme_claims.jsonl", accepted_claims)
    _write_jsonl(theme_dir / "accepted_relations.jsonl", accepted_relations)
    _write_jsonl(theme_dir / "accepted_insights.jsonl", accepted_insights)
    _write_jsonl(theme_dir / "external_verification_queue.jsonl", external_queue)
    manifest = json.loads((theme_dir / "source_manifest.json").read_text(encoding="utf-8"))
    frozen_at = max(str(row.get("reviewed_at") or "") for row in verification_decisions.values())
    accepted_claim_by_id = {row["theme_claim_id"]: row for row in accepted_claims}
    contradicted_count = sum(row["external_fact_status"] == "contradicted" for row in verification_decisions.values())
    unqualified_unchecked = []
    qualified_unchecked = []
    for queue_id, decision in verification_decisions.items():
        if decision["external_fact_status"] not in {"not_checked", "insufficient_evidence"}:
            continue
        affected = [accepted_claim_by_id[claim_id] for claim_id in p0_by_id[queue_id].get("theme_claim_ids", []) if claim_id in accepted_claim_by_id]
        target = qualified_unchecked if affected and all(_qualified_as_view_or_hypothesis(claim) for claim in affected) else unqualified_unchecked
        target.append(queue_id)
    factual_readiness = "blocked" if contradicted_count else "needs_external_verification" if unqualified_unchecked else "ready"
    judgment = {
        "schema_version": SCHEMA_VERSION,
        "theme_slug": THEME_SLUG,
        "judgment_version": "theme_judgment_v1",
        "status": "human_reviewed_provisional",
        "frozen_at": frozen_at,
        "corpus_snapshot": {"source_corpus": "input/corpora/naval_recent_six", "input_files": manifest.get("input_files", {})},
        "calibrated_statement": "本批Naval及嘉宾语料共同指向一个值得进一步验证的判断：AI降低部分执行成本时，问题选择、架构、验证、现实约束与责任的相对重要性可能上升。",
        "accepted_claim_ids": [row["theme_claim_id"] for row in accepted_claims],
        "accepted_insight_ids": [row["insight_id"] for row in accepted_insights],
        "accepted_relation_ids": [row["relation_id"] for row in accepted_relations],
        "unresolved_tensions": [row["statement"] for row in accepted_insights if row.get("insight_type") == "unresolved_tension"],
        "confidence": "provisional_human_reviewed",
        "theme_asset_readiness": "ready",
        "factual_publication_readiness": factual_readiness,
        "externally_unverified_but_qualified_claim_ids": _unique(claim_id for queue_id in qualified_unchecked for claim_id in p0_by_id[queue_id].get("theme_claim_ids", [])),
        "evidence_scope": "Six fixed Naval pages; two transcript-bearing publication families; repeated pages are deweighted. Source fidelity is human-reviewed; external factual verification is incomplete unless explicitly recorded otherwise.",
        "known_limitations": ["Publication-family diversity is not independent industry validation.", "Most industrial mechanisms originate from one Frontier Founders conversation.", "Live in the Future has no official transcript and supplies no claim support."],
        "predictions_expected_observations": ["If the judgment is robust, later independent sources should report rising verification, architecture, regulatory, or accountability effort as generation costs fall."],
        "conditions_that_would_weaken_or_overturn": ["Independent evidence shows execution cost declines without increased verification or judgment burden.", "Productivity gains are evenly distributed regardless of domain judgment.", "Software scarcity remains the dominant constraint despite abundant generation."],
    }
    (theme_dir / "theme_judgment_v1.json").write_text(json.dumps(judgment, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    revision_path = theme_dir / "revision_history.jsonl"
    revisions = _read_jsonl(revision_path)
    revisions = [row for row in revisions if row.get("operation") != "phase_7_2c_provisional_freeze"]
    revisions.append({"schema_version": SCHEMA_VERSION, "revision_id": f"{THEME_SLUG}.revision_phase_7_2c_v1", "created_at": frozen_at, "operation": "phase_7_2c_provisional_freeze", "accepted_claim_count": len(accepted_claims), "accepted_relation_count": len(accepted_relations), "accepted_insight_count": len(accepted_insights), "external_verification_pending_count": len(external_queue), "review_status": "human_reviewed_provisional"})
    _write_jsonl(revision_path, revisions)
    reports = theme_dir / "reports"
    reports.mkdir(exist_ok=True)
    insight_lines = "\n".join(f'- {row["statement"]} (`{row["insight_id"]}`)' for row in accepted_insights)
    (reports / "current_judgment_v1.md").write_text(f'# Current Judgment v1\n\n> {judgment["calibrated_statement"]}\n\n## Accepted insights\n\n{insight_lines}\n\n## Evidence scope\n\n{judgment["evidence_scope"]}\n\n## What would weaken it\n\n' + "\n".join(f'- {row}' for row in judgment["conditions_that_would_weaken_or_overturn"]) + "\n", encoding="utf-8")
    (reports / "human_gate_report.md").write_text("# Phase 7.2C.1 Human Gate Report\n\nStatus: **provisional theme asset frozen**\n\n```json\n" + json.dumps({"accepted_theme_claim_count": len(accepted_claims), "accepted_relation_count": len(accepted_relations), "accepted_insight_count": len(accepted_insights), "active_p0_count": len(p0), "source_fidelity_completed_count": len(verification_decisions), "external_verification_pending_count": len(external_queue)}, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
    (reports / "publication_readiness_report.md").write_text(f"# Publication Readiness Report\n\n- theme_asset_readiness: **ready**\n- factual_publication_readiness: **{factual_readiness}**\n- external verification queue: {len(external_queue)}\n- unqualified external-verification blockers: {len(unqualified_unchecked)}\n- unverified items explicitly framed as speaker views/hypotheses: {len(qualified_unchecked)}\n\n`theme_judgment_v1` is a human-reviewed provisional theme asset. Unchecked facts can enter a publication candidate only when the human final wording explicitly frames them as a speaker view or hypothesis.\n", encoding="utf-8")
    if factual_readiness == "ready":
        _write_publication_candidates(theme_dir, accepted_claims, accepted_insights)
    if before != _tree_hashes(corpus_dir):
        raise ValueError("Phase 7.2C finalization modified frozen Phase 7.2A corpus")
    return {"status": "human_reviewed_provisional", "accepted_theme_claim_count": len(accepted_claims), "accepted_relation_count": len(accepted_relations), "accepted_insight_count": len(accepted_insights), "active_p0_count": len(p0), "source_fidelity_completed_count": len(verification_decisions), "external_verification_pending_count": len(external_queue), "theme_asset_readiness": "ready", "factual_publication_readiness": factual_readiness, "publication_candidates_generated": factual_readiness == "ready", "theme_judgment": str(theme_dir / "theme_judgment_v1.json")}

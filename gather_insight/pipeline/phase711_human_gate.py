"""Phase 7.1.1 human quality gate for trend candidates.

This module never edits the machine candidate or evidence JSONL.  Review
decisions are a separate append-only layer from which accepted/rejected and
canonical claim views are materialized.
"""

from __future__ import annotations

import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DECISION_SCHEMA_VERSION = "phase_7_1_1_review_decision_v1"
ACCEPTED_SCHEMA_VERSION = "phase_7_1_1_accepted_claim_v1"
MERGE_SCHEMA_VERSION = "phase_7_1_1_claim_merge_v1"
GATE_REPORT_SCHEMA_VERSION = "phase_7_1_1_gate_report_v1"
ENTAILMENT_LABELS = {
    "fully_supported",
    "supported_with_missing_condition",
    "partially_supported",
    "overgeneralized",
    "contradicted",
    "unrelated",
}
VERIFICATION_TAGS = (
    "needs_boundary_expansion",
    "needs_context",
    "needs_entity_verification",
    "needs_numeric_verification",
    "needs_negation_verification",
    "needs_speaker_verification",
)
DECISIONS = {
    "accept",
    "reject_low_value",
    "reject_incorrect",
    "reject_unsupported",
    "reject_duplicate",
    "merge_into",
    "needs_boundary_expansion",
    "needs_context",
    "needs_entity_verification",
    "needs_numeric_verification",
    "needs_negation_verification",
    "needs_speaker_verification",
}
GOLDEN_REVIEW_VERSION = "phase_7_1_1_golden_review_v1"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _decision_row(candidate: dict[str, Any], claim: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": DECISION_SCHEMA_VERSION,
        "review_id": f"review.{candidate['trend_candidate_id']}",
        "trend_candidate_id": candidate["trend_candidate_id"],
        "claim_id": candidate["claim_id"],
        "media_id": candidate["media_id"],
        "decision": "",
        "canonical_claim": "",
        "merge_into_claim_id": "",
        "entailment_label": "",
        "condition_preservation": "not_applicable",
        "verification_status": "open",
        "verification_tags": [],
        "reviewer": "",
        "review_version": "phase_7_1_1_review_v1",
        "reviewer_note": "",
        "review_seconds": None,
        "reviewed_at": "",
        "source_record_ids": list(claim.get("source_record_ids") or []),
        "evidence_ids": list(claim.get("evidence_ids") or evidence.get("evidence_id") and [evidence["evidence_id"]] or []),
    }


def generate_phase711_review(*, media_root: Path, output_dir: Path | None = None) -> dict[str, Any]:
    """Generate an algorithm-blind candidate review page and JSONL template."""
    intelligence = media_root / "intelligence"
    views = output_dir or (media_root / "views")
    views.mkdir(parents=True, exist_ok=True)
    candidates = _read_jsonl(intelligence / "trend_candidates.jsonl")
    claims = {row["claim_id"]: row for row in _read_jsonl(intelligence / "claims.jsonl")}
    evidence = {row["evidence_id"]: row for row in _read_jsonl(intelligence / "evidence.jsonl")}
    rows: list[dict[str, Any]] = []
    cards: list[str] = []
    for candidate in sorted(candidates, key=lambda row: (float(row.get("source_time_start", 0.0)), row["trend_candidate_id"])):
        claim = claims.get(candidate["claim_id"], {})
        evidence_ids = list(claim.get("evidence_ids") or candidate.get("evidence_ids") or [])
        ev = evidence.get(evidence_ids[0], {}) if evidence_ids else {}
        row = _decision_row(candidate, claim, ev)
        rows.append(row)
        # Candidate IDs and algorithm scores are deliberately omitted from the
        # visible card.  The hidden data attribute is only needed for export.
        payload = json.dumps(row, ensure_ascii=False)
        risks = {"entity": claim.get("entity_risks", []), "numeric": claim.get("numeric_risks", []), "negation": claim.get("negation_risks", [])}
        cards.append(
            f'<article class="candidate" data-row="{html.escape(payload, quote=True)}">'
            f'<h2>Candidate {len(rows):03d}</h2>'
            f'<p><a target="_blank" href="{html.escape(str(claim.get("source_url") or ev.get("source_url") or ""))}">YouTube time link</a> · '
            f'{float(claim.get("source_time_start", 0.0)):.1f}s–{float(claim.get("source_time_end", 0.0)):.1f}s · '
            f'speaker status: {html.escape(str(claim.get("speaker_status") or "unknown"))}</p>'
            f'<h3>Candidate claim</h3><p>{html.escape(str(claim.get("claim") or candidate.get("trend_signal") or ""))}</p>'
            f'<h3>Supporting evidence</h3><pre>{html.escape(str(ev.get("source_text") or "(evidence unavailable)"))}</pre>'
            f'<details><summary>Source and risk details</summary><pre>{html.escape(json.dumps({"source_record_ids": claim.get("source_record_ids", []), "evidence_ids": evidence_ids, "source_ranges": ev.get("source_ranges", []), "entity_risks": risks["entity"], "numeric_risks": risks["numeric"], "negation_risks": risks["negation"]}, ensure_ascii=False, indent=2))}</pre></details>'
            '<div class="form">'
            '<label>decision <select class="decision"><option></option>' + ''.join(f'<option>{value}</option>' for value in sorted(DECISIONS)) + '</select></label>'
            '<label>canonical claim <textarea class="canonical"></textarea></label>'
            '<label>merge into claim ID <input class="merge"></label>'
            '<label>entailment <select class="entailment"><option></option>' + ''.join(f'<option>{value}</option>' for value in sorted(ENTAILMENT_LABELS)) + '</select></label>'
            '<label>condition preservation <select class="condition"><option>not_applicable</option><option>preserved</option><option>missing</option><option>distorted</option></select></label>'
            '<label>verification status <select class="verification"><option>open</option><option>verified</option><option>rejected</option></select></label>'
            '<label>verification tags <span class="checks">' + ''.join(f'<label><input type="checkbox" class="tag" value="{value}">{value}</label>' for value in VERIFICATION_TAGS) + '</span></label>'
            '<label>review seconds <input class="seconds" type="number" min="0"></label>'
            '<label>reviewer note <textarea class="note"></textarea></label>'
            '</div></article>'
        )
    template = views / "review_decisions.template.jsonl"
    _write_jsonl(template, rows)
    pending_decisions = intelligence / "review_decisions.jsonl"
    if not pending_decisions.exists():
        _write_jsonl(pending_decisions, rows)
    for name in ("accepted_claims.jsonl", "rejected_claims.jsonl", "claim_merges.jsonl"):
        path = intelligence / name
        if not path.exists():
            _write_jsonl(path, [])
    page = views / "trend_candidate_review.html"
    page.write_text(
        '<!doctype html><html><head><meta charset="utf-8"><title>Trend candidate human gate</title>'
        '<style>body{font:14px/1.5 system-ui;max-width:1120px;margin:24px auto}.candidate{border:1px solid #bbb;padding:16px;margin:18px 0;background:#fffdf7}.candidate h2{color:#435a6b}pre{white-space:pre-wrap;background:#f3f3f3;padding:10px}.form{display:grid;gap:8px}.form label{display:grid;grid-template-columns:190px 1fr;gap:8px}.top{position:sticky;top:0;background:#fff;padding:12px;border-bottom:1px solid #aaa;z-index:2}.warning{background:#fff2cc;padding:10px}</style></head><body>'
        '<div class="top"><h1>Trend candidate human quality gate</h1><p class="warning">Algorithm identity and machine scores are hidden. Review the claim and evidence before opening source details. Do not edit machine claims/evidence.</p><label>Reviewer <input id="reviewer"></label> <label>Review version <input id="version" value="phase_7_1_1_review_v1"></label> <button onclick="downloadReview()">Download review_decisions.jsonl</button></div>'
        f'<p>{len(rows)} candidates. Blank decisions remain pending and cannot enter Phase 7.2.</p>{"".join(cards)}'
        '<script>function downloadReview(){const reviewer=document.getElementById("reviewer").value.trim();if(!reviewer){alert("Reviewer is required");return}const version=document.getElementById("version").value.trim();const rows=[...document.querySelectorAll(".candidate")].map(card=>{const row=JSON.parse(card.dataset.row);row.decision=card.querySelector(".decision").value;row.canonical_claim=card.querySelector(".canonical").value;row.merge_into_claim_id=card.querySelector(".merge").value;row.entailment_label=card.querySelector(".entailment").value;row.condition_preservation=card.querySelector(".condition").value;row.verification_status=card.querySelector(".verification").value;row.verification_tags=[...card.querySelectorAll(".tag:checked")].map(x=>x.value);row.review_seconds=card.querySelector(".seconds").value===""?null:Number(card.querySelector(".seconds").value);row.reviewer_note=card.querySelector(".note").value;row.reviewer=reviewer;row.review_version=version;row.reviewed_at=new Date().toISOString();return row});const text=rows.map(x=>JSON.stringify(x)).join("\\n")+"\\n";const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([text],{type:"application/jsonl"}));a.download="review_decisions.jsonl";a.click()}</script></body></html>'
    , encoding="utf-8")
    reports = media_root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "PHASE_7_1_1_HUMAN_GATE_REPORT.md").write_text(f'''# Phase 7.1.1 Human Quality Gate Report

Status: **pending human review**

- trend candidates in scope: {len(rows)}
- reviewed candidates: 0
- accepted/rejected/merged candidates: not yet measured
- actual precision: not yet measured
- claim-evidence entailment accuracy: not yet measured
- final canonical claim count: 0

The blind review package is ready. Machine `claims.jsonl` and `evidence.jsonl` remain unchanged. Phase 7.2 is blocked until every in-scope decision is completed and `finalize-phase711-review` materializes the accepted claim set.
''', encoding="utf-8")
    return {"status": "pending_human_review", "candidate_count": len(rows), "review_html": str(page.resolve()), "review_template": str(template.resolve()), "review_decisions": str(pending_decisions.resolve()), "accepted_claims": str((intelligence / "accepted_claims.jsonl").resolve()), "rejected_claims": str((intelligence / "rejected_claims.jsonl").resolve()), "claim_merges": str((intelligence / "claim_merges.jsonl").resolve())}


def finalize_phase711_review(*, media_root: Path, decisions_path: Path, output_dir: Path | None = None) -> dict[str, Any]:
    """Materialize accepted/rejected/merge views from human decisions."""
    intelligence = media_root / "intelligence"
    out = output_dir or intelligence
    out.mkdir(parents=True, exist_ok=True)
    decisions = _read_jsonl(decisions_path)
    candidates = {row["trend_candidate_id"]: row for row in _read_jsonl(intelligence / "trend_candidates.jsonl")}
    claims = {row["claim_id"]: row for row in _read_jsonl(intelligence / "claims.jsonl")}
    evidence = {row["evidence_id"]: row for row in _read_jsonl(intelligence / "evidence.jsonl")}
    if not decisions:
        raise ValueError("review decisions are empty; human quality gate is not complete")
    reviewed_ids = [str(row.get("trend_candidate_id") or "") for row in decisions]
    if len(reviewed_ids) != len(set(reviewed_ids)):
        raise ValueError("review decisions contain duplicate trend_candidate_id values")
    missing = sorted(set(candidates) - set(reviewed_ids))
    extra = sorted(set(reviewed_ids) - set(candidates))
    if missing or extra:
        raise ValueError(f"human gate requires exactly all trend candidates; missing={len(missing)} extra={len(extra)}")
    accepted_by_id: dict[str, dict[str, Any]] = {}
    rejected, merges = [], []
    valid_rows = []
    for decision in decisions:
        candidate_id = str(decision.get("trend_candidate_id") or "")
        claim_id = str(decision.get("claim_id") or "")
        if candidate_id not in candidates or claim_id not in claims:
            raise ValueError(f"review decision references unknown candidate/claim: {candidate_id}/{claim_id}")
        value = str(decision.get("decision") or "")
        if value not in DECISIONS:
            raise ValueError(f"review decision is missing or invalid for {candidate_id}: {value!r}")
        entailment = str(decision.get("entailment_label") or "")
        if value in {"accept", "merge_into"} and entailment not in ENTAILMENT_LABELS:
            raise ValueError(f"accepted decision needs entailment_label: {candidate_id}")
        valid_rows.append(decision)
        claim = claims[claim_id]
        evidence_ids = list(dict.fromkeys(decision.get("evidence_ids") or claim.get("evidence_ids") or []))
        parent_ids = [claim_id]
        canonical_text = str(decision.get("canonical_claim") or claim.get("claim") or "").strip()
        if value == "accept":
            accepted_by_id[claim_id] = {
                "schema_version": ACCEPTED_SCHEMA_VERSION,
                "canonical_claim_id": f"canonical.{claim_id}",
                "media_id": claim["media_id"],
                "canonical_claim": canonical_text,
                "parent_claim_ids": parent_ids,
                "evidence_ids": evidence_ids,
                "source_record_ids": list(dict.fromkeys(claim.get("source_record_ids") or [])),
                "source_ranges": [item for evidence_id in evidence_ids for item in evidence.get(evidence_id, {}).get("source_ranges", [])],
                "source_time_start": claim.get("source_time_start"),
                "source_time_end": claim.get("source_time_end"),
                "source_url": claim.get("source_url"),
                "speaker": claim.get("speaker"),
                "speaker_status": claim.get("speaker_status"),
                "verification_status": decision.get("verification_status") or "open",
                "entailment_label": entailment,
                "condition_preservation": decision.get("condition_preservation") or "not_applicable",
                "review_metadata": {"reviewer": decision.get("reviewer"), "review_version": decision.get("review_version"), "reviewed_at": decision.get("reviewed_at"), "reviewer_note": decision.get("reviewer_note"), "verification_tags": decision.get("verification_tags", [])},
            }
        elif value != "merge_into":
            rejected.append({**decision, "schema_version": DECISION_SCHEMA_VERSION, "rejected_claim": claim.get("claim")})
        merge_target = str(decision.get("merge_into_claim_id") or "")
        if value == "merge_into" and not merge_target:
            raise ValueError(f"merge_into decision needs merge_into_claim_id: {candidate_id}")
    for decision in valid_rows:
        if decision.get("decision") != "merge_into":
            continue
        claim_id = str(decision["claim_id"])
        claim = claims[claim_id]
        target = str(decision.get("merge_into_claim_id") or "")
        target_claim_id = target.removeprefix("canonical.")
        if target_claim_id not in accepted_by_id:
            raise ValueError(f"merge target must be an accepted claim in the same review: {target}")
        canonical = accepted_by_id[target_claim_id]
        evidence_ids = list(dict.fromkeys(decision.get("evidence_ids") or claim.get("evidence_ids") or []))
        canonical["parent_claim_ids"] = list(dict.fromkeys([*canonical["parent_claim_ids"], claim_id]))
        canonical["evidence_ids"] = list(dict.fromkeys([*canonical["evidence_ids"], *evidence_ids]))
        canonical["source_record_ids"] = list(dict.fromkeys([*canonical["source_record_ids"], *(claim.get("source_record_ids") or [])]))
        canonical["source_ranges"] = [item for evidence_id in canonical["evidence_ids"] for item in evidence.get(evidence_id, {}).get("source_ranges", [])]
        canonical["source_time_start"] = min(float(canonical["source_time_start"]), float(claim.get("source_time_start") or canonical["source_time_start"]))
        canonical["source_time_end"] = max(float(canonical["source_time_end"]), float(claim.get("source_time_end") or canonical["source_time_end"]))
        merges.append({"schema_version": MERGE_SCHEMA_VERSION, "merge_id": f"merge.{decision['trend_candidate_id']}", "media_id": claim["media_id"], "parent_claim_id": claim_id, "canonical_claim_id": canonical["canonical_claim_id"], "evidence_ids": evidence_ids, "reviewer": decision.get("reviewer"), "review_version": decision.get("review_version"), "reviewed_at": decision.get("reviewed_at"), "reviewer_note": decision.get("reviewer_note", "")})
    accepted = sorted(accepted_by_id.values(), key=lambda row: (float(row["source_time_start"]), row["canonical_claim_id"]))
    _write_jsonl(out / "review_decisions.jsonl", valid_rows)
    _write_jsonl(out / "accepted_claims.jsonl", accepted)
    _write_jsonl(out / "rejected_claims.jsonl", rejected)
    _write_jsonl(out / "claim_merges.jsonl", merges)
    reviewed = len(valid_rows)
    fully_supported = sum(row.get("entailment_label") == "fully_supported" for row in valid_rows)
    labeled_entailment = sum(bool(row.get("entailment_label")) for row in valid_rows)
    accepted_verified = sum(row.get("verification_status") == "verified" for row in accepted)
    wrong_speaker = sum(row.get("speaker_status") not in {"source_provided", "audio_confirmed"} for row in accepted)
    accepted_candidate_count = sum(row.get("decision") in {"accept", "merge_into"} for row in valid_rows)
    rejected_candidate_count = sum(str(row.get("decision", "")).startswith("reject_") for row in valid_rows)
    risk_priority_counts = Counter()
    for row in valid_rows:
        if row.get("decision") not in {"accept", "merge_into"}:
            continue
        tags = {str(value) for value in row.get("verification_tags", [])}
        if tags & {"numeric", "negation", "exact_speaker", "speaker", "conclusion_changing_entity", "needs_numeric_verification", "needs_negation_verification", "needs_speaker_verification"}:
            risk_priority_counts["P0"] += 1
        elif tags & {"entity", "person", "company", "paper", "model", "direct_quote", "performance", "needs_entity_verification"}:
            risk_priority_counts["P1"] += 1
        else:
            risk_priority_counts["P2"] += 1
    metrics = {
        "candidate_count": len(candidates),
        "reviewed_candidate_count": reviewed,
        "pending_candidate_count": max(0, len(candidates) - reviewed),
        "accepted_candidate_count": accepted_candidate_count,
        "rejected_candidate_count": rejected_candidate_count,
        "candidate_acceptance_rate": round(accepted_candidate_count / max(1, reviewed), 6),
        "actual_precision": round(fully_supported / max(1, reviewed), 6),
        "low_value_rejection_rate": round(sum(row.get("decision") == "reject_low_value" for row in valid_rows) / max(1, reviewed), 6),
        "incorrect_rejection_rate": round(sum(row.get("decision") == "reject_incorrect" for row in valid_rows) / max(1, reviewed), 6),
        "duplicate_rate": round(sum(row.get("decision") == "reject_duplicate" for row in valid_rows) / max(1, reviewed), 6),
        "merge_rate": round(sum(row.get("decision") == "merge_into" for row in valid_rows) / max(1, reviewed), 6),
        "average_candidates_per_canonical_claim": round(accepted_candidate_count / max(1, len(accepted)), 6),
        "claim_evidence_entailment_accuracy": round(fully_supported / max(1, labeled_entailment), 6),
        "condition_preservation_accuracy": round(sum(row.get("condition_preservation") == "preserved" for row in valid_rows if row.get("condition_preservation") != "not_applicable") / max(1, sum(row.get("condition_preservation") != "not_applicable" for row in valid_rows)), 6),
        "wrong_speaker_accepted_claim_count": wrong_speaker,
        "accepted_claim_verification_rate": round(accepted_verified / max(1, len(accepted)), 6),
        "average_human_review_seconds": round(sum(float(row.get("review_seconds") or 0.0) for row in valid_rows) / max(1, reviewed), 3),
        "entailment_label_counts": dict(Counter(str(row.get("entailment_label") or "unlabeled") for row in valid_rows)),
        "overgeneralized_claim_count": sum(row.get("entailment_label") == "overgeneralized" for row in valid_rows),
        "missing_condition_claim_count": sum(row.get("entailment_label") == "supported_with_missing_condition" or row.get("condition_preservation") == "missing" for row in valid_rows),
        "risk_priority_counts": dict(risk_priority_counts),
    }
    report = {"schema_version": GATE_REPORT_SCHEMA_VERSION, "status": "complete", "media_id": next(iter(claims.values()))["media_id"] if claims else "", "metrics": metrics, "rejected_reason_counts": dict(Counter(str(row.get("decision")) for row in valid_rows if str(row.get("decision", "")).startswith("reject_"))), "canonical_claim_count": len(accepted), "merge_count": len(merges), "overgeneralized_claim_ids": [row["claim_id"] for row in valid_rows if row.get("entailment_label") == "overgeneralized"], "missing_condition_claim_ids": [row["claim_id"] for row in valid_rows if row.get("entailment_label") == "supported_with_missing_condition" or row.get("condition_preservation") == "missing"], "trend_changing_risk_claim_ids": [row["claim_id"] for row in valid_rows if row.get("decision") in {"accept", "merge_into"} and set(row.get("verification_tags", [])) & {"numeric", "negation", "exact_speaker", "speaker", "conclusion_changing_entity", "needs_numeric_verification", "needs_negation_verification", "needs_speaker_verification"}], "phase_7_2_allowed": bool(accepted) and reviewed == len(candidates), "created_at": _now()}
    (media_root / "reports" / "PHASE_7_1_1_HUMAN_GATE_REPORT.md").write_text(_report_markdown(report), encoding="utf-8")
    (media_root / "reports" / "phase_7_1_1_gate_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _report_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    return f'''# Phase 7.1.1 Human Quality Gate Report

Status: **{report["status"]}**

This report is generated only from human `review_decisions.jsonl`. It does not modify machine `claims.jsonl` or `evidence.jsonl`.

## Metrics

- trend candidates: {metrics["candidate_count"]}
- reviewed: {metrics["reviewed_candidate_count"]}
- pending: {metrics["pending_candidate_count"]}
- accepted: {metrics["accepted_candidate_count"]}
- rejected: {metrics["rejected_candidate_count"]}
- merges: {report["merge_count"]}
- canonical claims: {report["canonical_claim_count"]}
- candidate acceptance rate: {metrics["candidate_acceptance_rate"]:.3f}
- actual precision (fully supported / reviewed): {metrics["actual_precision"]:.3f}
- claim-evidence entailment accuracy: {metrics["claim_evidence_entailment_accuracy"]:.3f}
- condition preservation accuracy: {metrics["condition_preservation_accuracy"]:.3f}
- overgeneralized claims: {metrics["overgeneralized_claim_count"]}
- claims missing conditions: {metrics["missing_condition_claim_count"]}
- wrong-speaker accepted claims: {metrics["wrong_speaker_accepted_claim_count"]}
- accepted claim verification rate: {metrics["accepted_claim_verification_rate"]:.3f}
- average human review time (seconds): {metrics["average_human_review_seconds"]:.1f}

## Rejection reasons

{chr(10).join(f'- {key}: {value}' for key, value in sorted(report["rejected_reason_counts"].items())) or '- none'}

## Verification priority among accepted candidates

{chr(10).join(f'- {key}: {value}' for key, value in sorted(metrics["risk_priority_counts"].items())) or '- none'}

## Claims requiring wording or condition correction

- overgeneralized claim IDs: {', '.join(report["overgeneralized_claim_ids"]) or 'none'}
- missing-condition claim IDs: {', '.join(report["missing_condition_claim_ids"]) or 'none'}
- trend-changing risk claim IDs: {', '.join(report["trend_changing_risk_claim_ids"]) or 'none'}

## Gate conclusion

Phase 7.2 allowed: **{str(report["phase_7_2_allowed"]).lower()}**. Only `accepted_claims.jsonl` may enter Phase 7.2. Pending and rejected claims remain excluded; open verification status must remain visible and cannot be promoted as a verified fact.
'''


_GOLDEN_REQUIRED = ("gold_claim", "supporting_text", "claim_type", "expected_theme")
_GOLDEN_AUTHOR_FIELDS = (*_GOLDEN_REQUIRED, "why_valuable", "speaker_requirement", "verification_requirement")


def _golden_has_content(row: dict[str, Any]) -> bool:
    times = row.get("supporting_time_range") or []
    return bool(any(str(row.get(key) or "").strip() for key in _GOLDEN_AUTHOR_FIELDS) or row.get("value_types") or row.get("expected_risks") or any(value is not None for value in times))


def _golden_is_complete(row: dict[str, Any]) -> bool:
    times = row.get("supporting_time_range") or []
    return bool(all(str(row.get(key) or "").strip() for key in _GOLDEN_REQUIRED) and len(times) == 2 and all(value is not None for value in times))


def _selected(value: str, current: str) -> str:
    return " selected" if value == current else ""


def _golden_card(row: dict[str, Any], index: int, *, optional: bool) -> str:
    current = str(row.get("review_action") or ("optional" if optional else "pending"))
    if optional and not _golden_has_content(row) and current == "pending":
        current = "optional"
    actions = ("optional", "approve", "edit", "exclude") if optional else ("pending", "approve", "edit", "exclude")
    times = list(row.get("supporting_time_range") or [None, None])
    times += [None] * (2 - len(times))
    return f'''<article class="gold {'optional' if optional else 'populated'}" data-row="{html.escape(json.dumps(row, ensure_ascii=False), quote=True)}"><h2>Golden item {index:02d} · {html.escape(row["selection_source"])}</h2><p class="kind">{html.escape(row["label_kind"])}</p><div class="form"><label>review action <select class="action">{''.join(f'<option{_selected(value, current)}>{value}</option>' for value in actions)}</select></label><label>gold claim <textarea class="claim">{html.escape(str(row.get("gold_claim") or ""))}</textarea></label><label>supporting text <textarea class="support">{html.escape(str(row.get("supporting_text") or ""))}</textarea></label><label>time start <input class="start" type="number" value="{html.escape(str(times[0] if times[0] is not None else ""))}"></label><label>time end <input class="end" type="number" value="{html.escape(str(times[1] if times[1] is not None else ""))}"></label><label>claim type <input class="claim-type" value="{html.escape(str(row.get("claim_type") or ""))}"></label><label>value types <input class="value-types" value="{html.escape(", ".join(row.get("value_types") or []))}"></label><label>expected theme <input class="theme" value="{html.escape(str(row.get("expected_theme") or ""))}"></label><label>why valuable <textarea class="why">{html.escape(str(row.get("why_valuable") or ""))}</textarea></label><label>speaker requirement <input class="speaker" value="{html.escape(str(row.get("speaker_requirement") or ""))}"></label><label>verification requirement <input class="verification" value="{html.escape(str(row.get("verification_requirement") or ""))}"></label><label>expected risks <input class="risks" value="{html.escape(", ".join(row.get("expected_risks") or []))}"></label><label>reviewer note <textarea class="note">{html.escape(str(row.get("reviewer_note") or ""))}</textarea></label></div></article>'''


def generate_phase711_golden_review(*, draft_path: Path, output_dir: Path, reviewed_path: Path | None = None) -> dict[str, Any]:
    """Build or restore a blind golden review without treating empty slots as pending."""
    output_dir.mkdir(parents=True, exist_ok=True)
    completed = reviewed_path or (output_dir / "golden_review_completed.jsonl")
    rows = _read_jsonl(completed) if completed.exists() else []
    if not rows:
        draft = _read_jsonl(draft_path)
        if not draft:
            raise ValueError("golden reviewer draft is empty")
        rows = [{**item, "review_item_id": f"golden_review.existing.{index:03d}", "label_kind": "positive", "selection_source": "existing_reviewer_draft", "review_action": "pending", "system_output_hidden": True, "reviewer_note": "", "change_history": []} for index, item in enumerate(draft, 1)]
        for group, label_kind, count in (("independent_important", "positive", 10), ("hard_negative", "hard_negative", 10), ("background_overestimate", "background_negative", 5)):
            for index in range(1, count + 1):
                rows.append({"review_item_id": f"golden_review.{group}.{index:02d}", "gold_id": f"pending_{group}_{index:02d}", "label_kind": label_kind, "selection_source": group, "review_action": "optional", "gold_claim": "", "claim_type": "", "value_types": [], "supporting_time_range": [None, None], "supporting_text": "", "expected_theme": "", "why_valuable": "", "speaker_requirement": "", "verification_requirement": "", "expected_risks": [], "category": group, "system_output_hidden": True, "reviewer_note": "", "change_history": []})
    populated = [row for row in rows if row.get("selection_source") == "existing_reviewer_draft" and _golden_has_content(row)]
    optional_rows = [row for row in rows if row.get("selection_source") != "existing_reviewer_draft"]
    optional_completed = [row for row in optional_rows if _golden_has_content(row)]
    action_counts = Counter(str(row.get("review_action") or "pending") for row in populated)
    reviewed_count = sum(action_counts[value] for value in ("approve", "edit", "exclude"))
    template = output_dir / "golden_review_template.jsonl"
    _write_jsonl(template, rows)
    existing_cards = [_golden_card(row, index, optional=False) for index, row in enumerate(populated, 1)]
    optional_cards = [_golden_card(row, index, optional=True) for index, row in enumerate(optional_rows, 1)]
    reviewer = next((str(row.get("reviewer") or "") for row in rows if row.get("reviewer")), "")
    version = next((str(row.get("golden_version") or "") for row in rows if row.get("golden_version")), "yc_claim_golden_v2")
    page = output_dir / "golden_review.html"
    page.write_text(f'''<!doctype html><html><head><meta charset="utf-8"><title>Phase 7.1.1 golden review</title><style>body{{font:14px/1.5 system-ui;max-width:1100px;margin:24px auto}}.gold{{border:1px solid #bbb;padding:16px;margin:18px 0;background:#fffdf7}}.optional{{background:#f5f7f9}}.kind{{font-weight:bold}}.form{{display:grid;gap:8px}}.form label{{display:grid;grid-template-columns:190px 1fr;gap:8px}}textarea{{min-height:70px}}.top{{position:sticky;top:0;background:white;padding:12px;border-bottom:1px solid #aaa;z-index:2}}.warning{{background:#fff2cc;padding:10px}}.progress{{display:flex;gap:14px;flex-wrap:wrap;font-weight:600}}details.expansion{{border:1px solid #9aa;padding:12px;background:#eef3f7}}</style></head><body><div class="top"><h1>Phase 7.1.1a — Review and Freeze Existing Golden</h1><p class="warning">System hit/miss status is hidden. This page contains {len(populated)} populated items and {len(optional_rows)} optional empty authoring slots. Optional slots do not count as pending or block freeze.</p><div class="progress"><span>populated: <b id="p-populated">0</b></span><span>reviewed populated: <b id="p-reviewed">0</b></span><span>approved: <b id="p-approved">0</b></span><span>edited: <b id="p-edited">0</b></span><span>excluded: <b id="p-excluded">0</b></span><span>optional expansion completed: <b id="p-optional">0</b></span></div><label>Reviewer <input id="reviewer" value="{html.escape(reviewer, quote=True)}"></label><label> Golden version <input id="version" value="{html.escape(version, quote=True)}"></label><button onclick="downloadGolden()">Download reviewed golden JSONL</button></div><h1>Populated Existing Golden — {len(populated)} populated items</h1>{''.join(existing_cards)}<details class="expansion"><summary><strong>Optional Golden Expansion — {len(optional_rows)} authoring slots (default collapsed, non-blocking)</strong></summary><p>These slots are Phase 7.1.1b material. Leave them empty to exclude them from progress and freeze.</p>{''.join(optional_cards)}</details><script>function values(el){{return el.value.split(',').map(x=>x.trim()).filter(Boolean)}}function content(card){{return card.querySelector('.claim').value.trim()!==''||card.querySelector('.support').value.trim()!==''||card.querySelector('.start').value!==''||card.querySelector('.end').value!==''||card.querySelector('.claim-type').value.trim()!==''||card.querySelector('.theme').value.trim()!==''}}function progress(){{const populated=[...document.querySelectorAll('.gold.populated')].filter(content);const actions=populated.map(x=>x.querySelector('.action').value);document.getElementById('p-populated').textContent=populated.length;document.getElementById('p-reviewed').textContent=actions.filter(x=>['approve','edit','exclude'].includes(x)).length;document.getElementById('p-approved').textContent=actions.filter(x=>x==='approve').length;document.getElementById('p-edited').textContent=actions.filter(x=>x==='edit').length;document.getElementById('p-excluded').textContent=actions.filter(x=>x==='exclude').length;document.getElementById('p-optional').textContent=[...document.querySelectorAll('.gold.optional')].filter(content).length}}document.addEventListener('input',progress);document.addEventListener('change',progress);progress();function downloadGolden(){{const reviewer=document.getElementById('reviewer').value.trim();if(!reviewer){{alert('Reviewer required');return}}const version=document.getElementById('version').value.trim();const now=new Date().toISOString();const rows=[...document.querySelectorAll('.gold')].map(card=>{{const row=JSON.parse(card.dataset.row);row.review_action=card.querySelector('.action').value;row.gold_claim=card.querySelector('.claim').value;row.supporting_text=card.querySelector('.support').value;const start=card.querySelector('.start').value,end=card.querySelector('.end').value;row.supporting_time_range=[start===''?null:Number(start),end===''?null:Number(end)];row.claim_type=card.querySelector('.claim-type').value;row.value_types=values(card.querySelector('.value-types'));row.expected_theme=card.querySelector('.theme').value;row.why_valuable=card.querySelector('.why').value;row.speaker_requirement=card.querySelector('.speaker').value;row.verification_requirement=card.querySelector('.verification').value;row.expected_risks=values(card.querySelector('.risks'));row.reviewer_note=card.querySelector('.note').value;row.reviewer=reviewer;row.golden_version=version;row.reviewed_at=now;row.system_output_hidden=true;row.change_history=[...(row.change_history||[]),{{at:now,reviewer,action:row.review_action,note:row.reviewer_note}}];return row}});const text=rows.map(x=>JSON.stringify(x)).join('\\n')+'\\n';const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{{type:'application/jsonl'}}));a.download='golden_review_completed.jsonl';a.click()}}</script></body></html>''', encoding="utf-8")
    manifest = {"schema_version": GOLDEN_REVIEW_VERSION, "status": "ready_to_freeze" if reviewed_count == len(populated) and 20 <= action_counts["approve"] + action_counts["edit"] <= 25 else "pending_human_review", "input_row_count": len(rows), "populated_item_count": len(populated), "reviewed_populated_item_count": reviewed_count, "approved_count": action_counts["approve"], "edited_count": action_counts["edit"], "excluded_count": action_counts["exclude"], "pending_populated_count": action_counts["pending"], "optional_slot_count": len(optional_rows), "optional_completed_count": len(optional_completed), "system_output_hidden": True, "review_source": str(completed.resolve()) if completed.exists() else str(draft_path.resolve()), "review_html": str(page.resolve()), "review_template": str(template.resolve())}
    (output_dir / "golden_review_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def freeze_phase711_golden(*, reviewed_path: Path, output_path: Path, reviewer: str, golden_version: str) -> dict[str, Any]:
    """Freeze reviewed existing positives; empty expansion templates are ignored."""
    rows = _read_jsonl(reviewed_path)
    if not reviewer.strip() or not golden_version.strip():
        raise ValueError("reviewer and golden_version are required")
    nonempty = [row for row in rows if _golden_has_content(row)]
    incomplete = [row for row in nonempty if not _golden_is_complete(row)]
    if incomplete:
        raise ValueError(f"golden contains {len(incomplete)} partially filled incomplete rows: {', '.join(str(row.get('review_item_id')) for row in incomplete[:5])}")
    existing = [row for row in nonempty if row.get("selection_source") == "existing_reviewer_draft"]
    invalid_actions = [row for row in existing if row.get("review_action") not in {"approve", "edit", "exclude"}]
    if invalid_actions:
        raise ValueError(f"all {len(existing)} populated existing items must be reviewed; pending={len(invalid_actions)}: {', '.join(str(row.get('gold_id')) for row in invalid_actions[:5])}")
    included = [row for row in existing if row.get("review_action") in {"approve", "edit"}]
    if not 20 <= len(included) <= 25:
        raise ValueError(f"YC golden v2 must freeze 20-25 approved/edited existing positives, got {len(included)}")
    for row in existing:
        if row.get("system_output_hidden") is not True:
            raise ValueError(f"golden item was not reviewed blind: {row.get('review_item_id')}")
    frozen_at = _now()
    frozen = [{**row, "schema_version": "phase_7_1_1_frozen_golden_v1", "golden_version": golden_version, "frozen_at": frozen_at, "reviewer": reviewer, "system_output_hidden": True} for row in included]
    if any(not str(row.get("gold_claim") or "").strip() or not str(row.get("supporting_text") or "").strip() for row in frozen):
        raise ValueError("frozen golden cannot contain empty claim or support")
    _write_jsonl(output_path, frozen)
    decisions_path = output_path.parent / "golden_review_decisions.jsonl"
    _write_jsonl(decisions_path, existing)
    optional_completed = [row for row in nonempty if row.get("selection_source") != "existing_reviewer_draft"]
    report = {"schema_version": "phase_7_1_1_golden_freeze_report_v1", "golden_version": golden_version, "frozen_at": frozen_at, "reviewer": reviewer, "system_output_hidden": True, "input_row_count": len(rows), "populated_existing_count": len(existing), "empty_template_ignored_count": len(rows) - len(nonempty), "optional_expansion_completed_count": len(optional_completed), "approved_count": sum(row.get("review_action") == "approve" for row in existing), "edited_count": sum(row.get("review_action") == "edit" for row in existing), "excluded_count": sum(row.get("review_action") == "exclude" for row in existing), "frozen_count": len(frozen), "output": str(output_path.resolve()), "review_decisions": str(decisions_path.resolve())}
    (output_path.parent / "golden_freeze_report.md").write_text(f'''# Golden Freeze Report

- golden version: `{golden_version}`
- input rows: {report["input_row_count"]}
- populated existing items: {report["populated_existing_count"]}
- approved: {report["approved_count"]}
- edited: {report["edited_count"]}
- excluded: {report["excluded_count"]}
- frozen positive golden: {report["frozen_count"]}
- empty optional templates ignored: {report["empty_template_ignored_count"]}
- optional expansion items completed: {report["optional_expansion_completed_count"]}
- system output hidden during review: true

Phase 7.1.1b optional expansion was not required for this freeze.
''', encoding="utf-8")
    (output_path.parent / f"{output_path.stem}.manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def adapt_phase711_golden_review(*, input_path: Path, output_path: Path, reviewer: str) -> dict[str, Any]:
    """Adapt the original 50-row review export to the 7.1.1a/7.1.1b contract.

    This conversion is only valid after the reviewer explicitly confirms that
    populated rows left at the old UI's default ``pending`` mean "unchanged and
    approved".  Empty expansion rows become non-blocking ``optional`` rows.
    The source review export is never modified.
    """
    if not reviewer.strip():
        raise ValueError("reviewer confirmation is required for golden review adaptation")
    rows = _read_jsonl(input_path)
    if not rows:
        raise ValueError("golden review input is empty")
    adapted_at = _now()
    pending_promoted = 0
    empty_optional = 0
    adapted: list[dict[str, Any]] = []
    for row in rows:
        value = dict(row)
        if value.get("selection_source") == "existing_reviewer_draft" and _golden_has_content(value) and value.get("review_action") == "pending":
            value["review_action"] = "approve"
            value["reviewer"] = reviewer
            value["reviewed_at"] = adapted_at
            value["change_history"] = [*(value.get("change_history") or []), {"at": adapted_at, "reviewer": reviewer, "action": "approve", "note": "Reviewer confirmed the prior result is unchanged; legacy pending default adapted to approve."}]
            pending_promoted += 1
        if value.get("selection_source") != "existing_reviewer_draft" and not _golden_has_content(value):
            value["review_action"] = "optional"
            empty_optional += 1
        value["format_version"] = "phase_7_1_1_split_golden_v2"
        adapted.append(value)
    _write_jsonl(output_path, adapted)
    report = {"schema_version": "phase_7_1_1_golden_adaptation_report_v1", "status": "ok", "source": str(input_path.resolve()), "output": str(output_path.resolve()), "input_row_count": len(rows), "populated_existing_count": sum(row.get("selection_source") == "existing_reviewer_draft" and _golden_has_content(row) for row in adapted), "legacy_pending_promoted_to_approve": pending_promoted, "empty_optional_rows_normalized": empty_optional, "reviewer_confirmation": reviewer, "adapted_at": adapted_at}
    (output_path.parent / "golden_review_adaptation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report

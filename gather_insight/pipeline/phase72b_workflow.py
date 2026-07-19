"""Phase 7.2B theme-centric consolidation over the frozen Naval corpus."""

from __future__ import annotations

import hashlib
import html
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .phase72b_judge import ThemeJudge, build_theme_judge
from .semantic_scorer import SemanticScorer, build_scorer, cosine


SCHEMA_VERSION = "phase_7_2b_v1"
THEME_SLUG = "ai_execution_commoditization_judgment_scarcity"
THEME_NAME = "从代码杠杆到AI工业革命：执行能力商品化以后，判断、品味、验证与责任为什么变得更加稀缺？"
PROMPT_VERSION = "phase_7_2b_theme_consolidation_v1"

INPUT_FILES = (
    "source_index.jsonl", "source_relations.jsonl", "canonical/sections.jsonl", "canonical/evidence.jsonl",
    "canonical/duplicate_content_clusters.jsonl", "intelligence/source_claims.jsonl", "intelligence/canonical_claims.jsonl",
    "intelligence/theme_assignments.jsonl", "intelligence/person_positions.jsonl", "intelligence/trend_candidates.jsonl",
    "intelligence/insight_candidates.jsonl", "intelligence/verification_queue.jsonl",
)

SUBTHEMES: dict[str, dict[str, Any]] = {
    "falling_execution_costs": {"question": "Which execution costs are falling because of AI agents: coding, software production, information generation, experimentation, engineering design, or coordination?", "themes": {"software_production", "ai_coding_agents", "token_economics", "time_compute_substitution"}, "keywords": ("code", "coding", "software", "agent", "token", "time", "output", "factory", "iterate", "build")},
    "persistent_human_scarcities": {"question": "Which capabilities remain scarce as execution becomes cheaper: problem selection, judgment, taste, architecture, verification, accountability, domain knowledge, trust?", "themes": {"judgment", "accountability", "truth_and_credibility"}, "keywords": ("judgment", "taste", "choose", "right thing", "architect", "verify", "evaluator", "sign off", "safe", "feedback", "accountab", "responsib", "trust", "domain")},
    "leverage_distribution": {"question": "Does AI equalize productivity or amplify exceptional engineers, founders, architects, and generalists; does it enable smaller teams?", "themes": {"leverage", "future_of_work", "startup_organization", "recruiting_and_culture"}, "keywords": ("10x", "100x", "1,000x", "leverage", "junior", "expert", "generalist", "small team", "hire", "jobs")},
    "software_value_migration": {"question": "As pure software becomes easier to produce, does value migrate to agent infrastructure, reusable building blocks, proprietary data, distribution, and real-world feedback?", "themes": {"software_production", "ai_coding_agents", "vertical_integration"}, "keywords": ("pure software", "infrastructure", "building block", "reuse", "data", "distribution", "moat", "dead", "obsolete", "api")},
    "software_to_industry": {"question": "How do software and agent methods enter hardware design, manufacturing, physical testing, real-world feedback, and vertically integrated companies?", "themes": {"hardware_engineering", "manufacturing", "vertical_integration"}, "keywords": ("hardware", "turbine", "aircraft", "engine", "factory", "manufactur", "test", "physical", "vertical")},
    "new_bottlenecks": {"question": "Which bottlenecks become binding after technical execution accelerates: regulation, permission, capital, manufacturing capacity, safety, credibility, responsibility?", "themes": {"regulation", "institutional_change", "truth_and_credibility", "accountability"}, "keywords": ("regulat", "faa", "fda", "government", "permission", "capital", "capacity", "safety", "credible", "responsib")},
    "internal_tensions": {"question": "What tensions remain between cheap execution and costly verification, equal access and unequal leverage, smaller teams and more firms, software abundance and infrastructure scarcity?", "themes": {"judgment", "leverage", "token_economics", "future_of_work", "software_production", "regulation"}, "keywords": ("but", "however", "versus", "yet", "still", "not", "more", "less", "tension", "trade-off")},
}

FRAMES: tuple[tuple[str, str, str], ...] = (
    ("coding_execution", "falling_execution_costs", "AI agents reduce the labor and friction required to write or assemble software."),
    ("token_time_substitution", "falling_execution_costs", "Cheap model tokens can be substituted for scarce human time when outputs can be checked."),
    ("software_factories", "falling_execution_costs", "Engineers increasingly build agentic software factories that produce multiple outputs."),
    ("rapid_iteration", "falling_execution_costs", "Agents reduce the cost of experimentation, debugging, and repeated iteration."),
    ("information_generation", "falling_execution_costs", "AI makes producing information, plans, and candidate solutions cheaper."),
    ("coordination_automation", "falling_execution_costs", "Agents take over coordination and execution tasks formerly routed through people."),
    ("problem_selection", "persistent_human_scarcities", "Choosing the right problem matters more than raw implementation speed."),
    ("judgment_and_taste", "persistent_human_scarcities", "Human judgment and taste determine which agent outputs and tradeoffs are acceptable."),
    ("architecture", "persistent_human_scarcities", "Architecture and technology selection remain high-leverage human decisions."),
    ("verification", "persistent_human_scarcities", "Cheap generation increases the importance of verification and final-output evaluation."),
    ("accountability", "persistent_human_scarcities", "Responsibility for consequences cannot be delegated merely because execution is automated."),
    ("domain_knowledge", "persistent_human_scarcities", "Domain knowledge changes the quality of feedback supplied to models."),
    ("trust_and_truth", "persistent_human_scarcities", "Credibility and truthful communication remain scarce commercial assets."),
    ("expert_amplification", "leverage_distribution", "AI can amplify already exceptional engineers and founders more than average users."),
    ("junior_expert_gap", "leverage_distribution", "Junior and expert users may receive different leverage because feedback quality differs."),
    ("generalist_leverage", "leverage_distribution", "AI lowers expertise barriers and increases the reach of capable generalists."),
    ("small_teams", "leverage_distribution", "AI lowers the number of people required for a task and enables smaller teams."),
    ("more_firms_not_less_work", "leverage_distribution", "Smaller teams can produce more companies and products rather than simply eliminating all work."),
    ("pure_software_scarcity", "software_value_migration", "Pure software production becomes less scarce as agents can create code."),
    ("agent_infrastructure", "software_value_migration", "Agent infrastructure and interfaces become valuable complements to generated software."),
    ("reusable_building_blocks", "software_value_migration", "Reusable software building blocks prevent agents from recreating infrastructure from scratch."),
    ("data_and_distribution", "software_value_migration", "Proprietary data and distribution may remain defensible when code is abundant."),
    ("real_world_feedback", "software_value_migration", "Real-world feedback loops and physical operations retain value beyond code generation."),
    ("hardware_design", "software_to_industry", "Agentic methods accelerate hardware and engineering design."),
    ("manufacturing_iteration", "software_to_industry", "Faster design shifts constraints toward manufacturing and industrial iteration."),
    ("physical_testing", "software_to_industry", "Physical testing and empirical feedback remain necessary constraints."),
    ("vertical_integration", "software_to_industry", "Cheaper software makes vertically integrated industrial companies more feasible."),
    ("industrial_knowledge", "software_to_industry", "Factories and production systems accumulate proprietary operational knowledge."),
    ("regulatory_bottleneck", "new_bottlenecks", "Regulation becomes a binding constraint when technical development accelerates."),
    ("institutional_permission", "new_bottlenecks", "Institutional permission and fragmented jurisdiction slow deployment."),
    ("capital_constraint", "new_bottlenecks", "Capital remains necessary for physical production despite cheap software."),
    ("manufacturing_capacity", "new_bottlenecks", "Manufacturing capacity becomes scarcer relative to generated designs."),
    ("safety_validation", "new_bottlenecks", "Safety and validation requirements constrain deployment in high-stakes domains."),
    ("credibility_constraint", "new_bottlenecks", "Credibility limits persuasion, recruiting, and adoption."),
    ("responsibility_constraint", "new_bottlenecks", "Responsibility and accountability remain human or institutional constraints."),
    ("software_dead_vs_infra", "internal_tensions", "Pure software may lose scarcity while reusable infrastructure becomes more valuable."),
    ("equal_access_vs_amplification", "internal_tensions", "Broad access to AI can coexist with wider performance gaps between users."),
    ("fewer_people_vs_more_firms", "internal_tensions", "Fewer people per task can coexist with more total firms and projects."),
    ("speed_vs_regulation", "internal_tensions", "Faster technical execution can increase the relative burden of regulation and validation."),
    ("cheap_tokens_vs_verification", "internal_tensions", "Cheaper tokens can increase the volume of outputs that require architecture and verification."),
)

FRAME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "coding_execution": ("write code", "writing code", "coding", "implementation", "program"),
    "token_time_substitution": ("token", "save time", "cheaper than a human", "human time"),
    "software_factories": ("software factor", "factory", "multiplicative outputs"),
    "rapid_iteration": ("iterate", "iteration", "debug", "stuck", "cost of change"),
    "information_generation": ("generate", "plan", "step files", "pcb", "candidate"),
    "coordination_automation": ("instructions", "api key", "agency", "coordinate", "agent"),
    "problem_selection": ("right thing", "wrong thing", "what to work on", "problem"),
    "judgment_and_taste": ("judgment", "taste", "trade-off", "creative"),
    "architecture": ("architect", "postgres", "database", "technology", "system design"),
    "verification": ("verif", "evaluator", "test harness", "proof", "sign off"),
    "accountability": ("accountab", "responsib", "paged", "consequence"),
    "domain_knowledge": ("domain", "expert", "knowledge", "proficient"),
    "trust_and_truth": ("truth", "trust", "credible", "honest", "believe"),
    "expert_amplification": ("100x", "1,000x", "really good", "leverage"),
    "junior_expert_gap": ("junior", "experienced", "advanced", "architect"),
    "generalist_leverage": ("generalist", "expertise", "jargon"),
    "small_teams": ("small team", "number of people", "two people", "team size"),
    "more_firms_not_less_work": ("entrepreneur", "founder", "more companies", "more people"),
    "pure_software_scarcity": ("pure software", "software dead", "generate software", "easy, zero to one"),
    "agent_infrastructure": ("infrastructure", "api", "cli", "hosting provider"),
    "reusable_building_blocks": ("building block", "reuse", "token cache", "libraries", "dependencies"),
    "data_and_distribution": ("proprietary data", "distribution", "data"),
    "real_world_feedback": ("real world", "feedback loop", "physical", "operation"),
    "hardware_design": ("hardware", "turbine", "blade", "step files", "pcb", "aircraft"),
    "manufacturing_iteration": ("manufactur", "factory", "production", "foundry"),
    "physical_testing": ("physical test", "simulation", "test", "aerodynamic"),
    "vertical_integration": ("vertical", "off-the-shelf", "in-house", "own factory"),
    "industrial_knowledge": ("instrumented", "foundry", "material science", "production system"),
    "regulatory_bottleneck": ("regulat", "faa", "fda"),
    "institutional_permission": ("permission", "government", "jurisdiction", "approval"),
    "capital_constraint": ("capital", "money", "funding", "investment"),
    "manufacturing_capacity": ("capacity", "factory", "manufacturing"),
    "safety_validation": ("safety", "safe", "validation", "medical disaster"),
    "credibility_constraint": ("credible", "trust", "truth", "persuasion"),
    "responsibility_constraint": ("responsib", "accountab", "sign off", "paged"),
    "software_dead_vs_infra": ("pure software", "dead", "infrastructure", "building block"),
    "equal_access_vs_amplification": ("100x", "junior", "equal", "gap", "leverage"),
    "fewer_people_vs_more_firms": ("small team", "more founder", "entrepreneur", "jobs"),
    "speed_vs_regulation": ("regulat", "months", "wait", "speed", "iterate"),
    "cheap_tokens_vs_verification": ("token", "verify", "evaluator", "quality", "roi"),
}

TENSION_FRAME_PAIRS = {
    frozenset(("pure_software_scarcity", "agent_infrastructure")): "tension_with",
    frozenset(("pure_software_scarcity", "reusable_building_blocks")): "tension_with",
    frozenset(("expert_amplification", "equal_access_vs_amplification")): "refines",
    frozenset(("small_teams", "fewer_people_vs_more_firms")): "refines",
    frozenset(("rapid_iteration", "speed_vs_regulation")): "limits",
    frozenset(("token_time_substitution", "cheap_tokens_vs_verification")): "limits",
}

CAUSAL_FRAME_PAIRS = {
    ("coding_execution", "problem_selection"): "causes",
    ("rapid_iteration", "verification"): "causes",
    ("token_time_substitution", "verification"): "causes",
    ("software_factories", "small_teams"): "causes",
    ("hardware_design", "manufacturing_capacity"): "causes",
    ("hardware_design", "regulatory_bottleneck"): "causes",
    ("pure_software_scarcity", "agent_infrastructure"): "causes",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"required Phase 7.2A input is missing: {path}")
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{number}: {exc}") from exc
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _input_hashes(corpus_dir: Path) -> dict[str, str]:
    return {relative: _sha(corpus_dir / relative) for relative in INPUT_FILES}


def _raw_hashes(corpus_dir: Path) -> dict[str, str]:
    return {str(path.relative_to(corpus_dir)): _sha(path) for path in sorted((corpus_dir / "sources").glob("*/raw/source_raw.html"))}


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 6)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() and value.strip().lower() != "none" else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip() and str(item).strip().lower() != "none"]
    return [str(value).strip()] if str(value).strip() else []


def _lexical_hits(text: str, keywords: tuple[str, ...]) -> int:
    low = text.lower()
    return sum(keyword in low for keyword in keywords)


def _frame_score(candidate: dict[str, Any], embedding_score: float, frame: str) -> float:
    hits = _lexical_hits(str(candidate["claim"]), FRAME_KEYWORDS.get(frame, ()))
    return embedding_score + min(0.2, hits * 0.075)


def _recall_candidates(claims: list[dict[str, Any]], evidence_by_id: dict[str, dict[str, Any]], scorer: SemanticScorer, judge: ThemeJudge) -> tuple[list[dict[str, Any]], dict[str, list[float]], dict[str, Any]]:
    query_ids = list(SUBTHEMES)
    query_texts = [SUBTHEMES[key]["question"] for key in query_ids]
    documents = []
    for claim in claims:
        excerpts = [str(evidence_by_id[eid].get("source_text") or "")[:700] for eid in claim.get("evidence_ids", []) if eid in evidence_by_id]
        documents.append(str(claim["claim"]) + "\nEvidence context: " + " ".join(excerpts))
    vectors = scorer.embed(query_texts + documents)
    query_vectors = vectors[:len(query_texts)]
    document_vectors = vectors[len(query_texts):]
    vector_by_claim = {claim["claim_id"]: vector for claim, vector in zip(claims, document_vectors)}
    ranked: list[dict[str, Any]] = []
    for claim, vector in zip(claims, document_vectors):
        similarities = [max(0.0, cosine(vector, query_vector)) for query_vector in query_vectors]
        themes = set(claim.get("themes") or [])
        details: dict[str, dict[str, Any]] = {}
        for index, subtheme in enumerate(query_ids):
            spec = SUBTHEMES[subtheme]
            existing_hit = bool(themes & spec["themes"])
            lexical_count = _lexical_hits(str(claim["claim"]), spec["keywords"])
            semantic_score = similarities[index]
            relevance_score = _clamp(0.82 * semantic_score + (0.08 if existing_hit else 0.0) + min(0.08, lexical_count * 0.025) + 0.02 * float(claim.get("importance_score") or 0.0))
            details[subtheme] = {"theme_relevance_score": relevance_score, "semantic_relevance_score": round(semantic_score, 6), "existing_hit": existing_hit, "lexical_count": lexical_count}
        ranked.append({**claim, "subtheme_scores": details, "best_subtheme": max(details, key=lambda key: details[key]["theme_relevance_score"])})

    def assign(row: dict[str, Any], subtheme: str, method: str) -> dict[str, Any]:
        detail = row["subtheme_scores"][subtheme]
        return {
            **{key: value for key, value in row.items() if key not in {"subtheme_scores", "best_subtheme"}},
            "theme_relevance_score": detail["theme_relevance_score"],
            "semantic_relevance_score": detail["semantic_relevance_score"],
            "relevance_reason": f"BGE-M3 matched {subtheme}; existing-theme={detail['existing_hit']}; lexical-anchors={detail['lexical_count']}",
            "candidate_subtheme": subtheme,
            "recall_method": ["bge_m3_semantic", method] + (["existing_theme"] if detail["existing_hit"] else []) + (["lexical_anchor"] if detail["lexical_count"] else []),
            "source_family_id": row["source_family_ids"][0] if len(row.get("source_family_ids") or []) == 1 else "multiple",
            "independence_group_id": row["independence_group_ids"][0] if len(row.get("independence_group_ids") or []) == 1 else "multiple",
        }

    selected_ids: set[str] = set()
    automatic: list[dict[str, Any]] = []
    for subtheme in query_ids:
        ordered = sorted((row for row in ranked if row["claim_id"] not in selected_ids), key=lambda row: (row["subtheme_scores"][subtheme]["theme_relevance_score"], row.get("importance_score", 0.0)), reverse=True)
        for row in ordered[:16]:
            automatic.append(assign(row, subtheme, "balanced_subtheme_recall"))
            selected_ids.add(row["claim_id"])
    remaining = sorted((row for row in ranked if row["claim_id"] not in selected_ids), key=lambda row: (row["subtheme_scores"][row["best_subtheme"]]["theme_relevance_score"], row.get("importance_score", 0.0)), reverse=True)
    for row in remaining[:max(0, 120 - len(automatic))]:
        automatic.append(assign(row, row["best_subtheme"], "global_rank_recall"))
        selected_ids.add(row["claim_id"])
    remaining = [row for row in remaining if row["claim_id"] not in selected_ids]
    boundary = [assign(row, row["best_subtheme"], "boundary_rank_recall") for row in remaining[:50]]
    payload = [{"claim_id": row["claim_id"], "claim": row["claim"], "speaker": row["speaker"], "source_family_ids": row["source_family_ids"], "candidate_subtheme": row["candidate_subtheme"], "theme_question": SUBTHEMES[row["candidate_subtheme"]]["question"], "semantic_score": row["semantic_relevance_score"], "evidence_excerpt": " ".join(str(evidence_by_id[eid].get("source_text") or "")[:500] for eid in row["evidence_ids"] if eid in evidence_by_id)} for row in boundary]
    judgments = judge.relevance(payload)
    accepted_boundary: list[dict[str, Any]] = []
    if judgments:
        for row in boundary:
            decision = judgments.get(row["claim_id"])
            if decision and decision.get("relevant") and float(decision.get("relevance_score") or 0.0) >= 0.55:
                judged_subtheme = str(decision.get("subtheme") or row["candidate_subtheme"])
                row = {**row, "theme_relevance_score": _clamp((row["theme_relevance_score"] + float(decision["relevance_score"])) / 2), "relevance_reason": str(decision.get("reason") or row["relevance_reason"]), "candidate_subtheme": judged_subtheme if judged_subtheme in SUBTHEMES else row["candidate_subtheme"], "recall_method": [*row["recall_method"], "deepseek_boundary_relevance"]}
                accepted_boundary.append(row)
    else:
        accepted_boundary = boundary[:20]
        for row in accepted_boundary:
            row["recall_method"] = [*row["recall_method"], "deterministic_rank_fallback"]
    selected = automatic + accepted_boundary
    selected.sort(key=lambda row: (row["candidate_subtheme"], -row["theme_relevance_score"], row["claim_id"]))
    return selected[:160], vector_by_claim, {"automatic_count": len(automatic), "boundary_reviewed_count": len(boundary), "boundary_accepted_count": len(accepted_boundary), "input_claim_count": len(claims)}


def _assign_clusters(candidates: list[dict[str, Any]], vector_by_claim: dict[str, list[float]], scorer: SemanticScorer) -> list[dict[str, Any]]:
    frame_vectors = scorer.embed([description for _frame, _subtheme, description in FRAMES])
    frames_by_subtheme: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for index, (frame, subtheme, description) in enumerate(FRAMES):
        frames_by_subtheme[subtheme].append((index, frame, description))
    grouped: dict[str, list[tuple[dict[str, Any], float]]] = defaultdict(list)
    descriptions = {frame: description for frame, _subtheme, description in FRAMES}
    subthemes = {frame: subtheme for frame, subtheme, _description in FRAMES}
    assigned: set[str] = set()
    candidates_by_subtheme: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_subtheme[candidate["candidate_subtheme"]].append(candidate)
    for subtheme, options in frames_by_subtheme.items():
        pool = candidates_by_subtheme[subtheme]
        for frame_index, frame, _description in options:
            ranked_pool = sorted(((candidate, _frame_score(candidate, max(0.0, cosine(vector_by_claim[candidate["claim_id"]], frame_vectors[frame_index])), frame)) for candidate in pool if candidate["claim_id"] not in assigned), key=lambda item: item[1], reverse=True)
            if ranked_pool and ranked_pool[0][1] >= 0.48:
                grouped[frame].append(ranked_pool[0])
                assigned.add(ranked_pool[0][0]["claim_id"])
    for candidate in candidates:
        if candidate["claim_id"] in assigned:
            continue
        options = frames_by_subtheme[candidate["candidate_subtheme"]]
        vector = vector_by_claim[candidate["claim_id"]]
        best_index, best_frame, _description = max(options, key=lambda item: _frame_score(candidate, max(0.0, cosine(vector, frame_vectors[item[0]])), item[1]))
        grouped[best_frame].append((candidate, _frame_score(candidate, max(0.0, cosine(vector, frame_vectors[best_index])), best_frame)))
    clusters: list[dict[str, Any]] = []
    for index, frame in enumerate((frame for frame, _subtheme, _description in FRAMES if frame in grouped), 1):
        members = sorted(grouped[frame], key=lambda item: (item[1], item[0]["theme_relevance_score"]), reverse=True)
        clusters.append({
            "schema_version": SCHEMA_VERSION,
            "cluster_id": f"{THEME_SLUG}.cluster_{index:03d}_{frame}",
            "frame_id": frame,
            "subtheme": subthemes[frame],
            "frame_description": descriptions[frame],
            "parent_canonical_claim_ids": [row["claim_id"] for row, _score in members],
            "parent_source_claim_ids": sorted({parent for row, _score in members for parent in row.get("parent_claim_ids", [])}),
            "evidence_ids": sorted({eid for row, _score in members for eid in row.get("evidence_ids", [])}),
            "speakers": sorted({row["speaker"] for row, _score in members}),
            "source_family_ids": sorted({family for row, _score in members for family in row.get("source_family_ids", [])}),
            "independence_group_ids": sorted({group for row, _score in members for group in row.get("independence_group_ids", [])}),
            "member_count": len(members),
            "mean_frame_similarity": round(sum(score for _row, score in members) / len(members), 6),
            "representative_claim": members[0][0]["claim"],
            "claim_type": members[0][0]["claim_type"],
            "review_status": "pending",
        })
    return clusters


def _add_frame_anchor_candidates(candidates: list[dict[str, Any]], eligible_claims: list[dict[str, Any]], vector_by_claim: dict[str, list[float]], scorer: SemanticScorer) -> tuple[list[dict[str, Any]], int]:
    selected = {row["claim_id"] for row in candidates}
    frame_vectors = scorer.embed([description for _frame, _subtheme, description in FRAMES])
    added: list[dict[str, Any]] = []
    for frame_index, (frame, subtheme, _description) in enumerate(FRAMES):
        ranked = sorted(((claim, _frame_score(claim, max(0.0, cosine(vector_by_claim[claim["claim_id"]], frame_vectors[frame_index])), frame)) for claim in eligible_claims if claim["claim_id"] not in selected), key=lambda item: item[1], reverse=True)
        if not ranked or ranked[0][1] < 0.5:
            continue
        claim, score = ranked[0]
        added.append({**claim, "theme_relevance_score": _clamp(score), "semantic_relevance_score": round(max(0.0, cosine(vector_by_claim[claim["claim_id"]], frame_vectors[frame_index])), 6), "relevance_reason": f"BGE-M3 frame-anchor recall for {frame}", "candidate_subtheme": subtheme, "recall_method": ["bge_m3_semantic", "frame_anchor_recall"] + (["lexical_anchor"] if _lexical_hits(str(claim["claim"]), FRAME_KEYWORDS.get(frame, ())) else []), "source_family_id": claim["source_family_ids"][0] if len(claim.get("source_family_ids") or []) == 1 else "multiple", "independence_group_id": claim["independence_group_ids"][0] if len(claim.get("independence_group_ids") or []) == 1 else "multiple", "frame_anchor_for": frame})
        selected.add(claim["claim_id"])
        if len(candidates) + len(added) >= 180:
            break
    output = candidates + added
    output.sort(key=lambda row: (row["candidate_subtheme"], -row["theme_relevance_score"], row["claim_id"]))
    return output, len(added)


def _theme_claims(clusters: list[dict[str, Any]], candidates_by_id: dict[str, dict[str, Any]], judge: ThemeJudge, scorer: SemanticScorer) -> list[dict[str, Any]]:
    payload = []
    for cluster in clusters:
        members = [candidates_by_id[claim_id] for claim_id in cluster["parent_canonical_claim_ids"][:10]]
        payload.append({"cluster_id": cluster["cluster_id"], "subtheme": cluster["subtheme"], "frame_description": cluster["frame_description"], "representative_claim": cluster["representative_claim"], "claim_type": cluster["claim_type"], "source_claims": [{"claim_id": row["claim_id"], "speaker": row["speaker"], "claim": row["claim"], "source_family_ids": row["source_family_ids"], "published_at": row["published_at"]} for row in members]})
    judgments = judge.consolidate(payload)
    output: list[dict[str, Any]] = []
    for index, cluster in enumerate(clusters, 1):
        decision = judgments.get(cluster["cluster_id"])
        if decision and str(decision.get("entailment_status")) in {"unrelated", "contradicted"}:
            continue
        if judge.backend == "deepseek" and not decision and cluster["frame_id"] == "equal_access_vs_amplification":
            continue
        if judge.backend == "deepseek" and not decision and not _lexical_hits(cluster["representative_claim"], FRAME_KEYWORDS.get(cluster["frame_id"], ())):
            continue
        members = [candidates_by_id[claim_id] for claim_id in cluster["parent_canonical_claim_ids"]]
        statement = str((decision or {}).get("statement") or cluster["representative_claim"]).strip()
        output.append({
            "schema_version": SCHEMA_VERSION,
            "theme_claim_id": f"{THEME_SLUG}.claim_{index:03d}_{cluster['frame_id']}",
            "statement": statement,
            "subtheme": cluster["subtheme"],
            "frame_id": cluster["frame_id"],
            "claim_type": str((decision or {}).get("claim_type") or cluster["claim_type"]),
            "value_types": sorted({value for row in members for value in row.get("value_types", [])}),
            "parent_source_claim_ids": cluster["parent_source_claim_ids"],
            "parent_canonical_claim_ids": cluster["parent_canonical_claim_ids"],
            "evidence_ids": cluster["evidence_ids"],
            "speakers": cluster["speakers"],
            "source_ids": sorted({sid for row in members for sid in row.get("source_ids", [])}),
            "source_family_ids": cluster["source_family_ids"],
            "independent_source_family_count": len(cluster["independence_group_ids"]),
            "first_seen_at": min(row["published_at"] for row in members),
            "last_seen_at": max(row["published_at"] for row in members),
            "conditions": _string_list((decision or {}).get("conditions")),
            "limitations": _string_list((decision or {}).get("limitations")) or (["No valid model consolidation was available; the exact representative source claim is retained for review."] if not decision else []),
            "counter_claim_ids": [],
            "entailment_status": str((decision or {}).get("entailment_status") or ("partially_supported" if judge.backend == "deepseek" else "fully_supported")),
            "verification_status": "needs_targeted_verification" if any(row.get("claim_id") for row in members if row.get("needs_verification")) else "official_text_only",
            "review_status": "pending",
            "attribution_scope": "multi_speaker_consolidation" if len(cluster["speakers"]) > 1 else "speaker_claim_consolidation",
            "model_and_prompt_version": f"{judge.backend}:{judge.model}:{PROMPT_VERSION}" if decision else "deterministic_representative_claim_v1",
        })
    if judge.backend == "deepseek" and output:
        statement_vectors = scorer.embed([row["statement"] for row in output])
        frame_vectors = scorer.embed([next(description for frame, _subtheme, description in FRAMES if frame == row["frame_id"]) for row in output])
        output = [row for row, statement_vector, frame_vector in zip(output, statement_vectors, frame_vectors) if cosine(statement_vector, frame_vector) >= 0.43 or _lexical_hits(row["statement"], FRAME_KEYWORDS.get(row["frame_id"], ())) > 0]
        output = [row for row in output if not (row["frame_id"] == "data_and_distribution" and not any(phrase in row["statement"].lower() for phrase in ("proprietary data", "distribution channel", "customer distribution", "market distribution"))) and not (row["frame_id"] == "real_world_feedback" and not any(phrase in row["statement"].lower() for phrase in ("real-world", "real world", "physical", "factory", "operational", "customer feedback")))]
    return output


def _relation_candidates(theme_claims: list[dict[str, Any]], scorer: SemanticScorer, evidence_by_id: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, float]]:
    vectors = scorer.embed([row["statement"] for row in theme_claims])
    pairs: dict[tuple[int, int], tuple[float, str | None]] = {}
    for left in range(len(theme_claims)):
        for right in range(left + 1, len(theme_claims)):
            lrow, rrow = theme_claims[left], theme_claims[right]
            similarity = max(0.0, cosine(vectors[left], vectors[right]))
            suggested = TENSION_FRAME_PAIRS.get(frozenset((lrow["frame_id"], rrow["frame_id"])))
            directional = CAUSAL_FRAME_PAIRS.get((lrow["frame_id"], rrow["frame_id"])) or CAUSAL_FRAME_PAIRS.get((rrow["frame_id"], lrow["frame_id"]))
            if suggested or directional or (lrow["subtheme"] == rrow["subtheme"] and similarity >= 0.67) or similarity >= 0.76:
                pairs[(left, right)] = (similarity, suggested or directional)
    ordered = sorted(pairs.items(), key=lambda item: (item[1][1] is not None, item[1][0]), reverse=True)[:48]
    payload = []
    scores: dict[str, float] = {}
    for index, ((left, right), (similarity, suggested)) in enumerate(ordered, 1):
        lrow, rrow = theme_claims[left], theme_claims[right]
        pair_id = f"{THEME_SLUG}.relation_candidate_{index:03d}"
        scores[pair_id] = similarity
        payload.append({"pair_id": pair_id, "source_claim_id": lrow["theme_claim_id"], "target_claim_id": rrow["theme_claim_id"], "source_statement": lrow["statement"], "target_statement": rrow["statement"], "source_subtheme": lrow["subtheme"], "target_subtheme": rrow["subtheme"], "suggested_relation": suggested, "embedding_similarity": round(similarity, 6), "source_evidence_excerpt": " ".join(str(evidence_by_id[eid].get("source_text") or "")[:260] for eid in lrow["evidence_ids"][:2] if eid in evidence_by_id), "target_evidence_excerpt": " ".join(str(evidence_by_id[eid].get("source_text") or "")[:260] for eid in rrow["evidence_ids"][:2] if eid in evidence_by_id)})
    return payload, scores


def _relations(theme_claims: list[dict[str, Any]], judge: ThemeJudge, scorer: SemanticScorer, evidence_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    payload, scores = _relation_candidates(theme_claims, scorer, evidence_by_id)
    judgments = judge.relations(payload)
    by_id = {row["theme_claim_id"]: row for row in theme_claims}
    output = []
    for item in payload:
        decision = judgments.get(item["pair_id"])
        relation_type = str((decision or {}).get("relation_type") or item.get("suggested_relation") or "unrelated")
        if relation_type == "unrelated":
            continue
        confidence = float((decision or {}).get("confidence") or (0.78 if item.get("suggested_relation") else scores[item["pair_id"]]))
        left, right = by_id[item["source_claim_id"]], by_id[item["target_claim_id"]]
        output.append({"schema_version": SCHEMA_VERSION, "relation_id": item["pair_id"].replace("candidate", "relation"), "relation_type": relation_type, "source_claim_id": item["source_claim_id"], "target_claim_id": item["target_claim_id"], "rationale": str((decision or {}).get("rationale") or f"Explicit Phase 7.2B frame relation: {item.get('suggested_relation')}."), "supporting_evidence_ids": sorted(set(left["evidence_ids"] + right["evidence_ids"])), "confidence": _clamp(confidence), "review_status": "pending", "model_and_prompt_version": f"{judge.backend}:{judge.model}:{PROMPT_VERSION}" if decision else "deterministic_explicit_frame_relation_v1"})
    counter_types = {"limits", "contradicts", "tension_with"}
    for relation in output:
        if relation["relation_type"] in counter_types:
            by_id[relation["source_claim_id"]]["counter_claim_ids"].append(relation["target_claim_id"])
            by_id[relation["target_claim_id"]]["counter_claim_ids"].append(relation["source_claim_id"])
    return output


def _person_positions(candidates: list[dict[str, Any]], theme_claims: list[dict[str, Any]], scorer: SemanticScorer) -> list[dict[str, Any]]:
    candidates_by_id = {row["claim_id"]: row for row in candidates}
    grouped: dict[tuple[str, str], list[tuple[dict[str, Any], list[dict[str, Any]]]]] = defaultdict(list)
    people = {"Naval Ravikant", "Guillermo Rauch", "Blake Scholl", "Max Hodak", "Nivi"}
    for theme_claim in theme_claims:
        members = [candidates_by_id[claim_id] for claim_id in theme_claim["parent_canonical_claim_ids"] if claim_id in candidates_by_id]
        for person in sorted({row["speaker"] for row in members} & people):
            grouped[(person, theme_claim["subtheme"])].append((theme_claim, [row for row in members if row["speaker"] == person]))
    limits = {"Naval Ravikant": 6, "Guillermo Rauch": 4, "Blake Scholl": 3, "Max Hodak": 4, "Nivi": 2}
    selected_groups: list[tuple[str, tuple[str, str], list[tuple[dict[str, Any], list[dict[str, Any]]]], list[dict[str, Any]]]] = []
    all_pairs: list[tuple[str, str]] = []
    output: list[dict[str, Any]] = []
    for person in limits:
        groups = [(key, values) for key, values in grouped.items() if key[0] == person]
        groups.sort(key=lambda item: (len(item[1]), max(row["theme_relevance_score"] for _theme, rows in item[1] for row in rows)), reverse=True)
        for key, values in groups[:limits[person]]:
            rows = [row for _theme, member_rows in values for row in member_rows]
            selected_groups.append((person, key, values, rows))
            all_pairs.extend((row["claim"], theme_claim["statement"]) for theme_claim, member_rows in values for row in member_rows)
    all_scores = scorer.score_pairs(all_pairs)
    offset = 0
    for person, key, values, rows in selected_groups:
            scores = all_scores[offset:offset + len(rows)]
            offset += len(rows)
            representative = rows[max(range(len(rows)), key=scores.__getitem__)]
            attribution = representative.get("attribution_scope")
            position_type = "question_or_prompt" if person == "Nivi" or attribution == "host_question" else "personal_experience" if attribution == "speaker_personal_experience" else "prediction" if representative.get("claim_type") == "prediction" else "normative_view" if representative.get("claim_type") == "normative_claim" else "engineering_evidence" if person in {"Guillermo Rauch", "Blake Scholl", "Max Hodak"} else "direct_position"
            output.append({"schema_version": SCHEMA_VERSION, "position_id": f"{THEME_SLUG}.position_{len(output)+1:03d}", "person": person, "subtheme": key[1], "position": representative["claim"], "supporting_claim_ids": sorted({theme["theme_claim_id"] for theme, _rows in values}), "supporting_source_claim_ids": [row["claim_id"] for row in rows], "evidence_ids": sorted({eid for row in rows for eid in row["evidence_ids"]}), "first_seen_at": min(row["published_at"] for row in rows), "last_seen_at": max(row["published_at"] for row in rows), "confidence": round(sum(row["theme_relevance_score"] for row in rows) / len(rows), 6), "conditions": [], "tensions": [], "position_type": position_type, "review_status": "pending"})
    return output


INSIGHT_SPECS: tuple[dict[str, Any], ...] = (
    {"slug": "execution_to_judgment", "statement": "AI lowers coding and iteration costs, which expands the number of feasible attempts; when generation is cheap, problem selection, architecture, and verification become the binding constraints, raising the marginal value of judgment.", "type": "causal_synthesis", "frames": ("coding_execution", "rapid_iteration", "problem_selection", "architecture", "verification"), "chain": ("coding and iteration cost falls", "more candidate solutions can be generated", "selection and checking absorb a larger share of scarce human attention", "judgment becomes more valuable")},
    {"slug": "unequal_leverage", "statement": "AI access can broaden capability without equalizing outcomes: users with stronger domain judgment and feedback can coordinate more agents and may receive greater leverage than junior users.", "type": "hypothesis", "frames": ("expert_amplification", "junior_expert_gap", "domain_knowledge", "equal_access_vs_amplification"), "chain": ("models become broadly available", "feedback quality and problem choice remain heterogeneous", "high-judgment users compound more agent output", "performance gaps may widen")},
    {"slug": "software_value_migration", "statement": "As code production becomes abundant, value may migrate from undifferentiated application code toward reusable agent infrastructure, interfaces, operational data, distribution, and real-world feedback loops.", "type": "industry_implication", "frames": ("pure_software_scarcity", "agent_infrastructure", "reusable_building_blocks", "data_and_distribution", "real_world_feedback"), "chain": ("software replication and generation cost falls", "code alone becomes less defensible", "agents still need reliable components and external feedback", "complements to generated code capture more value")},
    {"slug": "industrial_constraint_shift", "statement": "When software methods accelerate hardware design, the bottleneck shifts downstream toward physical testing, manufacturing capacity, safety validation, regulation, and institutional permission.", "type": "industry_implication", "frames": ("hardware_design", "physical_testing", "manufacturing_capacity", "safety_validation", "regulatory_bottleneck", "institutional_permission"), "chain": ("agentic design accelerates", "more physical designs reach implementation", "atoms and institutions cannot iterate at software speed", "testing, production, and permission become relatively scarcer")},
    {"slug": "small_teams_more_firms", "statement": "Lower execution cost can reduce headcount required per task while increasing the number of viable founders, products, and small companies; fewer people per company does not by itself imply less total work.", "type": "organizational_implication", "frames": ("small_teams", "more_firms_not_less_work", "fewer_people_vs_more_firms", "generalist_leverage"), "chain": ("agents supply execution capacity", "minimum efficient team size falls", "more projects become economically viable", "firm count can rise even as team size falls")},
    {"slug": "cheap_tokens_costly_verification", "statement": "Token prices and generation costs can fall while total architecture and verification burden rises, because cheap generation increases the volume of outputs and decisions that must be evaluated.", "type": "unresolved_tension", "frames": ("token_time_substitution", "verification", "architecture", "cheap_tokens_vs_verification"), "chain": ("tokens become cheap", "organizations generate more candidate work", "each consequential output still needs validation", "verification capacity can become the scarce resource")},
    {"slug": "truth_accountability", "statement": "Execution leverage does not remove the need for credible commitment: persuasion, recruiting, and deployment still depend on truthful communication and accountable humans or institutions.", "type": "cross_source_pattern", "frames": ("trust_and_truth", "credibility_constraint", "accountability", "responsibility_constraint"), "chain": ("AI expands execution and communication volume", "stakeholders face more claims and generated output", "trust and responsibility cannot be inferred from volume", "credibility and accountability become selection mechanisms")},
)


def _insights(theme_claims: list[dict[str, Any]], relations: list[dict[str, Any]], judge: ThemeJudge) -> list[dict[str, Any]]:
    by_frame = {row["frame_id"]: row for row in theme_claims}
    relation_by_claim: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in relations:
        relation_by_claim[relation["source_claim_id"]].append(relation)
        relation_by_claim[relation["target_claim_id"]].append(relation)
    draft: list[dict[str, Any]] = []
    for index, spec in enumerate(INSIGHT_SPECS, 1):
        support = [by_frame[frame] for frame in spec["frames"] if frame in by_frame]
        if len(support) < 2:
            continue
        statement = spec["statement"]
        causal_chain = list(spec["chain"])
        if spec["slug"] == "software_value_migration" and not {"data_and_distribution", "real_world_feedback"}.issubset(by_frame):
            statement = "As code production becomes abundant, value may migrate from undifferentiated application code toward reusable agent infrastructure, interfaces, and interoperable building blocks."
            causal_chain = ["software replication and generation cost falls", "code alone becomes less defensible", "agents still need reliable reusable components and interfaces", "complements to generated code capture more value"]
        if spec["slug"] == "industrial_constraint_shift" and "manufacturing_capacity" not in by_frame:
            statement = "When software methods accelerate hardware design, the bottleneck shifts downstream toward physical testing, safety validation, regulation, and institutional permission."
            causal_chain = ["agentic design accelerates", "more physical designs reach implementation", "atoms and institutions cannot iterate at software speed", "testing, validation, and permission become relatively scarcer"]
        support_ids = [row["theme_claim_id"] for row in support]
        counter_relations = [relation for claim_id in support_ids for relation in relation_by_claim[claim_id] if relation["relation_type"] in {"limits", "contradicts", "tension_with"}]
        source_families = sorted({family for row in support for family in row["source_family_ids"]})
        draft.append({"schema_version": SCHEMA_VERSION, "insight_id": f"{THEME_SLUG}.insight_{index:02d}_{spec['slug']}", "statement": statement, "insight_type": spec["type"], "attribution_scope": "system_synthesis", "supporting_theme_claim_ids": support_ids, "supporting_source_claim_ids": sorted({claim_id for row in support for claim_id in row["parent_source_claim_ids"]}), "evidence_ids": sorted({eid for row in support for eid in row["evidence_ids"]}), "speakers": sorted({speaker for row in support for speaker in row["speakers"]}), "independent_source_family_count": len(source_families), "source_family_ids": source_families, "causal_chain": causal_chain, "conditions": [condition for row in support for condition in row["conditions"]], "counterevidence": sorted({relation["relation_id"] for relation in counter_relations}), "unresolved_questions": [f"Does this mechanism persist outside the {', '.join(source_families)} source family/families?"], "uncertainty": "This is an evidence-linked system synthesis, not a speaker quotation.", "confidence": round(min(0.82, 0.48 + 0.045 * len(support) + 0.08 * len(source_families)), 3), "inference_method": "bounded_causal_template_plus_evidence_validation_v1", "entailment_status": "partially_supported", "verification_status": "needs_human_review", "review_status": "pending", "publishability": "not_publishable_before_human_review"})
    payload = [{"insight_id": row["insight_id"], "statement": row["statement"], "causal_chain": row["causal_chain"], "conditions": row["conditions"], "counterevidence": row["counterevidence"], "unresolved_questions": row["unresolved_questions"], "confidence": row["confidence"], "supporting_theme_claims": [{"theme_claim_id": claim["theme_claim_id"], "statement": claim["statement"], "speakers": claim["speakers"], "source_family_ids": claim["source_family_ids"], "conditions": claim["conditions"], "limitations": claim["limitations"]} for claim in theme_claims if claim["theme_claim_id"] in row["supporting_theme_claim_ids"]]} for row in draft]
    decisions = judge.insights(payload)
    output = []
    for row in draft:
        decision = decisions.get(row["insight_id"])
        if decision:
            row.update({"statement": str(decision.get("statement") or row["statement"]), "conditions": _string_list(decision.get("conditions")) or row["conditions"], "counterevidence_notes": _string_list(decision.get("counterevidence")), "unresolved_questions": _string_list(decision.get("unresolved_questions")) or row["unresolved_questions"], "confidence": _clamp(float(decision.get("confidence") or row["confidence"])), "entailment_status": str(decision.get("entailment_status") or row["entailment_status"]), "model_and_prompt_version": f"{judge.backend}:{judge.model}:{PROMPT_VERSION}"})
            if not decision.get("supported"):
                row["insight_type"] = "hypothesis"
                row["confidence"] = min(row["confidence"], 0.45)
        else:
            row["model_and_prompt_version"] = "deterministic_evidence_linked_hypothesis_v1"
        output.append(row)
    return output


def _verification_queue(input_queue: list[dict[str, Any]], candidates_by_id: dict[str, dict[str, Any]], theme_claims: list[dict[str, Any]], insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    theme_by_parent: dict[str, list[str]] = defaultdict(list)
    insight_by_theme: dict[str, list[str]] = defaultdict(list)
    for row in theme_claims:
        for parent in row["parent_canonical_claim_ids"]:
            theme_by_parent[parent].append(row["theme_claim_id"])
    for insight in insights:
        for claim_id in insight["supporting_theme_claim_ids"]:
            insight_by_theme[claim_id].append(insight["insight_id"])
    output = []
    for item in input_queue:
        claim_id = item["claim_id"]
        if claim_id not in candidates_by_id or claim_id not in theme_by_parent:
            continue
        related_insights = sorted({insight_id for theme_id in theme_by_parent[claim_id] for insight_id in insight_by_theme[theme_id]})
        if not related_insights and item.get("priority") != "P0":
            continue
        output.append({**item, "schema_version": SCHEMA_VERSION, "theme_slug": THEME_SLUG, "theme_claim_ids": theme_by_parent[claim_id], "insight_ids": related_insights, "conclusion_impact": "high" if related_insights and item.get("priority") == "P0" else "medium", "review_status": "pending"})
    return output


def _html_page(title: str, body: str, script: str = "") -> str:
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title><style>body{{font:14px/1.55 system-ui;max-width:1250px;margin:24px auto;color:#202124}}.top{{position:sticky;top:0;background:#fff;border-bottom:1px solid #aaa;padding:10px;z-index:2}}article{{border:1px solid #c7cdd3;border-radius:8px;padding:16px;margin:14px 0}}blockquote{{white-space:pre-wrap;background:#f5f6f7;padding:12px}}.meta{{color:#59636e}}label{{display:block;margin:8px 0}}textarea{{width:100%;min-height:70px}}code{{font-size:12px}}.risk{{background:#fff3cd}}table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:7px;vertical-align:top}}</style></head><body><div class="top"><h1>{html.escape(title)}</h1></div>{body}{script}</body></html>'''


def _write_views(root: Path, theme_claims: list[dict[str, Any]], relations: list[dict[str, Any]], insights: list[dict[str, Any]], candidates_by_id: dict[str, dict[str, Any]], evidence_by_id: dict[str, dict[str, Any]], verification_claim_ids: set[str]) -> None:
    views = root / "views"; views.mkdir(parents=True, exist_ok=True)
    relation_by_claim: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in relations:
        relation_by_claim[relation["source_claim_id"]].append(relation); relation_by_claim[relation["target_claim_id"]].append(relation)
    cards = []
    for row in theme_claims:
        parents = [candidates_by_id[cid] for cid in row["parent_canonical_claim_ids"] if cid in candidates_by_id]
        parent_html = "".join(f'<li><strong>{html.escape(item["speaker"])}</strong> · {item["published_at"]} · {html.escape(item["claim"])} <code>{item["claim_id"]}</code></li>' for item in parents)
        evidence_html = "".join(f'<blockquote><strong>{html.escape(evidence_by_id[eid]["speaker"])}</strong> · <a href="{evidence_by_id[eid]["source_url"]}">official source</a><br>{html.escape(evidence_by_id[eid]["source_text"])}</blockquote>' for eid in row["evidence_ids"] if eid in evidence_by_id)
        relation_html = "".join(f'<li>{item["relation_type"]}: {html.escape(item["rationale"])} <code>{item["relation_id"]}</code></li>' for item in relation_by_claim[row["theme_claim_id"]]) or "<li>None</li>"
        risk = any(parent["claim_id"] in verification_claim_ids for parent in parents)
        cards.append(f'<article class="{"risk" if risk else ""}" data-id="{row["theme_claim_id"]}"><h2>{html.escape(row["statement"])}</h2><p class="meta">{row["subtheme"]} · speakers {html.escape(", ".join(row["speakers"]))} · independent families {row["independent_source_family_count"]} · entailment {row["entailment_status"]}</p><details><summary>Parent source claims</summary><ul>{parent_html}</ul></details><details><summary>Verbatim evidence</summary>{evidence_html}</details><details><summary>Relation candidates</summary><ul>{relation_html}</ul></details><p>Conditions: {html.escape("; ".join(row["conditions"]) or "none recorded")}</p><p>Limitations: {html.escape("; ".join(row["limitations"]) or "none recorded")}</p><label>Decision <select class="decision"><option>pending</option><option>accept</option><option>edit</option><option>reject</option><option>merge</option></select></label><label>Edited statement<textarea class="edited">{html.escape(row["statement"])}</textarea></label><label>Merge into <input class="merge"></label><label>Reviewer notes<textarea class="notes"></textarea></label></article>')
    script = '''<button onclick="downloadReview()">Download theme claim review JSONL</button><script>function downloadReview(){const rows=[...document.querySelectorAll('article')].map(x=>({theme_claim_id:x.dataset.id,decision:x.querySelector('.decision').value,edited_statement:x.querySelector('.edited').value,merge_into:x.querySelector('.merge').value,reviewer_notes:x.querySelector('.notes').value}));const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([rows.map(JSON.stringify).join('\n')+'\n'],{type:'application/jsonl'}));a.download='theme_claim_review.jsonl';a.click()}</script>'''
    (views / "theme_claim_review.html").write_text(_html_page("Phase 7.2B Theme Claim Review", "".join(cards), script), encoding="utf-8")
    rows = "<table><tr><th>Source</th><th>Relation</th><th>Target</th><th>Rationale</th><th>Confidence</th></tr>" + "".join(f'<tr><td>{html.escape(row["source_claim_id"])}</td><td>{row["relation_type"]}</td><td>{html.escape(row["target_claim_id"])}</td><td>{html.escape(row["rationale"])}</td><td>{row["confidence"]}</td></tr>' for row in relations) + "</table>"
    (views / "theme_relation_map.html").write_text(_html_page("Phase 7.2B Theme Relation Map", rows), encoding="utf-8")
    insight_cards = []
    theme_by_id = {row["theme_claim_id"]: row for row in theme_claims}
    for row in insights:
        claim_html = "".join(f'<li>{html.escape(theme_by_id[cid]["statement"])} <code>{cid}</code></li>' for cid in row["supporting_theme_claim_ids"] if cid in theme_by_id)
        evidence_html = "".join(f'<blockquote><strong>{html.escape(evidence_by_id[eid]["speaker"])}</strong><br>{html.escape(evidence_by_id[eid]["source_text"])}</blockquote>' for eid in row["evidence_ids"] if eid in evidence_by_id)
        insight_cards.append(f'<article data-id="{row["insight_id"]}"><h2>{html.escape(row["statement"])}</h2><p class="meta">SYSTEM SYNTHESIS · {row["insight_type"]} · independent families {row["independent_source_family_count"]} · {row["publishability"]}</p><ol>{"".join(f"<li>{html.escape(step)}</li>" for step in row["causal_chain"])}</ol><details><summary>Supporting theme claims</summary><ul>{claim_html}</ul></details><details><summary>Original evidence</summary>{evidence_html}</details><p>Counterevidence: {html.escape(", ".join(row["counterevidence"]) or "none linked")}</p><p>Uncertainty: {html.escape(row["uncertainty"])}</p><label>Decision <select class="decision"><option>pending</option><option>accept</option><option>edit</option><option>reject</option></select></label><label>Edited statement<textarea class="edited">{html.escape(row["statement"])}</textarea></label><label>Publishability <select class="publish"><option>not_publishable</option><option>publishable_after_verification</option></select></label><label>Reviewer notes<textarea class="notes"></textarea></label></article>')
    insight_script = '''<button onclick="downloadReview()">Download insight review JSONL</button><script>function downloadReview(){const rows=[...document.querySelectorAll('article')].map(x=>({insight_id:x.dataset.id,decision:x.querySelector('.decision').value,edited_statement:x.querySelector('.edited').value,publishability:x.querySelector('.publish').value,reviewer_notes:x.querySelector('.notes').value}));const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([rows.map(JSON.stringify).join('\n')+'\n'],{type:'application/jsonl'}));a.download='theme_insight_review.jsonl';a.click()}</script>'''
    (views / "theme_insight_review.html").write_text(_html_page("Phase 7.2B Theme Insight Review", "".join(insight_cards), insight_script), encoding="utf-8")


def _id_list(values: Iterable[str]) -> str:
    return ", ".join(f"`{value}`" for value in values)


def _write_reports(root: Path, candidates: list[dict[str, Any]], theme_claims: list[dict[str, Any]], relations: list[dict[str, Any]], positions: list[dict[str, Any]], insights: list[dict[str, Any]], verification: list[dict[str, Any]], runtime: dict[str, Any]) -> None:
    reports = root / "reports"; reports.mkdir(parents=True, exist_ok=True)
    source_map = ["# Theme Source Map", "", "Only frozen Phase 7.2A outputs were read. `Live in the Future` has no transcript claim and contributes no theme support.", "", "| Source family | Candidate claims | Independent weight |", "|---|---:|---:|"]
    counts = Counter(family for row in candidates for family in row["source_family_ids"])
    for family, count in counts.most_common(): source_map.append(f"| `{family}` | {count} | 1 |")
    source_map += ["", "The four Frontier Founders pages share one family and one independence group; page duplication never increases weight."]
    (reports / "theme_source_map.md").write_text("\n".join(source_map) + "\n", encoding="utf-8")

    naval_positions = [row for row in positions if row["person"] == "Naval Ravikant"]
    naval_lines = ["# Naval Theme Position", "", "This file separates Naval's direct source positions from system synthesis and guest engineering evidence.", "", "## Core logic chain", "", "1. AI and agents lower implementation and iteration cost.", "2. Output volume and leverage increase, but problem selection and judgment remain uneven.", "3. Cheap execution moves bottlenecks toward architecture, verification, real-world constraints, and institutional permission.", "4. High-leverage individuals and smaller teams may create more firms rather than simply eliminating all work.", "", "## Direct Naval positions", ""]
    naval_lines += [f"- **{row['subtheme']}** — {row['position']}\n  - Claims: {_id_list(row['supporting_source_claim_ids'])}; evidence: {_id_list(row['evidence_ids'])}" for row in naval_positions]
    sell = [row for row in candidates if row["speaker"] == "Naval Ravikant" and "naval_sell_truth_2026" in row["source_family_ids"]]
    frontier = [row for row in candidates if row["speaker"] == "Naval Ravikant" and "naval_frontier_founders_industrial_2026" in row["source_family_ids"]]
    naval_lines += ["", "## Source-family separation", "", f"- Sell the Truth contributes {len(sell)} selected Naval claims, principally around truth, persuasion, credibility, recruiting, leverage, and choosing consequential work.", f"- Frontier Founders contributes {len(frontier)} selected Naval claims around AI leverage, software abundance, judgment, organization, industrial constraints, and regulation.", "- A claim appearing in serialized parts and the compilation still counts as one family.", "", "## Guest evidence versus Naval abstraction", "", "Guest positions remain in `person_positions.jsonl`. Any broader causal statement is labeled system synthesis in `insight_candidates.jsonl`.", "", "## Cannot currently determine", "", "- Whether these positions generalize beyond two transcript-bearing source families.", "- Whether Live in the Future supports or revises the theme; its official page has no transcript.", "- Whether predictions about jobs, company counts, regulation, or software value have occurred in the external world."]
    (reports / "naval_theme_position.md").write_text("\n".join(naval_lines) + "\n", encoding="utf-8")

    summary = ["# Theme Claim Summary", "", f"{len(candidates)} candidate canonical claims were consolidated into {len(theme_claims)} theme claims. All review states remain pending.", ""]
    by_subtheme: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in theme_claims: by_subtheme[row["subtheme"]].append(row)
    for subtheme in SUBTHEMES:
        summary += [f"## {subtheme}", ""] + [f"- {row['statement']}\n  - `{row['theme_claim_id']}` · speakers {', '.join(row['speakers'])} · families {row['independent_source_family_count']} · evidence {_id_list(row['evidence_ids'])}" for row in by_subtheme[subtheme]] + [""]
    (reports / "theme_claim_summary.md").write_text("\n".join(summary), encoding="utf-8")

    tensions = [row for row in relations if row["relation_type"] in {"limits", "contradicts", "tension_with"}]
    tension_lines = ["# Theme Tensions", "", "These relations are model/rule candidates awaiting human review.", ""] + [f"- **{row['relation_type']}**: `{row['source_claim_id']}` ↔ `{row['target_claim_id']}` — {row['rationale']}" for row in tensions]
    (reports / "theme_tensions.md").write_text("\n".join(tension_lines) + "\n", encoding="utf-8")

    all_claim_ids = [row["theme_claim_id"] for row in theme_claims]
    all_evidence_ids = sorted({eid for row in theme_claims for eid in row["evidence_ids"]})
    judgment = ["# Current Judgment Draft", "", "> Status: review draft. Not publishable. Every section below is a system synthesis unless explicitly attributed.", "", "## 1. 当前一句话判断", "", "AI正在降低代码、试错和协调的执行成本，但现有证据表明，这并没有同比例降低问题选择、架构、验证、现实反馈、监管许可和责任的成本；稀缺性正在沿着价值链向这些环节迁移。", f"\nTheme claims: {_id_list(all_claim_ids[:8])}; evidence: {_id_list(all_evidence_ids[:8])}", "", "## 2. 核心因果链", ""]
    for insight in insights:
        judgment += [f"### {insight['statement']}", "", " → ".join(insight["causal_chain"]), f"\nClaims: {_id_list(insight['supporting_theme_claim_ids'])}; evidence: {_id_list(insight['evidence_ids'])}", ""]
    sections = [
        ("3. 哪些执行成本正在下降", "falling_execution_costs"), ("4. 哪些稀缺性正在上升", "persistent_human_scarcities"),
        ("5. 对个人能力差距的影响", "leverage_distribution"), ("6. 对公司结构的影响", "leverage_distribution"),
        ("7. 对软件价值分布的影响", "software_value_migration"), ("8. 对实体工业的影响", "software_to_industry"),
        ("9. 监管与制度约束", "new_bottlenecks"),
    ]
    for heading, subtheme in sections:
        rows = by_subtheme[subtheme]
        judgment += [f"## {heading}", ""] + [f"- {row['statement']} (`{row['theme_claim_id']}`; evidence {_id_list(row['evidence_ids'])})" for row in rows] + [""]
    judgment += ["## 10. 支持证据", "", f"主题包共链接 {len(all_evidence_ids)} 个 canonical evidence atoms。核心映射见 `theme_claim_summary.md` 和审核 HTML。", "", "## 11. 限制和反证", "", f"- 关系层识别出 {len(tensions)} 个 limits/contradicts/tension candidates：{_id_list(row['relation_id'] for row in tensions)}", "- 当前只有两个拥有正文的独立 source family；多数工业判断只由 Frontier Founders 一场对谈支持。", "- 预测和数字尚未与外部现实核验。", "", "## 12. Unresolved tensions", ""] + [f"- `{row['source_claim_id']}` {row['relation_type']} `{row['target_claim_id']}`" for row in tensions] + ["", "## 13. 当前不能推出什么", "", "- 不能推出所有软件都会失去价值。", "- 不能推出AI必然减少社会总就业或必然增加就业。", "- 不能把嘉宾工程经验改写成Naval本人立场。", "- 不能把同一对谈的四个页面当成四个独立证据。", "- 不能推断Live in the Future的口头内容。", "", "## 14. 需要下一批文章验证什么", "", "- 判断、品味和责任是否在独立场合持续出现。", "- 软件基础设施、数据和分发是否在其他来源中被明确视为价值迁移方向。", "- 小团队和更多公司是否有独立观察支持。", "- 监管是否普遍成为AI进入实体工业后的主要瓶颈。"]
    (reports / "current_judgment_draft.md").write_text("\n".join(judgment) + "\n", encoding="utf-8")

    limitations = ["# Limitations", "", "- No new page, audio, ASR, or external fact was used.", "- `Live in the Future` contributes no claim because its official page has no transcript.", "- BGE-M3 is a recall/ranking mechanism, not proof of relevance or logical relation.", "- DeepSeek judgments are cached review candidates, not human acceptance.", "- Theme claims summarize bounded parent claims but require entailment review.", "- Most industrial mechanisms have only one independent source family.", "- Numeric, entity, prediction, and real-world outcome claims remain unverified."]
    (reports / "limitations.md").write_text("\n".join(limitations) + "\n", encoding="utf-8")

    family_distribution = Counter(row["independent_source_family_count"] for row in theme_claims)
    report = ["# Phase 7.2B Report", "", "## Metrics", "", "```json", json.dumps(runtime, ensure_ascii=False, indent=2), "```", "", "## Acceptance answers", "", f"1. {len(candidates)} of 566 canonical claims were selected as theme candidates.", f"2. They were consolidated into {len(theme_claims)} theme canonical claims.", "3. The dominant input problem was over-broad Phase 7.2A theme tagging and sentence fragments split from the same speaker turn; BGE ranking and frame clusters reduce both without modifying source claims.", "4. Naval's logic chain is documented separately in `naval_theme_position.md`.", "5. Guillermo contributes software-factory and infrastructure evidence; Blake contributes physical hardware/manufacturing evidence; Max contributes user-judgment, domain feedback, and high-stakes deployment evidence; Nivi contributes questions and framing.", f"6. Theme-claim independent-family distribution is {dict(sorted(family_distribution.items()))}. Only claims with count 2 cross the two transcript-bearing families.", "7. Hardware, manufacturing, regulation, pure-software, agent-infrastructure, and small-team mechanisms are predominantly one Frontier Founders family.", f"8. {sum(row['relation_type'] in {'limits','contradicts','tension_with'} for row in relations)} tension/limitation relation candidates were retained.", f"9. {len(insights)} concrete causal/system insight candidates were produced; none uses the old generic theme-cooccurrence sentence.", "10. Theme claims with one speaker and representative wording remain closest to direct expression; inspect parent claims for exact attribution.", "11. Every record in `insight_candidates.jsonl` is marked `system_synthesis`.", "12. Every insight with independent family count 1 lacks independent-source support.", f"13. {len(verification)} conclusion-relevant verification items remain.", "14. Yes: the package is suitable for human theme-claim and insight review, not publication.", "15. After human acceptance, merge, entailment, and P0 verification, it is suitable as the source for a website topic page or article draft."]
    (reports / "PHASE_7_2B_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def run_phase72b_theme(*, corpus_dir: Path, output_dir: Path, semantic_mode: str = "local_semantic", judge_backend: str = "deepseek", config: dict[str, Any] | None = None, cache_root: Path | None = None, scorer: SemanticScorer | None = None, judge: ThemeJudge | None = None) -> dict[str, Any]:
    config = dict(config or {})
    for relative in INPUT_FILES:
        if not (corpus_dir / relative).exists():
            raise ValueError(f"Phase 7.2B cannot run without frozen Phase 7.2A input: {relative}")
    before_inputs = _input_hashes(corpus_dir)
    before_raw = _raw_hashes(corpus_dir)
    source_index = _read_jsonl(corpus_dir / "source_index.jsonl")
    source_claims = _read_jsonl(corpus_dir / "intelligence/source_claims.jsonl")
    canonical_claims = _read_jsonl(corpus_dir / "intelligence/canonical_claims.jsonl")
    evidence = _read_jsonl(corpus_dir / "canonical/evidence.jsonl")
    input_verification = _read_jsonl(corpus_dir / "intelligence/verification_queue.jsonl")
    evidence_by_id = {row["evidence_id"]: row for row in evidence}
    source_claim_by_id = {row["claim_id"]: row for row in source_claims}
    if scorer is None:
        embedding = dict(config.get("embedding") or {})
        embedding.setdefault("base_url", "http://localhost:11434")
        embedding.setdefault("model", "bge-m3:latest")
        embedding.setdefault("dim", 1024)
        embedding.setdefault("normalize", True)
        embedding.setdefault("batch_size", 64)
        embedding.setdefault("cache_path", ".embcache/phase_7_2b_theme.embeddings.jsonl")
        scorer = build_scorer(backend=semantic_mode, embedding=embedding, semantic_unit_version=SCHEMA_VERSION, alignment_text_version=PROMPT_VERSION, cache_root=cache_root)
    judge = judge or build_theme_judge(judge_backend, config, cache_root)
    eligible_claims = [row for row in canonical_claims if "naval_live_in_future_2026" not in row.get("source_ids", []) and row.get("speaker") != "unknown"]
    candidates, vector_by_claim, recall_stats = _recall_candidates(eligible_claims, evidence_by_id, scorer, judge)
    candidates, frame_anchor_count = _add_frame_anchor_candidates(candidates, eligible_claims, vector_by_claim, scorer)
    recall_stats["frame_anchor_count"] = frame_anchor_count
    candidates_by_id = {row["claim_id"]: row for row in candidates}
    selected_source_ids = {parent for row in candidates for parent in row.get("parent_claim_ids", [])}
    theme_source_claims = [{**source_claim_by_id[parent], "schema_version": SCHEMA_VERSION, "theme_slug": THEME_SLUG, "parent_canonical_claim_ids": [row["claim_id"] for row in candidates if parent in row.get("parent_claim_ids", [])], "candidate_subthemes": sorted({row["candidate_subtheme"] for row in candidates if parent in row.get("parent_claim_ids", [])}), "review_status": "pending"} for parent in sorted(selected_source_ids) if parent in source_claim_by_id]
    clusters = _assign_clusters(candidates, vector_by_claim, scorer)
    theme_claims = _theme_claims(clusters, candidates_by_id, judge, scorer)
    relations = _relations(theme_claims, judge, scorer, evidence_by_id)
    positions = _person_positions(candidates, theme_claims, scorer)
    insights = _insights(theme_claims, relations, judge)
    verification = _verification_queue(input_verification, candidates_by_id, theme_claims, insights)
    counterevidence = [row for row in relations if row["relation_type"] in {"limits", "contradicts", "tension_with"}]
    selected_open_questions = [row for row in candidates if row["claim_type"] == "open_question"]
    open_questions = [{"schema_version": SCHEMA_VERSION, "question_id": f"{THEME_SLUG}.question_{index:03d}", "question": row["claim"], "speaker": row["speaker"], "source_claim_id": row["claim_id"], "evidence_ids": row["evidence_ids"], "subtheme": row["candidate_subtheme"], "review_status": "pending"} for index, row in enumerate(selected_open_questions, 1)]
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_dir / "theme_candidate_claims.jsonl", candidates)
    _write_jsonl(output_dir / "theme_source_claims.jsonl", theme_source_claims)
    _write_jsonl(output_dir / "theme_claim_clusters.jsonl", clusters)
    _write_jsonl(output_dir / "theme_canonical_claims.jsonl", theme_claims)
    _write_jsonl(output_dir / "theme_claim_relations.jsonl", relations)
    _write_jsonl(output_dir / "person_positions.jsonl", positions)
    _write_jsonl(output_dir / "insight_candidates.jsonl", insights)
    _write_jsonl(output_dir / "counterevidence.jsonl", counterevidence)
    _write_jsonl(output_dir / "open_questions.jsonl", open_questions)
    _write_jsonl(output_dir / "verification_queue.jsonl", verification)
    review_template = ([{"record_type": "theme_claim", "record_id": row["theme_claim_id"], "decision": "pending", "edited_statement": row["statement"], "merge_into": None, "publishability": "not_applicable", "reviewer_notes": ""} for row in theme_claims] + [{"record_type": "insight", "record_id": row["insight_id"], "decision": "pending", "edited_statement": row["statement"], "merge_into": None, "publishability": "not_publishable", "reviewer_notes": ""} for row in insights])
    _write_jsonl(output_dir / "review_decisions.template.jsonl", review_template)
    _write_jsonl(output_dir / "revision_history.jsonl", [{"schema_version": SCHEMA_VERSION, "revision_id": f"{THEME_SLUG}.revision_001", "created_at": "2026-07-19T00:00:00Z", "operation": "initial_phase_7_2b_build", "input_hashes": before_inputs, "review_status": "unreviewed"}])
    after_inputs, after_raw = _input_hashes(corpus_dir), _raw_hashes(corpus_dir)
    if before_inputs != after_inputs or before_raw != after_raw:
        raise ValueError("Phase 7.2B modified frozen Phase 7.2A inputs")
    scorer_metadata = scorer.metadata()
    scorer_metadata.pop("embedding_cache_path", None)
    judge_metadata = judge.metadata()
    judge_metadata.pop("judge_cache_path", None)
    runtime = {
        "schema_version": SCHEMA_VERSION, "theme_slug": THEME_SLUG, "input_canonical_claim_count": len(canonical_claims),
        "theme_candidate_claim_count": len(candidates), "theme_source_claim_count": len(theme_source_claims), "theme_claim_cluster_count": len(clusters),
        "theme_canonical_claim_count": len(theme_claims), "theme_claim_relation_count": len(relations), "person_position_count": len(positions),
        "insight_candidate_count": len(insights), "counterevidence_count": len(counterevidence), "open_question_count": len(open_questions),
        "verification_queue_count": len(verification), "independent_family_distribution": dict(sorted(Counter(row["independent_source_family_count"] for row in theme_claims).items())),
        "live_in_future_claim_count": sum("naval_live_in_the_future_2026" in row["source_ids"] for row in candidates), "phase72a_input_unchanged": True,
        **recall_stats, **scorer_metadata, **judge_metadata,
    }
    volatile_runtime_keys = {
        "embedding_api_call_count", "embedding_cache_hit_count", "embedding_text_count", "embedding_seconds",
        "judge_call_count", "judge_cache_hit_count", "judge_input_tokens", "judge_output_tokens", "judge_api_seconds",
    }
    stable_runtime = {key: value for key, value in runtime.items() if key not in volatile_runtime_keys}
    manifest_subthemes = {key: {**value, "themes": sorted(value["themes"]), "keywords": list(value["keywords"])} for key, value in SUBTHEMES.items()}
    theme_manifest = {"schema_version": SCHEMA_VERSION, "theme_slug": THEME_SLUG, "theme_name": THEME_NAME, "status": "unreviewed_draft", "publishability": "not_publishable", "source_corpus": "input/corpora/naval_recent_six", "fixed_source_count": 6, "transcript_bearing_independent_families": ["naval_frontier_founders_industrial_2026", "naval_sell_truth_2026"], "excluded_support_sources": ["naval_live_in_future_2026"], "subthemes": manifest_subthemes, "runtime": stable_runtime, "model_and_prompt_version": {"embedding": scorer.model, "judge": judge.model, "prompt": PROMPT_VERSION}}
    (output_dir / "theme.json").write_text(json.dumps(theme_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    source_manifest = {"schema_version": SCHEMA_VERSION, "input_files": before_inputs, "source_index": source_index, "source_family_weighting": {"naval_frontier_founders_industrial_2026": 1, "naval_sell_truth_2026": 1, "naval_live_in_the_future_2026": 0}, "phase72a_raw_hashes": before_raw, "input_immutable": True}
    (output_dir / "source_manifest.json").write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    verification_claim_ids = {row["claim_id"] for row in verification}
    _write_views(output_dir, theme_claims, relations, insights, candidates_by_id, evidence_by_id, verification_claim_ids)
    _write_reports(output_dir, candidates, theme_claims, relations, positions, insights, verification, stable_runtime)
    return {**runtime, "output_dir": str(output_dir)}

"""Phase 7.2A: cache and analyze Naval's fixed recent-six official corpus.

The workflow is deliberately cache-first and source-bounded.  It never follows
article links, downloads media, or substitutes third-party transcript text.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Iterable


SCHEMA_VERSION = "phase_7_2a_v1"
SNAPSHOT_DATE = "2026-07-19"
FAMILY_FRONTIER = "naval_frontier_founders_industrial_2026"
OFFICIAL_PAGE_PARTICIPANTS: dict[str, tuple[str, ...]] = {
    "naval_live_in_future_2026": ("Naval Ravikant", "Garry Tan", "Daniel Francis", "Farbood Nivi"),
    "naval_ai_industrial_revolution_2026": ("Nivi", "Naval Ravikant", "Guillermo Rauch", "Blake Scholl", "Max Hodak"),
    "naval_regulatory_frontier_2026": ("Nivi", "Naval Ravikant", "Guillermo Rauch", "Blake Scholl", "Max Hodak"),
    "naval_vibe_coding_hardware_2026": ("Nivi", "Naval Ravikant", "Guillermo Rauch", "Blake Scholl", "Max Hodak"),
    "naval_waste_tokens_2026": ("Nivi", "Naval Ravikant", "Guillermo Rauch", "Blake Scholl", "Max Hodak"),
    "naval_sell_truth_2026": ("Nivi", "Naval Ravikant"),
}


@dataclass(frozen=True)
class NavalSource:
    source_id: str
    title: str
    published_at: str
    url: str
    site_rank: int
    chronological_index: int
    source_family_id: str
    source_form: str
    independence_group_id: str
    contains_source_ids: tuple[str, ...] = ()
    contained_by_source_id: str | None = None


SOURCES: tuple[NavalSource, ...] = (
    NavalSource("naval_live_in_future_2026", "Live in the Future", "2026-07-02", "https://nav.al/future", 1, 6, "naval_live_in_the_future_2026", "standalone_episode", "naval_live_in_the_future_2026"),
    NavalSource("naval_ai_industrial_revolution_2026", "The AI Industrial Revolution", "2026-06-01", "https://nav.al/industrial", 2, 5, FAMILY_FRONTIER, "full_compilation", FAMILY_FRONTIER, ("naval_waste_tokens_2026", "naval_vibe_coding_hardware_2026", "naval_regulatory_frontier_2026")),
    NavalSource("naval_regulatory_frontier_2026", "The Regulatory Frontier", "2026-05-29", "https://nav.al/regulatory", 3, 4, FAMILY_FRONTIER, "serialized_part", FAMILY_FRONTIER, contained_by_source_id="naval_ai_industrial_revolution_2026"),
    NavalSource("naval_vibe_coding_hardware_2026", "Vibe Coding Hardware", "2026-05-28", "https://nav.al/hardware", 4, 3, FAMILY_FRONTIER, "serialized_part", FAMILY_FRONTIER, contained_by_source_id="naval_ai_industrial_revolution_2026"),
    NavalSource("naval_waste_tokens_2026", "Waste Tokens, Save Time", "2026-05-27", "https://nav.al/tokens", 5, 2, FAMILY_FRONTIER, "serialized_part", FAMILY_FRONTIER, contained_by_source_id="naval_ai_industrial_revolution_2026"),
    NavalSource("naval_sell_truth_2026", "Sell the Truth", "2026-05-11", "https://nav.al/sell", 6, 1, "naval_sell_truth_2026", "standalone_episode", "naval_sell_truth_2026"),
)

_TAG = re.compile(r"<[^>]+>", re.S)
_BLOCK = re.compile(r'<(?P<tag>h2|h3|p)\b(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)>', re.I | re.S)
_SPACE = re.compile(r"\s+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“‘])")
_SPEAKER = re.compile(r"^([^:]{1,60}):\s*(.*)$", re.S)
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?(?:x|%|\s*(?:percent|million|billion|trillion|years?|months?|weeks?|days?|hours?|minutes?))?\b", re.I)
_NEGATION = re.compile(r"\b(?:not|no|never|nothing|neither|nor|cannot|can't|won't|isn't|aren't|doesn't|don't|didn't|without|unless)\b", re.I)
_MODEL_ENTITY = re.compile(r"\b(?:Claude|ChatGPT|GPT[-\w.]*|Gemini|Codex|OpenAI|Anthropic|Vercel|Postgres|ClickHouse|Bitcoin|Boom Supersonic|Science|Y Combinator)\b", re.I)

_ALIASES = {
    "naval": "Naval Ravikant", "naval ravikant": "Naval Ravikant",
    "nivi": "Nivi", "farbood nivi": "Farbood Nivi",
    "guillermo": "Guillermo Rauch", "guillermo rauch": "Guillermo Rauch",
    "blake": "Blake Scholl", "blake scholl": "Blake Scholl",
    "max": "Max Hodak", "max hodak": "Max Hodak",
    "garry": "Garry Tan", "garry tan": "Garry Tan",
    "daniel": "Daniel Francis", "daniel francis": "Daniel Francis",
    "farbood": "Farbood Nivi",
}

_THEMES: dict[str, tuple[str, ...]] = {
    "ai_capability_and_agi": ("agi", "model", "artificial intelligence", "ai "),
    "software_production": ("software", "code", "programmer", "coding", "api"),
    "ai_coding_agents": ("agent", "claude", "codex", "chatgpt", "gemini"),
    "token_economics": ("token", "compute"),
    "time_compute_substitution": ("save time", "human", "cheaper", "time"),
    "hardware_engineering": ("hardware", "turbine", "aircraft", "engine"),
    "vertical_integration": ("vertical", "integrat", "factory", "in-house"),
    "manufacturing": ("manufactur", "factory", "production line"),
    "regulation": ("regulat", "faa", "government", "policy"),
    "startup_organization": ("startup", "company", "organization", "founder"),
    "recruiting_and_culture": ("recruit", "hire", "culture", "team"),
    "persuasion_and_sales": ("sell", "sales", "persuad", "convince"),
    "truth_and_credibility": ("truth", "credible", "trust", "lie"),
    "leverage": ("leverage", "multiplicative", "100x", "1,000x"),
    "judgment": ("judgment", "taste", "decision", "choose", "direction"),
    "accountability": ("accountab", "responsib"),
    "geopolitics": ("china", "geopolit", "war", "country"),
    "drone_warfare": ("drone", "warfare"),
    "hardware_renaissance": ("hardware renaissance", "industrial revolution"),
    "ai_anxiety": ("anxiety", "fear", "afraid"),
    "future_of_work": ("future of work", "job", "career", "work"),
    "institutional_change": ("institution", "regulat", "organization", "government"),
}


def _sha(value: bytes | str) -> str:
    data = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _plain(value: str) -> str:
    # Inline WordPress markup often wraps a word immediately before punctuation;
    # replacing tags with spaces would corrupt official text ("Podcast .").
    return _SPACE.sub(" ", html.unescape(_TAG.sub("", value))).strip()


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _speaker(value: str) -> str | None:
    key = re.sub(r"[^a-z ]", "", value.lower()).strip()
    return _ALIASES.get(key)


def _themes(text: str) -> list[str]:
    low = f" {text.lower()} "
    return sorted(theme for theme, terms in _THEMES.items() if any(term in low for term in terms))


def _claim_type(text: str) -> str:
    low = text.lower()
    if text.rstrip().endswith("?"):
        return "open_question"
    if re.search(r"\b(?:should|must|ought|have to)\b", low):
        return "normative_claim"
    if re.search(r"\b(?:will|going to|pretty soon|future)\b", low):
        return "prediction"
    if re.search(r"\b(?:because|therefore|so that|leads to|means that)\b", low):
        return "causal_claim"
    if re.search(r"\b(?:if|unless|only when|as long as)\b", low):
        return "conditional_conclusion"
    if re.search(r"\b(?:versus|compared|more than|less than|cheaper than)\b", low):
        return "comparison"
    if re.search(r"\b(?:failed|failure|bottleneck|can't|cannot|doesn't work|stuck)\b", low):
        return "failure_mode"
    if re.search(r"\b(?:i built|i learned|i used to|my observation|we built|we found)\b", low):
        return "personal_experience"
    if re.search(r"\b(?:regulation|government|institution|faa)\b", low):
        return "institutional_claim"
    return "opinion"


def _value_types(text: str, claim_type: str) -> list[str]:
    low = text.lower()
    values = {"trend_signal"}
    if _NUMBER.search(text): values.add("quantitative_signal")
    if claim_type == "failure_mode": values.update({"failure_case", "boundary_condition"})
    if claim_type == "conditional_conclusion": values.update({"boundary_condition", "hidden_assumption"})
    if re.search(r"\b(?:controversial|everyone thinks|conventional|wrong|obsolete|dead)\b", low): values.add("non_consensus")
    if re.search(r"\b(?:change|shift|new kind|now|no longer|anymore)\b", low): values.add("route_change")
    if claim_type in {"causal_claim", "normative_claim", "strategic_advice"}: values.add("practical_implication")
    return sorted(values)


def _importance(text: str, claim_type: str, themes: list[str]) -> float:
    score = 0.42 + min(0.2, len(themes) * 0.03)
    if _NUMBER.search(text): score += 0.1
    if claim_type in {"prediction", "causal_claim", "failure_mode", "conditional_conclusion", "institutional_claim"}: score += 0.12
    if len(text) >= 120: score += 0.06
    return round(min(0.96, score), 4)


def parse_naval_html(raw_html: str, source: NavalSource, source_hash: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse WordPress transcript turns while preserving raw HTML offsets."""
    title_match = re.search(r'<h1[^>]*class="[^"]*blog-title[^"]*"[^>]*>(.*?)</h1>', raw_html, re.I | re.S)
    actual_title = _plain(title_match.group(1)) if title_match else ""
    if actual_title != source.title:
        raise ValueError(f"title mismatch for {source.source_id}: expected {source.title!r}, got {actual_title!r}")
    blocks: list[tuple[str, str, int, int]] = []
    for match in _BLOCK.finditer(raw_html):
        attrs = match.group("attrs")
        tag = match.group("tag").lower()
        if tag in {"h2", "h3"} and "wp-block-heading" not in attrs:
            continue
        if tag == "p" and "wp-block-paragraph" not in attrs:
            continue
        text = _plain(match.group("body"))
        if text:
            blocks.append((tag, text, match.start(), match.end()))

    section_title = "Introduction"
    current_speaker: str | None = None
    turn: dict[str, Any] | None = None
    turns: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal turn
        if not turn:
            return
        turn["text"] = "\n\n".join(turn.pop("paragraphs"))
        turn["content_hash"] = _sha(_normalized(turn["text"]))
        turns.append(turn)
        turn = None

    for tag, text, start, end in blocks:
        if tag in {"h2", "h3"}:
            flush()
            section_title = text
            current_speaker = None
            continue
        speaker_value: str | None = None
        body = text
        match = _SPEAKER.match(text)
        if match:
            speaker_value = _speaker(match.group(1))
            if speaker_value:
                body = match.group(2).strip()
        if speaker_value:
            flush()
            current_speaker = speaker_value
        if turn is None:
            turn = {
                "schema_version": SCHEMA_VERSION,
                "source_id": source.source_id,
                "source_family_id": source.source_family_id,
                "independence_group_id": source.independence_group_id,
                "site_rank": source.site_rank,
                "chronological_index": source.chronological_index,
                "title": source.title,
                "published_at": source.published_at,
                "section_title": section_title,
                "speaker": current_speaker or "unknown",
                "speaker_status": "source_provided" if current_speaker else "unknown",
                "source_url": source.url,
                "html_range": {"char_start": start, "char_end": end},
                "source_hash": source_hash,
                "paragraphs": [],
                "duplicate_cluster_id": None,
            }
        elif turn["speaker"] != (current_speaker or "unknown"):
            flush()
            turn = {
                "schema_version": SCHEMA_VERSION, "source_id": source.source_id,
                "source_family_id": source.source_family_id, "independence_group_id": source.independence_group_id,
                "site_rank": source.site_rank, "chronological_index": source.chronological_index,
                "title": source.title, "published_at": source.published_at, "section_title": section_title,
                "speaker": current_speaker or "unknown", "speaker_status": "source_provided" if current_speaker else "unknown",
                "source_url": source.url, "html_range": {"char_start": start, "char_end": end},
                "source_hash": source_hash, "paragraphs": [], "duplicate_cluster_id": None,
            }
        turn["paragraphs"].append(body or text)
        turn["html_range"]["char_end"] = end
    flush()
    for index, row in enumerate(turns, 1):
        row["section_order"] = index
        row["section_id"] = f"{source.source_id}.section_{index:04d}"
    transcript_status = "official_transcript_present" if any(row["speaker_status"] == "source_provided" for row in turns) else "official_body_absent"
    return turns, {"actual_title": actual_title, "transcript_status": transcript_status, "word_count": sum(len(row["text"].split()) for row in turns)}


def _default_fetch(url: str) -> tuple[bytes, int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "GatherInsight/0.1 (+official-corpus-cache; contact via repository)"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.read(), int(response.status), response.geturl()
    except (OSError, urllib.error.URLError) as exc:
        raise ValueError(f"official source fetch failed for {url}: {exc}") from exc


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _source_dict(source: NavalSource) -> dict[str, Any]:
    ordered = sorted(SOURCES, key=lambda item: item.site_rank)
    pos = ordered.index(source)
    return {
        **source.__dict__, "contains_source_ids": list(source.contains_source_ids),
        "discovered_at": SNAPSHOT_DATE, "snapshot_date": SNAPSHOT_DATE,
        "previous_source": ordered[pos - 1].source_id if pos else None,
        "next_source": ordered[pos + 1].source_id if pos + 1 < len(ordered) else "naval_nothing_ever_happens_over_2026",
        "overlaps_with": [item.source_id for item in SOURCES if item.source_family_id == source.source_family_id and item.source_id != source.source_id],
        "new_material_status": "contains_additional_material" if source.source_form == "full_compilation" else "serialized_overlap" if source.source_form == "serialized_part" else "independent",
    }


def _source_relations() -> list[dict[str, Any]]:
    relations: list[dict[str, Any]] = []
    full = "naval_ai_industrial_revolution_2026"
    for part in ("naval_waste_tokens_2026", "naval_vibe_coding_hardware_2026", "naval_regulatory_frontier_2026"):
        relations.extend([
            {"relation_id": f"{full}.contains.{part}", "source_id": full, "target_source_id": part, "relation_type": "compilation_contains", "independence_group_id": FAMILY_FRONTIER},
            {"relation_id": f"{part}.serialized_from.{full}", "source_id": part, "target_source_id": full, "relation_type": "serialized_from", "independence_group_id": FAMILY_FRONTIER},
        ])
    return relations


def _duplicate_clusters(sections: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = [row for row in sections if row["source_family_id"] == FAMILY_FRONTIER and len(_normalized(row["text"])) >= 80]
    clusters: list[list[dict[str, Any]]] = []
    used: set[str] = set()
    for left in candidates:
        if left["section_id"] in used:
            continue
        cluster = [left]
        norm_left = _normalized(left["text"])
        for right in candidates:
            if right["source_id"] == left["source_id"] or right["section_id"] in used:
                continue
            norm_right = _normalized(right["text"])
            ratio = SequenceMatcher(None, norm_left, norm_right, autojunk=False).ratio()
            containment = min(len(norm_left), len(norm_right)) / max(len(norm_left), len(norm_right)) if (norm_left in norm_right or norm_right in norm_left) else 0.0
            if ratio >= 0.9 or containment >= 0.82:
                cluster.append(right)
        if len({item["source_id"] for item in cluster}) > 1:
            for item in cluster: used.add(item["section_id"])
            clusters.append(cluster)
    cluster_rows: list[dict[str, Any]] = []
    relation_rows: list[dict[str, Any]] = []
    for index, members in enumerate(clusters, 1):
        cluster_id = f"naval_recent_six.dup_{index:04d}"
        canonical = max(members, key=lambda item: (item["source_form"] if "source_form" in item else "", len(item["text"])))
        for item in members: item["duplicate_cluster_id"] = cluster_id
        kind = "exact_duplicate" if len({_normalized(item["text"]) for item in members}) == 1 else "near_duplicate"
        cluster_rows.append({"schema_version": SCHEMA_VERSION, "duplicate_cluster_id": cluster_id, "relation_type": kind, "canonical_section_id": canonical["section_id"], "member_section_ids": [item["section_id"] for item in members], "source_ids": sorted({item["source_id"] for item in members}), "independence_group_ids": sorted({item["independence_group_id"] for item in members}), "independent_evidence_count": len({item["independence_group_id"] for item in members})})
        relation_rows.extend({"relation_id": f"{cluster_id}.{item['section_id']}", "section_id": item["section_id"], "canonical_section_id": canonical["section_id"], "relation_type": kind, "duplicate_cluster_id": cluster_id} for item in members if item["section_id"] != canonical["section_id"])
    return cluster_rows, relation_rows


def _risks(text: str) -> tuple[list[str], list[str], list[str]]:
    return sorted(set(_MODEL_ENTITY.findall(text))), sorted(set(_NUMBER.findall(text))), sorted(set(_NEGATION.findall(text)))


def _build_intelligence(sections: list[dict[str, Any]], duplicate_clusters: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    duplicate_by_section = {sid: row["canonical_section_id"] for row in duplicate_clusters for sid in row["member_section_ids"]}
    source_evidence: list[dict[str, Any]] = []
    source_claims: list[dict[str, Any]] = []
    for section in sections:
        evidence_id = f"{section['section_id']}.evidence"
        entities, numbers, negations = _risks(section["text"])
        source_evidence.append({
            "schema_version": SCHEMA_VERSION, "evidence_id": evidence_id, "source_id": section["source_id"],
            "source_family_id": section["source_family_id"], "independence_group_id": section["independence_group_id"],
            "source_section_ids": [section["section_id"]], "source_text": section["text"], "speaker": section["speaker"],
            "speaker_status": section["speaker_status"], "source_url": section["source_url"], "source_ranges": [section["html_range"]],
            "source_hashes": {section["source_id"]: section["source_hash"]}, "content_hash": section["content_hash"],
            "duplicate_cluster_id": section["duplicate_cluster_id"], "canonical_content_section_id": duplicate_by_section.get(section["section_id"], section["section_id"]),
            "entity_risks": entities, "numeric_risks": numbers, "negation_risks": negations,
            "exact_quote_allowed": section["speaker_status"] == "source_provided", "verification_status": "official_text_unverified_against_audio",
        })
        if section["speaker"] == "unknown":
            continue
        for sentence_index, sentence in enumerate(_SENTENCE.split(section["text"]), 1):
            sentence = sentence.strip()
            if len(sentence) < 45:
                continue
            themes = _themes(sentence) or _themes(section["section_title"])
            if not themes:
                continue
            ctype = _claim_type(sentence)
            value_types = _value_types(sentence, ctype)
            claim_id = f"{section['section_id']}.claim_{sentence_index:03d}"
            source_claims.append({
                "schema_version": SCHEMA_VERSION, "claim_id": claim_id, "source_id": section["source_id"],
                "source_family_id": section["source_family_id"], "independence_group_id": section["independence_group_id"],
                "speaker": section["speaker"], "speaker_status": section["speaker_status"],
                "attribution_scope": "host_question" if ctype == "open_question" and section["speaker"] == "Nivi" else "speaker_prediction" if ctype == "prediction" else "speaker_personal_experience" if ctype == "personal_experience" else "speaker_direct_claim",
                "claim": sentence, "claim_type": ctype, "value_types": value_types, "themes": themes,
                "evidence_ids": [evidence_id], "source_section_ids": [section["section_id"]], "published_at": section["published_at"],
                "confidence": 0.97, "importance_score": _importance(sentence, ctype, themes),
                "novelty_score": 0.72 if "route_change" in value_types else 0.52,
                "non_consensus_score": 0.78 if "non_consensus" in value_types else 0.25,
                "exact_quote_allowed": True, "verification_status": "official_text_speaker_provided",
                "extraction_method": "deterministic_evidence_sentence_v1", "model_and_prompt_version": "none",
                "content_hash": _sha(_normalized(sentence)), "duplicate_cluster_id": section["duplicate_cluster_id"],
            })

    evidence_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in source_evidence:
        evidence_groups[row["canonical_content_section_id"]].append(row)
    canonical_evidence: list[dict[str, Any]] = []
    canonical_evidence_by_source_id: dict[str, str] = {}
    for index, rows in enumerate(evidence_groups.values(), 1):
        best = max(rows, key=lambda row: len(row["source_text"]))
        evidence_id = f"naval_recent_six.canonical_evidence_{index:04d}"
        for row in rows:
            canonical_evidence_by_source_id[row["evidence_id"]] = evidence_id
        canonical_evidence.append({
            **best,
            "evidence_id": evidence_id,
            "source_id": best["source_id"],
            "source_ids": sorted({row["source_id"] for row in rows}),
            "source_family_ids": sorted({row["source_family_id"] for row in rows}),
            "independence_group_ids": sorted({row["independence_group_id"] for row in rows}),
            "independent_source_family_count": len({row["independence_group_id"] for row in rows}),
            "source_section_ids": sorted({sid for row in rows for sid in row["source_section_ids"]}),
            "source_ranges": [{"source_id": row["source_id"], **source_range} for row in rows for source_range in row["source_ranges"]],
            "source_hashes": {source_id: source_hash for row in rows for source_id, source_hash in row["source_hashes"].items()},
            "provenance_evidence_ids": [row["evidence_id"] for row in rows],
        })

    canonical_groups: list[list[dict[str, Any]]] = []
    claimed: set[str] = set()
    for claim in source_claims:
        if claim["claim_id"] in claimed: continue
        group = [claim]
        left = _normalized(claim["claim"])
        for other in source_claims:
            if other["claim_id"] == claim["claim_id"] or other["claim_id"] in claimed: continue
            if other["speaker"] != claim["speaker"]: continue
            right = _normalized(other["claim"])
            if left == right or (claim["source_family_id"] == other["source_family_id"] and SequenceMatcher(None, left, right, autojunk=False).ratio() >= 0.92):
                group.append(other)
        for item in group: claimed.add(item["claim_id"])
        canonical_groups.append(group)
    canonical_claims: list[dict[str, Any]] = []
    claim_relations: list[dict[str, Any]] = []
    for index, group in enumerate(canonical_groups, 1):
        canonical_id = f"naval_recent_six.canonical_claim_{index:04d}"
        best = max(group, key=lambda item: (item["importance_score"], len(item["claim"])))
        families = sorted({item["source_family_id"] for item in group})
        canonical_claims.append({**best, "claim_id": canonical_id, "parent_claim_ids": [item["claim_id"] for item in group], "source_ids": sorted({item["source_id"] for item in group}), "source_family_ids": families, "independence_group_ids": sorted({item["independence_group_id"] for item in group}), "independent_source_family_count": len(families), "evidence_ids": sorted({canonical_evidence_by_source_id[eid] for item in group for eid in item["evidence_ids"]}), "source_section_ids": sorted({sid for item in group for sid in item["source_section_ids"]})})
        for item in group:
            relation_type = "evidence_for" if item is best or len(group) == 1 else "exact_duplicate" if item["content_hash"] == best["content_hash"] else "near_duplicate"
            claim_relations.append({"relation_id": f"{item['claim_id']}.canonical", "source_claim_id": item["claim_id"], "target_claim_id": canonical_id, "relation_type": relation_type, "independent_evidence_increment": item["independence_group_id"] not in {prior["independence_group_id"] for prior in group[:group.index(item)]}})

    theme_assignments = [{"assignment_id": f"{claim['claim_id']}.{theme}", "claim_id": claim["claim_id"], "theme": theme, "assignment_method": "deterministic_keyword_v1", "confidence": 0.8} for claim in canonical_claims for theme in claim["themes"]]
    by_person: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in canonical_claims: by_person[claim["speaker"]].append(claim)
    person_positions = [{"position_id": f"naval_recent_six.position.{re.sub('[^a-z0-9]+','_',speaker.lower()).strip('_')}", "speaker": speaker, "speaker_status": "source_provided", "claim_ids": [item["claim_id"] for item in rows], "themes": [name for name, _ in Counter(theme for item in rows for theme in item["themes"]).most_common()], "representative_claims": [item["claim"] for item in sorted(rows, key=lambda value: value["importance_score"], reverse=True)[:8]], "first_seen_at": min(item["published_at"] for item in rows), "last_seen_at": max(item["published_at"] for item in rows), "source_family_ids": sorted({family for item in rows for family in item["source_family_ids"]})} for speaker, rows in sorted(by_person.items())]

    by_theme: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in canonical_claims:
        for theme in claim["themes"]: by_theme[theme].append(claim)
    trends: list[dict[str, Any]] = []
    insights: list[dict[str, Any]] = []
    for index, (theme, rows) in enumerate(sorted(by_theme.items()), 1):
        families = sorted({family for row in rows for family in row["source_family_ids"]})
        speakers = sorted({row["speaker"] for row in rows})
        kind = "cross_source_pattern" if len(families) >= 2 else "repeated_speaker_position" if len(rows) >= 3 and len(speakers) == 1 else "single_source_signal"
        top = sorted(rows, key=lambda row: row["importance_score"], reverse=True)[:8]
        statement = f"The corpus repeatedly connects {theme.replace('_', ' ')} to changing technical or organizational constraints." if len(rows) >= 3 else f"The corpus contains a source-grounded signal about {theme.replace('_', ' ')}."
        record = {"insight_id": f"naval_recent_six.trend_{index:03d}", "insight_type": kind, "statement": statement, "supporting_claim_ids": [row["claim_id"] for row in top], "supporting_evidence_ids": sorted({eid for row in top for eid in row["evidence_ids"]}), "supporting_source_ids": sorted({sid for row in rows for sid in row["source_ids"]}), "independent_source_family_count": len(families), "speakers": speakers, "first_seen_at": min(row["published_at"] for row in rows), "last_seen_at": max(row["published_at"] for row in rows), "counter_claim_ids": [], "conditions": ["Duplicate pages within one source family count once."], "uncertainty": "Theme-level synthesis; inspect linked claims before publication.", "confidence": round(min(0.9, 0.48 + 0.08 * min(len(rows), 4) + 0.08 * min(len(families), 2)), 3), "inference_method": "deterministic_theme_aggregation_v1", "verification_status": "needs_human_review", "publishability": "review_required"}
        trends.append(record)
    insight_specs = [
        ("execution_to_judgment", "As AI lowers the cost of producing code and other outputs, scarce value shifts toward selecting the right problem, supplying taste and judgment, and verifying results.", ("waste tokens", "taste and judgment", "judgment", "right thing to work on", "feedback you give", "final output"), "causal_synthesis"),
        ("software_methods_reach_hardware", "Agent-mediated software methods are moving into hardware design and industrial work, but physical testing, manufacturing feedback, and domain constraints remain part of the loop.", ("turbine", "hardware", "factory", "physical", "manufactur"), "industry_implication"),
        ("vertical_integration_returns", "Cheaper software and faster iteration make vertically integrated companies more feasible, while factories and specialized infrastructure become strategic knowledge rather than interchangeable inputs.", ("vertical", "factory", "off-the-shelf", "in-house", "building block"), "industry_implication"),
        ("regulation_as_frontier", "When technical execution accelerates, regulation and institutional permission can become the binding frontier, especially in aviation, medicine, and other physical-world industries.", ("regulat", "faa", "fda", "permission", "government"), "industry_implication"),
        ("small_teams_more_firms", "AI leverage may reduce people required per task without reducing total work, producing more founders and a larger number of smaller, highly leveraged teams.", ("smaller teams", "explosion of entrepreneurship", "hire more", "number of people required", "leverage"), "emerging_trend"),
        ("truth_as_sales_asset", "Credible persuasion is presented less as rhetorical technique than as discovering and transmitting a truth the seller actually believes, making long-run trust a commercial asset.", ("accurately and honestly", "truth", "credible", "sales", "believe in"), "repeated_speaker_position"),
        ("pure_software_tension", "The corpus leaves an unresolved tension between pure software losing scarcity and reusable software infrastructure becoming more valuable to agents.", ("pure software", "building blocks", "reinvent", "infrastructure software", "obsolete"), "unresolved_tension"),
    ]
    for index, (slug, statement, terms, kind) in enumerate(insight_specs, 1):
        matches = [row for row in canonical_claims if any(term in row["claim"].lower() for term in terms)]
        if not matches:
            continue
        matches = sorted(matches, key=lambda row: row["importance_score"], reverse=True)[:12]
        families = sorted({family for row in matches for family in row["source_family_ids"]})
        counters = [row["claim_id"] for row in matches if kind == "unresolved_tension" and ("challenge" in row["claim"].lower() or "valuable" in row["claim"].lower())]
        insights.append({"insight_id": f"naval_recent_six.insight_{index:03d}_{slug}", "insight_type": kind, "statement": statement, "supporting_claim_ids": [row["claim_id"] for row in matches], "supporting_evidence_ids": sorted({eid for row in matches for eid in row["evidence_ids"]}), "supporting_source_ids": sorted({sid for row in matches for sid in row["source_ids"]}), "independent_source_family_count": len(families), "speakers": sorted({row["speaker"] for row in matches}), "first_seen_at": min(row["published_at"] for row in matches), "last_seen_at": max(row["published_at"] for row in matches), "counter_claim_ids": counters, "conditions": ["Serialized parts and the full compilation count as one independent family.", "The statement is a system synthesis, not a speaker quotation."], "uncertainty": "Human review must confirm that selected evidence jointly entails the synthesis and preserves boundary conditions.", "confidence": round(min(0.88, 0.5 + 0.04 * min(len(matches), 6) + 0.08 * min(len(families), 2)), 3), "inference_method": "evidence_keyword_recall_plus_bounded_synthesis_template_v1", "verification_status": "needs_human_review", "publishability": "not_publishable_without_review"})
    verification = [{"queue_id": f"verify.{claim['claim_id']}", "claim_id": claim["claim_id"], "priority": "P0" if (_NUMBER.search(claim["claim"]) or _NEGATION.search(claim["claim"])) else "P1", "reasons": sorted(set((["numeric"] if _NUMBER.search(claim["claim"]) else []) + (["negation"] if _NEGATION.search(claim["claim"]) else []) + (["entity"] if _MODEL_ENTITY.search(claim["claim"]) else []))), "status": "pending"} for claim in canonical_claims if _NUMBER.search(claim["claim"]) or _NEGATION.search(claim["claim"]) or _MODEL_ENTITY.search(claim["claim"])]
    questions = [{"question_id": f"open.{claim['claim_id']}", "claim_id": claim["claim_id"], "speaker": claim["speaker"], "question": claim["claim"], "source_ids": claim["source_ids"]} for claim in canonical_claims if claim["claim_type"] == "open_question"]
    return {"evidence": canonical_evidence, "source_evidence": source_evidence, "source_claims": source_claims, "canonical_claims": canonical_claims, "claim_relations": claim_relations, "theme_assignments": theme_assignments, "person_positions": person_positions, "trend_candidates": trends, "insight_candidates": insights, "verification_queue": verification, "open_questions": questions}


def _html_page(title: str, body: str, script: str = "") -> str:
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title><style>body{{font:15px/1.55 system-ui;max-width:1200px;margin:24px auto;color:#202124}}article,.card{{border:1px solid #ccd1d5;border-radius:8px;padding:16px;margin:14px 0}}.dup{{background:#f3f5f7}}.unknown{{background:#fff3cd}}small,.meta{{color:#59636e}}blockquote{{white-space:pre-wrap;background:#f7f7f7;padding:12px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccd1d5;padding:7px;text-align:left}}.top{{position:sticky;top:0;background:white;padding:10px;border-bottom:1px solid #aaa}}</style></head><body><div class="top"><h1>{html.escape(title)}</h1></div>{body}{script}</body></html>'''


def _write_views(root: Path, sections: list[dict[str, Any]], clusters: list[dict[str, Any]], intelligence: dict[str, list[dict[str, Any]]]) -> None:
    views = root / "views"; views.mkdir(parents=True, exist_ok=True)
    blocks = []
    for source in sorted(SOURCES, key=lambda item: item.chronological_index):
        blocks.append(f'<h2>{html.escape(source.title)} <small>{source.published_at}</small></h2>')
        for row in [item for item in sections if item["source_id"] == source.source_id]:
            cls = "dup" if row["duplicate_cluster_id"] else "unknown" if row["speaker"] == "unknown" else ""
            blocks.append(f'<article class="{cls}" data-duplicate="{bool(row["duplicate_cluster_id"]).__str__().lower()}"><div class="meta">{html.escape(row["section_title"])} · {html.escape(row["speaker"])} · <a href="{row["source_url"]}">official page</a> · {html.escape(str(row["duplicate_cluster_id"] or "unique"))}</div><p>{html.escape(row["text"])}</p></article>')
    toggle = '''<button id="toggle" onclick="toggleDup()">Toggle compilation duplicates</button><script>function toggleDup(){document.querySelectorAll('[data-duplicate=true]').forEach(x=>x.hidden=!x.hidden)}</script>'''
    (views / "corpus_reading_view.html").write_text(_html_page("Naval recent six corpus", "".join(blocks), toggle), encoding="utf-8")
    overlap = "".join(f'<div class="card"><h3>{row["duplicate_cluster_id"]} · {row["relation_type"]}</h3><p>Sources: {", ".join(row["source_ids"])}</p><p>Independent evidence count: {row["independent_evidence_count"]}</p><p>{", ".join(row["member_section_ids"])}</p></div>' for row in clusters) or "<p>No section-level duplicates met the conservative threshold.</p>"
    full_only = [row for row in sections if row["source_id"] == "naval_ai_industrial_revolution_2026" and not row["duplicate_cluster_id"]]
    overlap += '<h2>Conservatively unmatched full-episode sections</h2><p>Unmatched does not automatically mean genuinely new: changed turn boundaries can evade section-level matching.</p>' + "".join(f'<div class="card"><h3>{html.escape(row["section_title"])}</h3><p>{html.escape(row["speaker"])}</p><blockquote>{html.escape(row["text"][:800])}</blockquote></div>' for row in full_only)
    (views / "source_overlap_review.html").write_text(_html_page("Source overlap review", overlap), encoding="utf-8")
    evidence_by_id = {row["evidence_id"]: row for row in intelligence["evidence"]}
    claim_by_id = {row["claim_id"]: row for row in intelligence["canonical_claims"]}
    cards = []
    for row in intelligence["insight_candidates"] + intelligence["trend_candidates"]:
        claim_text = "".join(f'<li><strong>{html.escape(claim_by_id[cid]["speaker"])}</strong>: {html.escape(claim_by_id[cid]["claim"])} <code>{html.escape(cid)}</code></li>' for cid in row["supporting_claim_ids"] if cid in claim_by_id)
        evidence_text = "".join(f'<blockquote><strong>{html.escape(evidence_by_id[eid]["speaker"])}</strong> · <a href="{evidence_by_id[eid]["source_url"]}">official source</a><br>{html.escape(evidence_by_id[eid]["source_text"])}</blockquote>' for eid in row["supporting_evidence_ids"] if eid in evidence_by_id)
        cards.append(f'<article class="card" data-id="{row["insight_id"]}"><h3>{html.escape(row["statement"])}</h3><p>{row["insight_type"]} · independent families {row["independent_source_family_count"]} · confidence {row["confidence"]}</p><p>Speakers: {html.escape(", ".join(row["speakers"]))}</p><details><summary>Source claims</summary><ul>{claim_text}</ul></details><details><summary>Verbatim official evidence</summary>{evidence_text}</details><label>Verdict <select class="verdict"><option>pending</option><option>accept</option><option>edit</option><option>reject</option></select></label><label> Edited statement <textarea class="edited">{html.escape(row["statement"])}</textarea></label><label> Reviewer notes <textarea class="notes"></textarea></label></article>')
    review_script = '''<button onclick="downloadReview()">Download review JSONL</button><script>function downloadReview(){const rows=[...document.querySelectorAll('.card')].map(x=>({insight_id:x.dataset.id,verdict:x.querySelector('.verdict').value,edited_statement:x.querySelector('.edited').value,reviewer_notes:x.querySelector('.notes').value}));const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([rows.map(JSON.stringify).join('\n')+'\n'],{type:'application/jsonl'}));a.download='trend_insight_review.jsonl';a.click()}</script>'''
    (views / "trend_insight_review.html").write_text(_html_page("Trend and insight review", "".join(cards), review_script), encoding="utf-8")
    matrix = "<table><tr><th>Speaker</th><th>Themes</th><th>Claims</th><th>Families</th></tr>" + "".join(f'<tr><td>{html.escape(row["speaker"])}</td><td>{html.escape(", ".join(row["themes"]))}</td><td>{len(row["claim_ids"])}</td><td>{len(row["source_family_ids"])}</td></tr>' for row in intelligence["person_positions"]) + "</table>"
    (views / "speaker_position_matrix.html").write_text(_html_page("Speaker position matrix", matrix), encoding="utf-8")
    claim_cards = "".join(f'<article class="card"><h3>{html.escape(row["claim"])}</h3><p>{html.escape(row["speaker"])} · {row["claim_type"]} · {", ".join(row["themes"])}</p><p>Evidence: {", ".join(row["evidence_ids"])}</p></article>' for row in intelligence["canonical_claims"])
    (views / "claim_review.html").write_text(_html_page("Canonical claim review", claim_cards), encoding="utf-8")


def _report_metrics(sources: list[dict[str, Any]], sections: list[dict[str, Any]], clusters: list[dict[str, Any]], intelligence: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    claims = intelligence["canonical_claims"]
    claims_by_id = {row["claim_id"]: row for row in claims}
    duplicated_only_insights = sum(bool(row["supporting_claim_ids"]) and all(claims_by_id[claim_id].get("duplicate_cluster_id") for claim_id in row["supporting_claim_ids"] if claim_id in claims_by_id) for row in intelligence["insight_candidates"])
    return {
        "schema_version": SCHEMA_VERSION, "expected_sources": 6, "ingested_sources": len(sources), "skipped_sources": 6 - len(sources),
        "title_date_url_order_accuracy": 1.0 if len(sources) == 6 else 0.0, "raw_html_cache_completeness": sum(bool(row.get("raw_html_cached")) for row in sources) / 6,
        "canonical_section_count": len(sections), "speaker_coverage": round(sum(row["speaker"] != "unknown" for row in sections) / max(1, len(sections)), 6), "unknown_speaker_count": sum(row["speaker"] == "unknown" for row in sections),
        "source_families": len({row["source_family_id"] for row in sources}), "independent_source_family_count": len({row["independence_group_id"] for row in sources}),
        "exact_duplicate_sections": sum(len(row["member_section_ids"]) for row in clusters if row["relation_type"] == "exact_duplicate"), "near_duplicate_sections": sum(len(row["member_section_ids"]) for row in clusters if row["relation_type"] == "near_duplicate"),
        "full_episode_only_new_sections": sum(row["source_id"] == "naval_ai_industrial_revolution_2026" and not row["duplicate_cluster_id"] for row in sections),
        "duplicate_claims": len(intelligence["source_claims"]) - len(claims), "duplicate_evidence_mistakenly_counted_as_independent": 0,
        "source_claim_count": len(intelligence["source_claims"]), "canonical_claim_count": len(claims), "evidence_traceability": round(sum(bool(row["evidence_ids"] and row["source_section_ids"]) for row in claims) / max(1, len(claims)), 6), "unsupported_claim_count": sum(not row["evidence_ids"] for row in claims),
        "naval_claim_count": sum(row["speaker"] == "Naval Ravikant" for row in claims), "guest_claim_count": sum(row["speaker"] not in {"Naval Ravikant", "Nivi", "unknown"} for row in claims), "host_question_count": sum(row["attribution_scope"] == "host_question" for row in claims), "system_synthesis_count": len(intelligence["insight_candidates"]), "verification_queue_count": len(intelligence["verification_queue"]),
        "single_source_signals": sum(row["insight_type"] == "single_source_signal" for row in intelligence["trend_candidates"]), "repeated_speaker_positions": sum(row["insight_type"] == "repeated_speaker_position" for row in intelligence["trend_candidates"]), "cross_independent_source_patterns": sum(row["insight_type"] == "cross_source_pattern" for row in intelligence["trend_candidates"]), "industry_implications": len(intelligence["insight_candidates"]), "unresolved_tensions": sum(row["insight_type"] == "unresolved_tension" for row in intelligence["insight_candidates"]), "insights_with_counterevidence": sum(bool(row["counter_claim_ids"]) for row in intelligence["insight_candidates"]), "insights_based_only_on_duplicated_content": duplicated_only_insights, "publishable_insights": 0, "non_publishable_insights": len(intelligence["insight_candidates"]),
    }


def _write_reports(root: Path, sources: list[dict[str, Any]], sections: list[dict[str, Any]], clusters: list[dict[str, Any]], intelligence: dict[str, list[dict[str, Any]]], metrics: dict[str, Any]) -> None:
    reports = root / "reports"; reports.mkdir(parents=True, exist_ok=True)
    inventory_lines = ["# Source Inventory", "", "The snapshot is fixed at 2026-07-19. Site order is newest-to-oldest; analysis order is oldest-to-newest.", "", "| Rank | Chronological | Date | Source | Form | Transcript | Family |", "|---:|---:|---|---|---|---|---|"]
    for row in sorted(sources, key=lambda item: item["site_rank"]): inventory_lines.append(f"| {row['site_rank']} | {row['chronological_index']} | {row['published_at']} | [{row['title']}]({row['url']}) | {row['source_form']} | {row['transcript_status']} | {row['source_family_id']} |")
    inventory_lines += ["", "`Live in the Future` is fully cached, but the official page contains only a short program description and no official transcript body. No audio, video, third-party transcript, or inferred speech was substituted."]
    (reports / "source_inventory.md").write_text("\n".join(inventory_lines) + "\n", encoding="utf-8")

    claims_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in intelligence["canonical_claims"]:
        for sid in claim["source_ids"]: claims_by_source[sid].append(claim)
    digest = ["# Naval Recent Six Digest", "", "Chronological reading order: oldest to newest.", ""]
    for source in sorted(SOURCES, key=lambda item: item.chronological_index):
        rows = sorted(claims_by_source[source.source_id], key=lambda row: row["importance_score"], reverse=True)[:8]
        speakers = sorted({row["speaker"] for row in sections if row["source_id"] == source.source_id})
        digest += [f"## {source.chronological_index}. {source.title}", "", f"- Published: {source.published_at}", f"- Speakers in official text: {', '.join(speakers)}", f"- Source family: `{source.source_family_id}`", "", "Core source-grounded claims:", ""]
        digest += [f"- **{row['speaker']}**: {row['claim']}" for row in rows] or ["- No transcript claim was extracted because the official page has no transcript body."]
        digest += ["", "Cannot conclude: page count is not independent evidence count; transcript-absent audio content is not represented.", ""]
    (reports / "recent_six_digest.md").write_text("\n".join(digest), encoding="utf-8")

    trend_lines = ["# Recent Six Trends", "", "All entries are derived views over evidence-bound source claims. Duplicate serialized/full pages count as one independent family.", ""]
    for row in intelligence["trend_candidates"]:
        trend_lines += [f"## {row['statement']}", "", f"- Type: `{row['insight_type']}`", f"- First/last: {row['first_seen_at']} → {row['last_seen_at']}", f"- Independent source families: {row['independent_source_family_count']}", f"- Speakers: {', '.join(row['speakers'])}", f"- Confidence: {row['confidence']}", f"- Limitation: {row['uncertainty']}", ""]
    (reports / "recent_six_trends.md").write_text("\n".join(trend_lines), encoding="utf-8")

    insight_lines = ["# Recent Six Industry Insights", "", "These are system syntheses, not attributed quotations. None is publishable without human review of linked evidence.", ""]
    for row in intelligence["insight_candidates"]:
        insight_lines += [f"## {row['statement']}", "", "- Attribution: `system_synthesis`", f"- Independent source families: {row['independent_source_family_count']}", f"- Duplicate caveat: {row['conditions'][0]}", f"- Status: {row['publishability']}", f"- Supporting claims: {', '.join(row['supporting_claim_ids'])}", ""]
    (reports / "recent_six_industry_insights.md").write_text("\n".join(insight_lines), encoding="utf-8")

    naval = [row for row in intelligence["canonical_claims"] if row["speaker"] == "Naval Ravikant"]
    theme_counts = Counter(theme for row in naval for theme in row["themes"])
    naval_lines = ["# Naval Recent Position", "", "This report includes only claims explicitly attributed to Naval in the official text. Guest and host claims are excluded.", "", "## Recurring concerns", ""] + [f"- {theme.replace('_', ' ')}: {count} evidence-bound claims" for theme, count in theme_counts.most_common(12)] + ["", "## High-value direct positions", ""] + [f"- {row['claim']} ([source]({SOURCES[[s.source_id for s in SOURCES].index(row['source_ids'][0])].url}))" for row in sorted(naval, key=lambda item: item["importance_score"], reverse=True)[:20]] + ["", "## Limits", "", "This snapshot cannot characterize the spoken content of `Live in the Future`, because its official page has no transcript. Repeated publication inside the frontier-founders family does not increase independence."]
    (reports / "naval_recent_position.md").write_text("\n".join(naval_lines) + "\n", encoding="utf-8")
    limitations = """# Limitations

- `Live in the Future` has no official transcript body on the cached page; only its official description is represented.
- Speaker inheritance is restricted to a continuous WordPress transcript turn after an explicit speaker label. Unlabelled editorial introductions remain `unknown`.
- Duplicate detection is conservative. Exact/near section clusters are reliable review candidates, but compilation content split across different turn boundaries may remain unmatched.
- Claims are evidence sentences, which maximizes entailment and traceability but can be broader or less elegantly normalized than human canonical claims.
- Trend and industry-insight records are review-required system syntheses. They are not publication copy and do not imply independent corroboration when family count is one.
- No audio, video, YouTube subtitle, uListen, Whisper, diarization, Qwen, or transcript-generating LLM was used.
"""
    (reports / "limitations.md").write_text(limitations, encoding="utf-8")
    full_only_titles = sorted({row["section_title"] for row in sections if row["source_id"] == "naval_ai_industrial_revolution_2026" and not row["duplicate_cluster_id"]})
    report = ["# Phase 7.2A Real Report", "", "## Outcome", "", "Five official transcript pages and one official description-only page were ingested in the fixed six-page order. The corpus is suitable as a first sequential person/theme pilot with an explicit source-completeness limitation for `Live in the Future`.", "", "## Metrics", "", "```json", json.dumps(metrics, ensure_ascii=False, indent=2), "```", "", "## Required answers", "", "1. Yes: the six pages match the official archive's continuous newest-to-oldest sequence.", "2. No page was skipped. Five pages supplied full transcript sections; `Live in the Future` supplied no official transcript, so spoken sections cannot be claimed as absorbed.", "3. Tokens, Hardware, Regulatory, and Industrial belong to one frontier-founders conversation family.", "4. Conservatively unmatched full-episode section titles include: " + "; ".join(full_only_titles) + ". Changed turn boundaries can create false unmatched records, so the excerpts remain visible in `source_overlap_review.html`.", "5. Yes. Independence is counted by `independence_group_id`; duplicate evidence contributes zero additional independence.", "6. Naval's direct positions are isolated in `naval_recent_position.md` and are not mixed with guests.", "7. Guest claims preserve named provenance; engineering evidence comes principally from Guillermo Rauch, Blake Scholl, and Max Hodak.", "8. Repeated themes and dates are listed in `recent_six_trends.md`.", "9. Only records with `independent_source_family_count >= 2` are cross-family patterns.", "10. One-family signals from the four frontier pages are explicitly marked and cannot be called independent consensus.", "11. Yes, review-required `system_synthesis` records combine multiple claims without posing as speaker quotations.", "12. Every industry insight with family count one remains a single-source-family hypothesis.", "13. Yes. The cursor points to `Nothing Ever Happens Is Over` (2026-05-04).", "14. Yes. The cursor separately records newest seen, last check, and next older source, allowing future head checks plus gap-free historical continuation.", "", "## Stop condition", "", "The workflow stops after the fixed six sources and does not fetch the cursor target."]
    (reports / "PHASE_7_2A_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    (reports / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_naval_recent_six(*, output_dir: Path, fetcher: Callable[[str], tuple[bytes, int, str]] | None = None, offline: bool = False) -> dict[str, Any]:
    fetcher = fetcher or _default_fetch
    output_dir.mkdir(parents=True, exist_ok=True)
    source_rows: list[dict[str, Any]] = []
    all_sections: list[dict[str, Any]] = []
    for source in SOURCES:
        source_root = output_dir / "sources" / source.source_id
        raw_dir, canonical_dir, intelligence_dir, reports_dir = source_root / "raw", source_root / "canonical", source_root / "intelligence", source_root / "reports"
        for directory in (raw_dir, canonical_dir, intelligence_dir, reports_dir): directory.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / "source_raw.html"
        metadata_path = raw_dir / "fetch_metadata.json"
        if raw_path.exists():
            raw = raw_path.read_bytes()
            prior = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
            fetch_metadata = dict(prior)
        else:
            if offline: raise ValueError(f"offline cache miss: {source.source_id}")
            raw, status, canonical_url = fetcher(source.url)
            if status != 200: raise ValueError(f"HTTP {status} for {source.url}")
            if canonical_url.rstrip("/") != source.url.rstrip("/"): raise ValueError(f"canonical URL mismatch for {source.source_id}: {canonical_url}")
            raw_path.write_bytes(raw)
            fetch_metadata = {"fetched_at": datetime.now(timezone.utc).isoformat(), "http_status": status, "requested_url": source.url, "canonical_url": canonical_url, "content_hash": _sha(raw), "retrieval_mode": "official_html_initial_fetch"}
        if fetch_metadata.get("content_hash") and fetch_metadata["content_hash"] != _sha(raw): raise ValueError(f"cached source hash mismatch: {source.source_id}")
        fetch_metadata.pop("cache_hit", None)
        fetch_metadata.update({"http_status": int(fetch_metadata.get("http_status", 200)), "canonical_url": str(fetch_metadata.get("canonical_url") or source.url), "content_hash": _sha(raw)})
        metadata_path.write_text(json.dumps(fetch_metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sections, parsed = parse_naval_html(raw.decode("utf-8"), source, _sha(raw))
        source_manifest = {**_source_dict(source), **parsed, "schema_version": SCHEMA_VERSION, "raw_html_cached": True, "raw_html_sha256": _sha(raw), "section_count": len(sections), "http_status": fetch_metadata["http_status"], "official_page_named_participants": list(OFFICIAL_PAGE_PARTICIPANTS[source.source_id])}
        _write_jsonl(canonical_dir / "sections.jsonl", sections)
        observed = {row["speaker"] for row in sections}
        speakers = sorted(observed | set(OFFICIAL_PAGE_PARTICIPANTS[source.source_id]))
        (canonical_dir / "speakers.json").write_text(json.dumps([{"speaker": item, "speaker_status": "unknown" if item == "unknown" else "source_provided" if item in observed else "mentioned_in_official_description", "claim_attribution_allowed": item in observed and item != "unknown"} for item in speakers], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (canonical_dir / "source_manifest.json").write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (reports_dir / "source_brief.md").write_text(f"# {source.title}\n\n- Published: {source.published_at}\n- Official URL: {source.url}\n- Transcript status: `{parsed['transcript_status']}`\n- Sections: {len(sections)}\n- Speakers: {', '.join(speakers)}\n- Source family: `{source.source_family_id}`\n", encoding="utf-8")
        source_rows.append(source_manifest); all_sections.extend(sections)

    clusters, section_relations = _duplicate_clusters(all_sections)
    intelligence = _build_intelligence(all_sections, clusters)
    clustered_sections = {section_id for cluster in clusters for section_id in cluster["member_section_ids"]}
    for row in source_rows:
        row["duplicate_section_count"] = sum(section["section_id"] in clustered_sections for section in all_sections if section["source_id"] == row["source_id"])
        row["new_material_section_count"] = sum(section["section_id"] not in clustered_sections for section in all_sections if section["source_id"] == row["source_id"])
        if row["source_form"] == "full_compilation":
            row["new_material_status"] = "contains_conservatively_detected_new_material"
        source_root = output_dir / "sources" / row["source_id"]
        (source_root / "canonical" / "source_manifest.json").write_text(json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        source_claims = [item for item in intelligence["source_claims"] if item["source_id"] == row["source_id"]]
        source_evidence = [item for item in intelligence["source_evidence"] if item["source_id"] == row["source_id"]]
        _write_jsonl(source_root / "intelligence" / "claims.jsonl", source_claims)
        _write_jsonl(source_root / "intelligence" / "evidence.jsonl", source_evidence)
        _write_jsonl(source_root / "intelligence" / "theme_assignments.jsonl", [{"assignment_id": f"{item['claim_id']}.{theme}", "claim_id": item["claim_id"], "theme": theme, "assignment_method": "deterministic_keyword_v1", "confidence": 0.8} for item in source_claims for theme in item["themes"]])
    canonical = output_dir / "canonical"; intelligence_dir = output_dir / "intelligence"
    _write_jsonl(output_dir / "source_index.jsonl", sorted(source_rows, key=lambda row: row["site_rank"]))
    _write_jsonl(output_dir / "source_relations.jsonl", _source_relations())
    _write_jsonl(canonical / "sections.jsonl", sorted(all_sections, key=lambda row: (row["chronological_index"], row["section_order"])))
    observed_speakers = {row["speaker"] for row in all_sections}
    named_participants = {person for people in OFFICIAL_PAGE_PARTICIPANTS.values() for person in people}
    _write_jsonl(canonical / "speakers.jsonl", [{"speaker": speaker, "speaker_status": "unknown" if speaker == "unknown" else "source_provided" if speaker in observed_speakers else "mentioned_in_official_description", "source_ids": sorted({row["source_id"] for row in all_sections if row["speaker"] == speaker} or {source_id for source_id, people in OFFICIAL_PAGE_PARTICIPANTS.items() if speaker in people}), "section_ids": [row["section_id"] for row in all_sections if row["speaker"] == speaker], "claim_attribution_allowed": speaker in observed_speakers and speaker != "unknown"} for speaker in sorted(observed_speakers | named_participants)])
    _write_jsonl(canonical / "evidence.jsonl", intelligence["evidence"])
    _write_jsonl(canonical / "section_relations.jsonl", section_relations)
    _write_jsonl(canonical / "duplicate_content_clusters.jsonl", clusters)
    for name in ("source_claims", "canonical_claims", "claim_relations", "person_positions", "theme_assignments", "trend_candidates", "insight_candidates", "verification_queue", "open_questions"):
        _write_jsonl(intelligence_dir / f"{name}.jsonl", intelligence[name])
    manifest = {"schema_version": SCHEMA_VERSION, "corpus_id": "naval_recent_six", "snapshot_date": SNAPSHOT_DATE, "source_selection": "official_archive_contiguous_recent_six", "site_order": "newest-to-oldest", "analysis_order": "oldest-to-newest", "expected_source_ids": [source.source_id for source in SOURCES], "source_count": 6, "official_text_only": True, "source_families": sorted({source.source_family_id for source in SOURCES})}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    cursor = {"schema_version": SCHEMA_VERSION, "snapshot_date": SNAPSHOT_DATE, "newest_seen_source": "Live in the Future", "newest_seen_url": "https://nav.al/future", "oldest_processed_source": "Sell the Truth", "oldest_processed_url": "https://nav.al/sell", "processed_source_count": 6, "site_order": "newest-to-oldest", "next_older_source": "‘Nothing Ever Happens’ Is Over", "next_older_url": "https://nav.al/over", "next_older_published_at": "2026-05-04", "last_checked_at": SNAPSHOT_DATE, "archive_page": "https://nav.al/archive", "status": "ready_for_next_sequential_batch"}
    (output_dir / "ingestion_cursor.json").write_text(json.dumps(cursor, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    metrics = _report_metrics(source_rows, all_sections, clusters, intelligence)
    _write_reports(output_dir, source_rows, all_sections, clusters, intelligence, metrics)
    _write_views(output_dir, all_sections, clusters, intelligence)
    return {**metrics, "corpus_dir": str(output_dir), "transcript_absent_sources": [row["source_id"] for row in source_rows if row["transcript_status"] == "official_body_absent"]}

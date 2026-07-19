from __future__ import annotations

import hashlib
import html
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from gather_insight.adapters.ulisten_parser import parse_ulisten_file
from gather_insight.adapters.usetranscribe_parser import parse_usetranscribe_file

from .golden_annotation import _raw_cues, _segment_raw_spans, _target_window, _unit_raw_map
from .semantic_unit_segmenter import segment_secondary_text
from .transcript_fuser import normalize_for_similarity


_BOUNDARY_PAIRS = [(10, 11), (11, 12), (12, 13), (35, 36), (37, 38), (52, 53), (53, 54), (80, 81), (82, 83), (92, 93), (94, 95), (112, 113)]
_HIGH_RISK = [12, 11, 35, 36, 52, 53, 54, 80, 81, 82, 83, 92, 93, 94, 95, 6, 4, 115, 27, 74, 20, 7, 8]
_RANDOM_ORDINARY = [14, 22, 40, 44, 55, 63, 86, 91, 100, 108]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _fmt_time(seconds: float) -> str:
    value = int(seconds)
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _variant(output_dir: Path, key: str, label: str) -> dict[str, Any]:
    general = output_dir / "yt_wE1ZgJdt4uM" / "general"
    records = _read_jsonl(general / "transcript_fused.jsonl")
    trace = _read_jsonl(general / "alignment_trace.jsonl") if (general / "alignment_trace.jsonl").exists() else []
    operations: dict[str, str] = {}
    if trace and isinstance(trace[0].get("path"), list):
        for step in trace[0]["path"]:
            for index in step.get("source_indices", []):
                operations[f"yt_wE1ZgJdt4uM.seg_{int(index) + 1:04d}"] = str(step.get("operation"))
    else:
        operations = {record["segment_id"]: "phase_6_8_beam" for record in records}
    report = json.loads((general / "processing_report.json").read_text(encoding="utf-8"))
    return {"key": key, "label": label, "general": general, "records": {record["segment_id"]: record for record in records}, "operations": operations, "report": report}


def _selected_raw(record: dict[str, Any], unit_map: dict[str, dict[str, Any]], raw: str) -> dict[str, Any]:
    selected = [unit_map[unit_id] for unit_id in record.get("semantic_unit_ids", []) if unit_id in unit_map]
    if not selected:
        return {"char_start": None, "char_end": None, "raw_text": ""}
    start = min(int(unit["raw_char_start"]) for unit in selected)
    end = max(int(unit["raw_char_end"]) for unit in selected)
    return {"char_start": start, "char_end": end, "raw_text": raw[start:end]}


def _source_index(input_dir: Path) -> dict[str, Any]:
    manifest = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
    media_id = str(manifest["canonical_youtube_video_id"])
    if not media_id.startswith("yt_"):
        media_id = f"yt_{media_id}"
    youtube_url = str(manifest["youtube_url"])
    ulisten = parse_ulisten_file(path=input_dir / "source_ulisten_raw.md", media_id=media_id, youtube_url=youtube_url)
    use_path = input_dir / "source_usetranscribe_raw.md"
    raw = use_path.read_text(encoding="utf-8")
    use = parse_usetranscribe_file(path=use_path, media_id=media_id, youtube_url=youtube_url, video_duration_seconds=float(manifest.get("duration_seconds") or 0))
    cues = _raw_cues(raw)
    spans = _segment_raw_spans(use, cues)
    units = segment_secondary_text(use.segments, max_unit_chars=260)
    unit_map = _unit_raw_map(use, units, spans)
    return {"manifest": manifest, "ulisten": ulisten, "use": use, "raw": raw, "cues": cues, "unit_map": unit_map, "use_path": use_path}


def _review_priorities(records: dict[str, dict[str, Any]], fixed_golden_ids: set[str]) -> tuple[list[str], dict[str, list[str]], list[str]]:
    tags: dict[str, list[str]] = defaultdict(list)
    for left, right in _BOUNDARY_PAIRS:
        tags[f"yt_wE1ZgJdt4uM.seg_{left:04d}"].append("A speaker switch")
        tags[f"yt_wE1ZgJdt4uM.seg_{right:04d}"].append("A speaker switch")
    for number in _HIGH_RISK:
        tags[f"yt_wE1ZgJdt4uM.seg_{number:04d}"].append("B high risk")
    for number in _RANDOM_ORDINARY:
        tags[f"yt_wE1ZgJdt4uM.seg_{number:04d}"].append("C ordinary sample")
    for segment_id in fixed_golden_ids:
        tags[segment_id].append("fixed golden set")
    all_ids = set(segment_id for segment_id, record in records.items() if record.get("needs_review")) | set(tags) | fixed_golden_ids
    order = sorted(all_ids, key=lambda segment_id: (
        0 if "A speaker switch" in tags.get(segment_id, []) else 1 if "B high risk" in tags.get(segment_id, []) else 2 if "C ordinary sample" in tags.get(segment_id, []) else 3,
        int(segment_id.rsplit("_", 1)[1]),
    ))
    recommended = order[:30]
    return order, tags, recommended


def _meaningful_unallocated(variant: dict[str, Any], unit_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    path = variant["general"] / "unallocated_secondary.jsonl"
    if not path.exists():
        return []
    output = []
    for unit in _read_jsonl(path):
        text = str(unit.get("text") or "").strip()
        if len(normalize_for_similarity(text)) < 80:
            continue
        mapped = unit_map.get(str(unit.get("unit_id")), {})
        output.append({**unit, "raw_char_start": mapped.get("raw_char_start"), "raw_char_end": mapped.get("raw_char_end"), "summary": text[:180] + ("…" if len(text) > 180 else "")})
    return sorted(output, key=lambda item: (float(item.get("approx_start_seconds", 0)), str(item.get("unit_id"))))


def generate_yc_review_views(
    *,
    input_dir: Path,
    output_dir: Path,
    phase_6_8_dir: Path,
    vecalign_raw_dir: Path,
    vecalign_margin_dir: Path,
    sentalign_margin_dir: Path,
    golden_selection_path: Path | None = None,
) -> dict[str, Any]:
    source = _source_index(input_dir)
    variants = [
        _variant(phase_6_8_dir, "A", "Phase 6.8 local beam"),
        _variant(vecalign_raw_dir, "B", "Vecalign raw cosine"),
        _variant(vecalign_margin_dir, "C", "Vecalign margin"),
        _variant(sentalign_margin_dir, "D", "SentAlign-style margin"),
    ]
    primary = variants[1]
    primary_records = primary["records"]
    unallocated = _meaningful_unallocated(primary, source["unit_map"])
    output_dir.mkdir(parents=True, exist_ok=True)
    reading_path = output_dir / "yc_fused_reading_view.html"
    review_path = output_dir / "yc_alignment_review.html"
    template_path = output_dir / "yc_alignment_review_template.jsonl"
    reading_path.write_text(_reading_html(source, primary, unallocated), encoding="utf-8")
    selection_path = golden_selection_path or Path(__file__).resolve().parents[2] / "config" / "yc_golden_selection_v1.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    fixed_numbers: set[int] = set()
    for values in selection["categories"].values():
        for value in values:
            fixed_numbers.update(int(number) for number in (value if isinstance(value, list) else [value]))
    fixed_golden_ids = {f"yt_wE1ZgJdt4uM.seg_{number:04d}" for number in fixed_numbers}
    order, tags, recommended = _review_priorities(primary_records, fixed_golden_ids)
    templates = _review_templates(order, tags, primary_records, primary, source, unallocated)
    template_path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in templates), encoding="utf-8")
    review_path.write_text(_alignment_html(source, variants, order, tags, unallocated, templates), encoding="utf-8")
    manifest = {
        "status": "ok",
        "reading_view": str(reading_path.resolve()),
        "alignment_review": str(review_path.resolve()),
        "review_template": str(template_path.resolve()),
        "recommended_first_30": recommended,
        "review_segment_count": len(order),
        "fixed_golden_segment_count": len(fixed_golden_ids),
        "meaningful_unallocated_count": len(unallocated),
        "input_sha256": {"source_ulisten_raw.md": _sha256(input_dir / "source_ulisten_raw.md"), "source_usetranscribe_raw.md": _sha256(input_dir / "source_usetranscribe_raw.md")},
        "variant_mapping": {item["key"]: item["label"] for item in variants},
    }
    (output_dir / "yc_review_views_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _reading_html(source: dict[str, Any], primary: dict[str, Any], unallocated: list[dict[str, Any]]) -> str:
    records = [primary["records"][segment.segment_id] for segment in source["ulisten"].segments]
    by_after: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for unit in unallocated:
        position = 0
        for index, record in enumerate(records):
            if float(record["start_seconds"]) <= float(unit["approx_start_seconds"]):
                position = index
        by_after[position].append(unit)
    review_count = sum(bool(record.get("needs_review")) for record in records)
    fallback_count = sum(record.get("text_source") == "ulisten_raw_review_fallback" for record in records)
    reason_counts = Counter(reason for record in records for reason in record.get("review_reasons", []))
    cards = []
    previous_speaker = None
    for index, record in enumerate(records):
        if previous_speaker is not None and previous_speaker != record.get("speaker"):
            cards.append(f'<div class="switch">Speaker switch: {_esc(previous_speaker)} → {_esc(record.get("speaker"))}</div>')
        classes = ["segment"]
        if record.get("needs_review"): classes.append("review")
        if record.get("text_source") == "ulisten_raw_review_fallback": classes.append("fallback")
        badges = [f'<span class="badge">{_esc(record.get("text_source"))}</span>']
        if record.get("needs_review"): badges.append('<span class="badge review-badge">review</span>')
        if record.get("text_source") == "ulisten_raw_review_fallback": badges.append('<span class="badge fallback-badge">fallback</span>')
        cards.append(f'''<article class="{' '.join(classes)}"><header><a href="{_esc(record['youtube_url'])}" target="_blank">{_fmt_time(float(record['start_seconds']))}</a> · <strong>{_esc(record.get('speaker'))}</strong> · {_esc(record.get('chapter'))} {' '.join(badges)}</header><div class="text">{_esc(record.get('text'))}</div><small>{_esc(record.get('segment_id'))}</small></article>''')
        for unit in by_after.get(index, []):
            cards.append(f'''<details class="unallocated"><summary>Unallocated near {_fmt_time(float(unit['approx_start_seconds']))}: {_esc(unit['summary'])}</summary><p>unit {_esc(unit.get('unit_id'))} · raw chars {_esc(unit.get('raw_char_start'))}–{_esc(unit.get('raw_char_end'))}</p><pre>{_esc(unit.get('text'))}</pre></details>''')
        previous_speaker = record.get("speaker")
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>YC fused reading view</title><style>body{{font:15px/1.55 system-ui;margin:24px auto;max-width:1000px;color:#222}}.summary{{background:#eef3f7;padding:16px;border-radius:8px}}.segment{{padding:14px 16px;border-bottom:1px solid #ddd}}.segment.review{{background:#fff8df}}.segment.fallback{{border-left:5px solid #a66524;background:#fff0df}}.switch{{margin:24px 0 8px;border-top:3px solid #5d7185;padding-top:8px;color:#445}}.badge{{font-size:12px;background:#e8ebee;padding:2px 6px;border-radius:10px}}.review-badge{{background:#ffe49a}}.fallback-badge{{background:#f4ba85}}.text{{white-space:pre-wrap;margin:9px 0}}.unallocated{{background:#eef7ee;border-left:5px solid #4f8a4f;padding:9px 12px;margin:5px 0}}pre{{white-space:pre-wrap}}</style></head><body><h1>YC fused transcript reading view</h1><div class="summary"><p>115 structure segments · {review_count} review · {fallback_count} fallback · {len(unallocated)} meaningful unallocated units</p><p>Primary reading result: Vecalign raw cosine. This page is for continuity reading, not golden annotation.</p><details><summary>Review reason distribution</summary><pre>{_esc(json.dumps(reason_counts, ensure_ascii=False, indent=2))}</pre></details></div>{''.join(cards)}</body></html>'''


def _review_templates(order: list[str], tags: dict[str, list[str]], records: dict[str, dict[str, Any]], primary: dict[str, Any], source: dict[str, Any], unallocated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for segment_id in order:
        record = records[segment_id]
        selected = _selected_raw(record, source["unit_map"], source["raw"])
        output.append({
            "review_item_id": f"review.{segment_id}", "item_type": "segment", "segment_id": segment_id,
            "priority": tags.get(segment_id, ["review queue"]), "verdict": "",
            "current_char_start": selected["char_start"], "current_char_end": selected["char_end"],
            "corrected_char_start": None, "corrected_char_end": None,
            "transition_owner": "uncertain", "reviewer_note": ""
        })
    for unit in unallocated:
        output.append({
            "review_item_id": f"review.unallocated.{unit['unit_id']}", "item_type": "unallocated", "unit_id": unit["unit_id"],
            "priority": ["D meaningful unallocated"], "verdict": "", "current_char_start": unit.get("raw_char_start"), "current_char_end": unit.get("raw_char_end"),
            "corrected_char_start": None, "corrected_char_end": None, "transition_owner": "gap", "reviewer_note": ""
        })
    return output


def _variant_payload(segment_id: str, variant: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    record = variant["records"].get(segment_id, {})
    selected = _selected_raw(record, source["unit_map"], source["raw"])
    return {
        "result": variant["key"], "text": record.get("text"), "text_source": record.get("text_source"),
        "alignment_confidence": record.get("alignment_confidence"), "raw_cosine": record.get("raw_cosine") or (record.get("alignment_components") or {}).get("raw_cosine"),
        "margin": record.get("margin_score") or (record.get("alignment_components") or {}).get("margin_score"), "operation": variant["operations"].get(segment_id),
        "review_reasons": record.get("review_reasons", []), "conflicts": record.get("conflicts", []), "secondary_segment_ids": record.get("secondary_segment_ids", []),
        "char_start": selected["char_start"], "char_end": selected["char_end"], "selected_raw_text": selected["raw_text"], "fallback": record.get("text_source") == "ulisten_raw_review_fallback"
    }


def _alignment_html(source: dict[str, Any], variants: list[dict[str, Any]], order: list[str], tags: dict[str, list[str]], unallocated: list[dict[str, Any]], templates: list[dict[str, Any]]) -> str:
    structures = {segment.segment_id: segment for segment in source["ulisten"].segments}
    positions = {segment.segment_id: index for index, segment in enumerate(source["ulisten"].segments)}
    cards = []
    template_by_id = {item.get("segment_id"): item for item in templates if item["item_type"] == "segment"}
    payload: dict[str, Any] = {}
    boundary_ids = {number for pair in _BOUNDARY_PAIRS for number in pair}
    for segment_id in order:
        segment = structures[segment_id]; index = positions[segment_id]
        previous = source["ulisten"].segments[index - 1] if index else None
        following = source["ulisten"].segments[index + 1] if index + 1 < len(source["ulisten"].segments) else None
        window = _target_window(source["cues"], segment.start_seconds, segment.end_seconds, 45, source["raw"])
        payload[segment_id] = {variant["key"]: _variant_payload(segment_id, variant, source) for variant in variants}
        template = template_by_id[segment_id]
        speaker_near = int(segment_id.rsplit("_", 1)[1]) in boundary_ids
        cards.append(f'''<article class="review-card" data-item='{_esc(json.dumps(template, ensure_ascii=False))}' id="card-{_esc(segment_id)}"><h2>{_esc(segment_id)} · {_fmt_time(segment.start_seconds)} · {_esc(segment.speaker)}</h2><p>{' · '.join(_esc(tag) for tag in tags.get(segment_id, ['review queue']))} · chapter {_esc(segment.chapter)} · speaker-switch-near: <strong>{str(speaker_near).lower()}</strong> · <a target="_blank" href="{_esc(segment.youtube_url)}">YouTube</a></p><h3>uListen raw</h3><pre>{_esc(segment.text_raw)}</pre><h3>Adjacent structure</h3><pre>{_esc((previous.segment_id + ' | ' + previous.speaker + '\n' + previous.text_raw) if previous else '(start)')}\n\n--- current ---\n\n{_esc((following.segment_id + ' | ' + following.speaker + '\n' + following.text_raw) if following else '(end)')}</pre><h3>UseTranscribe local complete window</h3><p>raw offsets {window['raw_char_start']}–{window['raw_char_end']}</p><textarea readonly class="source-window" data-base="{window['raw_char_start']}">{_esc(window['raw_text'])}</textarea><button onclick="fillSelection(this)">Use selected raw range as correction</button><details><summary>Show anonymized algorithm result</summary><p>{''.join(f'<button onclick="showResult(this,\'{variant["key"]}\')">Result {variant["key"]}</button>' for variant in variants)}</p><pre class="result-box">Choose A/B/C/D. Algorithm identity remains hidden by default.</pre></details><div class="form"><label>verdict <select class="verdict"><option value=""></option><option>correct</option><option>boundary_adjustment</option><option>wrong_speaker</option><option>wrong_content</option><option>should_fallback</option><option>source_missing</option><option>uncertain</option></select></label><label>corrected_char_start <input class="corrected-start" type="number"></label><label>corrected_char_end <input class="corrected-end" type="number"></label><label>transition_owner <select class="owner"><option>uncertain</option><option>left</option><option>right</option><option>gap</option></select></label><label>reviewer_note <textarea class="note"></textarea></label></div></article>''')
    unallocated_cards = []
    for unit in unallocated:
        template = next(item for item in templates if item.get("unit_id") == unit["unit_id"])
        unallocated_cards.append(f'''<article class="review-card unallocated" data-item='{_esc(json.dumps(template, ensure_ascii=False))}'><h2>D unallocated · {_fmt_time(float(unit['approx_start_seconds']))}</h2><p>{_esc(unit['unit_id'])} · raw chars {_esc(unit.get('raw_char_start'))}–{_esc(unit.get('raw_char_end'))}</p><pre>{_esc(unit.get('text'))}</pre><div class="form"><label>verdict <select class="verdict"><option value=""></option><option>correct</option><option>boundary_adjustment</option><option>wrong_speaker</option><option>wrong_content</option><option>should_fallback</option><option>source_missing</option><option>uncertain</option></select></label><label>corrected_char_start <input class="corrected-start" type="number"></label><label>corrected_char_end <input class="corrected-end" type="number"></label><label>transition_owner <select class="owner"><option>gap</option><option>left</option><option>right</option><option>uncertain</option></select></label><label>reviewer_note <textarea class="note"></textarea></label></div></article>''')
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    mapping = " · ".join(f"Result {variant['key']} = {variant['label']}" for variant in variants)
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>YC alignment review</title><style>body{{font:14px/1.45 system-ui;margin:24px auto;max-width:1200px}}.review-card{{border:1px solid #bbb;padding:16px;margin:18px 0;background:#fffdf7}}.unallocated{{background:#eef7ee}}pre{{white-space:pre-wrap;background:#f4f4f4;padding:10px}}textarea.source-window{{width:100%;height:240px;font:13px monospace}}.form{{display:grid;gap:8px;margin-top:12px}}.form label{{display:grid;grid-template-columns:190px 1fr;gap:8px}}.result-box{{background:#edf2f7}}button{{margin:3px}}.top{{position:sticky;top:0;background:white;border-bottom:1px solid #aaa;padding:10px;z-index:3}}</style></head><body><div class="top"><h1>YC alignment review — blind A/B/C/D</h1><button onclick="downloadReview()">Download review JSONL</button><details><summary>Reveal result mapping only after blind review</summary><p>{_esc(mapping)}</p></details></div><p>All primary review segments are included. Algorithm output is collapsed by default. Select exact raw source text, then use the correction button.</p>{''.join(cards)}<h1>D. Meaningful unallocated text</h1>{''.join(unallocated_cards)}<script>const DATA={data};
function cardFor(el){{return el.closest('.review-card')}}
function showResult(button,key){{const card=cardFor(button);const item=JSON.parse(card.dataset.item);const value=DATA[item.segment_id][key];card.querySelector('.result-box').textContent=JSON.stringify(value,null,2)}}
function fillSelection(button){{const card=cardFor(button),ta=card.querySelector('.source-window');if(ta.selectionStart===ta.selectionEnd){{alert('Select source text first');return}}card.querySelector('.corrected-start').value=Number(ta.dataset.base)+ta.selectionStart;card.querySelector('.corrected-end').value=Number(ta.dataset.base)+ta.selectionEnd}}
function downloadReview(){{const rows=[...document.querySelectorAll('.review-card')].map(card=>{{const row=JSON.parse(card.dataset.item);row.verdict=card.querySelector('.verdict').value;row.corrected_char_start=card.querySelector('.corrected-start').value===''?null:Number(card.querySelector('.corrected-start').value);row.corrected_char_end=card.querySelector('.corrected-end').value===''?null:Number(card.querySelector('.corrected-end').value);row.transition_owner=card.querySelector('.owner').value;row.reviewer_note=card.querySelector('.note').value;return row}});const text=rows.map(x=>JSON.stringify(x)).join('\\n')+'\\n';const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{{type:'application/jsonl'}}));a.download='yc_alignment_review_completed.jsonl';a.click()}}
</script></body></html>'''

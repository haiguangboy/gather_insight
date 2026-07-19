"""Private, algorithm-blind YC golden-set packaging and evaluation."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gather_insight.adapters.ulisten_parser import UlistenParseResult, parse_ulisten_file
from gather_insight.adapters.usetranscribe_parser import UseTranscribeParseResult, parse_usetranscribe_file
from gather_insight.pipeline.alignment_evaluation import AlignmentEvaluation, _prf, _range_points
from gather_insight.pipeline.semantic_unit_segmenter import SEMANTIC_UNIT_VERSION, SemanticUnit, segment_secondary_text
from gather_insight.pipeline.transcript_fuser import normalize_for_similarity
from gather_insight.pipeline.transcript_normalizer import parse_timestamp


GOLDEN_PACKAGE_VERSION = "yc_golden_package_v1"
LABEL_SELECTION_VERSION = "yc_golden_selection_v1"
_CUE = re.compile(r"^\s*\[\[(?P<timestamp>\d{1,2}:\d{2}(?::\d{2})?)\]\]\((?P<url>https?://[^)]+)\)\s*$", re.MULTILINE)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _raw_cues(raw: str) -> list[dict[str, Any]]:
    matches = list(_CUE.finditer(raw))
    cues: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        raw_start = match.start()
        body_start = match.end()
        while body_start < len(raw) and raw[body_start] in "\r\n":
            body_start += 1
        raw_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        body_end = raw_end
        while body_end > body_start and raw[body_end - 1] in "\r\n":
            body_end -= 1
        cues.append({
            "cue_index": index + 1,
            "timestamp": match.group("timestamp"),
            "start_seconds": parse_timestamp(match.group("timestamp")),
            "youtube_url": match.group("url"),
            "raw_char_start": raw_start,
            "raw_char_end": raw_end,
            "text_char_start": body_start,
            "text_char_end": body_end,
            "raw_text": raw[raw_start:raw_end],
            "text": raw[body_start:body_end],
        })
    if not cues:
        raise ValueError("no UseTranscribe cue lines found for golden packaging")
    return cues


def _segment_raw_spans(parsed: UseTranscribeParseResult, cues: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if len(parsed.segments) != len(cues):
        raise ValueError(f"UseTranscribe cue/segment count changed: {len(cues)} != {len(parsed.segments)}")
    spans: dict[str, dict[str, Any]] = {}
    for segment, cue in zip(parsed.segments, cues):
        text = segment.text
        relative = cue["text"].find(text)
        exact = relative >= 0
        if not exact:
            compact = normalize_for_similarity(cue["text"])
            target = normalize_for_similarity(text)
            if target and target in compact:
                relative = cue["text"].find(text[: min(32, len(text))])
        if relative < 0:
            relative = 0
        spans[segment.segment_id] = {
            **cue,
            "segment_text": text,
            "segment_text_char_start": cue["text_char_start"] + relative,
            "segment_text_char_end": cue["text_char_start"] + relative + len(text),
            "raw_mapping_exact": exact,
        }
    return spans


def _unit_raw_map(parsed: UseTranscribeParseResult, units: list[SemanticUnit], spans: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_segment: dict[str, list[SemanticUnit]] = {}
    for unit in units:
        by_segment.setdefault(unit.secondary_segment_id, []).append(unit)
    output: dict[str, dict[str, Any]] = {}
    for segment in parsed.segments:
        cursor = 0
        span = spans[segment.segment_id]
        for unit in by_segment.get(segment.segment_id, []):
            local = segment.text.find(unit.text, cursor)
            if local < 0:
                local = cursor
            raw_start = int(span["segment_text_char_start"]) + local
            raw_end = raw_start + len(unit.text)
            output[unit.unit_id] = {**unit.as_dict(), "unit_index": len(output), "raw_char_start": raw_start, "raw_char_end": raw_end}
            cursor = local + len(unit.text)
    return output


def _load_selection(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("selection_version") != LABEL_SELECTION_VERSION:
        raise ValueError("unsupported YC golden selection version")
    return value


def _selection_items(selection: dict[str, Any]) -> list[tuple[str, str, list[int]]]:
    rows: list[tuple[str, str, list[int]]] = []
    number = 1
    for category in ("speaker_switch", "ordinary", "short_or_repeated", "phase_6_8_fallback"):
        for value in selection["categories"][category]:
            ids = list(value) if category == "speaker_switch" else [int(value)]
            rows.append((f"yc_golden_v1.{number:03d}.{category}", category, ids))
            number += 1
    if len(rows) != 52:
        raise ValueError(f"YC golden selection must contain 52 items, got {len(rows)}")
    return rows


def _context_segments(result: UlistenParseResult, indices: list[int]) -> list[dict[str, Any]]:
    selected = set(indices)
    context = set()
    for index in indices:
        context.update({index - 1, index, index + 1})
    return [segment.as_dict() for index, segment in enumerate(result.segments, 1) if index in context and index not in selected]


def _target_window(cues: list[dict[str, Any]], start: float, end: float, padding: float, raw: str) -> dict[str, Any]:
    candidates = [cue for cue in cues if cue["start_seconds"] <= end + padding and cue["start_seconds"] >= start - padding]
    if not candidates:
        candidates = [min(cues, key=lambda cue: abs(cue["start_seconds"] - start))]
    first, last = candidates[0], candidates[-1]
    return {
        "start_seconds": first["start_seconds"],
        "end_seconds": (last["start_seconds"] if last is not first else end) + padding,
        "raw_char_start": first["raw_char_start"],
        "raw_char_end": last["raw_char_end"],
        "raw_text": raw[first["raw_char_start"]:last["raw_char_end"]],
        "cues": candidates,
    }


def build_yc_golden_package(*, input_dir: Path, package_dir: Path, selection_path: Path, target_window_padding_seconds: float | None = None) -> dict[str, Any]:
    selection = _load_selection(selection_path)
    manifest = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
    media_id = str(manifest["canonical_youtube_video_id"])
    youtube_url = str(manifest["youtube_url"])
    if not media_id.startswith("yt_"):
        media_id = f"yt_{media_id}"
    ulisten = parse_ulisten_file(path=input_dir / "source_ulisten_raw.md", media_id=media_id, youtube_url=youtube_url)
    use_path = input_dir / "source_usetranscribe_raw.md"
    use_raw = use_path.read_text(encoding="utf-8")
    use = parse_usetranscribe_file(path=use_path, media_id=media_id, youtube_url=youtube_url, video_duration_seconds=float(manifest.get("duration_seconds") or 0))
    cues = _raw_cues(use_raw)
    spans = _segment_raw_spans(use, cues)
    units = segment_secondary_text(use.segments, max_unit_chars=260)
    unit_map = _unit_raw_map(use, units, spans)
    padding = float(target_window_padding_seconds if target_window_padding_seconds is not None else selection.get("target_window_padding_seconds", 45))
    items: list[dict[str, Any]] = []
    for item_id, category, indices in _selection_items(selection):
        selected_segments = [ulisten.segments[index - 1] for index in indices]
        start = min(segment.start_seconds for segment in selected_segments)
        end = max(segment.end_seconds for segment in selected_segments)
        window = _target_window(cues, start, end, padding, use_raw)
        item = {
            "item_id": item_id,
            "category": category,
            "structure_segment_ids": [segment.segment_id for segment in selected_segments],
            "structure_segments": [segment.as_dict() for segment in selected_segments],
            "structure_context_before_after": _context_segments(ulisten, indices),
            "youtube_url": selected_segments[0].youtube_url,
            "youtube_window_url": f"{youtube_url}&t={int(max(0, start - 5))}s",
            "target_source_file": use_path.name,
            "target_source_sha256": _sha256(use_path),
            "target_window": window,
            "target_units": [value for unit in units for value in [unit_map[unit.unit_id]] if value["raw_char_end"] >= window["raw_char_start"] and value["raw_char_start"] <= window["raw_char_end"]],
            "semantic_unit_version": SEMANTIC_UNIT_VERSION,
            "raw_mapping_exact": all(spans[segment.segment_id]["raw_mapping_exact"] for segment in use.segments),
            "algorithm_output": None
        }
        items.append(item)
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "items.jsonl").write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items), encoding="utf-8")
    labels_template = [
        {"item_id": item["item_id"], "selection_version": LABEL_SELECTION_VERSION, "reviewer": "", "annotation_version": "", "status": "uncertain", "ranges": [], "notes": "", "finalized_at": ""}
        for item in items
    ]
    (package_dir / "labels.template.jsonl").write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in labels_template), encoding="utf-8")
    manifest_out = {
        "package_version": GOLDEN_PACKAGE_VERSION,
        "selection_version": LABEL_SELECTION_VERSION,
        "media_id": media_id,
        "youtube_url": youtube_url,
        "item_count": len(items),
        "categories": dict(Counter(item["category"] for item in items)),
        "input_sha256": {"source_ulisten_raw.md": _sha256(input_dir / "source_ulisten_raw.md"), "source_usetranscribe_raw.md": _sha256(use_path)},
        "selection_path": str(selection_path),
        "algorithm_output_included": False,
        "package_id": hashlib.sha256((selection["selection_version"] + _sha256(input_dir / "source_ulisten_raw.md") + _sha256(use_path)).encode("utf-8")).hexdigest(),
    }
    (package_dir / "package_manifest.json").write_text(json.dumps(manifest_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (package_dir / "review.html").write_text(_review_html(items, manifest_out), encoding="utf-8")
    return manifest_out


def _review_html(items: list[dict[str, Any]], manifest: dict[str, Any]) -> str:
    data = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(f"GatherInsight YC Golden {manifest['selection_version']}")
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font:14px system-ui;margin:24px;max-width:1200px}}.item{{border:1px solid #bbb;padding:16px;margin:20px 0}}pre{{white-space:pre-wrap;background:#f5f5f5;padding:10px}}textarea{{width:100%;height:230px;font:13px monospace}}.ctx{{color:#555}}label{{margin-right:16px}}.saved{{color:#087f23}}</style></head>
<body><h1>YC Golden Annotation — algorithm-blind</h1>
<p>This package intentionally contains no prediction, score, threshold, or algorithm name. Select exact ranges in the immutable raw UseTranscribe window. Offsets shown are offsets in <code>source_usetranscribe_raw.md</code>.</p>
<p>Reviewer <input id="reviewer" placeholder="name or ID"> Annotation version <input id="version" value="golden_annotation_v1"></p>
<button onclick="downloadLabels()">Download labels JSONL</button> <span id="saved" class="saved"></span>
<div id="items"></div><script>
const ITEMS={data}; const LABELS={{}};
function esc(s){{return String(s??'').replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]))}}
function offset(textarea,pos){{return textarea.dataset.base*1+pos}}
function speakerFor(item,role){{if(['left_speaker_end','short_transition_left'].includes(role))return item.structure_segments[0].speaker;if(['right_speaker_start','short_transition_right'].includes(role))return item.structure_segments[item.structure_segments.length-1].speaker;if(role==='segment_text'&&item.structure_segments.length===1)return item.structure_segments[0].speaker;return null}}
function addRange(id,role){{const item=ITEMS.find(x=>x.item_id===id);const ta=document.getElementById('ta-'+id); const start=ta.selectionStart,end=ta.selectionEnd; if(start===end){{alert('Select a non-empty raw range first');return}}; const box=document.getElementById('ranges-'+id); const row=document.createElement('div'); const value={{role,char_start:offset(ta,start),char_end:offset(ta,end),speaker:speakerFor(item,role),unit_ids:[]}}; row.textContent=role+': '+value.char_start+'–'+value.char_end+' '; const hidden=document.createElement('input');hidden.type='hidden';hidden.className='range-json';hidden.value=JSON.stringify(value);row.appendChild(hidden); const btn=document.createElement('button');btn.textContent='remove';btn.onclick=()=>row.remove();row.appendChild(btn);box.appendChild(row)}}
function collect(item){{const id=item.item_id; const ranges=[...document.querySelectorAll('#ranges-'+id+' .range-json')].map(x=>JSON.parse(x.value)); return {{item_id:id,selection_version:'{LABEL_SELECTION_VERSION}',reviewer:document.getElementById('reviewer').value,annotation_version:document.getElementById('version').value,status:document.getElementById('status-'+id).value,ranges,notes:document.getElementById('notes-'+id).value,finalized_at:new Date().toISOString()}}}}
function downloadLabels(){{if(!document.getElementById('reviewer').value.trim()){{alert('Reviewer is required');return}}const out=ITEMS.map(collect).map(x=>JSON.stringify(x)).join('\\n')+'\\n'; const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([out],{{type:'application/jsonl'}}));a.download='labels.{LABEL_SELECTION_VERSION}.jsonl';a.click();document.getElementById('saved').textContent='Downloaded '+new Date().toLocaleTimeString()}}
function render(item){{const id=item.item_id; const el=document.createElement('section');el.className='item'; const structure=item.structure_segments.map(x=>'<pre>'+esc(x.segment_id+' | '+x.speaker+' | '+x.start_seconds+'–'+x.end_seconds+'\\n'+x.text_raw)+'</pre>').join(''); const ctx=item.structure_context_before_after.map(x=>esc(x.segment_id+' | '+x.speaker+' | '+x.start_seconds+'–'+x.end_seconds+'\\n'+x.text_raw)).join('\\n\\n'); const roles=['segment_text','left_speaker_end','gap_event','right_speaker_start','short_transition_left','short_transition_right','short_transition_gap']; el.innerHTML='<h2>'+esc(id)+' — '+esc(item.category)+'</h2><p><a target="_blank" href="'+esc(item.youtube_window_url)+'">Open YouTube window</a></p><h3>uListen segment</h3>'+structure+'<h3>Adjacent structure context</h3><pre class="ctx">'+ctx+'</pre><h3>Raw UseTranscribe window</h3><p>global raw offsets '+item.target_window.raw_char_start+'–'+item.target_window.raw_char_end+'</p><textarea readonly id="ta-'+id+'" data-base="'+item.target_window.raw_char_start+'">'+esc(item.target_window.raw_text)+'</textarea><p><select id="role-'+id+'">'+roles.map(x=>'<option>'+x+'</option>').join('')+'</select> <button onclick="addRange(\''+id+'\',document.getElementById(\'role-'+id+'\').value)">Add selected range</button></p><div id="ranges-'+id+'"></div><select id="status-'+id+'"><option>uncertain</option><option>correct_alignment</option><option>should_fallback</option><option>source_missing</option><option>structure_segmentation_questionable</option></select><br><textarea id="notes-'+id+'" placeholder="notes"></textarea>'; el.querySelector('#ranges-'+id).innerHTML=''; return el}}
ITEMS.forEach(item=>document.getElementById('items').appendChild(render(item)));
</script></body></html>'''


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _validate_labels(labels: list[dict[str, Any]], item_ids: set[str]) -> None:
    seen: set[str] = set()
    for label in labels:
        item_id = str(label.get("item_id"))
        if item_id in seen or item_id not in item_ids:
            raise ValueError(f"invalid or duplicate golden label item_id: {item_id}")
        seen.add(item_id)
        if label.get("selection_version") != LABEL_SELECTION_VERSION:
            raise ValueError(f"label {item_id} has an incompatible selection version")
        for item in label.get("ranges", []):
            if int(item["char_end"]) <= int(item["char_start"]):
                raise ValueError(f"empty or reversed range in {item_id}")
    missing = item_ids - seen
    if missing:
        raise ValueError(f"golden labels are incomplete; missing {len(missing)} items")


def _prediction_chars(record: dict[str, Any], units: dict[str, dict[str, Any]]) -> set[int]:
    points: set[int] = set()
    for unit_id in record.get("semantic_unit_ids", []):
        unit = units.get(str(unit_id))
        if unit:
            points.update(range(int(unit["raw_char_start"]), int(unit["raw_char_end"])))
    return points


def evaluate_yc_golden(*, package_dir: Path, labels_path: Path, predictions_path: Path, output_path: Path | None = None) -> dict[str, Any]:
    items = _read_jsonl(package_dir / "items.jsonl")
    labels = _read_jsonl(labels_path)
    predictions = {str(item["segment_id"]): item for item in _read_jsonl(predictions_path)}
    item_by_id = {item["item_id"]: item for item in items}
    _validate_labels(labels, set(item_by_id))
    units = {unit["unit_id"]: unit for item in items for unit in item["target_units"]}
    char_pred: set[tuple[str, int]] = set(); char_gold: set[tuple[str, int]] = set()
    unit_pred: set[tuple[str, str]] = set(); unit_gold: set[tuple[str, str]] = set()
    exact_boundary: list[bool] = []; tolerance_boundary: list[bool] = []; speaker_results: list[bool] = []
    fallback_gold: set[str] = set(); fallback_pred: set[str] = set(); omissions = 0; meaningful = 0; wrong_speaker = 0
    for label in labels:
        item = item_by_id[label["item_id"]]
        segment_ids = item["structure_segment_ids"]
        records = [predictions.get(segment_id, {}) for segment_id in segment_ids]
        pred_chars_by_segment = {segment_id: _prediction_chars(record, units) for segment_id, record in zip(segment_ids, records)}
        pred_units_by_segment = {segment_id: {str(x) for x in record.get("semantic_unit_ids", [])} for segment_id, record in zip(segment_ids, records)}
        gold_ranges = label.get("ranges", [])
        gold_chars = _range_points([[r["char_start"], r["char_end"]] for r in gold_ranges if r["role"] != "gap_event"])
        pred_chars = set().union(*(pred_chars_by_segment.values())) if pred_chars_by_segment else set()
        for point in pred_chars: char_pred.add((label["item_id"], point))
        for point in gold_chars: char_gold.add((label["item_id"], point))
        gold_units = {unit_id for unit_id, unit in units.items() if gold_chars.intersection(range(int(unit["raw_char_start"]), int(unit["raw_char_end"])))} if gold_chars else set()
        for segment_id, unit_ids in pred_units_by_segment.items():
            unit_pred.update((label["item_id"], unit_id) for unit_id in unit_ids)
        unit_gold.update((label["item_id"], unit_id) for unit_id in gold_units)
        if label["status"] in {"should_fallback", "source_missing"}:
            fallback_gold.add(label["item_id"])
        if any(record.get("text_source") == "ulisten_raw_review_fallback" for record in records):
            fallback_pred.add(label["item_id"])
        meaningful += len(gold_chars)
        omissions += len(gold_chars - pred_chars)
        if item["category"] == "speaker_switch":
            left_range = _range_points([[r["char_start"], r["char_end"]] for r in gold_ranges if r["role"] in {"left_speaker_end", "short_transition_left"}])
            right_range = _range_points([[r["char_start"], r["char_end"]] for r in gold_ranges if r["role"] in {"right_speaker_start", "short_transition_right"}])
            left_pred = pred_chars_by_segment.get(segment_ids[0], set())
            right_pred = pred_chars_by_segment.get(segment_ids[-1], set())
            speaker_ok = bool(left_range <= left_pred and right_range <= right_pred and not (left_pred & right_range) and not (right_pred & left_range))
            speaker_results.append(speaker_ok)
            wrong_speaker += int(not speaker_ok)
        if gold_chars:
            pred_min = min(pred_chars) if pred_chars else -1; pred_max = max(pred_chars) if pred_chars else -1
            exact_boundary.append(pred_min == min(gold_chars) and pred_max == max(gold_chars))
            predicted_unit_indexes = sorted(int(units[unit_id]["unit_index"]) for values in pred_units_by_segment.values() for unit_id in values if unit_id in units)
            gold_unit_indexes = sorted(int(units[unit_id]["unit_index"]) for unit_id in gold_units)
            tolerance_boundary.append(bool(predicted_unit_indexes and gold_unit_indexes and abs(predicted_unit_indexes[0] - gold_unit_indexes[0]) <= 1 and abs(predicted_unit_indexes[-1] - gold_unit_indexes[-1]) <= 1))
    char_p, char_r, char_f1 = _prf(char_pred, char_gold)
    unit_p, unit_r, unit_f1 = _prf(unit_pred, unit_gold)
    fallback_p, fallback_r, fallback_f1 = _prf(fallback_pred, fallback_gold)
    result = {
        "package_version": GOLDEN_PACKAGE_VERSION,
        "selection_version": LABEL_SELECTION_VERSION,
        "item_count": len(items),
        "character_precision": char_p, "character_recall": char_r, "character_f1": char_f1,
        "unit_overlap_precision": unit_p, "unit_overlap_recall": unit_r, "unit_overlap_f1": unit_f1,
        "exact_boundary_accuracy": round(sum(exact_boundary) / len(exact_boundary), 6) if exact_boundary else None,
        "tolerance_boundary_accuracy": round(sum(tolerance_boundary) / len(tolerance_boundary), 6) if tolerance_boundary else None,
        "wrong_speaker_count": wrong_speaker,
        "speaker_boundary_accuracy": round(sum(speaker_results) / len(speaker_results), 6) if speaker_results else None,
        "fallback_precision": fallback_p, "fallback_recall": fallback_r, "fallback_f1": fallback_f1,
        "meaningful_text_omission_rate": round(omissions / max(1, meaningful), 6),
        "labels_sha256": _sha256(labels_path),
        "predictions_sha256": _sha256(predictions_path),
    }
    if output_path:
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def convert_review_to_golden(*, package_dir: Path, review_path: Path, output_path: Path, reviewer: str, annotation_version: str) -> dict[str, Any]:
    if not reviewer.strip() or not annotation_version.strip():
        raise ValueError("reviewer and annotation_version are required")
    items = _read_jsonl(package_dir / "items.jsonl")
    reviews = _read_jsonl(review_path)
    by_segment = {str(row.get("segment_id")): row for row in reviews if row.get("item_type", "segment") == "segment"}
    allowed = {"correct", "boundary_adjustment", "wrong_speaker", "wrong_content", "should_fallback", "source_missing", "uncertain"}
    labels: list[dict[str, Any]] = []
    for item in items:
        rows = [by_segment.get(segment_id) for segment_id in item["structure_segment_ids"]]
        if any(row is None for row in rows):
            raise ValueError(f"review is missing structure rows for {item['item_id']}")
        verdicts = [str(row.get("verdict") or "").strip() for row in rows if row]
        invalid = [value for value in verdicts if value not in allowed]
        if invalid:
            raise ValueError(f"unfilled or invalid verdict in {item['item_id']}: {invalid}")
        ranges: list[dict[str, Any]] = []
        notes: list[str] = []
        for index, row in enumerate(rows):
            assert row is not None
            start = row.get("corrected_char_start")
            end = row.get("corrected_char_end")
            if start is None or end is None:
                if row["verdict"] == "correct":
                    start, end = row.get("current_char_start"), row.get("current_char_end")
            if start is not None and end is not None and int(end) > int(start):
                owner = str(row.get("transition_owner") or "uncertain")
                if item["category"] == "speaker_switch":
                    if owner == "gap":
                        role = "short_transition_gap"
                        speaker = None
                    elif owner == "left" or (owner == "uncertain" and index == 0):
                        role = "left_speaker_end" if owner == "uncertain" else "short_transition_left"
                        speaker = item["structure_segments"][0]["speaker"]
                    elif owner == "right" or (owner == "uncertain" and index == len(rows) - 1):
                        role = "right_speaker_start" if owner == "uncertain" else "short_transition_right"
                        speaker = item["structure_segments"][-1]["speaker"]
                    else:
                        role = "gap_event"
                        speaker = None
                else:
                    role = "segment_text"
                    speaker = item["structure_segments"][0]["speaker"]
                unit_ids = [unit["unit_id"] for unit in item["target_units"] if int(unit["raw_char_end"]) > int(start) and int(unit["raw_char_start"]) < int(end)]
                ranges.append({"role": role, "char_start": int(start), "char_end": int(end), "speaker": speaker, "unit_ids": unit_ids})
            if str(row.get("reviewer_note") or "").strip():
                notes.append(f"{row['segment_id']}: {row['reviewer_note'].strip()}")
        if "source_missing" in verdicts:
            status = "source_missing"
        elif "uncertain" in verdicts:
            status = "uncertain"
        elif "should_fallback" in verdicts or (any(value in {"wrong_speaker", "wrong_content"} for value in verdicts) and not ranges):
            status = "should_fallback"
        elif ranges:
            status = "correct_alignment"
        else:
            status = "should_fallback"
        labels.append({
            "item_id": item["item_id"],
            "selection_version": LABEL_SELECTION_VERSION,
            "reviewer": reviewer.strip(),
            "annotation_version": annotation_version.strip(),
            "status": status,
            "ranges": ranges,
            "notes": " | ".join(notes),
            "finalized_at": datetime.now(timezone.utc).isoformat(),
        })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(json.dumps(label, ensure_ascii=False) + "\n" for label in labels), encoding="utf-8")
    return {"status": "ok", "label_count": len(labels), "output": str(output_path), "sha256": _sha256(output_path), "selection_version": LABEL_SELECTION_VERSION}

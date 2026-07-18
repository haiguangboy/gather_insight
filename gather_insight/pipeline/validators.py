from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


class ValidationError(ValueError):
    pass


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValidationError(f"{path}:{line_number}: JSONL record must be an object")
        records.append(value)
    return records


def validate_records(records: list[dict[str, Any]], schema_path: Path, label: str = "records") -> None:
    validate_document(records, schema_path, label)


def validate_document(value: Any, schema_path: Path, label: str = "document") -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(value), key=lambda error: list(error.path))
    if errors:
        details = "; ".join(error.message for error in errors[:5])
        raise ValidationError(f"{label} failed schema validation: {details}")


def validate_evidence_orphans(records: list[dict[str, Any]]) -> None:
    ids = [record.get("evidence_id") for record in records]
    if any(not value for value in ids):
        raise ValidationError("evidence_id cannot be empty")
    if len(ids) != len(set(ids)):
        raise ValidationError("duplicate evidence_id")
    for record in records:
        start, end = record.get("start_seconds"), record.get("end_seconds")
        if start is None or end is None or end < start:
            raise ValidationError(f"invalid evidence interval: {record.get('evidence_id')}")
        if not record.get("youtube_url"):
            raise ValidationError(f"missing youtube_url: {record.get('evidence_id')}")


def dump_yaml(path: Path, value: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")

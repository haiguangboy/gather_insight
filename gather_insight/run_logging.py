from __future__ import annotations

import json
import re
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


def _safe_url(value: str) -> str:
    """Remove query secrets while retaining a YouTube video identifier."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<invalid-url>"
    query = parse_qs(parsed.query)
    safe_query = urlencode({"v": query["v"][0]}) if "v" in query else ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, safe_query, ""))


_URL_IN_TEXT = re.compile(r"https?://[^\s\]\[()<>\"']+")
_CREDENTIAL_IN_TEXT = re.compile(r"(?i)\b(token|secret|password|api[_-]?key|authorization)=([^\s&]+)")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+")


def _sanitize_text(value: str) -> str:
    value = _URL_IN_TEXT.sub(lambda match: _safe_url(match.group(0)), value)
    value = _CREDENTIAL_IN_TEXT.sub(lambda match: f"{match.group(1)}=<redacted>", value)
    return _BEARER.sub("Bearer <redacted>", value)


def _sanitize(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if any(token in lowered for token in ("token", "secret", "password", "authorization", "cookie")):
        return "<redacted>"
    if isinstance(value, str):
        return _safe_url(value) if lowered.endswith("url") or value.startswith(("http://", "https://")) else _sanitize_text(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(item_key): _sanitize(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value


class RunLogger:
    """Append-only JSONL logger shared by source resolution and ingest."""

    def __init__(self, command: str, global_log: Path = Path("logs/gather_insight.jsonl"), run_id: str | None = None):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = run_id or f"{stamp}_{uuid.uuid4().hex[:8]}"
        self.command = command
        self.global_log = global_log
        self.media_log: Path | None = None
        self.media_id: str | None = None
        self._history: list[str] = []

    def bind_media(self, media_id: str, media_dir: Path) -> None:
        self.media_id = media_id
        self.media_log = media_dir / "logs" / f"{self.run_id}.jsonl"
        self.media_log.parent.mkdir(parents=True, exist_ok=True)
        if self._history and not self.media_log.exists():
            self.media_log.write_text("".join(self._history), encoding="utf-8")

    @property
    def log_paths(self) -> list[str]:
        paths = [str(self.global_log)]
        if self.media_log:
            paths.append(str(self.media_log))
        return paths

    def event(self, level: str, event: str, message: str = "", **context: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": level.upper(),
            "event": event,
            "message": _sanitize_text(message),
            "run_id": self.run_id,
            "command": self.command,
            "media_id": self.media_id,
            "context": _sanitize(context),
        }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        self._history.append(line)
        for path in (self.global_log, self.media_log):
            if path is None:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)

    def exception(self, event: str, exc: BaseException, **context: Any) -> None:
        self.event(
            "ERROR",
            event,
            str(exc),
            exception_type=type(exc).__name__,
            traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            **context,
        )

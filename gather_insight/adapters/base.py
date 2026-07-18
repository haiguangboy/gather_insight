from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


@dataclass(frozen=True)
class SourceHint:
    provider: str
    file: Path | None = None
    url: str | None = None


@dataclass(frozen=True)
class SourceCheck:
    provider: str
    priority: int
    status: str
    available: bool
    has_local_content: bool
    source_type: str
    transcript_format: str | None = None
    file: Path | None = None
    url: str | None = None
    message: str = ""

    def manifest_value(self) -> dict[str, object]:
        value = asdict(self)
        if value["file"] is not None:
            value["file"] = str(value["file"])
        if value["url"]:
            value["url"] = sanitize_url(str(value["url"]))
        return value


def sanitize_url(value: str) -> str:
    parsed = urlsplit(value)
    query = parse_qs(parsed.query)
    safe_query = urlencode({"v": query["v"][0]}) if "v" in query else ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, safe_query, ""))


def infer_format(path: Path) -> str | None:
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"md", "markdown", "txt"}:
        return "markdown"
    if suffix == "vtt":
        return "vtt"
    if suffix == "srt":
        return "srt"
    return None


def check_hint(*, hint: SourceHint, priority: int, source_type: str, allowed_formats: set[str]) -> SourceCheck:
    if hint.file is not None:
        transcript_format = infer_format(hint.file)
        if not hint.file.exists():
            return SourceCheck(hint.provider, priority, "failed", False, False, source_type, transcript_format, hint.file, hint.url, "file does not exist")
        if not hint.file.is_file():
            return SourceCheck(hint.provider, priority, "failed", False, False, source_type, transcript_format, hint.file, hint.url, "path is not a file")
        if transcript_format not in allowed_formats:
            return SourceCheck(hint.provider, priority, "failed", False, False, source_type, transcript_format, hint.file, hint.url, "unsupported transcript format")
        return SourceCheck(hint.provider, priority, "ready", True, True, source_type, transcript_format, hint.file, hint.url, "local transcript is ready")
    if hint.url:
        return SourceCheck(hint.provider, priority, "url_only", True, False, source_type, None, None, hint.url, "URL is available; manual download/import is required")
    return SourceCheck(hint.provider, priority, "not_configured", False, False, source_type, None, None, None, "no source hint configured")

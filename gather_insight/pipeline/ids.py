from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse


class URLParseError(ValueError):
    pass


def normalize_media_url(url: str) -> str:
    value = url.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise URLParseError("URL must use http or https")
    host = parsed.netloc.lower().split(":", 1)[0]
    if host in {"youtu.be", "www.youtu.be"}:
        video_id = parsed.path.strip("/").split("/", 1)[0]
        if not video_id:
            raise URLParseError("YouTube short URL has no video id")
        return f"https://www.youtube.com/watch?v={video_id}"
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith("/shorts/"):
            video_id = parsed.path.split("/", 2)[2]
        elif parsed.path.startswith("/embed/"):
            video_id = parsed.path.split("/", 2)[2]
        else:
            video_id = None
        if not video_id:
            raise URLParseError("YouTube URL has no video id")
        return f"https://www.youtube.com/watch?v={video_id.split('&', 1)[0]}"
    return value


def extract_video_id(url: str) -> str | None:
    normalized = normalize_media_url(url)
    parsed = urlparse(normalized)
    host = parsed.netloc.lower()
    if host in {"youtu.be", "www.youtu.be"}:
        return parsed.path.strip("/").split("/", 1)[0]
    if "youtube.com" in host:
        return parse_qs(parsed.query).get("v", [None])[0]
    return None


def media_id_for_url(url: str) -> tuple[str, str]:
    normalized = normalize_media_url(url)
    video_id = extract_video_id(normalized)
    if video_id:
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_id):
            raise URLParseError("invalid YouTube video id")
        return f"yt_{video_id}", normalized
    parsed = urlparse(normalized)
    slug = re.sub(r"[^a-z0-9]+", "-", parsed.path.lower()).strip("-") or "page"
    return f"web_{parsed.netloc.lower()}_{slug}", normalized


def evidence_id(media_id: str, number: int) -> str:
    return f"{media_id}.ev_{number:04d}"


def candidate_id(media_id: str, number: int) -> str:
    return f"{media_id}.candidate_{number:03d}"


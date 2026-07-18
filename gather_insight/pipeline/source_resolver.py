from __future__ import annotations

from dataclasses import dataclass

from gather_insight.adapters import manual_markdown, official_transcript, ulisten, usetranscribe, youtube
from gather_insight.adapters.base import SourceCheck, SourceHint
from gather_insight.run_logging import RunLogger


PROVIDER_PRIORITY = ("official_transcript", "ulisten", "usetranscribe", "manual_markdown", "youtube_export")


class SourceResolutionError(RuntimeError):
    def __init__(self, message: str, checks: list[SourceCheck]):
        super().__init__(message)
        self.checks = checks


@dataclass(frozen=True)
class ResolvedSource:
    selected: SourceCheck
    checks: list[SourceCheck]

    @property
    def manifest_checks(self) -> dict[str, dict[str, object]]:
        return {check.provider: check.manifest_value() for check in self.checks}


def resolve_source(hints: dict[str, SourceHint], logger: RunLogger | None = None) -> ResolvedSource:
    adapters = {
        "official_transcript": official_transcript.check,
        "ulisten": ulisten.check,
        "usetranscribe": usetranscribe.check,
        "manual_markdown": manual_markdown.check,
        "youtube_export": youtube.check,
    }
    checks: list[SourceCheck] = []
    for priority, provider in enumerate(PROVIDER_PRIORITY, 1):
        hint = hints.get(provider, SourceHint(provider))
        check = adapters[provider](hint, priority)
        checks.append(check)
        if logger:
            logger.event(
                "INFO" if check.status in {"ready", "url_only", "not_configured"} else "WARNING",
                "source.checked",
                check.message,
                provider=provider,
                priority=priority,
                status=check.status,
                available=check.available,
                has_local_content=check.has_local_content,
                source_url=check.url,
                source_file=check.file,
                transcript_format=check.transcript_format,
            )
    selected = next((check for check in checks if check.status == "ready"), None)
    if selected:
        if logger:
            logger.event("INFO", "source.selected", "selected highest-priority ingestible source", provider=selected.provider, priority=selected.priority, source_file=selected.file, source_url=selected.url)
        return ResolvedSource(selected, checks)
    url_only = next((check for check in checks if check.status == "url_only"), None)
    if url_only:
        message = f"{url_only.provider} is available only as a URL; download/export it and provide a local transcript file"
    else:
        message = "no ingestible transcript source is available"
    if logger:
        logger.event("ERROR", "source.unresolved", message, checks=[check.manifest_value() for check in checks])
    raise SourceResolutionError(message, checks)


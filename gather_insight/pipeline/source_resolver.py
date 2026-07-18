from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

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


@dataclass(frozen=True)
class TranscriptSourceState:
    provider: str
    filename: str
    path: Path
    status: str
    available: bool
    is_fixture: bool = False

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["path"] = str(self.path)
        return value


@dataclass(frozen=True)
class TranscriptCombinationResolution:
    fusion_mode: str
    structure_source: str | None
    text_source: str | None
    sources: dict[str, TranscriptSourceState]
    limitations: list[str]
    unused_sources: list[str]

    def as_dict(self) -> dict[str, object]:
        return {
            "fusion_mode": self.fusion_mode,
            "structure_source": self.structure_source,
            "text_source": self.text_source,
            "sources": {name: state.as_dict() for name, state in self.sources.items()},
            "limitations": self.limitations,
            "unused_sources": self.unused_sources,
        }


def resolve_transcript_combination(*, input_dir: Path, fixture_flags: dict[str, bool] | None = None, logger: RunLogger | None = None) -> TranscriptCombinationResolution:
    fixture_flags = fixture_flags or {}
    filenames = {
        "ulisten": "source_ulisten_raw.md",
        "usetranscribe": "source_usetranscribe_raw.md",
        "official_transcript": "source_official_transcript_raw.md",
    }
    sources: dict[str, TranscriptSourceState] = {}
    for provider, filename in filenames.items():
        path = input_dir / filename
        available = path.is_file()
        is_fixture = bool(fixture_flags.get(provider, False)) and available
        state = TranscriptSourceState(
            provider=provider,
            filename=filename,
            path=path,
            status="fixture" if is_fixture else "present" if available else "missing",
            available=available,
            is_fixture=is_fixture,
        )
        sources[provider] = state
        if logger:
            logger.event("INFO" if available else "WARNING", "transcript_source.checked", "transcript source checked", **state.as_dict())

    has_ulisten = sources["ulisten"].available
    has_use = sources["usetranscribe"].available
    has_official = sources["official_transcript"].available
    limitations: list[str] = []
    unused: list[str] = []
    if has_ulisten and has_official:
        mode, structure, text = "official_dual", "ulisten", "official_transcript"
        if has_use:
            unused.append("usetranscribe")
            limitations.append("Official transcript was preferred over UseTranscribe because it is the higher-authority text source.")
    elif has_ulisten and has_use:
        mode, structure, text = "dual_source", "ulisten", "usetranscribe"
    elif has_official:
        mode, structure, text = "official_single", "official_transcript", "official_transcript"
        if has_use:
            unused.append("usetranscribe")
            limitations.append("UseTranscribe was available but the official transcript was selected as the canonical single source.")
    elif has_use:
        mode, structure, text = "text_single", "text_timeline", "usetranscribe"
        limitations.append("Speaker attribution is unavailable and must remain null or unknown until reviewed.")
    elif has_ulisten:
        mode, structure, text = "structure_degraded", "ulisten", "ulisten"
        limitations.append("Readable secondary text is unavailable; uListen raw text is preserved without alignment confidence.")
    else:
        mode, structure, text = "failed", None, None
        limitations.append("All supported transcript sources are missing.")
    resolution = TranscriptCombinationResolution(mode, structure, text, sources, limitations, unused)
    if logger:
        logger.event("ERROR" if mode == "failed" else "INFO", "transcript_source.resolved", "transcript source combination resolved", **resolution.as_dict())
    return resolution

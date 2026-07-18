from .base import SourceCheck, SourceHint, check_hint


def check(hint: SourceHint, priority: int = 3) -> SourceCheck:
    return check_hint(hint=hint, priority=priority, source_type="third_party_transcript", allowed_formats={"markdown", "vtt", "srt"})


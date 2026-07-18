from .base import SourceCheck, SourceHint, check_hint


def check(hint: SourceHint, priority: int = 1) -> SourceCheck:
    return check_hint(hint=hint, priority=priority, source_type="official_transcript", allowed_formats={"markdown"})


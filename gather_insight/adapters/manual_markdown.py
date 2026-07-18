from .base import SourceCheck, SourceHint, check_hint


def check(hint: SourceHint, priority: int = 4) -> SourceCheck:
    return check_hint(hint=hint, priority=priority, source_type="manual_transcript", allowed_formats={"markdown"})


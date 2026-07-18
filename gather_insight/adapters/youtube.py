from .base import SourceCheck, SourceHint, check_hint


def check(hint: SourceHint, priority: int = 5) -> SourceCheck:
    return check_hint(hint=hint, priority=priority, source_type="youtube_caption", allowed_formats={"markdown", "vtt", "srt"})


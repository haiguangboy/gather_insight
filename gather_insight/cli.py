from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline.ingest import IngestError, ingest_media


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gather-insight")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="Build a media evidence package from Markdown")
    ingest.add_argument("--url", required=True, help="YouTube or supported media URL")
    ingest.add_argument("--transcript-file", required=True, type=Path)
    ingest.add_argument("--provider", default="manual_markdown")
    ingest.add_argument("--output-root", type=Path, default=Path("data/media"))
    ingest.add_argument("--title")
    ingest.add_argument("--channel")
    ingest.add_argument("--language", default="en")
    ingest.add_argument("--speaker-mode", default="unknown")
    ingest.add_argument("--participant", action="append", default=[])
    ingest.add_argument("--topic", action="append", default=[])
    ingest.add_argument("--force-source", action="store_true", help="Replace an existing source.md")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "ingest":
        try:
            result = ingest_media(
                url=args.url,
                transcript_file=args.transcript_file,
                provider=args.provider,
                output_root=args.output_root,
                title=args.title,
                channel=args.channel,
                language=args.language,
                speaker_mode=args.speaker_mode,
                participants=args.participant,
                topics=args.topic,
                force_source=args.force_source,
            )
        except IngestError as exc:
            print(f"ingest failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    return 2


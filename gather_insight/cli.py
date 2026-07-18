from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters.base import SourceHint
from .pipeline.ids import media_id_for_url
from .pipeline.ingest import IngestError, ingest_media
from .pipeline.source_resolver import SourceResolutionError, resolve_source
from .pipeline.fusion_workflow import FusionWorkflowError, run_fusion_workflow
from .pipeline.general_transcript_workflow import GeneralTranscriptWorkflowError, run_general_transcript_workflow
from .run_logging import RunLogger


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--transcript-file", type=Path, help="Local Markdown, VTT, or SRT transcript")
    parser.add_argument("--official-file", type=Path)
    parser.add_argument("--official-url")
    parser.add_argument("--ulisten-file", type=Path)
    parser.add_argument("--ulisten-url")
    parser.add_argument("--usetranscribe-file", type=Path)
    parser.add_argument("--usetranscribe-url")
    parser.add_argument("--youtube-export-file", type=Path)


def _source_hints(args: argparse.Namespace) -> dict[str, SourceHint]:
    hints = {
        "official_transcript": SourceHint("official_transcript", args.official_file, args.official_url),
        "ulisten": SourceHint("ulisten", args.ulisten_file, args.ulisten_url),
        "usetranscribe": SourceHint("usetranscribe", args.usetranscribe_file, args.usetranscribe_url),
        "youtube_export": SourceHint("youtube_export", args.youtube_export_file, None),
    }
    if args.transcript_file:
        provider = args.provider if args.provider not in {None, "auto"} else "manual_markdown"
        hints[provider] = SourceHint(provider, args.transcript_file, hints.get(provider, SourceHint(provider)).url)
    return hints


def _check_specific_source(args: argparse.Namespace, logger: RunLogger):
    hints = _source_hints(args)
    if args.provider != "auto":
        selected_hint = hints.get(args.provider, SourceHint(args.provider))
        hints = {args.provider: selected_hint}
    return resolve_source(hints, logger)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gather-insight")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="Build a media evidence package from a selected transcript source")
    ingest.add_argument("--url", required=True, help="YouTube or supported media URL")
    _add_source_arguments(ingest)
    ingest.add_argument("--provider", default="auto", choices=["auto", "official_transcript", "ulisten", "usetranscribe", "manual_markdown", "youtube_export"])
    ingest.add_argument("--output-root", type=Path, default=Path("data/media"))
    ingest.add_argument("--log-file", type=Path, default=Path("logs/gather_insight.jsonl"))
    ingest.add_argument("--title")
    ingest.add_argument("--channel")
    ingest.add_argument("--language", default="en")
    ingest.add_argument("--speaker-mode", default="unknown")
    ingest.add_argument("--participant", action="append", default=[])
    ingest.add_argument("--topic", action="append", default=[])
    ingest.add_argument("--force-source", action="store_true", help="Replace an existing source.md")
    resolve = sub.add_parser("resolve-sources", help="Check source hints and show the selected source without ingesting")
    resolve.add_argument("--url", required=True, help="YouTube or supported media URL")
    _add_source_arguments(resolve)
    resolve.add_argument("--provider", default="auto", choices=["auto", "official_transcript", "ulisten", "usetranscribe", "manual_markdown", "youtube_export"])
    resolve.add_argument("--log-file", type=Path, default=Path("logs/gather_insight.jsonl"))
    fuse = sub.add_parser("fuse-transcript", help="Fuse uListen structure with UseTranscribe text or explicit fixture/degraded mode")
    fuse.add_argument("--input-dir", required=True, type=Path)
    fuse.add_argument("--output-root", type=Path, default=Path("data/media"))
    fuse.add_argument("--use-fixture", action="store_true", help="Use the declared readable fixture; confidence remains null")
    fuse.add_argument("--log-file", type=Path, default=Path("logs/gather_insight.jsonl"))
    general = sub.add_parser("fuse-general", help="Resolve official/uListen/UseTranscribe combinations with single-source fallback")
    general.add_argument("--input-dir", required=True, type=Path)
    general.add_argument("--output-root", type=Path, default=Path("data/media"))
    general.add_argument("--log-file", type=Path, default=Path("logs/gather_insight.jsonl"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "ingest":
        logger = RunLogger("ingest", global_log=args.log_file)
        try:
            media_id, normalized_url = media_id_for_url(args.url)
            media_dir = args.output_root / media_id
            media_dir.mkdir(parents=True, exist_ok=True)
            logger.bind_media(media_id, media_dir)
            logger.event("INFO", "ingest.requested", "ingest request accepted", source_url=normalized_url)
            resolved = _check_specific_source(args, logger)
            selected = resolved.selected
            result = ingest_media(
                url=args.url,
                transcript_file=selected.file,
                provider=selected.provider,
                output_root=args.output_root,
                title=args.title,
                channel=args.channel,
                language=args.language,
                speaker_mode=args.speaker_mode,
                participants=args.participant,
                topics=args.topic,
                force_source=args.force_source,
                transcript_format=selected.transcript_format or "markdown",
                source_checks=resolved.manifest_checks,
                primary_source_url=selected.url,
                logger=logger,
            )
            result["source_resolution"] = {"selected": selected.manifest_value(), "checks": resolved.manifest_checks}
        except SourceResolutionError as exc:
            failure = {
                "status": "failed",
                "stage": "source_resolution",
                "run_id": logger.run_id,
                "media_id": logger.media_id,
                "error": str(exc),
                "checks": [check.manifest_value() for check in exc.checks],
                "logs": logger.log_paths,
            }
            if logger.media_id:
                (args.output_root / logger.media_id / "processing_report.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"ingest failed: {exc}", file=sys.stderr)
            return 2
        except IngestError as exc:
            print(f"ingest failed: {exc}", file=sys.stderr)
            return 2
        except ValueError as exc:
            logger.exception("ingest.request_failed", exc, source_url=args.url)
            print(f"ingest failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "resolve-sources":
        logger = RunLogger("resolve-sources", global_log=args.log_file)
        try:
            resolved = _check_specific_source(args, logger)
        except SourceResolutionError as exc:
            print(json.dumps({"status": "unresolved", "error": str(exc), "checks": [check.manifest_value() for check in exc.checks], "logs": logger.log_paths}, ensure_ascii=False, indent=2))
            return 2
        print(json.dumps({"status": "ok", "selected": resolved.selected.manifest_value(), "checks": resolved.manifest_checks, "logs": logger.log_paths}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "fuse-transcript":
        logger = RunLogger("fuse-transcript", global_log=args.log_file)
        try:
            result = run_fusion_workflow(input_dir=args.input_dir, output_root=args.output_root, use_fixture=args.use_fixture, logger=logger)
        except FusionWorkflowError as exc:
            print(f"fusion failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "fuse-general":
        logger = RunLogger("fuse-general", global_log=args.log_file)
        try:
            result = run_general_transcript_workflow(input_dir=args.input_dir, output_root=args.output_root, logger=logger)
        except GeneralTranscriptWorkflowError as exc:
            print(f"general fusion failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    return 2

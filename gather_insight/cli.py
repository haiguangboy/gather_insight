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
from .pipeline.golden_annotation import build_yc_golden_package, convert_review_to_golden, evaluate_yc_golden
from .pipeline.no_ulisten_trend_workflow import compare_phase7_trend, run_no_ulisten_trend
from .pipeline.naval_recent_six import run_naval_recent_six
from .pipeline.phase71_evaluator import evaluate_phase71
from .pipeline.phase711_human_gate import adapt_phase711_golden_review, finalize_phase711_review, freeze_phase711_golden, generate_phase711_golden_review, generate_phase711_review
from .pipeline.phase71_workflow import prepare_phase71_canonical, run_phase71_extraction
from .pipeline.phase72b_workflow import run_phase72b_theme
from .pipeline.review_views import generate_yc_review_views
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
    general.add_argument("--semantic-mode", choices=["lexical_only", "local_semantic", "hybrid_semantic", "mock_semantic"])
    general.add_argument("--alignment-algorithm", choices=["phase_6_8_beam", "vecalign", "sentalign"])
    general.add_argument("--alignment-score-mode", choices=["raw_cosine", "margin"])
    general.add_argument("--semantic-config", type=Path, help="YAML semantic_alignment configuration")
    general.add_argument("--semantic-cache-root", type=Path, default=Path("."))
    golden_build = sub.add_parser("build-yc-golden", help="Build an algorithm-blind private YC golden annotation package")
    golden_build.add_argument("--input-dir", required=True, type=Path)
    golden_build.add_argument("--package-dir", required=True, type=Path)
    golden_build.add_argument("--selection", type=Path, default=Path("config/yc_golden_selection_v1.json"))
    golden_evaluate = sub.add_parser("evaluate-yc-golden", help="Evaluate fused predictions against completed private YC golden labels")
    golden_evaluate.add_argument("--package-dir", required=True, type=Path)
    golden_evaluate.add_argument("--labels", required=True, type=Path)
    golden_evaluate.add_argument("--predictions", required=True, type=Path)
    golden_evaluate.add_argument("--output", type=Path)
    golden_convert = sub.add_parser("convert-yc-review", help="Convert completed YC review JSONL into formal private golden labels")
    golden_convert.add_argument("--package-dir", required=True, type=Path)
    golden_convert.add_argument("--review", required=True, type=Path)
    golden_convert.add_argument("--output", required=True, type=Path)
    golden_convert.add_argument("--reviewer", required=True)
    golden_convert.add_argument("--annotation-version", required=True)
    review_views = sub.add_parser("generate-yc-review-views", help="Generate private YC fused reading and blind alignment review pages")
    review_views.add_argument("--input-dir", required=True, type=Path)
    review_views.add_argument("--output-dir", required=True, type=Path)
    review_views.add_argument("--phase6-8-dir", required=True, type=Path)
    review_views.add_argument("--vecalign-raw-dir", required=True, type=Path)
    review_views.add_argument("--vecalign-margin-dir", required=True, type=Path)
    review_views.add_argument("--sentalign-margin-dir", required=True, type=Path)
    no_ulisten = sub.add_parser("fuse-no-ulisten-trend", help="Run the Phase 7.0 blind dual-text trend-mode fusion")
    no_ulisten.add_argument("--input-dir", required=True, type=Path)
    no_ulisten.add_argument("--output-dir", required=True, type=Path)
    no_ulisten.add_argument("--semantic-mode", choices=["local_semantic", "mock_semantic"], default="local_semantic")
    no_ulisten.add_argument("--semantic-config", type=Path)
    no_ulisten.add_argument("--semantic-cache-root", type=Path, default=Path("."))
    phase7_compare = sub.add_parser("compare-phase7-trend", help="Compare frozen no-uListen candidates with Result B after blind generation")
    phase7_compare.add_argument("--blind-output-dir", required=True, type=Path)
    phase7_compare.add_argument("--ulisten-result-dir", required=True, type=Path)
    phase7_compare.add_argument("--output-dir", required=True, type=Path)
    canonical = sub.add_parser("prepare-phase71-canonical", help="Build versioned Phase 7.1 canonical JSONL from a frozen transcript output")
    canonical.add_argument("--input-dir", required=True, type=Path)
    canonical.add_argument("--manifest", required=True, type=Path)
    canonical.add_argument("--media-root", required=True, type=Path)
    canonical.add_argument("--mode", required=True, choices=["high_quality_structure_mode", "dual_text_trend_mode"])
    canonical.add_argument("--source-input-dir", type=Path)
    extraction = sub.add_parser("extract-phase71", help="Extract evidence-bound claims and intelligence artifacts")
    extraction.add_argument("--media-root", required=True, type=Path)
    extraction.add_argument("--judge-backend", choices=["rules", "mock", "deepseek"], default="rules")
    extraction.add_argument("--judge-config", type=Path)
    extraction.add_argument("--judge-cache-root", type=Path, default=Path("."))
    extraction.add_argument("--judge-max-claims", type=int, default=32)
    phase71_eval = sub.add_parser("evaluate-phase71", help="Evaluate Phase 7.1 claims against a private golden set")
    phase71_eval.add_argument("--golden", required=True, type=Path)
    phase71_eval.add_argument("--claims", required=True, type=Path)
    phase71_eval.add_argument("--evidence", required=True, type=Path)
    phase71_eval.add_argument("--output", required=True, type=Path)
    gate_review = sub.add_parser("generate-phase711-review", help="Generate the Phase 7.1.1 blind trend-candidate human gate")
    gate_review.add_argument("--media-root", required=True, type=Path)
    gate_review.add_argument("--output-dir", type=Path)
    gate_finalize = sub.add_parser("finalize-phase711-review", help="Materialize accepted/rejected claims from human Phase 7.1.1 decisions")
    gate_finalize.add_argument("--media-root", required=True, type=Path)
    gate_finalize.add_argument("--decisions", required=True, type=Path)
    gate_finalize.add_argument("--output-dir", type=Path)
    golden_review = sub.add_parser("generate-phase711-golden-review", help="Generate a blind private golden review and extension package")
    golden_review.add_argument("--draft", required=True, type=Path)
    golden_review.add_argument("--output-dir", required=True, type=Path)
    golden_review.add_argument("--reviewed", type=Path, help="Existing completed JSONL to restore without overwriting human state")
    golden_freeze = sub.add_parser("freeze-phase711-golden", help="Validate and freeze a completed private Phase 7.1.1 golden")
    golden_freeze.add_argument("--reviewed", required=True, type=Path)
    golden_freeze.add_argument("--output", required=True, type=Path)
    golden_freeze.add_argument("--reviewer", required=True)
    golden_freeze.add_argument("--golden-version", required=True)
    golden_adapt = sub.add_parser("adapt-phase711-golden-review", help="Adapt the confirmed legacy golden export to the split 7.1.1a/7.1.1b format")
    golden_adapt.add_argument("--input", required=True, type=Path)
    golden_adapt.add_argument("--output", required=True, type=Path)
    golden_adapt.add_argument("--reviewer", required=True)
    naval = sub.add_parser("ingest-naval-recent-six", help="Cache and analyze the fixed Phase 7.2A Naval official corpus")
    naval.add_argument("--output-dir", type=Path, default=Path("input/corpora/naval_recent_six"))
    naval.add_argument("--offline", action="store_true", help="Require all six official HTML pages to be cached")
    theme72b = sub.add_parser("build-phase72b-theme", help="Consolidate the frozen Naval recent-six corpus into the Phase 7.2B theme package")
    theme72b.add_argument("--corpus-dir", type=Path, default=Path("input/corpora/naval_recent_six"))
    theme72b.add_argument("--output-dir", type=Path, default=Path("knowledge/themes/ai_execution_commoditization_judgment_scarcity"))
    theme72b.add_argument("--semantic-mode", choices=["local_semantic", "mock_semantic"], default="local_semantic")
    theme72b.add_argument("--judge-backend", choices=["deepseek", "mock", "rules"], default="deepseek")
    theme72b.add_argument("--config", type=Path)
    theme72b.add_argument("--cache-root", type=Path, default=Path("."))
    return parser


def _semantic_config(args: argparse.Namespace) -> dict[str, object]:
    value: dict[str, object] = {}
    if args.semantic_config:
        try:
            import yaml
            loaded = yaml.safe_load(args.semantic_config.read_text(encoding="utf-8")) or {}
            value = dict(loaded.get("semantic_alignment", loaded))
        except (OSError, ValueError, TypeError) as exc:
            raise GeneralTranscriptWorkflowError(f"cannot load semantic config: {exc}") from exc
    if args.semantic_mode:
        value["mode"] = args.semantic_mode
    else:
        value.setdefault("mode", "lexical_only")
    if args.alignment_algorithm:
        value["alignment_algorithm"] = args.alignment_algorithm
    if args.alignment_score_mode:
        value["score_mode"] = args.alignment_score_mode
    return value


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
            result = run_general_transcript_workflow(input_dir=args.input_dir, output_root=args.output_root, semantic_config=_semantic_config(args), semantic_cache_root=args.semantic_cache_root, logger=logger)
        except GeneralTranscriptWorkflowError as exc:
            print(f"general fusion failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "build-yc-golden":
        try:
            result = build_yc_golden_package(input_dir=args.input_dir, package_dir=args.package_dir, selection_path=args.selection)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"golden package build failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "evaluate-yc-golden":
        try:
            result = evaluate_yc_golden(package_dir=args.package_dir, labels_path=args.labels, predictions_path=args.predictions, output_path=args.output)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"golden evaluation failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "convert-yc-review":
        try:
            result = convert_review_to_golden(
                package_dir=args.package_dir,
                review_path=args.review,
                output_path=args.output,
                reviewer=args.reviewer,
                annotation_version=args.annotation_version,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"review conversion failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "generate-yc-review-views":
        try:
            result = generate_yc_review_views(
                input_dir=args.input_dir,
                output_dir=args.output_dir,
                phase_6_8_dir=args.phase6_8_dir,
                vecalign_raw_dir=args.vecalign_raw_dir,
                vecalign_margin_dir=args.vecalign_margin_dir,
                sentalign_margin_dir=args.sentalign_margin_dir,
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"review view generation failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "fuse-no-ulisten-trend":
        try:
            config: dict[str, object] = {"mode": args.semantic_mode}
            if args.semantic_config:
                import yaml
                loaded = yaml.safe_load(args.semantic_config.read_text(encoding="utf-8")) or {}
                config.update(dict(loaded.get("semantic_alignment", loaded)))
                config["mode"] = args.semantic_mode
            result = run_no_ulisten_trend(input_dir=args.input_dir, output_dir=args.output_dir, semantic_config=config, cache_root=args.semantic_cache_root)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"no-uListen trend fusion failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "compare-phase7-trend":
        try:
            result = compare_phase7_trend(blind_output_dir=args.blind_output_dir, ulisten_result_dir=args.ulisten_result_dir, output_dir=args.output_dir)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"Phase 7.0 trend comparison failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "prepare-phase71-canonical":
        try:
            result = prepare_phase71_canonical(input_dir=args.input_dir, manifest_path=args.manifest, media_root=args.media_root, mode=args.mode, source_input_dir=args.source_input_dir)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"Phase 7.1 canonical preparation failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "extract-phase71":
        try:
            config: dict[str, object] = {}
            if args.judge_config:
                import yaml
                loaded = yaml.safe_load(args.judge_config.read_text(encoding="utf-8")) or {}
                config = dict(loaded.get("phase_7_1", loaded))
            result = run_phase71_extraction(media_root=args.media_root, judge_backend=args.judge_backend, judge_config=config, cache_root=args.judge_cache_root, judge_max_claims=args.judge_max_claims)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"Phase 7.1 extraction failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "evaluate-phase71":
        try:
            result = evaluate_phase71(golden_path=args.golden, claims_path=args.claims, evidence_path=args.evidence, output_path=args.output)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"Phase 7.1 evaluation failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "generate-phase711-review":
        try:
            result = generate_phase711_review(media_root=args.media_root, output_dir=args.output_dir)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"Phase 7.1.1 review generation failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "finalize-phase711-review":
        try:
            result = finalize_phase711_review(media_root=args.media_root, decisions_path=args.decisions, output_dir=args.output_dir)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"Phase 7.1.1 review finalization failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "generate-phase711-golden-review":
        try:
            result = generate_phase711_golden_review(draft_path=args.draft, output_dir=args.output_dir, reviewed_path=args.reviewed)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"Phase 7.1.1 golden review generation failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "freeze-phase711-golden":
        try:
            result = freeze_phase711_golden(reviewed_path=args.reviewed, output_path=args.output, reviewer=args.reviewer, golden_version=args.golden_version)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"Phase 7.1.1 golden freeze failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "adapt-phase711-golden-review":
        try:
            result = adapt_phase711_golden_review(input_path=args.input, output_path=args.output, reviewer=args.reviewer)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"Phase 7.1.1 golden adaptation failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "ingest-naval-recent-six":
        try:
            result = run_naval_recent_six(output_dir=args.output_dir, offline=args.offline)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"Naval recent-six ingestion failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "build-phase72b-theme":
        try:
            config: dict[str, object] = {}
            if args.config:
                import yaml
                loaded = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
                config = dict(loaded.get("phase_7_2b", loaded))
            result = run_phase72b_theme(corpus_dir=args.corpus_dir, output_dir=args.output_dir, semantic_mode=args.semantic_mode, judge_backend=args.judge_backend, config=config, cache_root=args.cache_root)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"Phase 7.2B theme consolidation failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    return 2

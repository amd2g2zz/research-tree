"""CLI adapter for the intent-constrained research domain."""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

from research_domain import ACTIVE, SCHEMA, TERMINAL, ResearchState, safe_snapshot_id
from research_repository import pages_dir, saved_page_path, workspace
from research_service import ResearchService


for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, io.UnsupportedOperation):
        pass


def _read_json(value: str, expected: type):
    if value.startswith("@"):
        input_path = (workspace() / value[1:]).resolve()
        try:
            input_path.relative_to(workspace().resolve())
        except ValueError as exc:
            raise ValueError("JSON input file must be inside the research workspace") from exc
        if not input_path.is_file():
            raise FileNotFoundError(f"JSON input file not found: {input_path}")
        value = input_path.read_text(encoding="utf-8")
    parsed = json.loads(value)
    if not isinstance(parsed, expected):
        raise ValueError(f"expected JSON {expected.__name__}")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine", description="intent-constrained recursive research DAG")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create a versioned research intent")
    init.add_argument("--intent", required=True); init.add_argument("--clauses"); init.add_argument("--materials"); init.add_argument("--reference-time")
    analyze_intent = sub.add_parser("analyze-intent", help="record the pre-research requirements and deliverable contract"); analyze_intent.add_argument("--contract", required=True)
    answer_intent = sub.add_parser("answer-intent", help="record user answers, then return to intent analysis"); answer_intent.add_argument("--answers", required=True)
    register_material = sub.add_parser("register-material", help="register or replace a user file while intent requirements are still being clarified"); register_material.add_argument("--material", required=True); register_material.add_argument("--replace", action="store_true")
    bootstrap = sub.add_parser("bootstrap", help="add initial research frames"); bootstrap.add_argument("--frames", required=True)
    formulate = sub.add_parser("formulate", help="record a constraint-aware query plan"); formulate.add_argument("--frame", required=True); formulate.add_argument("--plan", required=True)
    aggregate = sub.add_parser("aggregate-sources", help="record hash-bound topic clustering and source-quality scoring from the saved collection"); aggregate.add_argument("--frame", required=True); aggregate.add_argument("--clusters", required=True); aggregate.add_argument("--source-manifest-sha256", required=True)
    evidence = sub.add_parser("evidence", help="record a reviewer selection from the current saved source manifest"); evidence.add_argument("--frame", required=True); evidence.add_argument("--evidence", required=True); evidence.add_argument("--reviewer-role")
    enrich_time = sub.add_parser("enrich-evidence-publication-time", help="attach a saved-page-witnessed publication date to evidence missing normalized metadata"); enrich_time.add_argument("--evidence", required=True); enrich_time.add_argument("--published-at", required=True); enrich_time.add_argument("--locator", required=True); enrich_time.add_argument("--rationale", required=True)
    extract = sub.add_parser("extract", help="record cited cognitions, information gaps, and source coverage"); extract.add_argument("--frame", required=True); extract.add_argument("--cognitions", required=True); extract.add_argument("--gaps", required=True); extract.add_argument("--coverage")
    synthesize = sub.add_parser("synthesize-decision", help="record the decision assessment after research frames are terminal"); synthesize.add_argument("--synthesis", required=True)
    expand = sub.add_parser("expand", help="expand an information gap into a child frame"); expand.add_argument("--gap", required=True); expand.add_argument("--frame", required=True)
    descend = sub.add_parser("descend", help="select one frontier gap and call one recursive child"); descend.add_argument("--frame", required=True); descend.add_argument("--gap", required=True); descend.add_argument("--child", required=True); descend.add_argument("--rationale", required=True)
    return_child = sub.add_parser("return-child", help="reduce a terminal recursive child into its parent"); return_child.add_argument("--frame", required=True); return_child.add_argument("--child", required=True); return_child.add_argument("--rationale", required=True)
    finish = sub.add_parser("finish", help="return a bounded result for a frame"); finish.add_argument("--frame", required=True); finish.add_argument("--state", required=True, choices=sorted(TERMINAL)); finish.add_argument("--summary", required=True); finish.add_argument("--confidence", type=float, default=0.0)
    reopen = sub.add_parser("reopen", help="reopen a terminal frame after new evidence"); reopen.add_argument("--frame", required=True); reopen.add_argument("--reason", required=True)
    clarify = sub.add_parser("clarify", help="record a user resolution for an intent clause"); clarify.add_argument("--clause", required=True); clarify.add_argument("--status", required=True); clarify.add_argument("--interpretation", default="")
    for name, help_text in [("next", "show the next required action"), ("status", "show research state"), ("time-audit", "validate temporal evidence"), ("freeze", "freeze a completed snapshot"), ("export", "export state")]:
        command = sub.add_parser(name, help=help_text)
        if name == "freeze": command.add_argument("--snapshot")
        if name == "export": command.add_argument("--format", choices=["json", "md"], default="json")
    args = parser.parse_args(argv)
    service = ResearchService()
    match args.command:
        case "init": result = service.initialize(args.intent, _read_json(args.clauses, list) if args.clauses else [], args.reference_time, _read_json(args.materials, list) if args.materials else [])
        case "analyze-intent": result = service.analyze_intent(_read_json(args.contract, dict))
        case "answer-intent": result = service.answer_intent_questions(_read_json(args.answers, dict))
        case "register-material": result = service.register_material(_read_json(args.material, dict), args.replace)
        case "bootstrap": result = service.bootstrap(_read_json(args.frames, list))
        case "formulate": result = service.formulate(args.frame, _read_json(args.plan, list))
        case "aggregate-sources": result = service.aggregate_sources(args.frame, _read_json(args.clusters, list), args.source_manifest_sha256)
        case "evidence": result = service.add_evidence(args.frame, _read_json(args.evidence, list), args.reviewer_role)
        case "enrich-evidence-publication-time": result = service.enrich_evidence_publication_time(args.evidence, args.published_at, args.locator, args.rationale)
        case "extract": result = service.extract(args.frame, _read_json(args.cognitions, list), _read_json(args.gaps, list), _read_json(args.coverage, list) if args.coverage else None)
        case "synthesize-decision": result = service.synthesize_decision(_read_json(args.synthesis, dict))
        case "expand": result = service.expand(args.gap, _read_json(args.frame, dict))
        case "descend": result = service.descend(args.frame, args.gap, _read_json(args.child, dict), args.rationale)
        case "return-child": result = service.return_child(args.frame, args.child, args.rationale)
        case "finish": result = service.finish(args.frame, args.state, args.summary, args.confidence)
        case "reopen": result = service.reopen(args.frame, args.reason)
        case "clarify": result = service.clarify(args.clause, args.status, args.interpretation)
        case "next": result = service.next()
        case "status": result = service.status()
        case "time-audit": result = service.time_audit()
        case "freeze": result = service.freeze(args.snapshot)
        case "export": result = service.export(args.format)
        case _: raise AssertionError(f"unhandled command: {args.command}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

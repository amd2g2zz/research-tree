"""Turn live recursive-research state into role-scoped worker batches."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import deque
from pathlib import Path

import anysearch_client
import providers
from research_domain import ACTIVE, ResearchState
from research_repository import atomic_write_json, atomic_write_text, saved_page_path, workspace
from research_service import ResearchService
from search_executor import run_plan
import source_acquirer


DISCOVERY_SCHEMA = 2
SOURCE_MANIFEST_SCHEMA = 2
MAX_SOURCE_CAPTURE_LIMIT = 64
MAX_NATIVE_METADATA_CANDIDATES = 8
MAX_NATIVE_METADATA_CHARS = 4_000
MIN_NATIVE_METADATA_CHARS = 240
MIN_NATIVE_METADATA_WORDS = 32
REVIEW_ROLES = ("source_triager", "source_adversary")


class ResearchOrchestrator:
    """Coordinator planning only; workers never mutate state directly."""

    def __init__(self, service: ResearchService | None = None):
        self.service = service or ResearchService()

    def plan(self, snapshot: str | None = None, question: str | None = None) -> dict:
        if question and not snapshot:
            raise ValueError("Q&A planning requires a frozen snapshot")
        if snapshot:
            return self._plan_qa(snapshot, question) if question else self._plan_frozen(snapshot)
        state = self.service.read_state()
        provider_plan = providers.eligible()
        intent_contract = state.intent_contract()
        if intent_contract["status"] == "pending":
            return {
                "schema": 2, "intent": state.current_intent()["raw"],
                "tasks": [self._intent_analysis_task(state, intent_contract)], "coordinator_tasks": [],
                "provider_policy": provider_plan["policy"], "max_parallel": 1,
            }
        if intent_contract["status"] == "needs_clarification":
            return {
                "schema": 2, "intent": state.current_intent()["raw"], "tasks": [],
                "coordinator_tasks": [self._intent_clarification_task(intent_contract)],
                "provider_policy": provider_plan["policy"], "max_parallel": 1,
            }
        tasks = []
        for frame in sorted(state.data["frames"].values(), key=lambda item: (-item["priority"], item["created_at"])):
            blocked = state.blocked_clauses_for(frame)
            if blocked and frame["state"] in ACTIVE:
                tasks.append(self._clarification_task(frame, blocked))
            elif frame["state"] == "open":
                tasks.append(self._formulation_task(state, frame))
            elif frame["state"] == "acquiring":
                # Network discovery and source materialisation are coordinator
                # work. Never start a worker until both durable archives exist.
                pending_collection = self._collection_pending(frame)
                if pending_collection:
                    tasks.append(pending_collection)
            elif frame["state"] == "aggregating":
                tasks.append(self._aggregation_task(frame))
            elif frame["state"] == "reviewing":
                review = frame.get("review", {})
                expected = set(review.get("expected_roles", []))
                completed = set(review.get("completed_roles", []))
                if "source_triager" in expected and "source_triager" not in completed:
                    tasks.append(self._triage_task(frame))
                if "source_adversary" in expected and "source_adversary" not in completed:
                    tasks.append(self._adversary_task(frame))
            elif frame["state"] == "extracting":
                tasks.append(self._extract_task(state, frame))
            elif frame["state"] == "expanded":
                frontier = state.frontier(frame["id"])
                decision = state.frontier_decision(frame["id"], frontier)
                tasks.append(self._selector_task(frame, frontier, decision)
                             if decision["recommendation"] != "return"
                             else self._return_task(frame, decision))
            elif frame["state"] == "waiting_child":
                child_id = frame.get("descent", {}).get("active_child_id")
                child = state.data["frames"].get(child_id)
                if child and child["state"] not in ACTIVE:
                    tasks.append(self._reducer_task(frame, child))
        if not tasks and not any(item["state"] in ACTIVE for item in state.data["frames"].values()):
            synthesis = state.decision_synthesis_audit()
            if synthesis["required"] and not synthesis["ok"]:
                tasks.append(self._decision_synthesis_task(state))
            else:
                tasks.append({"task_id": "publisher:freeze", "role": "publisher", "kind": "freeze",
                              "instruction": "Verify the temporal, source-coverage, decision-synthesis, and publication audits, then submit one freeze command.",
                              "allowed_operation": "freeze"})
        coordinator_tasks = [item for item in tasks if item.get("role") == "coordinator"]
        worker_tasks = [item for item in tasks if item.get("role") != "coordinator"]
        return {"schema": 2, "intent": state.current_intent()["raw"], "tasks": worker_tasks,
                "coordinator_tasks": coordinator_tasks,
                "provider_policy": provider_plan["policy"], "max_parallel": provider_plan["max_parallel"]}

    def discover(self, refresh: bool = False) -> dict:
        """Run every eligible engine, archive its raw response, then materialise leads.

        This is the only live-network stage. A worker is not planned until each
        enabled provider has a terminal record, every raw search response is
        archived, and the bounded source capture manifest is complete.
        """
        state = self.service.read_state()
        if state.intent_contract()["status"] != "ready":
            return {"schema": 1, "results": [], "max_parallel": 0,
                    "skipped": "intent_contract_not_ready"}
        provider_plan = providers.eligible()
        results = []
        acquiring_frames = [
            frame for frame in sorted(state.data["frames"].values(), key=lambda item: item["id"])
            if frame["state"] == "acquiring" and not state.blocked_clauses_for(frame)
        ]
        if acquiring_frames and not provider_plan["selected"]:
            raise ValueError("no eligible executable discovery providers; enable at least one installed provider")
        for frame in acquiring_frames:
            request = {
                "frame_id": frame["id"], "query_plan": frame["query_plan"],
                "providers": provider_plan["selected"], "policy": provider_plan["policy"],
            }
            request_sha256 = hashlib.sha256(
                json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            path = self._discovery_path(frame["id"])
            cached = self._read_cached_discovery(path, request_sha256)
            if cached is not None and not refresh:
                payload = cached
                discovery_status = "cached"
            else:
                discovery = run_plan(frame["query_plan"], provider_plan, include_raw=True)
                raw_archive = self._archive_raw_records(frame["id"], request_sha256, discovery)
                # A coordinator turn is not allowed to advance on a partial
                # engine matrix. This protects the all-provider guarantee even
                # if a future executor implementation returns early.
                if not self._valid_cached_discovery(request, discovery):
                    raise ValueError("discovery did not produce a complete archived provider matrix")
                payload = {"schema": DISCOVERY_SCHEMA, "frame_id": frame["id"], "request_sha256": request_sha256,
                           "request": request, "raw_archive": raw_archive, "discovery": discovery}
                atomic_write_json(path, payload)
                discovery_status = "executed"
            materialisation = self._materialize_sources(frame["id"], payload, provider_plan["policy"], refresh=refresh)
            self.service.collection_ready(frame["id"], {
                "discovery_path": self._relative(path),
                "source_manifest_path": materialisation["path"],
                "request_sha256": request_sha256,
                "summary": materialisation["summary"],
                "review_roles": list(REVIEW_ROLES),
            })
            results.append({"frame_id": frame["id"], "status": discovery_status, "path": self._relative(path),
                            "summary": payload.get("discovery", {}).get("summary", {}),
                            "raw_archive": payload.get("raw_archive", {}),
                            "source_materialisation": materialisation})
        return {"schema": 1, "results": results, "max_parallel": provider_plan["max_parallel"]}

    def _collection_pending(self, frame: dict) -> dict | None:
        discovery = self._read_cached_discovery(self._discovery_path(frame["id"]))
        if discovery is None:
            reason = "no archived multi-provider discovery exists"
        else:
            source_manifest = self._read_cached_source_manifest(self._source_manifest_path(frame["id"]), discovery.get("request_sha256"))
            reason = "no completed source materialisation manifest exists" if source_manifest is None else "collection is not marked ready"
        return self._base(frame, "coordinator", "discover-and-materialize", "coordinator") | {
            "reason": reason,
            "instruction": "Run the coordinator discovery stage. It must execute all eligible providers, archive every raw response, capture the bounded cross-provider source set, and only then create review workers.",
        }

    def _archive_raw_records(self, frame_id: str, request_sha256: str, discovery: dict) -> dict:
        records = discovery.get("records") if isinstance(discovery, dict) else None
        if not isinstance(records, list):
            raise ValueError("discovery records missing")
        archived = 0
        missing = 0
        root = self._raw_discovery_dir(frame_id, request_sha256)
        for record in records:
            if not isinstance(record, dict):
                continue
            raw = record.pop("_raw_response", None)
            if raw is None:
                missing += 1
                if record.get("status") == "ok":
                    # A successful normalized lead without its provider's
                    # original response is not admissible for materialisation.
                    record["status"] = "failed"
                    record["reason"] = "raw_response_missing"
                    record["candidates"] = []
                continue
            if not isinstance(raw, dict) or not isinstance(raw.get("text"), str) or not raw["text"]:
                missing += 1
                record["status"] = "failed"
                record["reason"] = "raw_response_invalid"
                record["candidates"] = []
                continue
            provider = record.get("provider")
            plan_index = record.get("plan_index")
            query = record.get("query")
            if not isinstance(provider, str) or not re.fullmatch(r"[a-z0-9_-]{1,64}", provider):
                raise ValueError("invalid provider name for raw response archive")
            if isinstance(plan_index, bool) or not isinstance(plan_index, int) or plan_index < 0 or not isinstance(query, str):
                raise ValueError("invalid raw response archive record")
            content = raw["text"]
            suffix = "md" if raw.get("content_type") == "text/markdown" else ("xml" if raw.get("content_type") == "application/atom+xml" else "json")
            token = hashlib.sha256(f"{provider}\0{plan_index}\0{query}".encode("utf-8")).hexdigest()[:20]
            target = root / f"{provider}-{plan_index:02d}-{token}.{suffix}"
            atomic_write_text(target, content)
            raw_bytes = content.encode("utf-8")
            record["raw_response"] = {
                "path": self._relative(target),
                "content_type": raw.get("content_type", "text/plain"),
                "character_count": len(content),
                "byte_count": len(raw_bytes),
                "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            }
            archived += 1
        return {"archived_records": archived, "records_without_raw": missing,
                "root": self._relative(root)}

    def _materialize_sources(self, frame_id: str, discovery_payload: dict, policy: dict, *, refresh: bool = False) -> dict:
        request_sha256 = discovery_payload.get("request_sha256")
        if not isinstance(request_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", request_sha256):
            raise ValueError("discovery request hash missing")
        path = self._source_manifest_path(frame_id)
        cached = self._read_cached_source_manifest(path, request_sha256)
        if cached is not None and not refresh:
            return {"path": self._relative(path), "status": "cached", "summary": cached.get("summary", {})}
        candidates = self._balanced_candidates(discovery_payload.get("discovery", {}))
        limit = self._source_capture_limit(policy)
        records = []
        for index, candidate in enumerate(candidates):
            record = dict(candidate)
            if index >= limit:
                record["status"] = "deferred_budget"
                record["reason"] = "source_capture_limit_per_frame"
                records.append(record)
                continue
            try:
                native_metadata = self._select_native_metadata_capture(candidate)
                if native_metadata is None:
                    captured = source_acquirer.acquire_anysearch(
                        candidate["url"],
                        candidate["title"],
                        discovered_by=candidate["discovered_by"],
                        source_metadata=candidate["source_metadata"],
                    )
                else:
                    captured = source_acquirer.acquire_provider_metadata(
                        native_metadata["url"],
                        native_metadata["title"],
                        provider=native_metadata["provider"],
                        content_kind=native_metadata["content_kind"],
                        content=native_metadata["text"],
                        possibly_truncated=native_metadata["possibly_truncated"],
                        discovered_by=candidate["discovered_by"],
                        source_metadata=native_metadata["source_metadata"],
                    )
                evidence, content_sha256 = self._capture_packet(captured)
            except (anysearch_client.AnySearchRequestError, ValueError, OSError, RuntimeError) as exc:
                record["status"] = "failed"
                code = getattr(exc, "code", "source_capture_failed")
                record["reason"] = code if isinstance(code, str) and re.fullmatch(r"[a-z0-9_]{1,64}", code) else "source_capture_failed"
            else:
                record["status"] = "captured"
                record["evidence"] = evidence
                record["content_sha256"] = content_sha256
            records.append(record)
        summary = {
            "candidate_count": len(candidates),
            "capture_limit": limit,
            "captured_count": sum(item["status"] == "captured" for item in records),
            "failed_count": sum(item["status"] == "failed" for item in records),
            "deferred_count": sum(item["status"] == "deferred_budget" for item in records),
            "origin_coverage": self._origin_coverage(records),
        }
        payload = {"schema": SOURCE_MANIFEST_SCHEMA, "frame_id": frame_id, "request_sha256": request_sha256,
                   "records": records, "summary": summary}
        atomic_write_json(path, payload)
        return {"path": self._relative(path), "status": "executed", "summary": summary}

    @staticmethod
    def _source_capture_limit(policy: dict) -> int:
        value = policy.get("source_capture_limit_per_frame", 24) if isinstance(policy, dict) else 24
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_SOURCE_CAPTURE_LIMIT:
            raise ValueError(f"source_capture_limit_per_frame must be an integer between 1 and {MAX_SOURCE_CAPTURE_LIMIT}")
        return value

    @staticmethod
    def _capture_packet(captured: object) -> tuple[dict, str]:
        if not isinstance(captured, dict) or not isinstance(captured.get("evidence"), dict):
            raise ValueError("source acquirer returned no evidence proposal")
        content_sha256 = captured.get("content_sha256")
        if not isinstance(content_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", content_sha256):
            raise ValueError("source acquirer returned an invalid content hash")
        return captured["evidence"], content_sha256

    @staticmethod
    def _balanced_candidates(discovery: dict) -> list[dict]:
        records = discovery.get("records") if isinstance(discovery, dict) else []
        buckets: dict[str, deque[str]] = {}
        by_url: dict[str, dict] = {}
        for record in records if isinstance(records, list) else []:
            if not isinstance(record, dict) or record.get("status") != "ok":
                continue
            provider = record.get("provider")
            if not isinstance(provider, str) or not re.fullmatch(r"[a-z0-9_-]{1,64}", provider):
                continue
            buckets.setdefault(provider, deque())
            candidates = record.get("candidates")
            for candidate in candidates if isinstance(candidates, list) else []:
                if not isinstance(candidate, dict):
                    continue
                url = None
                for field in ("landing_page_url", "url"):
                    try:
                        url = anysearch_client.validate_extract_url(candidate.get(field))
                    except anysearch_client.AnySearchRequestError:
                        continue
                    else:
                        break
                if url is None:
                    continue
                title = candidate.get("title")
                title = title.strip() if isinstance(title, str) else ""
                if len(title) > 1024 or any(ord(character) < 32 or ord(character) == 127 for character in title):
                    title = ""
                candidate_url = candidate.get("url")
                try:
                    candidate_url = anysearch_client.validate_extract_url(candidate_url)
                except anysearch_client.AnySearchRequestError:
                    candidate_url = url
                provenance = {
                    "provider": provider,
                    "plan_index": record.get("plan_index"),
                    "candidate_id": candidate.get("id"),
                    "candidate_url": candidate_url,
                }
                source_metadata = ResearchOrchestrator._source_metadata(candidate)
                native_metadata = ResearchOrchestrator._native_metadata_candidate(candidate, provider)
                existing = by_url.get(url)
                if existing is None:
                    existing = {
                        "url": url,
                        "title": title,
                        "discovered_by": [provenance],
                        "source_metadata": source_metadata,
                        "native_metadata": [native_metadata] if native_metadata is not None else [],
                    }
                    by_url[url] = existing
                    buckets[provider].append(url)
                else:
                    existing["discovered_by"].append(provenance)
                    if not existing["title"] and title:
                        existing["title"] = title
                    for key, value in source_metadata.items():
                        existing["source_metadata"].setdefault(key, value)
                    ResearchOrchestrator._append_native_metadata(existing, native_metadata)
        ordered = []
        while any(bucket for bucket in buckets.values()):
            for provider in sorted(buckets):
                bucket = buckets[provider]
                if bucket:
                    ordered.append(by_url[bucket.popleft()])
        return ordered

    @staticmethod
    def _source_metadata(candidate: dict) -> dict:
        """Preserve provider-supplied temporal facts with the materialised page."""

        metadata = {}
        for key in ("published_at", "updated_at", "event_at"):
            value = candidate.get(key)
            if isinstance(value, str) and value.strip() and len(value) <= 128 and not any(ord(char) < 32 for char in value):
                metadata[key] = value.strip()
        return metadata

    @staticmethod
    def _native_metadata_candidate(candidate: dict, provider: str) -> dict | None:
        """Accept only bounded text that the current provider normalized itself."""

        value = candidate.get("native_metadata")
        if not isinstance(value, dict) or value.get("provider") != provider:
            return None
        try:
            url = anysearch_client.validate_extract_url(value.get("url"))
        except anysearch_client.AnySearchRequestError:
            return None
        title = value.get("title")
        if not isinstance(title, str):
            return None
        title = " ".join(title.split())
        if len(title) > 1_024 or any(ord(character) < 32 or ord(character) == 127 for character in title):
            return None
        content_kind = value.get("content_kind")
        if not isinstance(content_kind, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", content_kind):
            return None
        text = value.get("text")
        if not isinstance(text, str):
            return None
        text = " ".join(text.split())
        if (
            not text
            or len(text) > MAX_NATIVE_METADATA_CHARS
            or any(ord(character) < 32 or ord(character) == 127 for character in text)
        ):
            return None
        possibly_truncated = value.get("possibly_truncated")
        if not isinstance(possibly_truncated, bool):
            return None
        raw_source_metadata = value.get("source_metadata", {})
        if not isinstance(raw_source_metadata, dict):
            return None
        return {
            "provider": provider,
            "url": url,
            "title": title,
            "content_kind": content_kind,
            "text": text,
            "possibly_truncated": possibly_truncated,
            # Never borrow a date from a different discovery origin for a
            # metadata-only capture. The nested values came with this record.
            "source_metadata": ResearchOrchestrator._source_metadata(raw_source_metadata),
        }

    @staticmethod
    def _append_native_metadata(candidate: dict, native_metadata: dict | None) -> None:
        if native_metadata is None:
            return
        entries = candidate.get("native_metadata")
        if not isinstance(entries, list):
            return
        key = tuple(native_metadata[item] for item in ("provider", "url", "content_kind", "text"))
        if any(
            isinstance(entry, dict)
            and tuple(entry.get(item) for item in ("provider", "url", "content_kind", "text")) == key
            for entry in entries
        ):
            return
        if len(entries) < MAX_NATIVE_METADATA_CANDIDATES:
            entries.append(native_metadata)

    @staticmethod
    def _select_native_metadata_capture(candidate: dict) -> dict | None:
        """Prefer sufficiently substantive native text; otherwise extract a page."""

        entries = candidate.get("native_metadata")
        if not isinstance(entries, list):
            return None
        eligible = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            text = entry.get("text")
            if not isinstance(text, str):
                continue
            # Character length supports languages without whitespace-delimited
            # words; the token fallback still admits a concise structured
            # abstract with many short terms.
            if len(text) < MIN_NATIVE_METADATA_CHARS and len(text.split()) < MIN_NATIVE_METADATA_WORDS:
                continue
            eligible.append(entry)
        if not eligible:
            return None
        # Selecting the fullest bounded provider record is deterministic and
        # still keeps other provenance and native records in the manifest.
        return min(
            eligible,
            key=lambda item: (-len(item["text"]), item["provider"], item["url"], item["content_kind"]),
        )

    @staticmethod
    def _origin_coverage(records: list[dict]) -> dict:
        """Expose discovery origins separately from the page-capture transport."""

        candidates, captured, failed, deferred = {}, {}, {}, {}
        capture_transports = {}
        status_counts = {
            "captured": captured,
            "failed": failed,
            "deferred_budget": deferred,
        }
        for record in records:
            if not isinstance(record, dict):
                continue
            origin_names = {
                item.get("provider") for item in record.get("discovered_by", [])
                if isinstance(item, dict) and isinstance(item.get("provider"), str)
            }
            for provider in origin_names:
                candidates[provider] = candidates.get(provider, 0) + 1
                target = status_counts.get(record.get("status"))
                if target is not None:
                    target[provider] = target.get(provider, 0) + 1
            evidence = record.get("evidence")
            capture_provider = evidence.get("capture_provider") if isinstance(evidence, dict) else None
            if record.get("status") == "captured" and isinstance(capture_provider, str):
                capture_transports[capture_provider] = capture_transports.get(capture_provider, 0) + 1
        return {
            "candidate_origins": dict(sorted(candidates.items())),
            "captured_origins": dict(sorted(captured.items())),
            "failed_origins": dict(sorted(failed.items())),
            "deferred_origins": dict(sorted(deferred.items())),
            "capture_transports": dict(sorted(capture_transports.items())),
        }

    def _plan_frozen(self, snapshot: str) -> dict:
        # The project module owns snapshot validation and chapter task construction.
        import project

        tasks = project.chapter_plan(snapshot)
        writers = []
        deferred = []
        chapter_ready_cache = {}

        def is_ready(chapter_id: str) -> bool:
            if chapter_id not in chapter_ready_cache:
                chapter_ready_cache[chapter_id] = project.chapter_ready(snapshot, chapter_id)
            return chapter_ready_cache[chapter_id]

        for chapter in tasks["chapters"]:
            output = workspace() / "research" / "chapters" / f"{chapter['chapter_id']}.md"
            if is_ready(chapter["chapter_id"]):
                continue
            dependencies = chapter.get("dependency_chapter_ids", [])
            if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
                raise ValueError(f"chapter dependency plan is invalid for {chapter['chapter_id']}")
            unmet = [dependency_id for dependency_id in dependencies if not is_ready(dependency_id)]
            if unmet:
                deferred.append({
                    "chapter_id": chapter["chapter_id"],
                    "dependency_chapter_ids": dependencies,
                    "unmet_dependency_chapter_ids": sorted(unmet),
                })
                continue
            writers.append({"task_id": f"writer:{chapter['chapter_id']}", "role": "writer", "kind": "write-chapter",
                            "snapshot_id": snapshot, "chapter": chapter,
                            "output_path": str(output.relative_to(workspace())).replace("\\", "/"),
                            "instruction": "Write only this chapter from the cited frozen snapshot claims and source spans. Do not query live sources or use another chapter as evidence."})
        if writers:
            # One independent writer owns one chapter. The host may impose a
            # lower resource ceiling, but the plan must never imply that one
            # writer is responsible for multiple chapters.
            result = {"schema": 1, "snapshot_id": snapshot, "tasks": writers,
                      "max_parallel": len(writers)}
            if deferred:
                result["deferred_chapters"] = deferred
            return result
        if deferred:
            return {"schema": 1, "snapshot_id": snapshot, "status": "waiting_for_dependencies",
                    "tasks": [], "deferred_chapters": deferred, "max_parallel": 0}
        if project.report_ready(snapshot):
            return {"schema": 1, "snapshot_id": snapshot, "status": "complete", "tasks": [], "max_parallel": 1}
        packet = project.editor_packet(snapshot)
        if packet.get("decision_synthesis") is not None:
            draft_path = workspace() / "research" / "editor" / "report_draft.md"
            if not draft_path.is_file():
                return {"schema": 1, "snapshot_id": snapshot,
                        "tasks": [{"task_id": f"editor:draft:{snapshot}", "role": "editor", "kind": "stage-report",
                                   "packet": packet,
                                   "instruction": "Build a reader-facing draft from present frozen chapters only, then submit it through stage_report. Follow the frozen decision synthesis exactly: bind every decision question and parameter provenance id, distinguish supported evidence from conditions/gaps/user input, and do not turn a conditional or insufficient conclusion into approval."}],
                        "max_parallel": 1}
            if not project.report_review_ready(snapshot):
                return {"schema": 1, "snapshot_id": snapshot,
                        "tasks": [{"task_id": f"reviewer:{snapshot}", "role": "senior_user_reviewer", "kind": "review-report",
                                   "snapshot_id": snapshot,
                                   "draft_path": str(draft_path.relative_to(workspace())).replace("\\", "/"),
                                   "packet": packet,
                                   "instruction": "Review the staged report as an experienced user, independently of the editor. Submit an approved structured report review only if every frozen decision question has an evidence-to-inference-to-action chain, every non-supported conclusion preserves its conditions or user-input gap, and every parameter provenance basis is visibly disclosed. Do not edit research state, search, or invent evidence."}],
                        "max_parallel": 1}
            return {"schema": 1, "snapshot_id": snapshot,
                    "tasks": [{"task_id": f"editor:compile:{snapshot}", "role": "editor", "kind": "compile-report",
                               "snapshot_id": snapshot,
                               "content_path": str(draft_path.relative_to(workspace())).replace("\\", "/"),
                               "instruction": "Compile the reviewed staged draft through compile_report. Do not alter its content; the compiler verifies the frozen decision synthesis and independent review bindings."}],
                    "max_parallel": 1}
        return {"schema": 1, "snapshot_id": snapshot,
                "tasks": [{"task_id": f"editor:{snapshot}", "role": "editor", "kind": "compile-report",
                           "packet": packet,
                           "instruction": "Compile report.md from present frozen chapters only. Build a reader-facing report rather than a compressed chapter summary: preserve the executable protocol, decision rules, evidence boundaries, and limitations of every experiment/design deliverable. Follow packet.report_presentation, use readable evidence labels plus an evidence ledger, and keep machine chunk ids out of reader-facing prose. Turn unsupported claims or unmet presentation/delivery requirements into repair tasks rather than prose."}],
                "max_parallel": 1}

    @staticmethod
    def _plan_qa(snapshot: str, question: str) -> dict:
        """Prepare one dedicated Q&A worker from a verified frozen corpus."""
        import qa

        packet = qa.ask(snapshot, question, 8)
        return {"schema": 1, "snapshot_id": snapshot,
                "tasks": [{"task_id": f"qa:{snapshot}", "role": "qa", "kind": "answer-question",
                           "snapshot_id": snapshot, "question": packet["question"],
                           "reference_time": packet["reference_time"], "frozen_at": packet["frozen_at"],
                           "evidence_packets": packet["evidence_packets"],
                           "instruction": "Answer only from these frozen evidence packets. Cite chunk_id and source_path for every factual claim. State partial or unknown when the packets do not support an answer; do not search or mutate research."}],
                "max_parallel": 1}

    @staticmethod
    def _base(frame: dict, role: str, kind: str, operation: str) -> dict:
        return {"task_id": f"{kind}:{frame['id']}", "role": role, "kind": kind,
                "frame_id": frame["id"], "focus": frame["focus"], "information_gap": frame["information_gap"],
                "discriminator": frame["discriminator"], "expected_update": frame["expected_update"],
                "evidence_requirement": frame["evidence_requirement"], "intent_clause_ids": frame["intent_clause_ids"],
                "temporal_scope": frame.get("temporal_scope"),
                "allowed_operation": operation}

    def _formulation_task(self, state: ResearchState, frame: dict) -> dict:
        task = self._base(frame, "coordinator", "formulate", "formulate")
        contract = state.intent_contract().get("contract")
        task.update({
            "intent_contract": contract,
            "reference_time": state.data["reference_time"],
            "instruction": "As the coordinator, compile a bounded query plan from the original intent contract, this frame, inherited clauses, material/design requirements, and temporal_scope, then submit formulate. Treat temporal_scope as a hard constraint resolved against reference_time; do not silently broaden it in a recursive subproblem. Use the user anchors and explicit exclusions as query constraints; do not replace them with a nearby topic. Search only questions that need external evidence. Do not create a worker or search yet.",
        })
        return task

    @staticmethod
    def _intent_analysis_task(state: ResearchState, contract: dict) -> dict:
        """Plan a single preflight analyst before any research worker/search."""

        return {
            "task_id": "intent:analyze", "role": "intent_analyst", "kind": "analyze-intent",
            "allowed_operation": "analyze_intent", "intent": state.current_intent()["raw"],
            "clauses": state.active_clauses(), "reference_time": state.data["reference_time"],
            "registered_materials": list(state.data.get("materials", {}).values()),
            "prior_answers": contract.get("answers", {}),
            "instruction": (
                "Deeply interpret the user's intent before any search. Return one analyze_intent command with a contract, not a query plan. "
                "Separate requested deliverables, research questions, user-material analysis, design requirements, writing requirements, acceptance criteria, assumptions, and long-tail constraints. "
                "Identify the user decision separately in decision_questions: every entry needs an id, a concrete decision question, why_it_matters, impact, and any affected deliverable_ids. A decision question is not a generic research heading; it must state what the user will approve, reject, defer, or design differently after research. "
                "When registered_materials are present, read the local material first to identify its actual setting, constraints, and sufficiency; do not claim that a material supports something you have not inspected. "
                "Do not collapse a request such as 'based on my materials, write an experiment plan' into a research report: include material_analysis plus experiment_plan, identify any evidence research needed, and state feasibility/measurement/control requirements. "
                "Resolve relative temporal language against reference_time and preserve the resulting time constraint in each relevant research frame. When a material, audience, success criterion, scope, time interpretation, or conflicting instruction is genuinely decision-blocking, return status needs_clarification with the smallest discriminating questions. "
                "Only return status ready when the contract is executable; include research_frames only for research questions that need saved evidence. Do not search, create a frame outside the command, or fabricate user material."
            ),
        }

    @staticmethod
    def _intent_clarification_task(contract: dict) -> dict:
        return {
            "task_id": "intent:clarify", "role": "coordinator", "kind": "clarify-intent",
            "allowed_operation": "answer_intent_questions", "questions": contract.get("questions", []),
            "instruction": "Ask only the listed minimal questions. Record the user's answers with answer_intent_questions, then request a revised intent analysis. Do not search or create research workers while these questions remain blocking.",
        }

    def _triage_task(self, frame: dict) -> dict:
        """Create a review worker only after durable collection is complete."""

        collection = frame.get("collection")
        if not isinstance(collection, dict):
            raise ValueError("reviewing frame is missing a completed collection")
        aggregation = frame.get("aggregation", {})
        if aggregation.get("status") != "complete" or not isinstance(aggregation.get("path"), str):
            raise ValueError("source triage requires completed topic aggregation")
        task = self._base(frame, "source_triager", "triage-saved-sources", "evidence")
        task.update({
            "reviewer_role": "source_triager",
            "discovery_path": collection["discovery_path"],
            "source_manifest_path": collection["source_manifest_path"],
            "aggregation_path": aggregation["path"],
            "source_manifest_sha256": collection["source_manifest_sha256"],
            "aggregation_sha256": aggregation["sha256"],
            "collection_summary": collection["summary"],
            "instruction": "Read only the archived discovery records, source manifest, hash-verified topic aggregation, and saved pages. Use quality/confidence scores as triage signals, not proof: independently confirm relevance and select credible saved pages across needed topics. A low-quality or non-representative source is allowed only for a documented limitation, alternative explanation, or contradiction; include selection_override_rationale in that evidence proposal. Submit one evidence command with reviewer_role source_triager, or an empty list when none qualify. Do not search, extract URLs, create frames, or mutate the graph directly.",
        })
        return task

    def _adversary_task(self, frame: dict) -> dict:
        """Review the same completed source set for counter-evidence only."""

        collection = frame.get("collection")
        if not isinstance(collection, dict):
            raise ValueError("reviewing frame is missing a completed collection")
        aggregation = frame.get("aggregation", {})
        if aggregation.get("status") != "complete" or not isinstance(aggregation.get("path"), str):
            raise ValueError("source adversary requires completed topic aggregation")
        task = self._base(frame, "source_adversary", "challenge-saved-sources", "evidence")
        task.update({
            "reviewer_role": "source_adversary",
            "discovery_path": collection["discovery_path"],
            "source_manifest_path": collection["source_manifest_path"],
            "aggregation_path": aggregation["path"],
            "source_manifest_sha256": collection["source_manifest_sha256"],
            "aggregation_sha256": aggregation["sha256"],
            "collection_summary": collection["summary"],
            "instruction": "Read only the archived discovery records, source manifest, hash-verified topic aggregation, and saved pages. Challenge overconfident topic clusters, correlated sources, weak-quality representatives, temporal mismatches, and alternative explanations. A counterexample must remain visible as relation=contradictory, not be collapsed as a duplicate. If selecting a low-quality or non-representative source, include selection_override_rationale. Submit one evidence command with reviewer_role source_adversary, or an empty list when no saved page qualifies. Do not search, extract URLs, create a frame, weaken a user constraint, or mutate the graph directly.",
        })
        return task

    def _aggregation_task(self, frame: dict) -> dict:
        """Schedule exactly one post-collection semantic aggregation worker."""

        collection = frame.get("collection")
        if not isinstance(collection, dict):
            raise ValueError("source aggregation requires a completed collection")
        task = self._base(frame, "source_aggregator", "aggregate-saved-sources", "aggregate_sources")
        task.update({
            "discovery_path": collection["discovery_path"],
            "source_manifest_path": collection["source_manifest_path"],
            "source_manifest_sha256": collection["source_manifest_sha256"],
            "aggregator_role": "source_aggregator",
            "collection_summary": collection["summary"],
            "instruction": (
                "Read only the archived discovery records, source manifest, and pages already saved under research_drift/pages. "
                "Submit one aggregate_sources command with aggregator_role source_aggregator and source_manifest_sha256 repeated exactly. Cluster by substantive topic/claim and context, not URL/title similarity; preserve distinct time scopes, contradictions, and independent claims. "
                "Every captured page needs exactly one primary=true topic assessment, but a long page may appear in additional clusters with primary=false. Each source object must include its manifest content_sha256, relation (representative/corroborating/near_duplicate/contradictory/irrelevant), primary, quality_components {authority,directness,traceability,temporal_fit,capture_completeness,independence}, assessment_confidence, and rationale. "
                "Each cluster requires topic_key, topic, context_signature, dedup_rationale, representative_local_paths, confidence_components {source_quality,corroboration,independence,temporal_coherence,scope_match}, confidence_rationale, and unresolved. Scores are derived by the service from those components; do not invent score-only assessments. Representatives prioritize review only and never discard a captured source. "
                "Use collection_summary.origin_coverage and each source's discovery provenance when assessing independence: several records from one origin or transport are not independent corroboration. "
                "A capture whose metadata says completeness=metadata_limited or full_text=false is a provider metadata record, not a full page: score capture_completeness conservatively and state that limitation in the rationale. "
                "Do not search, fetch URLs, write a path, create frames, or accept evidence."
            ),
        })
        return task

    @staticmethod
    def _discovery_path(frame_id: str) -> Path:
        return workspace() / "research_drift" / "discovery" / f"{ResearchOrchestrator._frame_token(frame_id)}.json"

    @staticmethod
    def _raw_discovery_dir(frame_id: str, request_sha256: str) -> Path:
        if not isinstance(request_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", request_sha256):
            raise ValueError("invalid request hash for raw discovery archive")
        return (workspace() / "research_drift" / "discovery" / "raw" /
                ResearchOrchestrator._frame_token(frame_id) / request_sha256)

    @staticmethod
    def _source_manifest_path(frame_id: str) -> Path:
        return workspace() / "research_drift" / "sources" / f"{ResearchOrchestrator._frame_token(frame_id)}.json"

    @staticmethod
    def _frame_token(frame_id: str) -> str:
        if not isinstance(frame_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", frame_id):
            raise ValueError("invalid frame id for research artifact path")
        return frame_id

    @staticmethod
    def _read_cached_discovery(path: Path, request_sha256: str | None = None) -> dict | None:
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("schema") != DISCOVERY_SCHEMA:
            return None
        if request_sha256 and payload.get("request_sha256") != request_sha256:
            return None
        discovery = payload.get("discovery")
        if not ResearchOrchestrator._valid_cached_discovery(payload.get("request"), discovery):
            return None
        return payload

    @staticmethod
    def _read_cached_source_manifest(path: Path, request_sha256: str | None = None) -> dict | None:
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("schema") != SOURCE_MANIFEST_SCHEMA:
            return None
        if request_sha256 and payload.get("request_sha256") != request_sha256:
            return None
        if not ResearchOrchestrator._valid_cached_source_manifest(payload):
            return None
        return payload

    @staticmethod
    def _valid_cached_discovery(request: object, discovery: object) -> bool:
        """Require a complete, content-addressed raw archive before reuse."""

        if not isinstance(request, dict) or not isinstance(discovery, dict):
            return False
        query_plan = request.get("query_plan")
        providers_in_request = request.get("providers")
        records = discovery.get("records")
        if not isinstance(query_plan, list) or not isinstance(providers_in_request, list) or not isinstance(records, list):
            return False
        provider_names = []
        for provider in providers_in_request:
            name = provider.get("provider") if isinstance(provider, dict) else provider
            if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_-]{1,64}", name):
                return False
            if name not in provider_names:
                provider_names.append(name)
        expected = set()
        for index, item in enumerate(query_plan):
            query = item.get("query") if isinstance(item, dict) else None
            if not isinstance(query, str) or not query:
                return False
            for provider in provider_names:
                expected.add((provider, index, query))
        if len(records) != len(expected):
            return False
        seen = set()
        for record in records:
            if not isinstance(record, dict):
                return False
            provider = record.get("provider")
            plan_index = record.get("plan_index")
            query = record.get("query")
            key = (provider, plan_index, query)
            if key not in expected or key in seen:
                return False
            seen.add(key)
            status = record.get("status")
            if status not in {"ok", "failed", "skipped", "unavailable"}:
                return False
            raw_response = record.get("raw_response")
            if status == "ok" and not ResearchOrchestrator._valid_raw_response(raw_response):
                return False
            if raw_response is not None and not ResearchOrchestrator._valid_raw_response(raw_response):
                return False
        return seen == expected

    @staticmethod
    def _valid_raw_response(value: object) -> bool:
        if not isinstance(value, dict):
            return False
        path_value = value.get("path")
        byte_count = value.get("byte_count")
        character_count = value.get("character_count")
        digest = value.get("sha256")
        content_type = value.get("content_type")
        if (
            not isinstance(path_value, str)
            or isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 1
            or isinstance(character_count, bool) or not isinstance(character_count, int) or character_count < 1
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not isinstance(content_type, str) or not content_type or len(content_type) > 128
        ):
            return False
        path = ResearchOrchestrator._artifact_file(path_value, workspace() / "research_drift" / "discovery" / "raw")
        if path is None:
            return False
        try:
            payload = path.read_bytes()
            text = payload.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return False
        return (len(payload) == byte_count and len(text) == character_count and
                hashlib.sha256(payload).hexdigest() == digest)

    @staticmethod
    def _valid_cached_source_manifest(payload: object) -> bool:
        if not isinstance(payload, dict):
            return False
        records = payload.get("records")
        summary = payload.get("summary")
        if not isinstance(records, list) or not isinstance(summary, dict):
            return False
        required = ("candidate_count", "capture_limit", "captured_count", "failed_count", "deferred_count")
        if any(isinstance(summary.get(key), bool) or not isinstance(summary.get(key), int) or summary[key] < 0 for key in required):
            return False
        if not 1 <= summary["capture_limit"] <= MAX_SOURCE_CAPTURE_LIMIT:
            return False
        if summary["candidate_count"] != len(records):
            return False
        totals = {"captured": 0, "failed": 0, "deferred_budget": 0}
        for record in records:
            if not isinstance(record, dict) or record.get("status") not in totals:
                return False
            status = record["status"]
            totals[status] += 1
            if status == "captured" and not ResearchOrchestrator._valid_captured_source(record):
                return False
        return (summary["captured_count"] == totals["captured"] and
                summary["failed_count"] == totals["failed"] and
                summary["deferred_count"] == totals["deferred_budget"])

    @staticmethod
    def _valid_captured_source(record: dict) -> bool:
        evidence = record.get("evidence")
        content_sha256 = record.get("content_sha256")
        if not isinstance(evidence, dict) or not isinstance(content_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", content_sha256):
            return False
        local_path = evidence.get("local_path")
        if not isinstance(local_path, str):
            return False
        try:
            path = saved_page_path(local_path)
            payload = path.read_bytes()
        except (OSError, ValueError):
            return False
        return path.is_file() and hashlib.sha256(payload).hexdigest() == content_sha256

    @staticmethod
    def _artifact_file(value: object, root: Path) -> Path | None:
        if not isinstance(value, str) or not value or "\x00" in value:
            return None
        candidate = (workspace() / value).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    @staticmethod
    def _relative(path: Path) -> str:
        return str(path.relative_to(workspace())).replace("\\", "/")

    def _extract_task(self, state: ResearchState, frame: dict) -> dict:
        task = self._base(frame, "extractor", "extract", "extract")
        aggregation = frame.get("aggregation", {})
        contract = state.intent_contract().get("contract")
        task.update({"evidence": [state.data["evidence"][item] for item in frame["evidence_ids"]],
                     "aggregation": {key: aggregation.get(key) for key in ("path", "sha256", "summary", "clusters")},
                     "intent_contract": contract,
                     "registered_materials": list(state.data.get("materials", {}).values()),
                     "prior_cognitions": [
                         {key: cognition.get(key) for key in ("id", "claim", "claim_key", "context_signature", "evidence_time", "frame_id")}
                         for cognition in state.data["cognitions"].values()
                         if cognition["id"] not in frame["cognition_ids"]
                     ][:128],
                      "instruction": "Produce only cited cognitions and candidate gaps. Each cognition must respect evidence aggregation assessments: quality, topic confidence, and assessment confidence are evidence limits, not decorative metadata. State uncertainty or a limitation for low-scored support; do not convert duplicate count into confidence. The service will cap requested cognition confidence by its strongest assessed topic support. Each gap must state expected information gain and acquisition cost in [0,1]; do not choose a child frame. To cite a cognition created in this same atomic extraction, assign that cognition a unique proposal_ref and list it in the gap's trigger_cognition_refs; use trigger_cognition_ids only for already persisted cognitions from this frame. A new gap may declare proposal_ref; use that ref in coverage.gap_refs when a source needs follow-up. When intent_contract.decision_questions is non-empty, submit coverage for every accepted evidence_id exactly once with cited, context_only, needs_followup, or excluded plus a concrete rationale. cited must be used by a cognition in this package; needs_followup must create or link a gap. Do not silently lose a high-quality representative source, and turn decision-changing unknowns into gaps or later user-input conditions. When primary evidence explicitly disagrees with or temporally updates a prior cognition under the same claim key, set contradicts_cognition_ids or updates_cognition_ids; updates require a strictly newer evidence_time. Do not infer contradiction from wording alone."})
        return task

    @staticmethod
    def _decision_synthesis_task(state: ResearchState) -> dict:
        """Schedule the post-descent decision integrator before snapshot freeze."""

        contract = state.intent_contract().get("contract", {})
        frames = []
        for frame in sorted(state.data["frames"].values(), key=lambda item: item["id"]):
            frames.append({
                "id": frame["id"], "focus": frame.get("focus"), "state": frame.get("state"),
                "return": frame.get("return"), "cognition_ids": frame.get("cognition_ids", []),
                "gap_ids": frame.get("gap_ids", []), "evidence_coverage": frame.get("evidence_coverage", []),
                "aggregation_unresolved": [
                    {"cluster_id": cluster.get("cluster_id"), "unresolved": cluster.get("unresolved", [])}
                    for cluster in frame.get("aggregation", {}).get("clusters", [])
                    if isinstance(cluster, dict) and cluster.get("unresolved")
                ],
            })
        return {
            "task_id": "decision:synthesize", "role": "decision_synthesizer", "kind": "synthesize-decision",
            "allowed_operation": "synthesize_decision", "synthesizer_role": "decision_synthesizer",
            "intent_contract": contract, "decision_questions": state.decision_questions(),
            "reference_time": state.data["reference_time"], "frames": frames,
            "cognitions": list(state.data["cognitions"].values()), "gaps": list(state.data["gaps"].values()),
            "instruction": "Produce one decision synthesis after recursive research has stopped. Assess every decision question exactly once as supported, conditional, gap_child, need_user_input, or insufficient. For each, give a bounded conclusion, actual supporting/refuting cognition ids, any gap ids or minimal user questions, conditions that would change the conclusion, and a concrete action. Do not turn transfer evidence, an incomplete source, or an unresolved aggregation item into approval. recommendation=approve is allowed only when every high-impact decision question is supported; otherwise use conditional, preflight_only, defer, or reject. Include parameter_provenance for every consequential number, threshold, budget, sample size, or operating rule: classify its basis as user_constraint, direct_evidence, transfer_method, assumption, or need_user_input and name its cognition/material basis. Do not search, fetch, formulate a new query, or mutate frames. Submit only synthesize_decision with synthesizer_role decision_synthesizer.",
        }

    def _selector_task(self, frame: dict, frontier: list[dict], decision: dict) -> dict:
        task = self._base(frame, "branch_selector", "select-descent", "descend")
        instruction = (
            "Select at most one frontier gap that blocks this frame's return contract. "
            "Explain why its score and discriminator justify descent, then submit one descend command with a child frame proposal. "
            "You may instead return the frame when current cited evidence satisfies its contract; do not expand every candidate."
        )
        if decision["recommendation"] == "review":
            instruction = (
                "The top frontier scores are within score_margin, so the ranking is deliberately non-decisive. "
                "Either return the frame or choose at most one gap with a comparative, explicit rationale that explains why the heuristic tie does not control. "
                "Leave every other alternative deferred."
            )
        task.update({"frontier": frontier, "frontier_decision": decision, "instruction": instruction})
        return task

    def _return_task(self, frame: dict, decision: dict | None = None) -> dict:
        task = self._base(frame, "resolver", "return", "finish")
        task["instruction"] = "Return a bounded terminal result using cited cognitions. Do not invent a child frame."
        if decision:
            task["frontier_decision"] = decision
            task["instruction"] += " Deferred alternatives remain preserved for later evidence or a revised budget."
        return task

    def _reducer_task(self, frame: dict, child: dict) -> dict:
        task = self._base(frame, "reducer", "return-child", "return_child")
        task.update({"child_frame_id": child["id"], "child_return": child["return"],
                     "instruction": "Reduce this terminal child result into the parent. State whether to revisit the frontier or return the parent in a later selector/resolver task."})
        return task

    def _clarification_task(self, frame: dict, clauses: list[dict]) -> dict:
        task = self._base(frame, "coordinator", "clarify", "clarify")
        task.update({"clauses": clauses, "instruction": "Ask the smallest user question that distinguishes the unresolved clause readings. Do not create a worker, search, or mutate any frame before the user responds."})
        return task


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="research-orchestrator", description="generate role-scoped recursive research tasks")
    parser.add_argument("--write", action="store_true", help="persist the current worker batch in the project workspace")
    parser.add_argument("--snapshot", help="plan frozen-snapshot writer/editor tasks instead of live research tasks")
    parser.add_argument("--question", help="prepare a dedicated Q&A task from the named frozen snapshot")
    parser.add_argument("--discover", action="store_true", help="run stored acquisition plans and save discovery leads before planning")
    parser.add_argument("--refresh-discovery", action="store_true", help="ignore unchanged cached discovery results")
    args = parser.parse_args(argv)
    if args.snapshot and (args.discover or args.refresh_discovery):
        parser.error("frozen writer/editor planning cannot run live discovery")
    if args.question and not args.snapshot:
        parser.error("--question requires --snapshot")
    if args.refresh_discovery and not args.discover:
        parser.error("--refresh-discovery requires --discover")
    orchestrator = ResearchOrchestrator()
    discovery = orchestrator.discover(refresh=args.refresh_discovery) if args.discover else None
    batch = orchestrator.plan(snapshot=args.snapshot, question=args.question)
    if discovery is not None:
        batch["discovery"] = discovery
    if args.write:
        path = workspace() / "research" / "orchestrator" / "worker_batch.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, batch)
        batch["path"] = str(path.relative_to(workspace())).replace("\\", "/")
    print(json.dumps(batch, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

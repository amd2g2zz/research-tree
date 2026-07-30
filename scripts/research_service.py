"""Application use cases shared by the CLI and workflow orchestrators."""

from __future__ import annotations

import re
from typing import Any

from research_domain import ResearchState, SCHEMA, now_iso
from research_repository import JsonResearchRepository, default_repository


class ResearchService:
    def __init__(self, repository: JsonResearchRepository | None = None):
        self.repository = repository or default_repository()

    def initialize(self, intent: str, clauses: list, reference_time: str | None,
                   materials: list | None = None) -> dict:
        with self.repository.locked():
            if self._state_file_exists():
                raise FileExistsError("research state already exists; use a new workspace")
            state = ResearchState.create(intent, clauses, reference_time, materials)
            state.event("intent_created", intent=intent, reference_time=state.data["reference_time"])
            self.repository.save_data(state.data)
        from research_repository import state_path
        return {"schema": SCHEMA, "state": str(state_path()), "reference_time": state.data["reference_time"]}

    def bootstrap(self, proposals: list) -> dict:
        return self._mutate(lambda state: state.bootstrap(proposals))

    def analyze_intent(self, contract: dict) -> dict:
        return self._mutate(lambda state: state.analyze_intent(contract))

    def answer_intent_questions(self, answers: dict) -> dict:
        return self._mutate(lambda state: state.answer_intent_questions(answers))

    def register_material(self, material: dict, replace: bool = False) -> dict:
        return self._mutate(lambda state: state.register_material(material, replace))

    def formulate(self, frame_id: str, plan: list) -> dict:
        return self._mutate(lambda state: state.formulate(frame_id, plan))

    def add_evidence(self, frame_id: str, proposals: list, reviewer_role: str | None = None) -> dict:
        return self._mutate(lambda state: state.add_evidence(frame_id, proposals, reviewer_role))

    def enrich_evidence_publication_time(self, evidence_id: str, published_at: str,
                                         locator: str, rationale: str) -> dict:
        return self._mutate(
            lambda state: state.enrich_evidence_publication_time(evidence_id, published_at, locator, rationale)
        )

    def collection_ready(self, frame_id: str, collection: dict) -> dict:
        """Apply the coordinator-only saved-source barrier transition."""

        return self._mutate(lambda state: state.collection_ready(frame_id, collection))

    def aggregate_sources(self, frame_id: str, clusters: list, source_manifest_sha256: str) -> dict:
        """Accept the saved-source aggregator's bounded semantic clustering."""

        return self._mutate(lambda state: state.aggregate_sources(frame_id, clusters, source_manifest_sha256))

    def extract(self, frame_id: str, cognitions: list, gaps: list, coverage: list | None = None) -> dict:
        return self._mutate(lambda state: state.extract(frame_id, cognitions, gaps, coverage))

    def synthesize_decision(self, synthesis: dict) -> dict:
        return self._mutate(lambda state: state.synthesize_decision(synthesis))

    def expand(self, gap_id: str, proposal: dict) -> dict:
        return self._mutate(lambda state: state.expand(gap_id, proposal))

    def descend(self, frame_id: str, gap_id: str, proposal: dict, selection_rationale: str) -> dict:
        return self._mutate(lambda state: state.descend(frame_id, gap_id, proposal, selection_rationale))

    def return_child(self, frame_id: str, child_frame_id: str, rationale: str) -> dict:
        return self._mutate(lambda state: state.return_child(frame_id, child_frame_id, rationale))

    def finish(self, frame_id: str, terminal_state: str, summary: str, confidence: float) -> dict:
        return self._mutate(lambda state: state.finish(frame_id, terminal_state, summary, confidence))

    def reopen(self, frame_id: str, reason: str) -> dict:
        return self._mutate(lambda state: state.reopen(frame_id, reason))

    def clarify(self, clause_id: str, status: str, interpretation: str) -> dict:
        return self._mutate(lambda state: state.set_clause(clause_id, status, interpretation))

    def next(self) -> dict:
        return self._load().next()

    def read_state(self) -> ResearchState:
        """Return a read-only domain view for an in-process coordinator."""
        return self._load()

    def status(self) -> dict:
        return self._load().status()

    def time_audit(self) -> dict:
        return self._load().time_audit()

    def freeze(self, snapshot_id: str | None) -> dict:
        return self._mutate(lambda state: state.freeze(snapshot_id))

    def export(self, output_format: str) -> dict:
        state = self._load()
        if output_format == "json":
            return state.data
        lines = ["# Research DAG", "", f"Intent: {state.current_intent()['raw']}", ""]
        for frame in state.data["frames"].values():
            lines.append(f"- [{frame['state']}] {frame['id']}: {frame['focus']}")
            for gap_id in frame["gap_ids"]:
                gap = state.data["gaps"][gap_id]
                lines.append(f"  - gap [{gap['status']}]: {gap['description']}")
        return {"markdown": "\n".join(lines)}

    def execute(self, command: dict) -> dict:
        """Apply one idempotent, workflow-submitted domain command.

        LangGraph may replay a node after recovery. A stable command id makes the
        domain write exactly once even when the orchestration layer retries it.
        """
        if not isinstance(command, dict):
            raise ValueError("workflow command must be an object")
        command_id = command.get("command_id")
        operation = command.get("operation")
        if not isinstance(command_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", command_id):
            raise ValueError("workflow command_id must use only letters, digits, dots, underscores, or hyphens")
        if not isinstance(operation, str):
            raise ValueError("workflow command requires an operation")
        with self.repository.locked():
            state = self._load()
            receipts = state.data.setdefault("command_receipts", {})
            if command_id in receipts:
                return {"deduplicated": True, "result": receipts[command_id]["result"]}
            self._assert_operation_is_allowed(state, operation, command)
            result = self._apply_command(state, operation, command)
            receipts[command_id] = {"operation": operation, "result": result, "applied_at": now_iso()}
            state.event("workflow_command_applied", command_id=command_id, operation=operation)
            self.repository.save_data(state.data)
            return {"deduplicated": False, "result": result}

    def execute_batch(self, commands: list[dict]) -> list[dict]:
        if not isinstance(commands, list) or not commands:
            raise ValueError("workflow batch requires at least one command")
        return [self.execute(command) for command in commands]

    def _load(self) -> ResearchState:
        data = self.repository.load_data()
        if data.get("schema") != SCHEMA:
            raise ValueError("unsupported research state schema")
        return ResearchState(data)

    def _mutate(self, operation: Any) -> dict:
        with self.repository.locked():
            state = self._load()
            result = operation(state)
            self.repository.save_data(state.data)
            return result

    def _state_file_exists(self) -> bool:
        from research_repository import state_path
        return state_path().exists()

    @staticmethod
    def _required(command: dict, key: str):
        if key not in command:
            raise ValueError(f"workflow command missing: {key}")
        return command[key]

    def _assert_operation_is_allowed(self, state: ResearchState, operation: str, command: dict) -> None:
        # Batch workers operate on independent frames, so validation is local to
        # each target rather than coupled to the coordinator's global priority.
        if operation == "freeze":
            if any(frame["state"] in {"open", "acquiring", "aggregating", "reviewing", "extracting", "expanded", "waiting_child", "blocked_on_user"}
                   for frame in state.data["frames"].values()):
                raise ValueError("workflow cannot freeze while active frames remain")
            return
        if operation in {"clarify", "reopen", "analyze_intent", "answer_intent_questions", "register_material"}:
            return
        if operation not in {"formulate", "aggregate_sources", "evidence", "extract", "expand", "descend", "return_child", "finish", "synthesize_decision"}:
            raise ValueError(f"unsupported workflow operation: {operation}")
        if operation == "synthesize_decision":
            if not state.decision_synthesis_required():
                raise ValueError("workflow decision synthesis is not required for this intent contract")
            if any(frame["state"] in {"open", "acquiring", "aggregating", "reviewing", "extracting", "expanded", "waiting_child", "blocked_on_user"}
                   for frame in state.data["frames"].values()):
                raise ValueError("workflow decision synthesis requires terminal research frames")
            if command.get("synthesizer_role") != "decision_synthesizer":
                raise ValueError("workflow decision synthesis requires synthesizer_role decision_synthesizer")
        if operation == "aggregate_sources":
            frame_id = self._required(command, "frame_id")
            frame = state.data["frames"].get(frame_id)
            if not isinstance(frame, dict):
                raise ValueError("workflow source aggregation references an unknown frame")
            if frame.get("state") != "aggregating":
                raise ValueError("workflow source aggregation requires an aggregating frame")
            if frame.get("aggregation", {}).get("status") == "complete":
                raise ValueError("workflow source aggregation is already complete")
            supplied_hash = self._required(command, "source_manifest_sha256")
            if supplied_hash != frame.get("collection", {}).get("source_manifest_sha256"):
                raise ValueError("workflow source aggregation must bind the current source manifest sha256")
            if command.get("aggregator_role") != "source_aggregator":
                raise ValueError("workflow source aggregation requires aggregator_role source_aggregator")
        if operation == "evidence":
            frame_id = self._required(command, "frame_id")
            frame = state.data["frames"].get(frame_id)
            if not isinstance(frame, dict):
                raise ValueError("workflow evidence references an unknown frame")
            if frame.get("state") != "reviewing":
                raise ValueError("workflow evidence is allowed only after saved-source collection reaches reviewing")
            if frame.get("aggregation", {}).get("status") != "complete":
                raise ValueError("workflow evidence requires completed source aggregation")
            reviewer_role = command.get("reviewer_role")
            review = frame.get("review", {})
            if reviewer_role not in review.get("expected_roles", []):
                raise ValueError("workflow evidence requires an expected reviewer_role")
            if reviewer_role in review.get("completed_roles", []):
                raise ValueError("workflow reviewer_role has already completed this collection")
        if operation == "finish":
            frame_id = self._required(command, "frame_id")
            frame = state.data["frames"].get(frame_id)
            if not isinstance(frame, dict):
                raise ValueError("workflow finish references an unknown frame")
            requested_state = command.get("state")
            if frame.get("state") != "expanded" and not (
                requested_state == "gap_user_input" and frame.get("state") in {"open", "blocked_on_user"}
            ):
                raise ValueError("workflow finish requires an expanded frame after collection and extraction")

    def _apply_command(self, state: ResearchState, operation: str, command: dict) -> dict:
        if operation == "analyze_intent":
            return state.analyze_intent(self._required(command, "contract"))
        if operation == "answer_intent_questions":
            return state.answer_intent_questions(self._required(command, "answers"))
        if operation == "register_material":
            return state.register_material(self._required(command, "material"), bool(command.get("replace", False)))
        if operation == "formulate":
            return state.formulate(self._required(command, "frame_id"), self._required(command, "plan"))
        if operation == "aggregate_sources":
            return state.aggregate_sources(
                self._required(command, "frame_id"), self._required(command, "clusters"),
                self._required(command, "source_manifest_sha256"),
            )
        if operation == "evidence":
            return state.add_evidence(self._required(command, "frame_id"), self._required(command, "evidence"),
                                      command.get("reviewer_role"))
        if operation == "extract":
            return state.extract(
                self._required(command, "frame_id"), self._required(command, "cognitions"),
                self._required(command, "gaps"), command.get("coverage"),
            )
        if operation == "synthesize_decision":
            return state.synthesize_decision(self._required(command, "synthesis"))
        if operation == "expand":
            return state.expand(self._required(command, "gap_id"), self._required(command, "frame"))
        if operation == "descend":
            return state.descend(self._required(command, "frame_id"), self._required(command, "gap_id"),
                                 self._required(command, "frame"), self._required(command, "selection_rationale"))
        if operation == "return_child":
            return state.return_child(self._required(command, "frame_id"), self._required(command, "child_frame_id"),
                                      self._required(command, "rationale"))
        if operation == "finish":
            return state.finish(self._required(command, "frame_id"), self._required(command, "state"), self._required(command, "summary"), float(command.get("confidence", 0.0)))
        if operation == "clarify":
            return state.set_clause(self._required(command, "clause_id"), self._required(command, "status"), str(command.get("interpretation", "")))
        if operation == "reopen":
            return state.reopen(self._required(command, "frame_id"), self._required(command, "reason"))
        if operation == "freeze":
            return state.freeze(command.get("snapshot_id"))
        raise ValueError(f"unsupported workflow operation: {operation}")

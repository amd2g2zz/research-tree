"""Compile a confirmed SQLite alignment graph into a persisted research tree."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .alignment_graph import AlignmentGraphStore
from .domain import ArtifactRef, ArtifactRevision, thaw_json, validate_identifier
from .recursive_search import initialize_research_state
from .run_ledger import RunLedger
from .tree_state import RESEARCH_TREE_STATE_KIND, ResearchTreeStateError

ALIGNMENT_GRAPH_KIND = "alignment-graph"
ALIGNMENT_HANDOFF_KIND = "alignment-handoff"


def initialize_research_from_alignment(
    ledger: RunLedger,
    *,
    round_id: str,
    tree_id: str,
    alignment_database: Path,
    expected_revision: int,
) -> ArtifactRevision:
    """Atomically persist an alignment handoff and its initial research tree."""

    if not isinstance(ledger, RunLedger):
        raise ResearchTreeStateError("alignment handoff requires a RunLedger")
    validate_identifier(tree_id, "tree_id")
    snapshot = ledger.load_run(round_id)
    if any(artifact.id == tree_id and artifact.kind == RESEARCH_TREE_STATE_KIND for artifact in snapshot.artifacts):
        raise ResearchTreeStateError(f"research tree already exists: {tree_id}")
    compiled = AlignmentGraphStore(alignment_database).compile_handoff()
    suffix = hashlib.sha256(tree_id.encode("utf-8")).hexdigest()[:10]
    graph_id = f"alignment-graph-{suffix}"
    handoff_id = f"alignment-handoff-{suffix}"
    graph_payload = {
        "schema": 1,
        "run_id": compiled["run_id"],
        "alignment_revision": compiled["alignment_revision"],
        "alignment_digest": compiled["alignment_digest"],
        "compiled_graph_digest": compiled["compiled_graph_digest"],
        "graph": compiled["alignment_graph"],
    }
    graph_ref = ArtifactRef(round_id, graph_id, _next_revision(snapshot.artifacts, graph_id))
    handoff_ref = ArtifactRef(round_id, handoff_id, _next_revision(snapshot.artifacts, handoff_id))
    finding_payloads = tuple(compiled["baseline_findings"])
    if len({str(payload["id"]) for payload in finding_payloads}) != len(finding_payloads):
        raise ResearchTreeStateError("alignment handoff baseline Finding Pack ids must be unique")
    findings = tuple(
        ArtifactRevision.create(
            artifact_id=str(payload["id"]),
            round_id=round_id,
            revision=_next_revision(snapshot.artifacts, str(payload["id"])),
            kind="finding-pack",
            payload=payload,
            parent_refs=(graph_ref,),
        )
        for payload in finding_payloads
    )
    state = initialize_research_state(
        round_id=round_id,
        tree_id=tree_id,
        decision_slots=compiled["decision_slots"],
        baseline_findings=findings,
        execution_context=compiled["execution_context"],
    )
    created = ledger.append_artifact_batch(
        round_id,
        (
            (graph_id, ALIGNMENT_GRAPH_KIND, graph_payload, ()),
            (
                handoff_id,
                ALIGNMENT_HANDOFF_KIND,
                {key: value for key, value in compiled.items() if key not in {"alignment_graph", "baseline_findings"}},
                (graph_ref,),
            ),
            *((finding.id, finding.kind, thaw_json(finding.payload), finding.parent_refs) for finding in findings),
            (
                tree_id,
                RESEARCH_TREE_STATE_KIND,
                thaw_json(state),
                (handoff_ref, *(ArtifactRef(finding.round_id, finding.id, finding.revision) for finding in findings)),
            ),
        ),
        expected_revision=expected_revision,
    )
    return created[-1]


def _next_revision(artifacts: tuple[ArtifactRevision, ...], artifact_id: str) -> int:
    return max((artifact.revision for artifact in artifacts if artifact.id == artifact_id), default=0) + 1

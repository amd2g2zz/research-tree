"""Compile a confirmed SQLite alignment graph into a persisted research tree."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .alignment_graph import AlignmentGraphStore
from .domain import ArtifactRef, ArtifactRevision, validate_identifier
from .recursive_search import RecursiveResearchCoordinator
from .storage import RunStore
from .tree_state import RESEARCH_TREE_STATE_KIND, ResearchTreeStateError


ALIGNMENT_GRAPH_KIND = "alignment-graph"
ALIGNMENT_HANDOFF_KIND = "alignment-handoff"


def initialize_research_from_alignment(
    store: RunStore,
    *,
    round_id: str,
    tree_id: str,
    alignment_database: Path,
) -> ArtifactRevision:
    """Persist the graph projection and initialize tree revision zero with explicit lineage."""

    validate_identifier(tree_id, "tree_id")
    snapshot = store.load_round(round_id)
    if any(
        artifact.id == tree_id and artifact.kind == RESEARCH_TREE_STATE_KIND
        for artifact in snapshot.artifacts
    ):
        raise ResearchTreeStateError(f"research tree already exists: {tree_id}")
    compiled = AlignmentGraphStore(alignment_database).compile_handoff()
    suffix = hashlib.sha256(tree_id.encode("utf-8")).hexdigest()[:10]
    graph = store.append_artifact(
        round_id,
        f"alignment-graph-{suffix}",
        ALIGNMENT_GRAPH_KIND,
        {
            "schema": 1,
            "run_id": compiled["run_id"],
            "alignment_revision": compiled["alignment_revision"],
            "alignment_digest": compiled["alignment_digest"],
            "compiled_graph_digest": compiled["compiled_graph_digest"],
            "graph": compiled["alignment_graph"],
        },
    )
    graph_ref = ArtifactRef(round_id, graph.id, graph.revision)
    handoff = store.append_artifact(
        round_id,
        f"alignment-handoff-{suffix}",
        ALIGNMENT_HANDOFF_KIND,
        {
            key: value
            for key, value in compiled.items()
            if key not in {"alignment_graph", "baseline_findings"}
        },
        parent_refs=(graph_ref,),
    )
    findings: list[ArtifactRevision] = []
    for payload in compiled["baseline_findings"]:
        finding = store.append_artifact(
            round_id,
            payload["id"],
            "finding-pack",
            payload,
            parent_refs=(graph_ref,),
        )
        findings.append(finding)
    return RecursiveResearchCoordinator(store).initialize(
        round_id=round_id,
        tree_id=tree_id,
        decision_slots=compiled["decision_slots"],
        baseline_findings=tuple(findings),
        execution_context=compiled["execution_context"],
        parent_artifacts=(handoff,),
    )
